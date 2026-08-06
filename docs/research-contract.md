# Research contract

Status: frozen for v0.1 smoke/demo on 2026-08-06. No headline experiment is authorized by this version. Exact public-benchmark manifests and real-model snapshot identifiers must be added in a reviewed amendment before headline runs.

## Research question

Under matched inference budgets, when does verifier-conditioned external recurrence (VCER) improve or degrade the cost–risk–coverage frontier for frozen language models, especially when verifier feedback is incomplete, conflicting, stale, malformed, or corrupted?

## Hypotheses

- **H1 (performance, not novelty):** On tasks with deterministic verifiers, VCER improves final exact accuracy over direct generation and intrinsic Self-Refine under matched model-token budgets.
- **H2 (transition safety):** Residual-aware control improves wrong→right correction without increasing right→wrong regression relative to a naive fixed-round external-feedback loop.
- **H3 (allocation, not novelty):** Residual-aware stopping improves the cost–risk–coverage frontier relative to fixed iteration counts and random stopping. Adaptive allocation itself is established prior art.
- **H4 (fault handling):** Provenance checks and conflict handling reduce false verification and failure amplification under controlled corrupted feedback.

Any null or reversal is reportable. None of these hypotheses is a claim that the components are new.

## v0.1 datasets and exclusions

The only frozen v0.1 dataset is a generated deterministic smoke suite:

- 12 integer arithmetic expressions over whitelisted `+`, `-`, `*`, and bounded integer operands;
- 8 restricted pure-function repair cases evaluated by an AST interpreter, not host-language execution;
- immutable task IDs and seed `1729`;
- no training split and no model fitting.

This suite validates software behavior only. It cannot support model-quality, generalization, scaling, contamination, or publication claims.

Excluded from v0.1: factual QA, live web retrieval, subjective generation, arbitrary code, private datasets, and any benchmark whose license or immutable split manifest has not been recorded. Planned headline domains are numerical/symbolic reasoning and isolated code tests, but their exact public datasets remain **unfrozen** until a contract amendment records versions, licenses, exclusions, and hashes.

## Model families

The frozen v0.1 model is `ReplayModel/v1`, a deterministic scripted weak model that fails first and revises only after valid independent evidence. It is a test fixture, not an ML system.

Headline work requires at least three pinned model families, including at least two open-weight families and one black-box OpenAI-compatible endpoint. Temperature, decoding parameters, prompt template, model revision, quantization, serving stack, and endpoint date must be recorded. Replacing a model snapshot after inspecting primary results requires a contract amendment.

## Baselines

Every evaluated task must run:

1. direct generation;
2. intrinsic Self-Refine;
3. Best-of-N;
4. fixed-round external feedback / CRITIC-like loop;
5. random allocation or stopping;
6. VCER residual-aware control;
7. a tool-augmented initial-answer baseline with the same verifier information available before its first answer;
8. oracle allocation, labeled only as an upper bound.

No “self-correction improvement” claim may compare a tool-free baseline with a tool-enabled method as though tools were controlled.

## Compute accounting and budget matching

Primary matching unit: total model tokens (`input + output`) with the same per-call output cap. Report input tokens, output tokens, calls, verifier calls, verifier runtime, wall time, and available monetary cost separately. Token counts from providers are preferred; deterministic whitespace-token estimates must be labeled when provider counts are unavailable.

Verifier calls are reported, not converted into model tokens. A second cost-normalized analysis assigns preregistered monetary or wall-time weights to model and verifier calls. Estimated FLOPs are reported only for open-weight models with a documented calculation. Comparisons that cannot be exactly matched use the lower common budget or a cost–performance curve; they do not silently compare unequal budgets.

## Seeds

- smoke/demo and bootstrap seed: `1729`;
- headline generation/evaluation seeds: `1729`, `2718`, `31415`, `57721`, `104729`;
- fault-injection schedules are generated before model calls and stored with each run.

## Stopping rules

VCER stops on verified success, exhausted budget, repeated residual plateau, candidate oscillation, verifier conflict, unverifiability, model error, or verifier error. Verification requires at least one applicable independent non-LLM packet with `pass` and no applicable independent `fail` or `unknown` packet. LLM-produced criticism is never sufficient for `VERIFIED`.

Fixed-loop baselines use their preregistered round count even after an intermediate pass, except that hard model/verifier errors terminate. Random stopping draws its schedule from the stored seed before observing outcomes. Abstention is the output for unresolved, conflicted, or unverifiable terminal states.

## Metrics

Primary metrics:

- final exact accuracy;
- wrong→right correction rate;
- right→wrong regression rate;
- false-verification rate;
- verified-answer precision;
- selective risk at fixed coverage and area under the risk–coverage curve;
- normalized cost per correct non-abstained answer.

Secondary metrics:

- initial accuracy, abstention coverage, expected calibration error where a confidence is available;
- average iterations, model/verifier calls, token/cost/runtime components;
- residual reduction per iteration;
- plateau, oscillation, conflict, error, and unverifiable frequencies;
- recovery, amplification depth, and termination under each corruption type and rate.

## Statistical analysis

Use paired per-example evaluation. Report task-clustered paired bootstrap 95% confidence intervals with 10,000 resamples and stored bootstrap seed. Use an exact two-sided McNemar test for paired binary final correctness. Report effect sizes and raw transition counts, not only p-values. For risk–coverage and corruption curves, bootstrap examples while keeping all methods and fault schedules paired. Correct the family of confirmatory H1–H4 tests with Holm’s method. All other analyses are exploratory.

Smoke/demo runs do not receive significance tests and must be labeled `smoke/demo`.

## Failure criteria

A hypothesis fails if its preregistered primary contrast is non-positive, its uncertainty interval includes practically harmful regression, or the effect appears only under unmatched tool access or compute. H2 fails if VCER’s right→wrong rate exceeds the fixed loop by more than 1 percentage point, regardless of average accuracy. H4 fails if conflict/provenance handling does not lower false verification under at least false-positive and contradictory-evidence conditions.

Engineering release failure includes nondeterministic smoke output, a false `VERIFIED` state without independent evidence, unsafe evaluation of candidate code, trace/provenance loss, secret or identity leakage, or any quick start that needs a network/API key.

## Claims allowed

- From unit/smoke tests: the runtime implements the documented state machine deterministically on generated fixtures.
- From a single pinned model/domain: only model/domain-specific paired effects.
- From multiple pinned families and both deterministic domains: a bounded cross-model empirical finding about cost, correction/regression, coverage, and fault robustness.
- From corruption experiments: robustness only to the injected fault model and rates, not to all real verifier failures.

## Claims prohibited

- novelty of recurrence, external feedback, adaptive halting, counterexamples, abstention, or transition metrics alone;
- truth, hallucination elimination, universal reliability, or verifier soundness outside its documented domain;
- generalization from scripted fixtures or a single model/domain;
- causal attribution to recurrence when tool access, prompts, budgets, or selection differ;
- SOTA or conference-readiness claims without the complete gate in `docs/novelty-decision.md`.

