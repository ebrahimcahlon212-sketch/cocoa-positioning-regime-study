"""Rebuild the derived analytical outputs, charts and one-page note offline."""

from __future__ import annotations

import argparse
from pathlib import Path

from render_note import main as render_note

from cocoa_positioning_study.pipeline import materialize

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
    print("derived outputs are current" if args.check else "derived outputs rebuilt")
    return render_note()


if __name__ == "__main__":
    raise SystemExit(main())
