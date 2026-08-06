from __future__ import annotations

import io
import json
from collections.abc import Mapping
from unittest.mock import patch

from verifaxis import Candidate, EvidenceStatus, JSONValue
from verifaxis.models import OpenAICompatibleModel, ReplayModel
from verifaxis.verifiers import SafeMathVerifier


class FakeResponse:
    def __init__(self, value: object) -> None:
        self.buffer = io.BytesIO(json.dumps(value).encode())

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self, size: int) -> bytes:
        return self.buffer.read(size)


def test_replay_repairs_only_after_canonical_independent_failure() -> None:
    model = ReplayModel()
    first = model.generate(task="What is 2 + 2?", state={"evidence": []})
    packet = SafeMathVerifier().verify(task="What is 2 + 2?", candidate=first)
    assert packet.status is EvidenceStatus.FAIL
    second = model.generate(task="What is 2 + 2?", state={"evidence": [packet.to_dict()]})
    assert first.content == "5"
    assert second.content == "4"


def test_replay_ignores_tampered_evidence() -> None:
    model = ReplayModel()
    packet = SafeMathVerifier().verify(task="What is 2 + 2?", candidate=Candidate("5"))
    tampered: dict[str, JSONValue] = packet.to_dict()
    tampered["counterexample"] = {"expected": 999}
    candidate = model.generate(task="What is 2 + 2?", state={"evidence": [tampered]})
    assert candidate.content == "5"


def test_openai_compatible_adapter_parses_text_and_usage() -> None:
    response = FakeResponse(
        {
            "choices": [{"message": {"content": " 42 "}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
        }
    )
    model = OpenAICompatibleModel(model="local", base_url="http://localhost:1234/v1")
    with patch("urllib.request.urlopen", return_value=response) as urlopen:
        candidate = model.generate(task="answer", state={})
    assert candidate == Candidate(
        "42",
        model_id="openai-compatible/local",
        metadata={
            "request_character_count": 302,
            "usage": {
                "input_tokens": 10,
                "output_tokens": 2,
                "total_tokens": 12,
                "cached_tokens": 0,
                "reasoning_tokens": 0,
                "estimated": False,
            },
            "raw_provider_usage": {
                "prompt_tokens": 10,
                "completion_tokens": 2,
                "total_tokens": 12,
            },
        },
    )
    request = urlopen.call_args.args[0]
    assert request.full_url == "http://localhost:1234/v1/chat/completions"


def test_openai_adapter_satisfies_generate_shape() -> None:
    model = ReplayModel()
    state: Mapping[str, JSONValue] = {"evidence": []}
    assert isinstance(model.generate(task="1 + 1", state=state), Candidate)
