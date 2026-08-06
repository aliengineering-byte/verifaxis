# Claim ledger

## Supported by v0.1 software tests

- VerifAxis can run a deterministic candidate–verify–revise loop with structured evidence and JSON traces.
- Default arithmetic and restricted-function verifiers do not execute arbitrary candidate Python.
- The controller exposes named success, budget, plateau, oscillation, conflict, unverifiable, model-error, and verifier-error outcomes.
- The smoke harness can exercise named baselines and controlled fault types offline.
- The smoke harness can cache one initial candidate, persist hash-verified
  baseline-independent fault schedules, and replay implemented policies over a
  shared maximal trajectory.

These are engineering claims, not model-quality findings.

## Not yet supported

- VCER improves real frozen models under matched compute.
- Residual stopping dominates fixed or random stopping.
- Provenance/conflict controls improve real-world verifier robustness.
- Results generalize across models, domains, verifier families, or corruption processes.
- The method is novel, SOTA, publication-ready, or hallucination-eliminating.
- VRR-Guard or VRR-Stop results; those contract baselines remain unavailable.

## Promotion rule

A claim moves into the supported section only after a preregistered contract amendment, immutable raw results, paired uncertainty, appropriate tests, negative-result disclosure, and reproduction from a clean clone. Wording must name the evaluated models, datasets, budgets, and verifier assumptions.
