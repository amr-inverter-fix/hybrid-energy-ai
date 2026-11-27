"""Tests for the local AI engine: hardware profiler, model catalog, RAG,
and the continuous learning pipeline. All offline; no model downloads.
Run: python3 -m unittest tests.test_local_ai -v
"""
import json
import os
import tempfile
import time
import unittest

from local_ai import hardware, model_catalog
from local_ai.rag import RagStore, chunk_markdown, chunk_json
from local_ai.learning import LearningStore, fault_features, wind_table, CLASSES


class TestHardware(unittest.TestCase):
    def test_profile_shape(self):
        p = hardware.profile()
        for k in ["os", "cpu_model", "cpu_arch", "ram_bytes", "ram_gb", "gpus",
                  "gpu_vram_mb_max", "acceleration_backends", "disk_free_gb"]:
            self.assertIn(k, p)
        self.assertGreater(p["ram_bytes"], 0)
        self.assertIn("cpu", p["acceleration_backends"])
        self.assertGreater(p["disk_free_gb"], 0)


class TestCatalog(unittest.TestCase):
    def rec(self, ram, vram=0, disk=100):
        return model_catalog.recommend({"ram_gb": ram, "gpu_vram_mb_max": vram,
                                        "disk_free_gb": disk})

    def test_tiny_machine_gets_lightweight(self):
        r = self.rec(2.0)
        self.assertEqual(r["default"]["id"], "qwen2.5:0.5b")
        self.assertIsNone(r["stronger"])

    def test_normal_laptop_gets_qwen3b(self):
        r = self.rec(8.0)
        self.assertEqual(r["default"]["id"], "qwen2.5:3b")
        self.assertIsNotNone(r["lightweight"])

    def test_strong_machine_offers_7b(self):
        r = self.rec(16.0, vram=8192)
        self.assertEqual(r["stronger"]["id"], "qwen2.5:7b")

    def test_under_2gb_no_model(self):
        r = self.rec(1.5)
        self.assertIsNone(r["default"])
        self.assertTrue(any("2 GB" in x for x in r["reasons"]))

    def test_cpu_note_when_no_gpu(self):
        r = self.rec(8.0)
        self.assertTrue(any("CPU" in x for x in r["reasons"]))

    def test_every_model_has_license(self):
        for m in model_catalog.CATALOG:
            self.assertTrue(m["license"])
            self.assertTrue(m["license_url"].startswith("http"))
        self.assertTrue(model_catalog.EMBED_MODEL["license"])


class TestRag(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.rag = RagStore(os.path.join(self.tmp, "rag.db"), embed_model=None)

    def tearDown(self):
        self.rag.close()

    def test_chunk_markdown_headings(self):
        chunks = chunk_markdown("A.md", "# Intro\nhello world this is a long enough chunk of text yes\n## Two\n" + "more text here " * 10)
        self.assertGreaterEqual(len(chunks), 2)
        self.assertEqual(chunks[0]["heading"], "Intro")

    def test_index_and_incremental_skip(self):
        r1 = self.rag.index_document("A.md", "# Title\n" + "solar panel fault diagnosis " * 10)
        self.assertEqual(r1["status"], "indexed")
        r2 = self.rag.index_document("A.md", "# Title\n" + "solar panel fault diagnosis " * 10)
        self.assertEqual(r2["status"], "skipped")

    def test_version_bump_on_change(self):
        self.rag.index_document("A.md", "# T\n" + "old content " * 10)
        r = self.rag.index_document("A.md", "# T\n" + "new content " * 10)
        self.assertEqual(r["version"], 2)
        hits = self.rag.search("new content", 3)
        self.assertTrue(hits)
        self.assertTrue(all(h["version"] == 2 for h in hits))

    def test_bm25_arabic_and_english(self):
        self.rag.index_document("faults.md", "# PV\n" + "انخفاض انتاج الالواح الشمسية بسبب الاتربة " * 8)
        self.rag.index_document("wind.md", "# Wind\n" + "turbine stall venturi obstruction " * 8)
        self.assertEqual(self.rag.search("turbine stall", 1)[0]["source"], "wind.md")
        self.assertEqual(self.rag.search("انتاج الالواح", 1)[0]["source"], "faults.md")

    def test_subsystem_filter(self):
        self.rag.index_document("a.md", "# T\n" + "battery charge controller " * 8, subsystem="battery")
        self.rag.index_document("b.md", "# T\n" + "battery charge controller " * 8, subsystem="wind")
        hits = self.rag.search("battery", 5, subsystem="wind")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["subsystem"], "wind")

    def test_duplicate_detection(self):
        text = "# T\n" + "identical paragraph about inverters " * 10
        self.rag.index_document("a.md", text)
        r = self.rag.index_document("b.md", text)
        self.assertGreater(r["duplicates_detected"], 0)

    def test_json_chunking(self):
        chunks = chunk_json("r.json", {"a": list(range(500))})
        self.assertGreater(len(chunks), 1)

    def test_stats(self):
        self.rag.index_document("a.md", "# T\n" + "some content here " * 10)
        s = self.rag.stats()
        self.assertEqual(s["documents"], 1)
        self.assertGreater(s["chunks"], 0)


