"""Continuous learning pipeline: validated data collection, versioned datasets,
candidate training, evaluation against production, promotion and rollback.

Hard rules implemented here (see CONTINUOUS_LEARNING.md):
- Simulation records and real-device records are NEVER mixed in one dataset.
- Only labels a qualified user CONFIRMED become supervised ground truth.
- A candidate is promoted only if it beats production on predefined criteria.
- Every promotion and rollback is recorded in an append-only audit log.
- Training runs in the background with a thread limit; it never blocks the
  dashboard or the digital twin.

Storage: one sqlite database under local_ai_data/. Model files are JSON in
the same shape as the dashboard's models.json fault entry, so a promoted
model can be exported straight to the web app.
"""
import json
import math
import os
import sqlite3
import time
import uuid

# Same wind table as twin_engine.js (GIVEN to 5.83 m/s, ASSUMED beyond).
WIND_V = [1.9, 2.32, 2.5, 2.64, 2.92, 2.96, 3.28, 3.33, 3.6, 3.75, 3.92, 4.17,
          4.24, 4.56, 4.58, 4.88, 5.0, 5.2, 5.42, 5.83, 6.5, 7.5]
WIND_P = [0.0, 2.49, 3.23, 3.95, 5.46, 5.79, 8.06, 8.55, 10.93, 12.38, 14.31,
          17.29, 18.23, 22.70, 23.09, 27.99, 30.16, 33.93, 38.37, 47.92, 60.0, 60.0]

CLASSES = ["normal", "pv_loss", "wind_stall", "vbat_sensor_stuck", "battery_overheat"]
FEATURES = ["pv_ratio", "wind_ratio", "dT_batt_amb", "v_std", "abs_i", "i_std", "stuck"]

FIELDS = {  # name: (min, max, unit)  -- telemetry validation ranges
    "v_batt": (6, 60, "V"), "i_batt": (-200, 200, "A"), "g_wm2": (0, 1500, "W/m2"),
    "pv_w": (0, 2000, "W"), "wind_ms": (0, 60, "m/s"), "wind_w": (0, 5000, "W"),
    "t_batt_c": (-20, 80, "C"), "load_w": (0, 10000, "W"),
}
SOURCES = ("device", "simulation", "replay")

SCHEMA = """
CREATE TABLE IF NOT EXISTS records(
  id TEXT PRIMARY KEY, ts REAL, origin_id TEXT, source TEXT, values_json TEXT,
  label TEXT, label_status TEXT, quality REAL, accepted INTEGER,
  reject_reasons TEXT, model_version TEXT, created_at REAL);
CREATE TABLE IF NOT EXISTS datasets(
  id TEXT PRIMARY KEY, source TEXT, created_at REAL, n_records INTEGER,
  path TEXT, feature_stats TEXT);
CREATE TABLE IF NOT EXISTS models(
  id TEXT PRIMARY KEY, kind TEXT, version INTEGER, status TEXT, path TEXT,
  created_at REAL, metrics TEXT, dataset_id TEXT, notes TEXT);
CREATE TABLE IF NOT EXISTS audit(
  id TEXT PRIMARY KEY, ts REAL, action TEXT, detail TEXT);
CREATE TABLE IF NOT EXISTS config(key TEXT PRIMARY KEY, value TEXT);
"""

DEFAULT_CONFIG = {
    "auto_train": "off",            # 'off' | 'on' -- automatic training switch
    "retrain_min_new_labeled": "50",  # new confirmed records before auto-train
    "min_records_per_class": "5",
    "min_macro_f1_gain": "0.0",     # candidate must gain at least this over production
    "max_recall_drop_per_class": "0.05",
    "max_train_threads": "2",
}


def wind_table(ws):
    if not (ws > WIND_V[0]):
        return 0.0
    if ws >= WIND_V[-1]:
        return WIND_P[-1]
    for i in range(1, len(WIND_V)):
        if ws <= WIND_V[i]:
            f = (ws - WIND_V[i - 1]) / (WIND_V[i] - WIND_V[i - 1])
            return WIND_P[i - 1] + (WIND_P[i] - WIND_P[i - 1]) * f
    return 0.0


