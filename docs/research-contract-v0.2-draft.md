# Draft research-contract amendment v0.2

Status: **BLOCKED / unconfirmed** on 2026-08-06. This draft authorizes software
preparation and a bounded pilot only. It does not authorize headline results,
paper claims, a release, or substituting approximations for named methods.

## Required frozen identifiers

The amendment remains blocked until every placeholder below is replaced in a
reviewed commit made before inspecting primary outcomes:

- exact model provider, snapshot/revision, tokenizer revision and hash,
  quantization, serving software/version, decoding parameters, and endpoint date;
- exact math and code dataset names, immutable versions/splits, upstream URLs,
  licenses, exclusions, contamination notes, task counts, and manifest hashes;
- exact initial and revision prompt bytes plus prompt hashes;
- evidence bandwidth (`status_only` primary; `counterexample` ablation),
  serialization version, per-call output cap, total-token cap, verifier-call cap,
  wall-time cap, overshoot rule, and monetary-cost source;
- global seeds, hash-verified fault schedules, bootstrap seed/resamples,
  confirmatory contrasts, Holm family, and the analysis commit SHA.

No field may be selected after reviewing the corresponding primary comparison.

## Paired design

Cache one candidate-independent initial request per model/example/seed and reuse
the identical candidate and recorded usage across every policy and feedback
condition. Generate one maximal trajectory from the shared revision prompt and
evidence serializer, then apply stopping/selection policies offline. Policy and
baseline identifiers must not enter model sampling or fault-schedule keys.

Primary feedback is status-only. The counterexample representation is a
separately named ablation with the same byte/token cap across methods. Evaluator
truth, fault kind, whether a fault was applied, and release timing live only in
sidecars and are never serialized into evidence sent to the model or controller.

Every example includes clean and no-feedback conditions. Fault comparisons use
the same schedule keyed only by global seed, example ID, verifier ID, fault
condition, and recurrence step; schedules are persisted and hash-verified.

## Required strategies

1. direct/no-feedback initial candidate;
2. verify-once/repair-once;
3. fixed-round external feedback;
4. accepted-first / stop-on-pass;
5. verifier-best-trajectory selection;
6. VCER residual-aware stopping;
7. VRR-Guard, faithfully reproduced from arXiv:2607.17641;
8. VRR-Stop, faithfully reproduced from arXiv:2607.17641;
9. VCER ablations for status-only versus counterexample bandwidth and each
   stopping signal.

Best-of-N is permitted only with an explicit selector whose model/verifier calls
and usage are charged. A tool-augmented initial answer is excluded unless its
evidence is candidate-independent and every tool call/runtime is charged. Oracle
selection is an upper bound only and never a primary baseline.

## Provisional go/no-go criterion

This criterion requires confirmation after a cost/variance pilot:

> With fault labels hidden, identical cached initial candidates, identical evidence bandwidth, and matched token/verifier caps, VCER must be non-inferior to the strongest deployable tool-parity baseline under clean feedback within 2 accuracy points. Under both 20% conditional false acceptance and 20% contradictory feedback, it must reduce wrong committed answers by at least 30% relative while losing no more than 5 coverage points. The direction must replicate in both math and code and in at least two of three pinned model families.

This criterion is provisional and must be confirmed or amended before the pilot
outcomes are opened. “Strongest baseline” is selected on the preregistered clean
validation aggregate, not per test example. Noninferiority and fault effects use
task-clustered paired bootstrap intervals; confirmatory p-values receive Holm
adjustment. Report raw transition counts and all negative/reversed contrasts.

## Pilot boundary

A one-model pilot may validate prompts, token/runtime accounting, trajectory
pairing, schedule integrity, fault rates, and analysis code. It may not estimate
cross-model claims or tune the go/no-go threshold. The headline experiment
remains blocked until exact identifiers above are frozen and VRR-Guard/VRR-Stop
pass equivalence checks against their published algorithms.
