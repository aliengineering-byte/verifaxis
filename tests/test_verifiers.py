from __future__ import annotations

from pathlib import Path
from time import monotonic

import pytest

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


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("x += 3", 5),
        ("x -= 3", -1),
        ("x *= 3", 6),
        ("x //= 2", 1),
        ("x %= 2", 0),
        ("x **= 3", 8),
    ],
)
def test_restricted_python_augassign_uses_normal_bounded_semantics(
    body: str, expected: int
) -> None:
    verifier = RestrictedPythonVerifier([((2,), expected)], function_name="f")
    packet = verifier.verify(
        task="write f", candidate=Candidate(f"def f(x):\n    {body}\n    return x")
    )
    assert packet.status is EvidenceStatus.PASS


@pytest.mark.parametrize(
    "source",
    [
        "def f():\n    x = 2\n    x **= 5000\n    return x",
        "def f():\n    x = [0]\n    x *= 10001\n    return len(x)",
        "def f():\n    x = [0] * 6000\n    x += [0] * 5000\n    return len(x)",
        "def f():\n    return [0] * 10001",
        "def f():\n    return 2 ** 5000",
        "def f():\n    return '%1000000000d' % 1",
    ],
)
def test_restricted_python_rejects_all_oversized_binary_paths_quickly(source: str) -> None:
    verifier = RestrictedPythonVerifier([((), None)], function_name="f")
    started = monotonic()
    packet = verifier.verify(task="write f", candidate=Candidate(source))
    assert monotonic() - started < 1.0
    assert packet.status is EvidenceStatus.FAIL
    assert isinstance(packet.counterexample, dict)
    assert packet.counterexample["error"] == "ValueError"


def test_restricted_python_rejects_oversized_test_inputs_before_interpretation() -> None:
    with pytest.raises(ValueError, match="container exceeds"):
        RestrictedPythonVerifier([(([0] * 10_001,), 0)], function_name="f")


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("def f():\n    x = [1]\n    x += [2, 3]\n    return x", [1, 2, 3]),
        ("def f():\n    x = 'ab'\n    x *= 3\n    return x", "ababab"),
        ("def f():\n    x = [1]\n    x *= -2\n    return x", []),
    ],
)
def test_restricted_python_normal_augmented_sequences(source: str, expected: object) -> None:
    verifier = RestrictedPythonVerifier([((), expected)], function_name="f")
    assert (
        verifier.verify(task="write f", candidate=Candidate(source)).status is EvidenceStatus.PASS
    )


@pytest.mark.parametrize("base", [-100, -2, -1, 0, 1, 2, 100])
@pytest.mark.parametrize("exponent", range(0, 8))
def test_restricted_python_bounded_power_matches_python(base: int, exponent: int) -> None:
    verifier = RestrictedPythonVerifier([((base, exponent), base**exponent)], function_name="power")
    packet = verifier.verify(
        task="write power",
        candidate=Candidate("def power(base, exponent):\n    return base ** exponent"),
    )
    assert packet.status is EvidenceStatus.PASS
