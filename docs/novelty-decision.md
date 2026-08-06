# Novelty decision

## PIVOT

Decision date: 2026-08-06.

The proposed method does **not** survive as a claim that verifier-conditioned recurrence for frozen language models is itself new.

CRITIC already applies repeated external tool feedback to an unchanged black-box model. Reflexion supplies environment-conditioned retry and memory. ProgCo supplies verification-program feedback and early stopping. BATS supplies persistent constraints, remaining-budget conditioning, adaptive continue/pivot routing, and unified cost curves. CEGIS supplies the more general candidate–counterexample–revision abstraction. Separate work already studies adaptive test-time allocation, correction versus regression, abstention, and imperfect verifier/reward signals.

VerifAxis therefore adopts the strongest defensible fallback contribution:

> An open, model-agnostic benchmark and runtime for measuring verifier-conditioned recurrence, correction/regression dynamics, evidence coverage, and safe stopping under equal compute and unreliable feedback.

## Allowed positioning

VerifAxis is an exploratory research prototype and reliability middleware for auditable inference experiments. Its differentiating engineering surface is:

- a normalized evidence schema with provenance, hashes, independence classifications, reliability metadata, artifact references, and explicit LLM-origin flags;
- explicit evidence residuals and conservative termination reasons;
- deterministic fault injection for temporal, structural, contradictory, and prompt-injection-like tool output failures;
- paired correction/regression, false-verification, risk–coverage, and cost accounting;
- one protocol spanning black-box endpoints and later open-weight adapters.

## Prohibited positioning

Until cross-model, cross-domain, matched-budget experiments are complete, the project must not claim:

- a new recurrence principle or architecture;
- that external tool feedback, typed evidence, adaptive stopping, abstention, or counterexamples are individually novel;
- elimination of hallucinations, guaranteed truth, or soundness beyond each verifier’s stated scope;
- SOTA, main-conference readiness, publication readiness, or superiority over named baselines;
- that smoke/demo output is a research result.

## Naming

`aliengineering-byte/verifaxis` and the `verifaxis` package name were available on GitHub, PyPI, and TestPyPI when checked on 2026-08-06. The working and public name remains **VerifAxis**.

## Gate to stronger claims

A stronger paper claim requires preregistered model snapshots and benchmark manifests, at least two deterministic domains, multiple model families, tool-parity baselines, matched compute, uncertainty intervals, paired tests, ablations, fault sweeps, and reported negative results. The finding must go beyond “tools help.”

