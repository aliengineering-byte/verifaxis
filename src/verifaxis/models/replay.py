"""Deterministic weak model for offline demos and tests."""

from __future__ import annotations

from collections.abc import Mapping

from ..types import Candidate, JSONValue, content_digest


class ReplayModel:
    """Answer arithmetic wrongly once, then repair only from valid evidence.

    This is a scripted smoke-test model, not an empirical model result.  It
    intentionally refuses to revise from LLM-produced, dependent, or
    tampered feedback.
    """

    def __init__(self, model_id: str = "replay/arithmetic-wrong-then-correct") -> None:
        self._model_id = model_id
        self.calls = 0

    @property
    def model_id(self) -> str:
        return self._model_id

    @staticmethod
    def _valid_expected(evidence: object) -> JSONValue | None:
        if not isinstance(evidence, list):
            return None
        for item in evidence:
            if not isinstance(item, dict):
                continue
            packet = dict(item)
            supplied_hash = packet.pop("content_hash", None)
            if supplied_hash != content_digest(packet):
                continue
            if (
                packet.get("status") != "FAIL"
                or packet.get("independence") != "INDEPENDENT"
                or packet.get("llm_produced") is not False
            ):
                continue
            counterexample = packet.get("counterexample")
            if isinstance(counterexample, dict) and "expected" in counterexample:
                expected = counterexample["expected"]
                if isinstance(expected, str | int | float | bool) or expected is None:
                    return expected
        return None

    def generate(self, *, task: str, state: Mapping[str, JSONValue]) -> Candidate:
        from ..verifiers.safe_math import evaluate_arithmetic_task

        self.calls += 1
        expected = self._valid_expected(state.get("evidence"))
        actual = evaluate_arithmetic_task(task)
        metadata: dict[str, JSONValue] = {"scripted_demo": True, "call": self.calls}

        if expected is not None and expected == actual:
            return Candidate(content=str(expected), model_id=self.model_id, metadata=metadata)

        if isinstance(actual, bool):
            wrong: int | float = int(actual) + 1
        elif isinstance(actual, int | float):
            wrong = actual + 1
        else:
            # The verifier will return UNKNOWN for unsupported tasks; the replay
            # model does not pretend to know an answer.
            return Candidate(content="unknown", model_id=self.model_id, metadata=metadata)
        return Candidate(content=str(wrong), model_id=self.model_id, metadata=metadata)
