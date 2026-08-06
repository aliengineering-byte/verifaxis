# Changelog

All notable changes follow [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). The project uses semantic versioning.

## [Unreleased]

### Security

- Route `BinOp` and `AugAssign` through one bounded-operation implementation,
  adding pre-allocation limits for exponentiation, integer growth, sequence and
  string allocation, materializing calls, and all alternate assignment/input
  paths. Reject allocation-prone string formatting.

### Changed

- Keep injected-fault labels exclusively in evaluator sidecars and use
  baseline-independent, hash-verified paired schedules.
- Cache initial candidates, generate shared maximal trajectories, and replay
  stopping policies with status-only primary feedback.
- Normalize per-call usage, enforce total-token budgets with recorded overshoot,
  measure verifier runtime, and return `answer=null` for unverified terminals.
- Mark undefined metrics unavailable instead of inventing zero rates or model
  confidence; add AURC availability, normalized cost, raw transitions,
  task-cluster bootstrap, and Holm adjustment.

## [0.1.0] - 2026-08-06

### Added

- Typed evidence and trace protocols for verifier-conditioned external recurrence.
- Residual-aware controller with verified, budget, plateau, oscillation, conflict, unverifiable, model-error, and verifier-error termination.
- Safe arithmetic and restricted pure-function verifiers.
- Deterministic replay model, black-box endpoint adapter, fault injection, baselines, metrics, reports, and CLI smoke demo.
- Phase-0 prior-art audit, PIVOT decision, and frozen smoke research contract.

[Unreleased]: https://github.com/aliengineering-byte/verifaxis/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/aliengineering-byte/verifaxis/releases/tag/v0.1.0
