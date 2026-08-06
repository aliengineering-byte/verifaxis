# AGENTS.md

## Repository map

- `src/verifaxis/`: protocols, controllers, models, verifiers, faults, baselines, metrics, reporting, and CLI.
- `tests/`: offline deterministic unit and integration tests.
- `examples/`, `configs/`, `benchmarks/`: JSON-valid YAML inputs and immutable smoke fixtures.
- `docs/`: architecture, audit, research contract, security, benchmark, and reproduction notes.
- `paper/`: provisional outline, claim ledger, and primary references; not a submitted paper.

## Commands

```bash
python -m pip install -e ".[dev]"
ruff format .
ruff check .
mypy src
pytest
python -m build
verifaxis demo
verifaxis bench --config configs/smoke.yaml
```

Tests and the quick start must not require a network, GPU, API key, or paid service.

## Scientific claim rules

- Label generated fixture output `smoke/demo`; never call it a research result.
- Treat `docs/research-contract.md` as frozen. Amend it explicitly before headline experiments.
- Keep raw paired results, task IDs, manifests, fault schedules, and seeds.
- Never claim novelty, SOTA, hallucination elimination, truth, or publication readiness from code existence.
- Separate model tokens, calls, verifier calls/runtime, wall time, and cost. Do not hide unequal tool access.
- Report negative results and right→wrong regressions.

## Security boundaries

- Model and verifier output is untrusted.
- Never `eval`, `exec`, shell, import, deserialize with pickle, or construct paths from model text.
- Arithmetic and restricted-code verifiers must use allowlisted AST interpretation.
- LLM-produced feedback cannot be classified as independent evidence.
- Evidence hashes cover canonical content; raw artifacts use safe references, not traversal-prone paths.
- Arbitrary-code execution requires a separate opt-in sandbox design and is out of scope for v0.1.

## Definition of done

Changes are done only when formatting, lint, strict typing, tests, build, isolated artifact install, installed CLI demo, deterministic repeated smoke, secret/identity scan, and a clean working tree pass. Documentation and public APIs must match executable behavior.
