# Benchmark card

## Purpose

The v0.1 smoke benchmark tests that VerifAxis measures verifier-conditioned recurrence reproducibly. It does not measure general model intelligence.

## Tasks

- 12 generated integer arithmetic tasks over a strict AST whitelist.
- 8 restricted pure-function repair tasks interpreted from allowlisted syntax.
- Fixed seed `1729`, stable task IDs, and deterministic ground truth.

No candidate code is executed with Python `exec` or in a host shell. The restricted-code domain deliberately trades expressiveness for a safe, complete vertical slice.

## Compared strategies

Direct generation, intrinsic Self-Refine, Best-of-N, fixed external feedback, random stopping, residual-aware VCER, tool-augmented initial answer, and oracle allocation (upper bound only).

Tool access and budgets are explicit. A tool-free method is not compared against a tool-enabled method and mislabeled as pure self-correction.

## Metrics

Initial/final exact accuracy, wrong→right, right→wrong, false verification, verified precision, abstention/coverage, risk–coverage, calibration when available, iterations, calls, tokens, runtime/cost, residual reduction, termination frequencies, and controlled corruption behavior. Raw per-example rows and seeds are retained.

Paired bootstrap intervals and exact McNemar tests exist for research-scale runs. They are not applied to smoke/demo output.

## Fault model

The reproducible corruption layer can inject false-positive/negative status, stale, malformed, contradictory, missing-counterexample, duplicate, delayed, and prompt-injection-like evidence. These faults approximate classes of verifier failure; robustness does not generalize beyond the injected model.

## Limitations

- `ReplayModel` is scripted and intentionally weak.
- Generated tasks are small, uncontaminated fixtures, not representative benchmarks.
- Exact answer checks do not validate reasoning quality.
- Reliability depends on constraint coverage and verifier correctness.
- No model-family comparison or headline result ships with v0.1.

License: repository-generated fixtures are Apache-2.0. Public benchmark data must not be added until its license, version, exclusions, manifest hash, and contamination limitations are documented in a research-contract amendment.
