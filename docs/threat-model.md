# Threat model

## Assets and goals

Protect the host, secrets, local files, network, trace integrity, experimental validity, and users from falsely verified or overconfident outputs. VerifAxis aims to fail closed when evidence is insufficient or conflicting.

## Untrusted inputs

- tasks, candidate text, model endpoint payloads, and model-generated configuration fragments;
- verifier messages, counterexamples, raw artifacts, timestamps, and tool text;
- benchmark/config files and report fields;
- paths, URLs, and provider metadata.

## Primary threats and controls

| Threat | v0.1 control | Residual risk |
|---|---|---|
| Code/command injection | No `eval`, `exec`, shell, dynamic import, or pickle; allowlisted AST interpreters | Parser/interpreter bugs |
| Path traversal | Runtime-generated trace paths; artifact references treated as opaque metadata | External integrations may dereference unsafe paths |
| Prompt injection in tool output | Evidence is structured; injected text is data; dedicated corruption case | A model can still follow hostile strings during revision |
| False verifier pass | Independence/reliability metadata, conflict checks, fault testing, false-verification metric | A single trusted verifier can be wrong or incomplete |
| LLM critique laundering | `llm_generated` is explicit; LLM-only evidence cannot verify | Incorrect integration metadata |
| Replay/stale evidence | Candidate/claim binding and stale-evidence faults | Weak semantic claim binding |
| Resource exhaustion | Shared preflight/postflight bounds for AST `BinOp`/`AugAssign`, bounded inputs/containers/calls, model/verifier/token budgets, and runtime accounting | HTTP endpoints enforce their own hard limits; parser/interpreter bugs remain possible |
| Secret leakage | No keys in config/examples/traces; environment-based endpoint credentials; secret scans | Provider request logs and user-supplied prompts |
| Unsafe deserialization | JSON only for public config/trace paths | JSON size/depth denial of service without caller limits |
| Misleading research claim | Frozen contract, raw paired results, explicit smoke labels | Human interpretation and selective reporting |

## Arbitrary code

Arbitrary model-generated code execution is not implemented. A future backend must be opt-in and use an ephemeral sandbox with time, memory, filesystem, process, syscall, and network restrictions. A subprocess alone is not a security boundary.

The restricted AST verifier allows only one pure function and a small statement,
operator, and call set. It rejects exponentiation before allocation when the
exponent or predicted integer bit length exceeds its bound; predicts sequence
concatenation/repetition size before allocation; rejects allocation-prone string
formatting; bounds values on input, literal, call, subscript, unary, assignment,
and result paths; and limits loops/ranges. The verifier never calls `exec` or
`eval`. A passing test establishes behavior only for the supplied cases.

## Experimental-validity boundary

Fault type, application decisions, and schedules are evaluator-side labels.
They must never be embedded in evidence sent to a model or stopping controller.
Prompt-injection-like tool text remains untrusted input and is deliberately
allowed to reach the model in the counterexample-bandwidth ablation. The primary
pilot uses status-only feedback.

## Non-goals

VerifAxis does not defend a compromised host, malicious package installer, provider-side retention, verifier collusion, or errors outside declared constraints. Evidence hashes provide integrity/auditability, not truth or authenticity.
