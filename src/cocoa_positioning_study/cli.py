"""Command-line interface for the offline study build."""

from __future__ import annotations

import argparse
from pathlib import Path

from cocoa_positioning_study.pipeline import materialize


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if committed outputs are stale")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="repository root",
    )
    args = parser.parse_args()
    materialize(args.root.resolve(), check=args.check)
    print("derived outputs are current" if args.check else "derived outputs rebuilt")
    return 0
