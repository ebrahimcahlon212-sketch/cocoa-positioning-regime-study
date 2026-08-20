"""Rebuild every derived table, chart and research note offline."""

from __future__ import annotations

import argparse
from pathlib import Path

from render_note import main as render_note
from render_trading_case import main as render_trading_case

from cocoa_positioning_study.evidence import materialize_evidence
from cocoa_positioning_study.fundamentals import materialize_fundamentals
from cocoa_positioning_study.pipeline import materialize
from cocoa_positioning_study.trading_case_pipeline import materialize_trading_case
from cocoa_positioning_study.weather import materialize_weather

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail when retained-source derived tables differ before rendering the note",
    )
    args = parser.parse_args()
    materialize(ROOT, check=args.check)
    materialize_fundamentals(ROOT, check=args.check)
    materialize_weather(ROOT, check=args.check)
    materialize_evidence(ROOT, check=args.check)
    materialize_trading_case(ROOT, check=args.check)
    print("derived outputs are current" if args.check else "derived outputs rebuilt")
    if render_note() != 0:
        return 1
    return render_trading_case()


if __name__ == "__main__":
    raise SystemExit(main())
