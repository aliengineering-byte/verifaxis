# Reproducing v0.1

## Environment

- Python 3.11 or newer
- Git
- no API key, network access, GPU, or paid endpoint for default checks

From a clean clone:

```bash
python -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/ruff format --check .
.venv/bin/ruff check .
.venv/bin/mypy src
.venv/bin/pytest
.venv/bin/python -m build
```

On Windows, replace `.venv/bin/` with `.venv\Scripts\`.

## Installed-artifact verification

Create two fresh environments. Install the wheel in one and the sdist in the other, then run:

```bash
verifaxis demo
verifaxis bench --config configs/smoke.yaml --output runs/first
verifaxis bench --config configs/smoke.yaml --output runs/second
python scripts/compare_runs.py runs/first runs/second
```

The raw smoke rows normalize wall-clock measurements to zero and omit timestamp-dependent evidence hashes. Every persisted field—including candidates, evidence summaries, decisions, metrics, and seeds—must match exactly.

## Research runs

Do not run headline experiments under the smoke contract. First add a dated contract amendment containing dataset manifests and licenses, exact model and serving snapshots, decoding parameters, prompts, budgets, seeds, fault schedules, primary contrasts, statistical tests, and permitted claims.

Store raw JSON results before aggregate reports. Never overwrite a frozen run; use a new run ID and record the code commit.
