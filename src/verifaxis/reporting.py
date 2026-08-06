"""Deterministic, dependency-free JSON and HTML benchmark reports."""

from __future__ import annotations

import html
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .metrics import summarize


def canonical_json(value: Any) -> str:
    """Serialize a report in stable, human-readable JSON."""

    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n"


def _safe(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple)):
        value = json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)
    return html.escape(str(value), quote=True)


def build_report(
    rows: Sequence[Mapping[str, Any]],
    *,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the stable report interchange object from raw rows."""

    ordered_rows = sorted(
        (dict(row) for row in rows),
        key=lambda row: (str(row.get("baseline", "")), str(row.get("example_id", ""))),
    )
    by_baseline: dict[str, list[Mapping[str, Any]]] = {}
    for row in ordered_rows:
        by_baseline.setdefault(str(row.get("baseline", "unknown")), []).append(row)
    summaries = {name: summarize(group) for name, group in sorted(by_baseline.items())}
    return {
        "schema_version": "2.0",
        "kind": "smoke/demo" if (metadata or {}).get("smoke", False) else "evaluation",
        "metadata": dict(sorted((metadata or {}).items())),
        "summaries": summaries,
        "results": ordered_rows,
    }


def render_html(report: Mapping[str, Any]) -> str:
    """Render a self-contained report while escaping all untrusted fields."""

    summaries = report.get("summaries", {})
    summary_rows = ""
    if isinstance(summaries, Mapping):
        for baseline, raw_summary in sorted(summaries.items(), key=lambda item: str(item[0])):
            summary = raw_summary if isinstance(raw_summary, Mapping) else {}
            summary_rows += (
                "<tr>"
                f"<td>{_safe(baseline)}</td>"
                f"<td>{_safe(summary.get('examples', 0))}</td>"
                f"<td>{_safe(_format_rate(summary.get('initial_accuracy')))}</td>"
                f"<td>{_safe(_format_rate(summary.get('final_accuracy')))}</td>"
                f"<td>{_safe(_format_rate(summary.get('correction_rate')))}</td>"
                f"<td>{_safe(_format_rate(summary.get('regression_rate')))}</td>"
                f"<td>{_safe(summary.get('total_tokens', 0))}</td>"
                f"<td>{_safe(summary.get('verifier_calls', 0))}</td>"
                "</tr>"
            )

    result_rows = ""
    raw_results = report.get("results", [])
    if isinstance(raw_results, Sequence) and not isinstance(raw_results, (str, bytes)):
        for raw_row in raw_results:
            row = raw_row if isinstance(raw_row, Mapping) else {}
            result_rows += (
                "<tr>"
                f"<td>{_safe(row.get('baseline'))}</td>"
                f"<td>{_safe(row.get('example_id'))}</td>"
                f"<td>{_safe(row.get('fault_kind', 'clean'))}</td>"
                f"<td>{_safe(row.get('fault_applied', False))}</td>"
                f"<td>{_safe(row.get('final_answer'))}</td>"
                f"<td>{_safe(row.get('final_correct'))}</td>"
                f"<td>{_safe(row.get('termination_reason'))}</td>"
                "</tr>"
            )

    title = f"VerifAxis {_safe(report.get('kind', 'evaluation'))} report"
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
:root {{ color-scheme: light dark; font-family: system-ui, sans-serif; }}
body {{ max-width: 1100px; margin: 2rem auto; padding: 0 1rem; }}
table {{ border-collapse: collapse; width: 100%; margin: 1rem 0 2rem; }}
th, td {{ border: 1px solid #8888; padding: .45rem; text-align: left; }}
th {{ background: #8882; }}
code {{ overflow-wrap: anywhere; }}
</style>
</head>
<body>
<h1>{title}</h1>
<p>Schema version: <code>{_safe(report.get("schema_version"))}</code></p>
<h2>Summary</h2>
<table>
<thead><tr><th>Baseline</th><th>N</th><th>Initial accuracy</th><th>Final accuracy</th>
<th>Correction</th><th>Regression</th><th>Tokens</th><th>Verifier calls</th></tr></thead>
<tbody>{summary_rows}</tbody>
</table>
<h2>Per-example results</h2>
<table>
<thead><tr><th>Baseline</th><th>Example</th><th>Fault</th><th>Applied</th>
<th>Final answer</th><th>Correct</th><th>Termination</th></tr></thead>
<tbody>{result_rows}</tbody>
</table>
</body>
</html>
"""


def _format_rate(value: Any) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{float(value):.3f}"
    return ""


def load_run(path: str | Path) -> dict[str, Any]:
    """Load either a report JSON file or a benchmark run directory."""

    source = Path(path)
    if source.is_dir():
        candidates = (source / "report.json", source / "results.json", source / "raw_results.json")
        source = next((candidate for candidate in candidates if candidate.is_file()), source)
    if not source.is_file():
        raise FileNotFoundError(f"no report data found at {source}")
    value = json.loads(source.read_text(encoding="utf-8"))
    if isinstance(value, list):
        return build_report(value)
    if not isinstance(value, dict):
        raise ValueError("report input must contain a JSON object or array")
    if "summaries" not in value and isinstance(value.get("results"), list):
        return build_report(value["results"], metadata=value.get("metadata"))
    return value


def write_report(
    report_or_path: Mapping[str, Any] | str | Path,
    destination: str | Path,
    *,
    format: str = "html",
) -> Path:
    """Write an HTML or JSON report and return its path."""

    report = (
        load_run(report_or_path)
        if isinstance(report_or_path, (str, Path))
        else dict(report_or_path)
    )
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    normalized = format.lower()
    if normalized == "html":
        target.write_text(render_html(report), encoding="utf-8", newline="\n")
    elif normalized == "json":
        target.write_text(canonical_json(report), encoding="utf-8", newline="\n")
    else:
        raise ValueError("format must be 'html' or 'json'")
    return target


generate_report = build_report
