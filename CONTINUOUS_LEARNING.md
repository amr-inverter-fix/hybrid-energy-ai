# Continuous Learning

A persistent pipeline that improves the fault-diagnosis model from validated
engineering data. Implemented in `local_ai/learning.py`, exposed by the
gateway and the dashboard's **Learning Center** page.

## Data collection

Every record carries: timestamp, origin id (device or simulation), data
source (`device` | `simulation` | `replay`), measurement values, optional
label, label status (`confirmed` | `suggested`), model version, a computed
quality score (0-1) and its validation result.

Validation rejects: unknown sources, missing origin/timestamp, non-finite
values, out-of-range measurements (per-field physical ranges), unknown
labels, and duplicates (same origin, timestamp and source). Rejected records
are stored with their reject reasons and counted; they are never trained on.

Hard rules enforced in code (unit-tested):

- Simulation and real-device datasets are built separately and never mixed
  (`build_dataset(source)` filters one source only).
- Only `confirmed` labels become supervised ground truth. Suggested labels
  are stored but excluded from training.
- Synthetic data is never presented as field measurements: every dataset
  file and model record carries its source.

## Workflow (as implemented)

1. New data arrives -> `POST /api/local/learning/records` (token required).
2. Schema, units, timestamps, ranges validated; suspicious records rejected.
3. Accepted records stored with a quality score.
4. Project knowledge index updates separately (`/api/local/rag/index`).
5. Drift check (`/api/local/learning/drift`): Welch mean-shift per feature
   between the recent window and the reference dataset; z > 3 flags a shift.
6. `build_dataset` creates a versioned training dataset (JSON export).
7. `train_candidate` trains a candidate fault MLP (scikit-learn,
   standardized features, 16-16 hidden layers) on a stratified holdout.
8. The candidate is evaluated against the current production model **on the
   same holdout**: accuracy, per-class precision/recall/F1, macro F1,
   confusion matrix, inference latency per sample.
9. Acceptance criteria (configurable): macro F1 gain >= `min_macro_f1_gain`
   and no per-class recall drop > `max_recall_drop_per_class`; every fault
   class needs at least `min_records_per_class` confirmed records or training
   is blocked with a clear reason.
10. Promotion is a separate explicit action (`/promote`, token required).
    The previous production model is archived, not deleted.
11. Rollback (`/rollback`) restores the most recent archived model.
12. Every dataset build, training, promotion and rollback is written to an
    append-only audit log.

Retraining is batch/scheduled, never per-message: automatic training
(`auto_train`, default off) triggers only when at least
`retrain_min_new_labeled` new confirmed records exist. Training runs in a
background thread with a thread cap; the dashboard and twin stay responsive.

## Learning Center (dashboard)

Shows: active model version, dataset size, accepted/rejected records,
confirmed labels (and new since last dataset), last training date, candidate
status with metrics, model performance history, dataset/source distribution,
drift report, rollback availability, and the audit log. Controls: train
(source selector), promote, rollback, automatic-training switch, retraining
threshold. All controls require the local training token.

## Honest limitations

- Metrics from training on the project's simulated data measure simulation
  performance only. Real-device accuracy needs confirmed field data.
- No neural weights are updated per sensor message; the LLM itself is not
  fine-tuned by this pipeline (that would be unsafe and hardware-heavy).
- Battery SoH/RUL is NOT predicted: there is no validated degradation
  history. The architecture (records + datasets + versioned models) is ready
  for it when such history exists.
