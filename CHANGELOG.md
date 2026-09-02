# Changelog

All notable changes follow [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). The project uses semantic versioning.

## [Unreleased]

### Added

- `demo` and `run` can export a complete claim/evidence recurrence artifact with package
  attribution, packet hashes, the full trace, and a named stopping decision.
- `verify-evidence` validates the unsigned outer digest, every evidence-packet hash, and derived
  claim/decision summaries offline; conflicting artifact writes are refused.
- Documented evidence sensitivity, repeat-output no-clobber behavior, unbounded-input validation,
  and the HTTPS requirement for API keys sent to remote OpenAI-compatible endpoints.

## [0.1.0] - 2026-08-06

### Added

- Typed evidence and trace protocols for verifier-conditioned external recurrence.
- Residual-aware controller with verified, budget, plateau, oscillation, conflict, unverifiable, model-error, and verifier-error termination.
- Safe arithmetic and restricted pure-function verifiers.
- Deterministic replay model, black-box endpoint adapter, fault injection, baselines, metrics, reports, and CLI smoke demo.
- Phase-0 prior-art audit, PIVOT decision, and frozen smoke research contract.

[Unreleased]: https://github.com/aliengineering-byte/verifaxis/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/aliengineering-byte/verifaxis/releases/tag/v0.1.0
