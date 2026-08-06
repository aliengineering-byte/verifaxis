from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from verifaxis.cli import main


def test_demo_is_offline_and_reports_smoke(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["demo"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["label"] == "smoke/demo"
    assert output["initial_answer"] != output["final_answer"]
    assert output["status"] == "VERIFIED"


def test_run_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config = tmp_path / "task.json"
    destination = tmp_path / "trace.json"
    config.write_text(
        json.dumps(
            {
                "task": "What is 12 * 9?",
                "model": "replay",
                "verifiers": ["safe_math"],
                "max_iterations": 3,
            }
        ),
        encoding="utf-8",
    )
    assert main(["run", str(config), "--output", str(destination)]) == 0
    assert json.loads(destination.read_text(encoding="utf-8"))["status"] == "VERIFIED"
    assert "Wrote trace" in capsys.readouterr().out


def test_bench_then_report(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config = tmp_path / "smoke.json"
    run_dir = tmp_path / "run"
    html = tmp_path / "out.html"
    config.write_text(
        json.dumps(
            {
                "seed": 1,
                "arithmetic_tasks": 1,
                "code_tasks": 0,
                "baselines": ["direct", "vcer"],
                "bootstrap_resamples": 10,
            }
        ),
        encoding="utf-8",
    )
    assert main(["bench", "--config", str(config), "--output", str(run_dir)]) == 0
    assert (run_dir / "raw_results.json").is_file()
    capsys.readouterr()
    assert main(["report", str(run_dir), "--format", "html", "--output", str(html)]) == 0
    assert html.read_text(encoding="utf-8").startswith("<!doctype html>")


def test_invalid_json_exits_two(tmp_path: Path) -> None:
    config = tmp_path / "task.json"
    config.write_text("task: no", encoding="utf-8")
    with pytest.raises(SystemExit) as error:
        main(["run", str(config)])
    assert error.value.code == 2


def test_run_openai_compatible_config_against_local_fake_server(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    requests: list[dict[str, object]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers["Content-Length"])
            requests.append(json.loads(self.rfile.read(length)))
            payload = json.dumps(
                {
                    "choices": [{"message": {"content": "108"}}],
                    "usage": {
                        "prompt_tokens": 20,
                        "completion_tokens": 1,
                        "total_tokens": 21,
                    },
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:
            del format, args

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        config = tmp_path / "openai-compatible.json"
        config.write_text(
            json.dumps(
                {
                    "task": "What is 12 * 9?",
                    "model": {
                        "type": "openai_compatible",
                        "model": "fake-model",
                        "base_url": f"http://127.0.0.1:{server.server_port}/v1",
                    },
                    "verifiers": ["safe_math"],
                    "max_iterations": 1,
                }
            ),
            encoding="utf-8",
        )
        assert main(["run", str(config)]) == 0
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "VERIFIED"
    assert output["trace"]["usage"]["total_tokens"] == 21
    assert requests[0]["model"] == "fake-model"
