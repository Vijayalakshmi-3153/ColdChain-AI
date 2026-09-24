# Data (ColdChain AI)

Local data folder for the project. Intended contents in later steps:

- `raw/` – raw sensor / logistics datasets
- `processed/` – cleaned datasets used for training
- `models/` – trained model artifacts (also mirrored in MinIO)

Notes:

- Large files and model binaries should NOT be committed to git
  (see the root `.gitignore`).
- A small sample CSV may be added later for development/testing.