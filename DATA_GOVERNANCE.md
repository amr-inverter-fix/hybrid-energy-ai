# Data Governance and Model Security

## Locality

- All local-AI data stays on the user's computer: `local_ai_data/` is
  git-ignored and never committed.
- The gateway binds 127.0.0.1 and contacts only the local Ollama runtime.
  No telemetry, training data, prompts or documents are sent to any external
  service. There is no upload code path.
- The hosted dashboard stores only device registrations and settings in the
  browser (localStorage/sessionStorage); no keys in code, no keys on GitHub.
- The optional weather provider (Open-Meteo) sends only coordinates when the
  user asks for a forecast; it is off unless used.

## Secrets

- Backend keys live in server environment variables (PythonAnywhere) and the
  user's password vault. Rotated on 2026-11-27 after an internal tool-trace
  exposure; old keys revoked.
- The local training token (`local_ai_data/training_token`) is created with
  owner-only file permissions and never printed to chat or committed.

## Training-data integrity

- Every record is validated (schema, units, ranges, timestamps, duplicates)
  before it can enter a dataset; rejected records are quarantined with reasons.
- Simulation and real-device data are strictly separated at dataset build time.
- Only user-confirmed labels are ground truth; suggestions never train models.
- Datasets and models are versioned; promotion and rollback are recorded in an
  append-only audit log, so any poisoning attempt is traceable and reversible.
- Training permissions are separated from ordinary dashboard access (token on
  mutation endpoints).

## Model files

- Candidate models are evaluated against production on a fixed holdout before
  they can be promoted; promotion is manual (or explicitly enabled automatic
  training with thresholds — promotion still requires the criteria to pass).
- Every promoted model is a JSON file in `local_ai_data/models/` with its
  metrics and dataset id; archived models stay available for rollback.

## Model licenses

All AI models are open-weight and downloaded once from the official Ollama
registry; each remains under its own license (see MODEL_SELECTION_REPORT.md
for the exact license per model and the embedding model). No manufacturer
manuals or standards are bundled; the assistant is instructed to say when the
knowledge base lacks evidence instead of inventing such documents.

## Known limitations

- The gateway trusts localhost callers that present the token; anyone with
  read access to the user's account on the computer can read the token file.
  This is the standard local-app threat model, not a server one.
- The hosted backend on PythonAnywhere (free tier) has cold starts and its
  SQLite storage is per-instance; see DEPLOYMENT.md.
