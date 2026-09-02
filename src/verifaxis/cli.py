"""Command-line entry points for the offline VerifAxis vertical slice."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from . import __version__
from .bench import load_config, run_benchmark
from .evidence import (
    load_and_validate_claim_evidence_artifact,
    write_claim_evidence_artifact,
)
from .models import ReplayModel
from .reporting import canonical_json, load_run, write_report
from .runtime import verify
from .types import VerificationResult
from .verifiers import SafeMathVerifier


def _json_file(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(
            f"{source} must be JSON (JSON is valid YAML); unsafe YAML features are unsupported"
        ) from error
    if not isinstance(value, dict):
        raise ValueError(f"{source} must contain an object")
    return value


def _name(value: Any, *, default: str) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict) and isinstance(value.get("type"), str):
        return str(value["type"])
    return default


def _run_spec(path: str | Path) -> VerificationResult:
    spec = _json_file(path)
    allowed = {"schema_version", "task", "model", "verifiers", "max_iterations"}
    unknown = set(spec) - allowed
    if unknown:
        raise ValueError(f"unknown run fields: {', '.join(sorted(unknown))}")
    task = spec.get("task")
    if not isinstance(task, str) or not task.strip():
        raise ValueError("run config requires a non-empty task")
    model_name = _name(spec.get("model"), default="replay").lower()
    if model_name not in {"replay", "replaymodel"}:
        raise ValueError(f"unsupported offline model: {model_name}")
    raw_verifiers = spec.get("verifiers", ["safe_math"])
    if not isinstance(raw_verifiers, list) or not raw_verifiers:
        raise ValueError("verifiers must be a non-empty array")
    verifier_names = [_name(value, default="").lower() for value in raw_verifiers]
    if any(name not in {"safe_math", "safemathverifier"} for name in verifier_names):
        raise ValueError("only the offline safe_math verifier is supported in run configs")
    max_iterations = int(spec.get("max_iterations", 4))
    result = verify(
        task,
        ReplayModel(),
        [SafeMathVerifier() for _ in verifier_names],
        max_iterations=max_iterations,
    )
    return result


def _demo(args: argparse.Namespace) -> int:
    task = "What is 197 * 83?"
    result = verify(task, ReplayModel(), [SafeMathVerifier()], max_iterations=4)
    payload = {
        "label": "smoke/demo",
        "task": task,
        "initial_answer": result.trace.steps[0].candidate.content if result.trace.steps else "",
        "final_answer": result.answer,
        "status": result.status.value,
        "iterations": len(result.trace.steps),
        "model_calls": result.trace.model_calls,
        "verifier_calls": result.trace.verifier_calls,
    }
    if args.evidence_output is not None:
        evidence_path = write_claim_evidence_artifact(
            result,
            args.evidence_output,
            producer_version=__version__,
        )
        payload["evidence_artifact"] = str(evidence_path)
    sys.stdout.write(canonical_json(payload))
    return 0 if result.verified else 1


def _run(args: argparse.Namespace) -> int:
    result = _run_spec(args.config)
    payload = result.to_dict()
    if args.evidence_output is not None:
        evidence_path = write_claim_evidence_artifact(
            result,
            args.evidence_output,
            producer_version=__version__,
        )
        payload["evidence_artifact"] = str(evidence_path)
    rendered = canonical_json(payload)
    if args.output is None:
        sys.stdout.write(rendered)
    else:
        target = Path(args.output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rendered, encoding="utf-8", newline="\n")
        sys.stdout.write(f"Wrote trace: {target}\n")
    return 0


def _verify_evidence(args: argparse.Namespace) -> int:
    validation = load_and_validate_claim_evidence_artifact(args.artifact)
    sys.stdout.write(canonical_json(validation))
    return 0


def _bench(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    result = run_benchmark(config, args.output)
    summaries = result["summaries"]
    sys.stdout.write(canonical_json({"kind": "smoke/demo", "summaries": summaries}))
    return 0


def _report(args: argparse.Namespace) -> int:
    source = Path(args.run)
    report = load_run(source)
    suffix = ".html" if args.format == "html" else ".json"
    default_parent = source if source.is_dir() else source.parent
    destination = Path(args.output) if args.output else default_parent / f"report{suffix}"
    write_report(report, destination, format=args.format)
    sys.stdout.write(f"Wrote report: {destination}\n")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="verifaxis",
        description="Think, test, falsify, revise, or abstain using executable evidence.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    demo_parser = subparsers.add_parser("demo", help="run the deterministic arithmetic smoke demo")
    demo_parser.add_argument(
        "--evidence-output", help="optional complete claim/evidence artifact destination"
    )

    run_parser = subparsers.add_parser("run", help="run a JSON-valid YAML task config")
    run_parser.add_argument("config", help="path to the run configuration")
    run_parser.add_argument("--output", help="optional JSON trace destination")
    run_parser.add_argument(
        "--evidence-output", help="optional complete claim/evidence artifact destination"
    )

    verify_evidence_parser = subparsers.add_parser(
        "verify-evidence", help="validate a claim/evidence artifact offline"
    )
    verify_evidence_parser.add_argument("artifact", help="artifact JSON path")

    bench_parser = subparsers.add_parser("bench", help="run deterministic smoke benchmarks")
    bench_parser.add_argument("--config", required=True, help="benchmark configuration path")
    bench_parser.add_argument("--output", default="runs/latest", help="run output directory")

    report_parser = subparsers.add_parser("report", help="render a saved run")
    report_parser.add_argument("run", help="run directory or JSON report")
    report_parser.add_argument("--format", choices=("html", "json"), default="html")
    report_parser.add_argument("--output", help="report destination")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and convert expected user errors into concise exit status 2."""

    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "demo":
            return _demo(args)
        if args.command == "run":
            return _run(args)
        if args.command == "bench":
            return _bench(args)
        if args.command == "report":
            return _report(args)
        if args.command == "verify-evidence":
            return _verify_evidence(args)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
