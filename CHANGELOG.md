# Changelog

All notable changes follow [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). The project uses semantic versioning.

## [Unreleased]

### Added

- The unreleased package identity is now `0.2.0` for the claim/evidence export contract.
- `demo` and `run` can export a complete claim/evidence recurrence artifact with package
  attribution, packet hashes, the full trace, and a named stopping decision.
- `verify-evidence` validates the unsigned outer digest, every evidence-packet hash, and derived
  claim/decision summaries offline; conflicting artifact writes are refused.
- Bounded untrusted evidence to 1 MiB, 32 JSON levels, 50,000 nodes, and 1,024 packets;
  malformed UTF-8, duplicate keys, conflicting summaries, and recomputed trace tampering fail
  closed.
- Remote OpenAI-compatible credentials now require HTTPS, with a loopback-only HTTP exception;
  credential-bearing URLs and unredacted transport errors are rejected.

## [0.1.0] - 2026-08-06

### Added

- Typed evidence and trace protocols for verifier-conditioned external recurrence.
- Residual-aware controller with verified, budget, plateau, oscillation, conflict, unverifiable, model-error, and verifier-error termination.
- Safe arithmetic and restricted pure-function verifiers.
- Deterministic replay model, black-box endpoint adapter, fault injection, baselines, metrics, reports, and CLI smoke demo.
- Phase-0 prior-art audit, PIVOT decision, and frozen smoke research contract.

[Unreleased]: https://github.com/aliengineering-byte/verifaxis/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/aliengineering-byte/verifaxis/releases/tag/v0.1.0
