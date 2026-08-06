"""Compare two deterministic VerifAxis smoke-run JSON artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _load(path: Path) -> Any:
    if path.is_dir():
        path = path / "raw_results.json"
    return _without_measurement_noise(json.loads(path.read_text(encoding="utf-8")))


def _without_measurement_noise(value: Any) -> Any:
    """Remove only explicitly nondeterministic measured-duration fields."""

    if isinstance(value, list):
        return [_without_measurement_noise(item) for item in value]
    if isinstance(value, dict):
        return {
            key: _without_measurement_noise(item)
            for key, item in value.items()
            if key not in {"tool_runtime_seconds", "wall_time_seconds"}
        }
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("left", type=Path)
    parser.add_argument("right", type=Path)
    args = parser.parse_args()
    if _load(args.left) != _load(args.right):
        print("deterministic run comparison: FAIL")
        return 1
    print("deterministic run comparison: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