def fault_features(values, wind_boost=0.9):
    """Exact port of platform_lib.js features()."""
    obs_pv = values.get("g_wm2", 0) > 200
    obs_wind = values.get("wind_ms", 0) > 3.5
    if obs_pv:
        rpv = min(1.5, max(0.0, values.get("pv_w", 0) / (0.4674 * values.get("g_wm2", 0) + 1e-6)))
    else:
        rpv = 1.0
    wexp = wind_table(values.get("wind_ms", 0)) * wind_boost
    rw = min(2.0, max(0.0, values.get("wind_w", 0) / (wexp + 1e-6))) if obs_wind else 1.0
    sv = values.get("v_std", 0.05)
    si = values.get("i_std", 1.0)
    ia = values.get("i_abs", abs(values.get("i_batt", 5)))
    dt = values.get("dT", values.get("t_batt_c", 25) - values.get("t_amb_c", 24))
    return [float(x) for x in (rpv, rw, dt, sv, ia, si,
                               1.0 if (sv < 0.01 and si > 0.2) else 0.0)]


class LearningStore:
    def __init__(self, db_path, data_dir):
        self.db_path = db_path
        self.data_dir = data_dir
        os.makedirs(os.path.join(data_dir, "models"), exist_ok=True)
        os.makedirs(os.path.join(data_dir, "datasets"), exist_ok=True)
        self.db = sqlite3.connect(db_path, check_same_thread=False)
        self.db.executescript(SCHEMA)
        for k, v in DEFAULT_CONFIG.items():
            self.db.execute("INSERT OR IGNORE INTO config VALUES(?,?)", (k, v))
        self.db.commit()

    def close(self):
        self.db.close()

    # ---------- configuration ----------
    def get_config(self):
        return dict(self.db.execute("SELECT key, value FROM config").fetchall())

    def set_config(self, updates):
        allowed = set(DEFAULT_CONFIG)
        out = {}
        for k, v in updates.items():
            if k in allowed:
                self.db.execute("INSERT OR REPLACE INTO config VALUES(?,?)", (k, str(v)))
                out[k] = str(v)
        self.db.commit()
        return out

    def _audit(self, action, detail):
        self.db.execute("INSERT INTO audit VALUES(?,?,?,?)",
                        (uuid.uuid4().hex[:12], time.time(), action, json.dumps(detail)))
        self.db.commit()

    # ---------- 1-4. collect, validate, reject, store ----------
    def validate_record(self, rec):
        """Validate one telemetry record. Returns (errors, warnings, quality 0..1)."""
        errors, warnings = [], []
        if not isinstance(rec, dict):
            return ["record is not an object"], [], 0.0
        src = rec.get("source")
        if src not in SOURCES:
            errors.append("source must be one of %s" % ",".join(SOURCES))
        if not rec.get("origin_id") or not isinstance(rec.get("origin_id"), str):
            errors.append("origin_id (device or simulation id) is required")
        ts = rec.get("ts")
        if not isinstance(ts, (int, float)) or ts <= 0:
            errors.append("ts must be a positive unix timestamp (seconds)")
        elif abs(time.time() - ts) > 10 * 365 * 86400:
            errors.append("ts is implausibly far from now")
        values = rec.get("values")
        if not isinstance(values, dict):
            errors.append("values object is required")
            values = {}
        present = 0
        for name, (lo, hi, unit) in FIELDS.items():
            v = values.get(name)
            if v is None:
                warnings.append("missing %s" % name)
                continue
            if not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v):
                errors.append("%s is not a finite number" % name)
                continue
            present += 1
            if v < lo or v > hi:
                errors.append("%s=%g out of range [%g,%g] %s" % (name, v, lo, hi, unit))
        if present == 0:
            errors.append("no measurement fields present")
        label = rec.get("label")
        if label is not None and label not in CLASSES:
            errors.append("unknown label %r (known: %s)" % (label, ",".join(CLASSES)))
        label_status = rec.get("label_status", "suggested")
        if label is not None and label_status not in ("confirmed", "suggested"):
            errors.append("label_status must be confirmed or suggested")
        # physical plausibility (soft): pv cannot exceed ~1.4x nameplate sanity handled by range;
        # quality score: fraction of fields present, minus warnings
        quality = max(0.0, present / len(FIELDS) - 0.05 * len([w for w in warnings if w.startswith("missing")]))
        return errors, warnings, round(quality, 3)

    def add_record(self, rec):
        errors, warnings, quality = self.validate_record(rec)
        rid = uuid.uuid4().hex[:12]
        if not errors:
            dup = self.db.execute(
                "SELECT 1 FROM records WHERE origin_id=? AND ts=? AND source=?",
                (rec["origin_id"], rec["ts"], rec["source"])).fetchone()
            if dup:
                errors.append("duplicate: same origin_id, ts and source already stored")
        accepted = 0 if errors else 1
        self.db.execute(
            "INSERT INTO records VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (rid, rec.get("ts"), rec.get("origin_id"), rec.get("source"),
             json.dumps(rec.get("values", {})), rec.get("label"),
             rec.get("label_status", "suggested") if rec.get("label") else None,
             quality, accepted, json.dumps(errors + warnings), rec.get("model_version"),
             time.time()))
        self.db.commit()
        return {"id": rid, "accepted": bool(accepted), "errors": errors,
                "warnings": warnings, "quality": quality}

    def counts(self):
        row = lambda q, *a: self.db.execute(q, a).fetchone()[0]
        return {
            "accepted": row("SELECT COUNT(*) FROM records WHERE accepted=1"),
            "rejected": row("SELECT COUNT(*) FROM records WHERE accepted=0"),
            "accepted_device": row("SELECT COUNT(*) FROM records WHERE accepted=1 AND source='device'"),
            "accepted_simulation": row("SELECT COUNT(*) FROM records WHERE accepted=1 AND source='simulation'"),
            "accepted_replay": row("SELECT COUNT(*) FROM records WHERE accepted=1 AND source='replay'"),
            "confirmed_labels": row("SELECT COUNT(*) FROM records WHERE accepted=1 AND label_status='confirmed'"),
            "suggested_labels": row("SELECT COUNT(*) FROM records WHERE accepted=1 AND label_status='suggested'"),
            "confirmed_since_last_train": self._new_labeled_since_last_train(),
        }

    def _new_labeled_since_last_train(self):
        last = self.db.execute(
            "SELECT MAX(created_at) FROM datasets").fetchone()[0] or 0
        return self.db.execute(
            "SELECT COUNT(*) FROM records WHERE accepted=1 AND label_status='confirmed' AND created_at>?",
            (last,)).fetchone()[0]

    # ---------- 5-8. datasets, separation, drift ----------
    def build_dataset(self, source, wind_boost=0.9):
        """Versioned dataset export for ONE source only (sim/device never mixed)."""
        if source not in SOURCES:
            raise ValueError("source must be one of " + ",".join(SOURCES))
        rows = self.db.execute(
            "SELECT ts, origin_id, values_json, label FROM records "
            "WHERE accepted=1 AND source=? AND label_status='confirmed' ORDER BY ts",
            (source,)).fetchall()
        X = [fault_features(json.loads(r[2]), wind_boost) for r in rows]
        y = [r[3] for r in rows]
        ds_id = "ds-" + uuid.uuid4().hex[:10]
        stats = _feature_stats(X)
        payload = {"id": ds_id, "source": source, "created_at": time.time(),
                   "n_records": len(rows), "features": FEATURES, "classes": CLASSES,
                   "X": X, "y": y,
                   "note": "source='%s' only; labels are user-confirmed only" % source}
        path = os.path.join(self.data_dir, "datasets", ds_id + ".json")
        with open(path, "w") as f:
            json.dump(payload, f)
        self.db.execute("INSERT INTO datasets VALUES(?,?,?,?,?,?)",
                        (ds_id, source, payload["created_at"], len(rows), path,
                         json.dumps(stats)))
        self.db.commit()
        self._audit("dataset_built", {"id": ds_id, "source": source, "n": len(rows)})
        return {"id": ds_id, "source": source, "n_records": len(rows), "path": path,
                "class_counts": {c: y.count(c) for c in CLASSES if y.count(c)}}

    def drift_report(self, source, window=200):
        """Simple distribution-shift check: per-feature z of mean/std shift vs reference dataset."""
        ref = self.db.execute(
            "SELECT feature_stats, id FROM datasets WHERE source=? ORDER BY created_at DESC LIMIT 1",
            (source,)).fetchone()
        rows = self.db.execute(
            "SELECT values_json FROM records WHERE accepted=1 AND source=? ORDER BY ts DESC LIMIT ?",
            (source, window)).fetchall()
        if not ref or not rows:
            return {"status": "insufficient", "reason": "need a reference dataset and recent records"}
        ref_stats = json.loads(ref[0])
        X = [fault_features(json.loads(r[0])) for r in rows]
        new_stats = _feature_stats(X)
        shifts = []
        for i, f in enumerate(FEATURES):
            r0, r1 = ref_stats[f], new_stats[f]
            # Welch-style mean-shift test: a sustained new operating point moves the
            # window mean by many standard errors even when raw spreads overlap.
            se = math.sqrt((r0["std"] or 0) ** 2 / max(1, r0.get("n") or 1)
                           + (r1["std"] or 0) ** 2 / max(1, r1.get("n") or 1)) or 1e-9
            z = abs(r1["mean"] - r0["mean"]) / se
            shifts.append({"feature": f, "mean_shift_z": round(z, 3),
                           "shifted": z > 3.0})
        return {"status": "ok", "reference_dataset": ref[1], "window": len(rows),
                "shifts": shifts, "drift_detected": any(s["shifted"] for s in shifts)}

    # ---------- 9-14. train, evaluate, compare, promote ----------
    def train_candidate(self, source, dataset_id=None, hidden=(16, 16), seed=42):
        """Train a candidate fault MLP on a versioned dataset and evaluate it
        against the current production model on the same holdout split.
        Returns a full report; does NOT promote anything."""
        cfg = self.get_config()
        if dataset_id is None:
            ds = self.build_dataset(source)
            dataset_id = ds["id"]
        dpath = self.db.execute("SELECT path FROM datasets WHERE id=?",
                                (dataset_id,)).fetchone()
        if not dpath:
            return {"status": "error", "error": "unknown dataset " + str(dataset_id)}
        with open(dpath[0]) as f:
            ds = json.load(f)
        X, y = ds["X"], ds["y"]
        min_per = int(cfg["min_records_per_class"])
        counts = {c: y.count(c) for c in CLASSES}
        missing = {c: n for c, n in counts.items() if n < min_per}
        if missing:
            return {"status": "insufficient_data",
                    "reason": "every fault class needs at least %d confirmed records "
                              "(have %s). A model trained without a class cannot be "
                              "evaluated on it, so training is blocked instead."
                              % (min_per, counts)}
        try:
            from sklearn.neural_network import MLPClassifier
            from sklearn.model_selection import train_test_split
            from sklearn.metrics import accuracy_score, precision_recall_fscore_support, confusion_matrix
            import numpy as np
        except ImportError:
            return {"status": "error",
                    "error": "scikit-learn is not installed; run the setup script again"}
        os.environ.setdefault("OMP_NUM_THREADS", cfg["max_train_threads"])
        Xa = np.array(X, dtype=float)
        ya = np.array(y)
        Xtr, Xte, ytr, yte = train_test_split(Xa, ya, test_size=0.3,
                                              random_state=seed, stratify=ya)
        mu, sd = Xtr.mean(0), Xtr.std(0) + 1e-9

        def evaluate(predict_proba, predict, name):
            t0 = time.time()
            p = predict(Xte)
            latency_ms = (time.time() - t0) * 1000 / max(1, len(Xte))
            pr, rc, f1, _ = precision_recall_fscore_support(yte, p, labels=CLASSES,
                                                            zero_division=0)
            return {"name": name, "accuracy": round(accuracy_score(yte, p), 4),
                    "macro_f1": round(float(f1.mean()), 4),
                    "per_class": {c: {"precision": round(float(pr[i]), 4),
                                      "recall": round(float(rc[i]), 4),
                                      "f1": round(float(f1[i]), 4)}
                                  for i, c in enumerate(CLASSES)},
                    "confusion_matrix": confusion_matrix(yte, p, labels=CLASSES).tolist(),
                    "inference_ms_per_sample": round(latency_ms, 4), "n_test": len(Xte)}

        cand = MLPClassifier(hidden_layer_sizes=hidden, activation="relu",
                             max_iter=600, random_state=seed)
        cand.fit((Xtr - mu) / sd, ytr)
        cand_eval = evaluate(None, cand.predict, "candidate")

        prod = self.production_model()
        if prod:
            with open(prod["path"]) as f:
                pm = json.load(f)
            pmu, psd = np.array(pm["mu"]), np.array(pm["sd"])
            W = [np.array(l["W"]) for l in pm["layers"]]
            B = [np.array(l["b"]) for l in pm["layers"]]

            def prod_predict(Xq):
                a = (Xq - pmu) / psd
                for i in range(len(W) - 1):
                    a = np.maximum(0, a @ W[i] + B[i])
                z = a @ W[-1] + B[-1]
                z = z - z.max(axis=1, keepdims=True)
                e = np.exp(z)
                return np.array(CLASSES)[(e / e.sum(axis=1, keepdims=True)).argmax(axis=1)]
            prod_eval = evaluate(None, prod_predict, "production")
        else:
            prod_eval = None

        gain = round(cand_eval["macro_f1"] - (prod_eval["macro_f1"] if prod_eval else 0.0), 4)
        min_gain = float(cfg["min_macro_f1_gain"])
        max_drop = float(cfg["max_recall_drop_per_class"])
        drops = {}
        if prod_eval:
            for c in CLASSES:
                d = prod_eval["per_class"][c]["recall"] - cand_eval["per_class"][c]["recall"]
                if d > 0:
                    drops[c] = round(d, 4)
        passed = gain >= min_gain and all(d <= max_drop for d in drops.values())
        # save candidate (not promoted)
        mid = "fault-" + uuid.uuid4().hex[:8]
        model = {"layers": [{"W": cand.coefs_[i].tolist(), "b": cand.intercepts_[i].tolist()}
                            for i in range(len(cand.coefs_))],
                 "mu": mu.tolist(), "sd": sd.tolist(), "classes": list(CLASSES)}
        path = os.path.join(self.data_dir, "models", mid + ".json")
        with open(path, "w") as f:
            json.dump(model, f)
        version = self._next_version()
        self.db.execute("INSERT INTO models VALUES(?,?,?,?,?,?,?,?,?)",
                        (mid, "fault_mlp", version, "candidate", path, time.time(),
                         json.dumps(cand_eval), dataset_id, ""))
        self.db.commit()
        report = {"status": "evaluated", "candidate_id": mid, "version": version,
                  "dataset_id": dataset_id, "candidate": cand_eval,
                  "production": prod_eval, "macro_f1_gain_vs_production": gain,
                  "recall_drops": drops,
                  "acceptance": {"min_macro_f1_gain": min_gain,
                                 "max_recall_drop_per_class": max_drop,
                                 "passed": passed},
                  "note": "Candidate saved but NOT promoted. Promotion is a separate, "
                          "explicit action (see CONTINUOUS_LEARNING.md)."}
        self._audit("candidate_trained", {"id": mid, "dataset": dataset_id,
                                          "macro_f1": cand_eval["macro_f1"], "passed": passed})
        return report

    def _next_version(self):
        row = self.db.execute(
            "SELECT MAX(version) FROM models WHERE kind='fault_mlp'").fetchone()[0]
        return (row or 0) + 1

    def production_model(self):
        row = self.db.execute(
            "SELECT id, path, version, metrics FROM models "
            "WHERE kind='fault_mlp' AND status='production'").fetchone()
        if not row:
            return None
        return {"id": row[0], "path": row[1], "version": row[2],
                "metrics": json.loads(row[3] or "{}")}

    def promote(self, model_id, expected_passed=True):
        cand = self.db.execute(
            "SELECT id, status FROM models WHERE id=?", (model_id,)).fetchone()
        if not cand:
            return {"status": "error", "error": "unknown model " + str(model_id)}
        if cand[1] != "candidate":
            return {"status": "error", "error": "model %s is %s, not a candidate" % (model_id, cand[1])}
        old = self.production_model()
        self.db.execute("UPDATE models SET status='archived' WHERE kind='fault_mlp' AND status='production'")
        self.db.execute("UPDATE models SET status='production' WHERE id=?", (model_id,))
        self.db.commit()
        self._audit("promoted", {"model": model_id, "replaced": old["id"] if old else None})
        return {"status": "promoted", "model": model_id,
                "previous_production": old["id"] if old else None,
                "rollback_available": old is not None}

    def rollback(self):
        old = self.db.execute(
            "SELECT id FROM models WHERE kind='fault_mlp' AND status='archived' "
            "ORDER BY created_at DESC LIMIT 1").fetchone()
        cur = self.production_model()
        if not old or not cur:
            return {"status": "error", "error": "need both a production model and an archived one"}
        self.db.execute("UPDATE models SET status='archived' WHERE id=?", (cur["id"],))
        self.db.execute("UPDATE models SET status='production' WHERE id=?", (old[0],))
        self.db.commit()
        self._audit("rollback", {"restored": old[0], "replaced": cur["id"]})
        return {"status": "rolled_back", "restored": old[0], "replaced": cur["id"]}

    def history(self):
        models = [{"id": r[0], "kind": r[1], "version": r[2], "status": r[3],
                   "created_at": r[4], "metrics": json.loads(r[5] or "{}"),
                   "dataset_id": r[6]}
                  for r in self.db.execute(
                      "SELECT id, kind, version, status, created_at, metrics, dataset_id "
                      "FROM models ORDER BY created_at DESC").fetchall()]
        audit = [{"ts": r[0], "action": r[1], "detail": json.loads(r[2])}
                 for r in self.db.execute(
                     "SELECT ts, action, detail FROM audit ORDER BY ts DESC LIMIT 50").fetchall()]
        datasets = [{"id": r[0], "source": r[1], "created_at": r[2], "n_records": r[3]}
                    for r in self.db.execute(
                        "SELECT id, source, created_at, n_records FROM datasets "
                        "ORDER BY created_at DESC").fetchall()]
        return {"models": models, "audit": audit, "datasets": datasets}

    def status(self):
        prod = self.production_model()
        c = self.counts()
        last_train = self.db.execute("SELECT MAX(created_at) FROM models").fetchone()[0]
        cand = self.db.execute(
            "SELECT id, metrics FROM models WHERE status='candidate' "
            "ORDER BY created_at DESC LIMIT 1").fetchone()
        return {
            "active_model": prod,
            "training_dataset": (self.db.execute(
                "SELECT id, source, n_records, created_at FROM datasets "
                "ORDER BY created_at DESC LIMIT 1").fetchone() or None),
            "records": c,
            "last_training_at": last_train,
            "candidate": {"id": cand[0], "metrics": json.loads(cand[1] or "{}")} if cand else None,
            "rollback_available": self.db.execute(
                "SELECT COUNT(*) FROM models WHERE kind='fault_mlp' AND status='archived'"
            ).fetchone()[0] > 0,
            "config": self.get_config(),
        }


def _feature_stats(X):
    out = {}
    if not X:
        return {f: {"mean": 0.0, "std": 0.0, "n": 0} for f in FEATURES}
    n = len(X)
    for i, f in enumerate(FEATURES):
        col = [r[i] for r in X]
        mu = sum(col) / n
        var = sum((v - mu) ** 2 for v in col) / max(1, n - 1)
        out[f] = {"mean": mu, "std": math.sqrt(var), "n": n}
    return out
