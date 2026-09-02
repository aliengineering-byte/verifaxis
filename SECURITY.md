# Security policy

## Supported versions

Security fixes target the latest pre-release revision on `main`.

## Reporting

Use GitHub's private vulnerability reporting for `aliengineering-byte/verifaxis`. Do not disclose suspected vulnerabilities in public issues. Include affected version, reproduction, impact, and any suggested mitigation. Expect an acknowledgement within seven days; remediation timing depends on severity and maintainer availability.

## Security model

Model candidates, prompts, endpoint responses, verifier output, counterexamples, artifacts, and configuration files are untrusted. Default verifiers never run arbitrary candidate code. The math and restricted-function paths interpret allowlisted syntax only. The OpenAI-compatible adapter sends data only to the endpoint explicitly configured by the caller, requires HTTPS for remote credentials, allows credentialed HTTP only for loopback testing, and redacts transport error details.

Out of scope: arbitrary-code sandboxes, multi-tenant hosting, authentication, secret storage, and network retrieval. See `docs/threat-model.md`.
