"""Command-line entry points for the offline VerifAxis vertical slice."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .bench import load_config, run_benchmark
from .models import OpenAICompatibleModel, ReplayModel
from .reporting import canonical_json, load_run, write_report
from .runtime import verify
from .types import Budget
from .verifiers import SafeMathVerifier


def _json_file(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"{source} must be strict JSON; YAML syntax is unsupported") from error
    if not isinstance(value, dict):
        raise ValueError(f"{source} must contain an object")
    return value


def _name(value: Any, *, default: str) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict) and isinstance(value.get("type"), str):
        return str(value["type"])
    return default


def _run_spec(path: str | Path) -> dict[str, Any]:
    spec = _json_file(path)
    allowed = {
        "schema_version",
        "task",
        "model",
        "verifiers",
        "max_iterations",
        "max_model_calls",
        "max_verifier_calls",
        "max_total_tokens",
        "max_wall_time_seconds",
    }
    unknown = set(spec) - allowed
    if unknown:
        raise ValueError(f"unknown run fields: {', '.join(sorted(unknown))}")
    task = spec.get("task")
    if not isinstance(task, str) or not task.strip():
        raise ValueError("run config requires a non-empty task")
    raw_model = spec.get("model", "replay")
    model_name = _name(raw_model, default="replay").lower()
    model: Any
    if model_name in {"replay", "replaymodel"}:
        model = ReplayModel()
    elif model_name in {"openai_compatible", "openai-compatible"}:
        if not isinstance(raw_model, dict):
            raise ValueError("openai_compatible model configuration must be an object")
        model_allowed = {
            "type",
            "model",
            "base_url",
            "api_key_env",
            "timeout_seconds",
            "temperature",
            "max_output_tokens",
        }
        model_unknown = set(raw_model) - model_allowed
        if model_unknown:
            raise ValueError(
                "unknown openai_compatible fields: " + ", ".join(sorted(model_unknown))
            )
        provider_model = raw_model.get("model")
        if not isinstance(provider_model, str) or not provider_model:
            raise ValueError("openai_compatible requires a non-empty model")
        api_key_env = raw_model.get("api_key_env")
        if api_key_env is not None and not isinstance(api_key_env, str):
            raise ValueError("api_key_env must be a string")
        model = OpenAICompatibleModel(
            model=provider_model,
            base_url=str(raw_model.get("base_url", "http://localhost:11434/v1")),
            api_key=os.environ.get(api_key_env) if api_key_env else None,
            timeout_seconds=float(raw_model.get("timeout_seconds", 60.0)),
            temperature=float(raw_model.get("temperature", 0.0)),
            max_output_tokens=(
                None
                if raw_model.get("max_output_tokens") is None
                else int(raw_model["max_output_tokens"])
            ),
        )
    else:
        raise ValueError(f"unsupported model type: {model_name}")
    raw_verifiers = spec.get("verifiers", ["safe_math"])
    if not isinstance(raw_verifiers, list) or not raw_verifiers:
        raise ValueError("verifiers must be a non-empty array")
    verifier_names = [_name(value, default="").lower() for value in raw_verifiers]
    if any(name not in {"safe_math", "safemathverifier"} for name in verifier_names):
        raise ValueError("only the offline safe_math verifier is supported in run configs")
    max_iterations = int(spec.get("max_iterations", 4))
    budget = Budget(
        max_iterations=max_iterations,
        max_model_calls=(
            None if spec.get("max_model_calls") is None else int(spec["max_model_calls"])
        ),
        max_verifier_calls=(
            None if spec.get("max_verifier_calls") is None else int(spec["max_verifier_calls"])
        ),
        max_total_tokens=(
            None if spec.get("max_total_tokens") is None else int(spec["max_total_tokens"])
        ),
        max_wall_time_seconds=(
            None
            if spec.get("max_wall_time_seconds") is None
            else float(spec["max_wall_time_seconds"])
        ),
    )
    result = verify(
        task,
        model,
        [SafeMathVerifier() for _ in verifier_names],
        max_iterations=max_iterations,
        budget=budget,
    )
    return result.to_dict()


def _demo() -> int:
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
    sys.stdout.write(canonical_json(payload))
    return 0 if result.verified else 1


def _run(args: argparse.Namespace) -> int:
    result = _run_spec(args.config)
    rendered = canonical_json(result)
    if args.output is None:
        sys.stdout.write(rendered)
    else:
        target = Path(args.output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rendered, encoding="utf-8", newline="\n")
        sys.stdout.write(f"Wrote trace: {target}\n")
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

    subparsers.add_parser("demo", help="run the deterministic arithmetic smoke demo")

    run_parser = subparsers.add_parser("run", help="run a JSON task config")
    run_parser.add_argument("config", help="path to the run configuration")
    run_parser.add_argument("--output", help="optional JSON trace destination")

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
            return _demo()
        if args.command == "run":
            return _run(args)
        if args.command == "bench":
            return _bench(args)
        if args.command == "report":
            return _report(args)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
