# Security policy

## Supported versions

Security fixes target the latest `0.1.x` revision on `main` while the project is pre-release.

## Reporting

Use GitHub's private vulnerability reporting for `aliengineering-byte/verifaxis`. Do not disclose suspected vulnerabilities in public issues. Include affected version, reproduction, impact, and any suggested mitigation. Expect an acknowledgement within seven days; remediation timing depends on severity and maintainer availability.

## Security model

Model candidates, prompts, endpoint responses, verifier output, counterexamples, artifacts, and configuration files are untrusted. Default verifiers never run arbitrary candidate code. The math and restricted-function paths interpret allowlisted syntax only. The OpenAI-compatible adapter sends data only to the endpoint explicitly configured by the caller.

`RestrictedPythonVerifier` is an AST interpreter, not a Python sandbox. Every
binary and augmented binary operation crosses the same pre-allocation and
post-operation size boundary. Integer powers, integer products, string/list/
tuple concatenation and repetition, materializing calls, input values, and
assignment paths are bounded. String `%` formatting is rejected because its
field width can allocate before a result-size check. These controls limit known
resource-exhaustion paths; they do not make arbitrary Python safe.

Out of scope for v0.1: arbitrary-code sandboxes, multi-tenant hosting, authentication, secret storage, and network retrieval. See `docs/threat-model.md`.
