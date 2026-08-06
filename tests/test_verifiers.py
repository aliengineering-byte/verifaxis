from __future__ import annotations

from pathlib import Path

from verifaxis import Candidate, EvidenceStatus
from verifaxis.verifiers import PythonTestCase, RestrictedPythonVerifier, SafeMathVerifier


def test_safe_math_returns_structured_counterexample() -> None:
    packet = SafeMathVerifier().verify(task="What is 197 * 83?", candidate=Candidate("16352"))
    assert packet.status is EvidenceStatus.FAIL
    assert packet.counterexample == {
        "expression": "197 * 83",
        "expected": 16351,
        "observed": 16352,
        "difference": 1,
    }
    assert packet.is_independent and packet.validate_hash()


def test_safe_math_rejects_calls_and_attributes_without_executing(tmp_path: Path) -> None:
    marker = tmp_path / "executed"
    task = f"What is __import__('pathlib').Path({str(marker)!r}).touch()?"
    packet = SafeMathVerifier().verify(task=task, candidate=Candidate("0"))
    assert packet.status is EvidenceStatus.UNKNOWN
    assert not marker.exists()


def test_restricted_python_checks_pure_function_cases() -> None:
    verifier = RestrictedPythonVerifier(
        [PythonTestCase(args=(2, 3), expected=5), ((10, -1), 9)],
        function_name="add",
    )
    packet = verifier.verify(
        task="write add", candidate=Candidate("def add(a, b):\n    return a + b")
    )
    assert packet.status is EvidenceStatus.PASS
    assert packet.reliability["exec_used"] is False


def test_restricted_python_reports_first_failing_case() -> None:
    verifier = RestrictedPythonVerifier([((2, 3), 5)], function_name="add")
    packet = verifier.verify(task="write add", candidate=Candidate("def add(a, b):\n return a-b"))
    assert packet.status is EvidenceStatus.FAIL
    assert isinstance(packet.counterexample, dict)
    assert packet.counterexample["expected"] == 5
    assert packet.counterexample["observed"] == -1


def test_restricted_python_never_executes_import_or_attribute(tmp_path: Path) -> None:
    marker = tmp_path / "executed"
    source = f"def f():\n    return __import__('pathlib').Path({str(marker)!r}).touch()"
    verifier = RestrictedPythonVerifier([((), None)], function_name="f")
    packet = verifier.verify(task="write f", candidate=Candidate(source))
    assert packet.status is EvidenceStatus.FAIL
    assert not marker.exists()