def rec(source, label=None, label_status="confirmed", ts=None, origin="dev1", **vals):
    v = dict(v_batt=25.2, i_batt=3.1, g_wm2=800, pv_w=380, wind_ms=5.0,
             wind_w=40, t_batt_c=30, load_w=300)
    v.update(vals)
    return {"ts": ts if ts is not None else time.time(), "origin_id": origin,
            "source": source, "values": v, "label": label, "label_status": label_status}


class TestLearningValidation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.ls = LearningStore(os.path.join(self.tmp, "l.db"), os.path.join(self.tmp, "data"))

    def tearDown(self):
        self.ls.close()

    def test_valid_record_accepted(self):
        r = self.ls.add_record(rec("device"))
        self.assertTrue(r["accepted"])
        self.assertGreater(r["quality"], 0.5)

    def test_out_of_range_rejected(self):
        r = self.ls.add_record(rec("device", v_batt=999))
        self.assertFalse(r["accepted"])
        self.assertTrue(any("out of range" in e for e in r["errors"]))

    def test_corrupted_rejected(self):
        r = self.ls.add_record(rec("device", pv_w="not-a-number"))
        self.assertFalse(r["accepted"])

    def test_bad_source_rejected(self):
        r = self.ls.add_record(rec("fake-source"))
        self.assertFalse(r["accepted"])

    def test_duplicate_rejected(self):
        t = 1700000000.0
        self.assertTrue(self.ls.add_record(rec("device", ts=t))["accepted"])
        r = self.ls.add_record(rec("device", ts=t))
        self.assertFalse(r["accepted"])
        self.assertTrue(any("duplicate" in e for e in r["errors"]))

    def test_unknown_label_rejected(self):
        r = self.ls.add_record(rec("device", label="made_up_fault"))
        self.assertFalse(r["accepted"])

    def test_counts_separate_sources(self):
        self.ls.add_record(rec("device", ts=1700000000.0))
        self.ls.add_record(rec("simulation", ts=1700000100.0, origin="sim1"))
        c = self.ls.counts()
        self.assertEqual(c["accepted_device"], 1)
        self.assertEqual(c["accepted_simulation"], 1)

    def test_wind_table_matches_power_curve(self):
        self.assertEqual(wind_table(0.5), 0.0)
        self.assertAlmostEqual(wind_table(5.83), 47.92)
        self.assertEqual(wind_table(99), 60.0)

    def test_features_shape(self):
        f = fault_features({"g_wm2": 800, "pv_w": 380, "wind_ms": 5, "wind_w": 40,
                            "t_batt_c": 30, "i_batt": 3})
        self.assertEqual(len(f), 7)
        self.assertTrue(all(isinstance(x, float) for x in f))


