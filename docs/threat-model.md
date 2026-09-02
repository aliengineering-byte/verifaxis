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
| Resource exhaustion | Bounded model/verifier calls, iterations, tokens, response bytes/JSON shape, and evidence file/JSON/packet counts | HTTP endpoints enforce their own server-side limits |
| Secret leakage | No keys in config/examples/traces; remote credentials require HTTPS; loopback-only HTTP credential exception; endpoint errors are redacted; secret scans | Provider request logs, caller-supplied custom header names, and user-supplied prompts |
| Unsafe deserialization | JSON only; evidence rejects malformed UTF-8, duplicate keys, files over 1 MiB, depth over 32, over 50,000 nodes, and over 1,024 packets | Callers that bypass the bounded file loader must impose equivalent transport limits |
| Misleading research claim | Frozen contract, raw paired results, explicit smoke labels | Human interpretation and selective reporting |

## Arbitrary code

Arbitrary model-generated code execution is not implemented. A future backend must be opt-in and use an ephemeral sandbox with time, memory, filesystem, process, syscall, and network restrictions. A subprocess alone is not a security boundary.

## Non-goals

VerifAxis does not defend a compromised host, malicious package installer, provider-side retention, verifier collusion, or errors outside declared constraints. Evidence hashes provide integrity/auditability, not truth or authenticity.
