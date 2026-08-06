# Prior-art audit

Audit cutoff: 2026-08-06. This is a focused novelty gate, not a systematic review. We used primary papers, official project pages, and original repositories. A check means the feature is central to the evaluated method; `partial` means adjacent or task-specific support. “Frozen” means unchanged during the evaluated inference loop.

## Comparison

| Work | Internal latent recurrence | Frozen base | External non-LLM verifier | Typed evidence | Counterexample generation | Residual tracking | Adaptive halting | Corrupted-feedback evaluation | Matched-compute comparison | Support |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| [Universal Transformer](https://arxiv.org/abs/1807.03819) | yes | no | no | no | no | no | yes | no | no | open-weight architecture |
| [Huginn / recurrent-pretraining](https://arxiv.org/abs/2502.05171) ([code](https://github.com/seal-rg/recurrent-pretraining)) | yes | no | no | no | no | partial: internal KL | yes | no | partial | open weights |
| [Retrofitting Recurrence](https://arxiv.org/abs/2511.07384) ([code](https://github.com/mcleish7/retrofitting-recurrence)) | yes | no | no | no | no | no | no | no | yes | open weights |
| [T²MLR](https://arxiv.org/abs/2607.15178) ([code](https://github.com/princeton-pli/T2MLR)) | yes | no | no | no | no | no | no | no | yes | open weights |
| [Ouro](https://arxiv.org/abs/2510.25741) ([project](https://ouro-llm.github.io/)) | yes | no | no | no | no | partial: internal loss/L2 | yes | no | partial | open weights |
| [Mixture-of-Recursions](https://arxiv.org/abs/2507.10524) ([code](https://github.com/raymin0223/mixture_of_recursions)) | yes | no | no | no | no | no | yes | no | yes | open weights |
| [Coconut](https://arxiv.org/abs/2412.06769) ([code](https://github.com/facebookresearch/coconut)) | yes | no | no | no | no | no | partial | no | partial | open weights |
| [ANIRA](https://arxiv.org/abs/2602.08864) ([code](https://github.com/merlresearch/ANIRA)) | yes | no | no | no | no | no | yes | no | partial | open weights |
| [ReAct](https://arxiv.org/abs/2210.03629) ([code](https://github.com/ysymyth/ReAct)) | no | yes | partial: environments/tools | no | no | no | partial | no | no | black-box + open-weight |
| [Self-Refine](https://proceedings.neurips.cc/paper_files/paper/2023/hash/91edff07232fb1b55a505a9e9f6c0ff3-Abstract-Conference.html) ([code](https://github.com/madaan/self-refine)) | no | yes | no | no | no | no | partial | no | no | black-box + open-weight |
| [Reflexion](https://proceedings.neurips.cc/paper_files/paper/2023/hash/1b44b878bb782e6954cd888628510e90-Abstract-Conference.html) ([code](https://github.com/noahshinn/reflexion)) | no | yes | partial | partial | partial | no | yes | no | no | black-box + open-weight |
| [CRITIC](https://openreview.net/forum?id=Sx038qxjek) ([code](https://github.com/microsoft/ProphetNet/tree/master/CRITIC)) | no | yes | yes | partial | partial | no | partial | no | no | black-box + open-weight |
| [ProgCo](https://aclanthology.org/2025.acl-short.73/) ([code](https://github.com/songxiaoshuai/progco)) | no | yes | partial; default is LLM-mediated | partial | partial | partial | yes | partial motivation only | partial | black-box + open-weight |
| [BATS](https://arxiv.org/abs/2511.17006) | no | yes | no: LLM/web evidence | partial | partial | yes | yes | no | yes: unified economic cost | black-box |
| [When2Tool](https://arxiv.org/abs/2605.09252) ([code](https://github.com/Trustworthy-ML-Lab/when2tool)) | no | yes | no | yes: tool boundary labels | no | no | yes: one-shot routing | no | yes | open-weight |
| [CEGIS / Program Synthesis by Sketching](https://www2.eecs.berkeley.edu/Pubs/TechRpts/2008/EECS-2008-176.html) | no | n/a | yes | yes | yes | yes: accumulated constraints | yes: proof/failure | no: sound verifier assumed | no | symbolic synthesis |
| [Large Language Models Cannot Self-Correct Reasoning Yet](https://openreview.net/forum?id=IkmD3fKBPQ) | no | yes | no | no | no | no | no | no | partial | black-box + open-weight |
| [Confidence v.s. Critique](https://aclanthology.org/2025.acl-long.203/) | no | yes | no | no | no | no | no | no | no | black-box + open-weight |
| [Best-of-N under imperfect rewards](https://proceedings.mlr.press/v267/huang25c.html) | no | yes | partial: learned reward | no | no | no | no | yes: reward hacking | yes | black-box + open-weight |
| [RL with verifiable yet noisy rewards](https://arxiv.org/abs/2510.00915) | no | no: training study | partial | no | no | no | no | yes: false positives/negatives | no | trained models |

| [Verify, Repair, Repeat, or Stop?](https://arxiv.org/abs/2607.17641) | no | yes | yes | partial | partial | partial: belief state | yes: VRR-Stop/Guard | yes: verifier/repair noise | yes | LLM agents |
| [Don't Blindly Trust It](https://arxiv.org/abs/2606.21409) | no | yes | partial: tool feedback | partial | no | no | partial | yes: faithful/misleading/absent | yes: matched loop | LLM agents |

## Essential findings

- Internal recurrence is established. Universal Transformer, Huginn, Retrofitted Recurrence, T²MLR, Ouro, Mixture-of-Recursions, Coconut, and ANIRA already study learned recurrence, dynamic depth, or latent convergence. VerifAxis must not present recurrence or adaptive depth as new.
- External text recurrence is established. ReAct interleaves actions and observations; Self-Refine uses intrinsic feedback; Reflexion uses environment feedback and verbal memory; CRITIC directly implements a frozen black-box `generate → tool critique → correct` loop.
- Constraint- and budget-aware control is established. ProgCo uses program-shaped verification and pass-based stopping. BATS maintains constraints, remaining budget, and continue/pivot routing. When2Tool studies whether tool calls are needed.
- Candidate–counterexample iteration is classical. CEGIS already couples synthesis, validation, counterexamples, accumulated constraints, and termination.
- Correction can regress correct answers. Huang et al. show intrinsic self-correction can fail or degrade reasoning. Yang et al. directly decompose retaining correct answers and converting wrong answers. CRITIC also reports regressions among initially correct mathematical-program outputs.
- Verifier reliability is not a blank area. Prior work studies reward hacking under imperfect proxy rewards and asymmetric false-positive/false-negative verifier noise, though mainly for selection or training rather than inference-time recurrent fault handling.
- The requested acronym “FAR / falsification-guided retrieval” could not be tied to a primary paper or official repository under that exact name. It is not cited as a work. The closest identified preprint, [FVA-RAG](https://arxiv.org/abs/2512.07015), retrieves adversarial counterevidence and uses LLM arbitration; it is not deterministic verification.

Two July-cutoff papers close the remaining broad positioning. Wu et al. directly
formalize noisy verify-repair stopping and introduce VRR-Stop plus the
estimation-free VRR-Guard fallback. Zhang et al. hold the agent loop, prompt,
action space, and decoding fixed while varying faithful, misleading, or absent
feedback. These establish VRR-Guard/Stop as required comparators and a matched
no-feedback fallback as a mandatory control. VerifAxis must not approximate
either method under its published name.

## Collision boundary

The method-level claim “a frozen model improves by iterating on external verification” collides with CRITIC and adjacent tool-feedback agents. The controller-level claims “track constraints and remaining budget” and “adaptively continue or stop” collide with BATS, ANIRA, adaptive-consistency, and test-time-compute allocation work. Typed evidence, counterexamples, abstention, correction/regression measurement, and noisy-verifier studies each have precedents.

What remains defensible is a unified, open benchmark and runtime that puts these pieces behind explicit protocols and evaluates their interaction: provenance-bearing executable evidence, independence labels, machine-readable residuals, conflict and fault handling, paired transition metrics, and matched accounting across black-box and open-weight models. The empirical contribution must be a reproducible finding about when this system changes the cost–risk–coverage frontier—not the combination alone.

Noisy verify-repair stopping and matched misleading/no-feedback evaluation are
therefore occupied; neither is available as a broad novelty claim.

## Scope notes

- T²MLR is temporal middle-layer recurrence, not an external verifier loop. Its matched-training result includes an important negative: a longer-trained conventional Transformer can win.
- Ouro’s internal “verifier” terminology does not mean an independent verifier; it is part of the model.
- ProgCo’s default pseudo-program execution is LLM-mediated and must not be counted as independent evidence.
- Retrieved text can be useful evidence, but retrieval quality and source correctness prevent “verified truth” claims.