class TestLearningPipeline(unittest.TestCase):
    """End-to-end: collect -> dataset -> train -> evaluate -> promote -> rollback."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.ls = LearningStore(os.path.join(self.tmp, "l.db"), os.path.join(self.tmp, "data"))
        try:
            import sklearn  # noqa
        except ImportError:
            self.skipTest("scikit-learn not installed")

    def tearDown(self):
        self.ls.close()

    def _fill(self, source, n=12, t0=1700000000.0):
        """Well-separated synthetic classes, all 5 classes (training requires each)."""
        for i in range(n):
            base = t0 + i * 1000
            self.ls.add_record(rec(source, label="normal", ts=base,
                                   origin=source + "-sim", pv_w=380, wind_w=40))
            self.ls.add_record(rec(source, label="pv_loss", ts=base + 100,
                                   origin=source + "-sim", pv_w=30))  # low pv ratio at high ghi
            self.ls.add_record(rec(source, label="wind_stall", ts=base + 200,
                                   origin=source + "-sim", wind_w=0.0))
            self.ls.add_record(rec(source, label="vbat_sensor_stuck", ts=base + 300,
                                   origin=source + "-sim", v_std=0.001, i_std=2.0))
            self.ls.add_record(rec(source, label="battery_overheat", ts=base + 400,
                                   origin=source + "-sim", t_batt_c=70))

    def test_dataset_separation(self):
        self._fill("simulation", n=8)
        self._fill("device", n=8, t0=1700100000.0)
        d_sim = self.ls.build_dataset("simulation")
        d_dev = self.ls.build_dataset("device")
        self.assertEqual(d_sim["source"], "simulation")
        self.assertEqual(d_dev["source"], "device")
        self.assertEqual(d_sim["n_records"], 40)
        self.assertEqual(d_dev["n_records"], 40)
        self.assertNotEqual(d_sim["id"], d_dev["id"])

    def test_suggested_labels_never_trained_on(self):
        for i in range(4):
            self.ls.add_record(rec("simulation", label="battery_overheat",
                                   label_status="suggested", ts=1700500000.0 + i, origin="sim-s"))
        ds = self.ls.build_dataset("simulation")
        self.assertEqual(ds["n_records"], 0)
        self.assertNotIn("battery_overheat", ds["class_counts"])

    def test_insufficient_data_blocks_training(self):
        self.ls.add_record(rec("simulation", label="normal", ts=1700000000.0, origin="s"))
        r = self.ls.train_candidate("simulation")
        self.assertEqual(r["status"], "insufficient_data")
        self._fill("simulation", n=6)  # only 4 classes filled? no: all 5, but too few? n=6 >= 5
        self.ls.add_record(rec("simulation", label="normal", ts=1700999999.0, origin="s"))
        r2 = self.ls.train_candidate("simulation")
        self.assertEqual(r2["status"], "evaluated", r2)

    def test_train_promote_rollback(self):
        self._fill("simulation")
        rep = self.ls.train_candidate("simulation")
        self.assertEqual(rep["status"], "evaluated", rep)
        self.assertIn("candidate", rep)
        self.assertIn("confusion_matrix", rep["candidate"])
        self.assertIn("per_class", rep["candidate"])
        self.assertIsNone(rep["production"])  # first model: no production yet
        self.assertTrue(rep["acceptance"]["passed"])
        cid = rep["candidate_id"]
        pr = self.ls.promote(cid)
        self.assertEqual(pr["status"], "promoted")
        self.assertFalse(pr["rollback_available"])  # nothing before it
        prod = self.ls.production_model()
        self.assertEqual(prod["id"], cid)
        # exported model matches the dashboard's models.json fault shape
        with open(prod["path"]) as f:
            m = json.load(f)
        self.assertEqual(len(m["mu"]), 7)
        shapes = [(len(l["W"]), len(l["W"][0])) for l in m["layers"]]
        self.assertEqual(shapes[0][0], 7)
        self.assertEqual(shapes[-1][1], len(CLASSES))
        # second candidate -> promote -> rollback restores the first
        self._fill("simulation", n=6, t0=1700600000.0)
        rep2 = self.ls.train_candidate("simulation")
        self.assertEqual(rep2["status"], "evaluated", rep2)
        self.assertIsNotNone(rep2["production"])
        self.assertIn("macro_f1", rep2["production"])
        self.ls.promote(rep2["candidate_id"])
        rb = self.ls.rollback()
        self.assertEqual(rb["status"], "rolled_back")
        self.assertEqual(self.ls.production_model()["id"], cid)
        hist = self.ls.history()
        actions = [a["action"] for a in hist["audit"]]
        for a in ["candidate_trained", "promoted", "rollback"]:
            self.assertIn(a, actions)

    def test_drift_report(self):
        self._fill("simulation", n=8)
        self.ls.build_dataset("simulation")
        for i in range(30):  # shifted pv ratio (much lower pv at same ghi)
            self.ls.add_record(rec("simulation", ts=1701000000.0 + i * 100,
                                   origin="sim-drift", pv_w=10))
        d = self.ls.drift_report("simulation")
        self.assertEqual(d["status"], "ok")
        self.assertTrue(d["drift_detected"])
        self.assertTrue(any(s["feature"] == "pv_ratio" and s["shifted"]
                            for s in d["shifts"]))

    def test_config_update(self):
        out = self.ls.set_config({"auto_train": "on", "retrain_min_new_labeled": "20",
                                  "not_a_real_key": "x"})
        self.assertEqual(out["auto_train"], "on")
        self.assertNotIn("not_a_real_key", out)
        self.assertEqual(self.ls.get_config()["auto_train"], "on")


class TestServer(unittest.TestCase):
    """HTTP API: token enforcement, degraded chat without a model, status."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        os.environ["HYBRID_LOCAL_AI_DATA"] = cls.tmp
        import importlib
        import local_ai.server as srv
        importlib.reload(srv)
        cls.srv = srv
        from fastapi.testclient import TestClient
        cls.client = TestClient(srv.app)

    def test_status_ok_and_private(self):
        r = self.client.get("/api/local/status")
        self.assertEqual(r.status_code, 200)
        j = r.json()
        self.assertEqual(j["gateway"], "running")
        self.assertIn("privacy", j)
        self.assertIn("learning", j)

    def test_mutation_requires_token(self):
        r = self.client.post("/api/local/rag/index")
        self.assertEqual(r.status_code, 403)
        r = self.client.post("/api/local/learning/records", json={
            "ts": time.time(), "origin_id": "d", "source": "device",
            "values": {"v_batt": 24}})
        self.assertEqual(r.status_code, 403)

    def test_record_with_token(self):
        with open(os.path.join(self.tmp, "training_token")) as f:
            tok = f.read().strip()
        r = self.client.post("/api/local/learning/records",
                             headers={"x-local-token": tok},
                             json={"ts": time.time(), "origin_id": "d", "source": "device",
                                   "values": {"v_batt": 24, "pv_w": 100, "g_wm2": 500,
                                              "wind_ms": 4, "wind_w": 20, "i_batt": 1,
                                              "t_batt_c": 28, "load_w": 90}})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["accepted"])

    def test_chat_degrades_honestly_without_model(self):
        r = self.client.post("/api/local/chat", json={"question": "why is SOC dropping?"})
        self.assertEqual(r.status_code, 200)
        j = r.json()
        self.assertEqual(j["provider"], "retrieval-only")
        self.assertIn("answer", j)

    def test_chat_empty_rejected(self):
        r = self.client.post("/api/local/chat", json={"question": "  "})
        self.assertEqual(r.status_code, 400)

    def test_unknown_train_source_rejected(self):
        with open(os.path.join(self.tmp, "training_token")) as f:
            tok = f.read().strip()
        r = self.client.post("/api/local/learning/train?source=outer-space",
                             headers={"x-local-token": tok})
        self.assertEqual(r.status_code, 400)


if __name__ == "__main__":
    unittest.main()
