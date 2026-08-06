# Reproducing the offline smoke demo

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
.venv/bin/pytest --cov=verifaxis --cov-report=term-missing --cov-fail-under=75
.venv/bin/python -m build
```

On Windows, replace `.venv/bin/` with `.venv\Scripts\`.

## Installed-artifact verification

Create fresh wheel and sdist environments, run `verifaxis demo` in each, then:

```bash
verifaxis bench --config configs/smoke.json --output runs/first
verifaxis bench --config configs/smoke.json --output runs/second
python scripts/compare_runs.py runs/first runs/second
```

Candidate sequences, schedule hashes, status transitions, replay usage, metrics,
and seeds must match exactly. Measured wall/verifier runtime is honest and may
differ; compare scripts may exclude only those declared timing fields.
`fault_schedules.json` is evaluator-side and its manifest hash must verify before
analysis.

## Research runs

Do not run headline experiments under the smoke contract. First confirm the v0.2
amendment with exact dataset manifests/licenses, model/serving/tokenizer
snapshots, decoding parameters, prompts, budgets, seeds, schedules, primary
contrasts, statistical tests, and permitted claims.

Store raw JSON before aggregate reports. Never overwrite a frozen run; use a new
run ID and record the analysis commit.
