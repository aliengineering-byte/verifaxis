from __future__ import annotations

import json
from pathlib import Path

from verifaxis.reporting import build_report, canonical_json, load_run, render_html, write_report


def test_report_is_sorted_and_json_deterministic() -> None:
    rows = [
        {"baseline": "vcer", "example_id": "b", "final_correct": True},
        {"baseline": "direct", "example_id": "a", "final_correct": False},
    ]
    report = build_report(rows, metadata={"seed": 4, "smoke": True})
    assert report["kind"] == "smoke/demo"
    assert report["results"][0]["baseline"] == "direct"
    assert canonical_json(report) == canonical_json(report)


def test_html_escapes_untrusted_fields() -> None:
    report = build_report(
        [
            {
                "baseline": "direct<script>alert(1)</script>",
                "example_id": 'x" onmouseover="bad',
                "final_answer": "<img src=x onerror=bad>",
                "final_correct": False,
            }
        ]
    )
    rendered = render_html(report)
    assert "<script>" not in rendered
    assert "<img src=x" not in rendered
    assert "&lt;script&gt;" in rendered


def test_write_and_load_json_and_html(tmp_path: Path) -> None:
    report = build_report([{"baseline": "direct", "example_id": "1"}])
    json_path = write_report(report, tmp_path / "report.json", format="json")
    html_path = write_report(json_path, tmp_path / "report.html", format="html")
    assert load_run(json_path)["schema_version"] == "2.0"
    assert html_path.read_text(encoding="utf-8").startswith("<!doctype html>")
    assert json.loads(json_path.read_text(encoding="utf-8"))["kind"] == "evaluation"
