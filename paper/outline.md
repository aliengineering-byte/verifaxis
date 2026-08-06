# Provisional paper outline

Working title: **When Should an LLM Think Deeper or Check Reality? Verifier-Conditioned External Recurrence for Frozen Language Models**

The title is provisional. This is an exploratory outline, not a submission.

1. Problem: test-time revision can correct or regress answers; verifiers can also fail.
2. Prior art and PIVOT: recurrence, tool-conditioned correction, CEGIS, adaptive allocation, and noisy verifier work.
3. Runtime: model/verifier/controller protocols, typed evidence, residuals, and safe stopping.
4. Benchmark: deterministic domains, matched accounting, baselines, and fault schedules.
5. Research contract: paired design, hypotheses, transition metrics, and claim boundaries.
6. Experiments: multiple pinned families and domains; correction/regression and cost–risk–coverage curves.
7. Fault study: false status, stale/conflicting/malformed/delayed/injected evidence.
8. Ablations: provenance, conflict handling, residual stopping, tool parity, verifier diversity.
9. Negative results and limitations.
10. Reproducibility and broader impact.

The publishable finding must identify when recurrence improves or amplifies verifier error under matched cost. “Tools help” is insufficient.
