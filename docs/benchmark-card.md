# Benchmark card

## Purpose

The v0.2 offline smoke benchmark tests experimental plumbing. It does not
measure general model intelligence and contains no real-model result.

## Tasks

- 12 generated integer arithmetic tasks over a strict AST whitelist.
- 8 restricted pure-function repair tasks interpreted from allowlisted syntax.
- Fixed seed `1729`, stable task IDs, and deterministic evaluator-side truth.

No candidate code is executed with Python `exec` or in a host shell. The
restricted-code domain deliberately trades expressiveness for a safe vertical
slice.

## Compared strategies

The canonical config contains seven implemented shared-trajectory policies:
direct, no-feedback, verify-once/repair-once, fixed external feedback,
accepted-first/stop-on-pass, verifier-best-trajectory, and residual-aware VCER.
VRR-Guard and VRR-Stop are in the research comparison contract but are marked
unavailable rather than approximated. This blocks headline evaluation.

The initial candidate is generated once per example and reused across clean,
no-feedback, and fault conditions. One maximal trajectory, revision state shape,
evidence serializer, and bandwidth setting feeds offline stopping/selection
policies. Best-of-N requires an explicit charged selector and is not in the
canonical smoke config. Candidate-dependent tool-augmented initial answers are
excluded.

## Metrics

Metrics include initial/final exact accuracy, raw wrong-to-right/right-to-wrong
transitions, false verification, verified precision, abstention/coverage,
risk-coverage and AURC when confidence is available, calibration only when
model confidence is available, iterations, calls, normalized provider usage,
token-budget overshoot, runtime/cost, residual reduction, termination
frequencies, and controlled corruption behavior. Undefined rates and
unavailable confidence metrics are `null`.

Task-clustered paired bootstrap intervals, exact McNemar tests, and Holm
adjustment are implemented. Smoke/demo intervals are software checks, not
inferential research results.

## Fault model

The corruption layer covers false-positive/negative status, stale, malformed,
contradictory, missing-counterexample, duplicate, delayed, and
prompt-injection-like evidence. Schedules are keyed only by global seed, example
ID, verifier ID, condition, and step, then persisted with a canonical hash.
Fault labels/application decisions remain evaluator sidecars and never enter
model/controller evidence. Robustness cannot generalize beyond this fault model.

## Limitations

- `ReplayModel` is scripted and intentionally weak.
- Generated tasks are small fixtures, not representative benchmarks.
- Exact answer checks do not validate reasoning quality.
- Reliability depends on constraint coverage and verifier correctness.
- VRR-Guard and VRR-Stop are not implemented.
- No model-family comparison or headline result is included.

License: repository-generated fixtures are Apache-2.0. Public benchmark data
must not be added until its license, version, exclusions, manifest hash, and
contamination limitations are frozen in a confirmed contract amendment.
