# Contributing

Thank you for improving VerifAxis. Open an issue before large API or research-contract changes.

## Development

Use Python 3.11 or newer:

```bash
python -m pip install -e ".[dev]"
ruff format .
ruff check .
mypy src
pytest
python -m build
```

Keep pull requests small and include tests for public behavior. Commit generated benchmark outputs only when they are immutable fixtures with recorded seeds and licenses.

## Verifiers

New verifiers must return typed evidence; document scope, failure modes, version, independence, provenance, reliability metadata, and raw artifacts. Treat all inputs as untrusted. Do not use `eval`, `exec`, shell commands, dynamic imports, pickle, or model-controlled paths. Arbitrary code execution is out of scope unless separately reviewed and isolated with explicit time, memory, filesystem, process, and network restrictions.

## Research changes

Do not rewrite a frozen contract after inspecting results. Add a dated amendment. Preserve per-example results, paired seeds, fault schedules, negative results, and budget accounting. Claims must remain within `paper/claims.md`.

By participating, you agree to the [Code of Conduct](CODE_OF_CONDUCT.md). Report vulnerabilities through [SECURITY.md](SECURITY.md), not a public issue.
