"""Command-line interface for the offline study build."""

from __future__ import annotations

import argparse
from pathlib import Path

from cocoa_positioning_study.evidence import materialize_evidence
from cocoa_positioning_study.fundamentals import materialize_fundamentals
from cocoa_positioning_study.pipeline import materialize
from cocoa_positioning_study.trading_case_pipeline import materialize_trading_case
from cocoa_positioning_study.weather import materialize_weather


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
    root = args.root.resolve()
    materialize(root, check=args.check)
    materialize_fundamentals(root, check=args.check)
    materialize_weather(root, check=args.check)
    materialize_evidence(root, check=args.check)
    materialize_trading_case(root, check=args.check)
    print("derived outputs are current" if args.check else "derived outputs rebuilt")
    return 0
