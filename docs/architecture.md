# Architecture

## Boundary

VerifAxis is a model-agnostic runtime around an unchanged model. The technical term is **Verifier-Conditioned External Recurrence (VCER)**. “Third axis” is only a motivating metaphor; ordinary Transformer neurons are not described as two-dimensional.

For task `x` and recurrence step `z`:

```text
h_z     = B_theta(x, p_z)
e_z     = V(y_z, environment)
p_{z+1} = A_phi(p_z, h_z, Encode(e_z))
```

`B_theta` is frozen, `V` is an independently characterized verifier, and v0.1's `A_phi` is a transparent rule-based controller.

## Protocols

| Protocol | Responsibility | Trust boundary |
|---|---|---|
| `ModelAdapter` | Produce a candidate from task, compact state, and budget | Output is untrusted; no private chain-of-thought required |
| `Verifier` | Check a specific claim and emit typed evidence | Must declare independence, provenance, reliability, and LLM-origin fields |
| `EvidencePacket` | Immutable check status, counterexample, metadata, hash, artifact reference | Hash protects trace integrity, not verifier truth |
| `EvidenceResidual` | Explicit unresolved/failed/conflicting constraints | Data, not free-form hidden reasoning |
| `VerificationController` | Continue, verify, abstain, or stop on a named failure mode | Cannot promote LLM criticism to independent proof |
| `RunTrace` | Persist steps, accounting, evidence, residuals, termination | JSON-safe and auditable |

Provider, verifier, controller, trace storage, and reporting boundaries remain separate so experiments can change one factor at a time.

## Paired evaluation path

The pilot harness is separate from the live convenience loop. It makes one
candidate-independent initial call, caches the candidate and usage, and reuses
them across clean/no-feedback/fault conditions. Each condition produces one
maximal trajectory with the same revision-state builder, evidence serializer,
and bandwidth. Stopping and selection policies replay that trajectory offline;
their names cannot influence sampling or fault scheduling.

The primary bandwidth is status-only. Counterexamples are an explicit ablation
and are serialized as untrusted data. Evaluator truth and fault labels never
enter the model/controller representation. An unverified terminal returns
`answer=null`; the last candidate remains separately available for audit and
candidate-quality metrics.

## State machine

```mermaid
stateDiagram-v2
    [*] --> Generate
    Generate --> ModelError: adapter failure
    Generate --> Verify: candidate
    Verify --> VerifierError: verifier failure
    Verify --> Verified: independent pass and no conflict
    Verify --> Conflict: independent pass and fail disagree
    Verify --> Unverifiable: no applicable independent check
    Verify --> Revise: actionable residual and budget remains
    Revise --> Generate
    Revise --> Plateau: unchanged residual limit
    Revise --> Oscillation: repeated candidate cycle
    Revise --> BudgetExhausted: next call exceeds budget
```

Pass/fail status from an LLM-generated component may be recorded, but cannot independently cause `VERIFIED`.

## Operating modes

### Black-box text recurrence

The convenience runtime can carry full structured evidence. The paired pilot
uses the shared status-only serializer above. `OpenAICompatibleModel` calls only
an explicitly configured endpoint and records normalized input/output, cached,
reasoning, raw-provider usage, estimated/provider flags, and available cost.
`ReplayModel` is the offline deterministic fixture.

### Open-weight latent recurrence (future)

The protocol allows a later frozen Hugging Face base plus a small trainable state/soft-prompt adapter. No such backend is claimed to work in v0.1. Huginn, T²MLR, Retrofitted Recurrence, Coconut, Ouro, and ANIRA are prior art and baselines.

## Data and privacy

Traces contain concise candidate text, evidence, decisions, and accounting. They do not require hidden activations or private chain-of-thought. Endpoint users remain responsible for provider retention policies and sensitive prompt handling.
