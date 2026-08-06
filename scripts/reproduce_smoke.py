"""Run the offline smoke benchmark twice and compare canonical outputs."""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

from verifaxis.bench import run_benchmark
from verifaxis.reporting import canonical_json


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("config", nargs="?", default="configs/smoke.json")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="verifaxis-smoke-") as directory:
        first = run_benchmark(args.config, Path(directory) / "first")
        second = run_benchmark(args.config, Path(directory) / "second")
    if canonical_json(first) != canonical_json(second):
        raise SystemExit("smoke benchmark outputs differed")
    print("deterministic smoke benchmark: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
