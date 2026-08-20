"""Acquire official sources and build the rights-minimal public source set.

This is the repository's only network-enabled module. CFTC annual archives
are retained verbatim. Source web pages and the World Bank workbook are kept
only under the ignored ``data/external`` directory, while deterministic factual
extracts are written to ``data/raw`` for offline reproduction.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import sys
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from source_extracts import (
    extract_cftc_2026_schedule,
    extract_cftc_exceptions,
    extract_cftc_methodology,
    extract_world_bank_cocoa,
)

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
EXTERNAL_DIR = ROOT / "data" / "external"
MANIFEST_PATH = ROOT / "data" / "source_manifest.csv"

Extractor = Callable[[bytes, str], bytes]


@dataclass(frozen=True)
class Source:
    source_id: str
    source_role: str
    provider: str
    title: str
    source_url: str
    landing_page_url: str
    public_local_name: str
    external_upstream_name: str | None
    extract_method: str
    extractor: Extractor | None
    license: str
    source_effective_period: str
    source_availability: str
    original_unit: str
    notes: str

    @property
    def upstream_redistributed(self) -> bool:
        return self.extractor is None


SOURCES = (
    Source(
        source_id="cftc_disagg_futures_only_2024",
        source_role="observation_archive",
        provider="U.S. Commodity Futures Trading Commission",
        title="2024 Disaggregated Commitments of Traders - Futures Only",
        source_url="https://www.cftc.gov/files/dea/history/fut_disagg_txt_2024.zip",
        landing_page_url=(
            "https://www.cftc.gov/MarketReports/CommitmentsofTraders/HistoricalCompressed/index.htm"
        ),
        public_local_name="cftc-fut-disagg-2024.zip",
        external_upstream_name=None,
        extract_method="retained_verbatim",
        extractor=None,
        license="U.S. federal government work; public domain",
        source_effective_period="2024",
        source_availability="Tuesday observations; publication timing modeled separately",
        original_unit="contracts; cocoa contract is 10 metric tons",
        notes=(
            "Current annual archive snapshot filtered to market code 073732. The archive may "
            "reflect corrections or reclassifications made before retrieval."
        ),
    ),
    Source(
        source_id="cftc_disagg_futures_only_2025",
        source_role="observation_archive",
        provider="U.S. Commodity Futures Trading Commission",
        title="2025 Disaggregated Commitments of Traders - Futures Only",
        source_url="https://www.cftc.gov/files/dea/history/fut_disagg_txt_2025.zip",
        landing_page_url=(
            "https://www.cftc.gov/MarketReports/CommitmentsofTraders/HistoricalCompressed/index.htm"
        ),
        public_local_name="cftc-fut-disagg-2025.zip",
        external_upstream_name=None,
        extract_method="retained_verbatim",
        extractor=None,
        license="U.S. federal government work; public domain",
        source_effective_period="2025",
        source_availability="Tuesday observations; publication timing modeled separately",
        original_unit="contracts; cocoa contract is 10 metric tons",
        notes=(
            "Current annual archive snapshot filtered to market code 073732. The archive may "
            "reflect corrections or reclassifications made before retrieval."
        ),
    ),
    Source(
        source_id="cftc_disagg_futures_only_2026",
        source_role="observation_archive",
        provider="U.S. Commodity Futures Trading Commission",
        title="2026 Disaggregated Commitments of Traders - Futures Only",
        source_url="https://www.cftc.gov/files/dea/history/fut_disagg_txt_2026.zip",
        landing_page_url=(
            "https://www.cftc.gov/MarketReports/CommitmentsofTraders/HistoricalCompressed/index.htm"
        ),
        public_local_name="cftc-fut-disagg-2026.zip",
        external_upstream_name=None,
        extract_method="retained_verbatim",
        extractor=None,
        license="U.S. federal government work; public domain",
        source_effective_period="2026 year to date through report date 2026-08-11",
        source_availability="Tuesday observations; publication timing modeled separately",
        original_unit="contracts; cocoa contract is 10 metric tons",
        notes=(
            "Current annual archive snapshot filtered to market code 073732. The archive may "
            "reflect corrections or reclassifications made before retrieval."
        ),
    ),
    Source(
        source_id="cftc_cot_methodology_page_2026_08",
        source_role="publication_methodology",
        provider="U.S. Commodity Futures Trading Commission",
        title="COT observation-day and ordinary-publication factual extract",
        source_url="https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm",
        landing_page_url="https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm",
        public_local_name="cftc-cot-publication-methodology-facts-2026-08.json",
        external_upstream_name="cftc-cot-methodology-2026-08.html",
        extract_method="scripts/source_extracts.py::extract_cftc_methodology",
        extractor=extract_cftc_methodology,
        license="U.S. federal government work; public domain",
        source_effective_period="retrieved 2026-08",
        source_availability="Public CFTC web page",
        original_unit="release time in America/New_York",
        notes=(
            "Only a sanitized factual summary is public; the upstream HTML wrapper is not "
            "redistributed."
        ),
    ),
    Source(
        source_id="cftc_cot_release_schedule_2026_08",
        source_role="publication_calendar",
        provider="U.S. Commodity Futures Trading Commission",
        title="COT 2026 report-date/release-date factual extract through 2026-08-14",
        source_url=(
            "https://www.cftc.gov/MarketReports/CommitmentsofTraders/ReleaseSchedule/index.htm"
        ),
        landing_page_url=(
            "https://www.cftc.gov/MarketReports/CommitmentsofTraders/ReleaseSchedule/index.htm"
        ),
        public_local_name="cftc-cot-release-schedule-through-2026-08-14.csv",
        external_upstream_name="cftc-cot-release-schedule-2026-08.html",
        extract_method="scripts/source_extracts.py::extract_cftc_2026_schedule",
        extractor=extract_cftc_2026_schedule,
        license="U.S. federal government work; public domain",
        source_effective_period="2026 report dates through 2026-08-11",
        source_availability="Official release dates at 15:30 America/New_York",
        original_unit="report dates and release dates",
        notes=(
            "Only normalized factual schedule rows are public; the upstream HTML wrapper is not "
            "redistributed."
        ),
    ),
    Source(
        source_id="cftc_cot_special_announcements_2026_08",
        source_role="publication_calendar",
        provider="U.S. Commodity Futures Trading Commission",
        title="COT special-release factual extract for covered 2025 delays",
        source_url=(
            "https://www.cftc.gov/MarketReports/CommitmentsofTraders/"
            "HistoricalSpecialAnnouncements/index.htm"
        ),
        landing_page_url=(
            "https://www.cftc.gov/MarketReports/CommitmentsofTraders/"
            "HistoricalSpecialAnnouncements/index.htm"
        ),
        public_local_name="cftc-cot-special-release-facts-2025-2026.csv",
        external_upstream_name="cftc-cot-special-announcements-2026-08.html",
        extract_method="scripts/source_extracts.py::extract_cftc_exceptions",
        extractor=extract_cftc_exceptions,
        license="U.S. federal government work; public domain",
        source_effective_period=(
            "2025-01-07 delay and final 2025-09-30 through 2025-12-23 catch-up schedule"
        ),
        source_availability="Official release dates at 15:30 America/New_York",
        original_unit="report dates and release dates",
        notes=(
            "Only normalized factual schedule rows are public; the upstream HTML wrapper is not "
            "redistributed. The catch-up schedule extends into January 2026 announcements."
        ),
    ),
    Source(
        source_id="world_bank_pink_sheet_monthly_august_2026",
        source_role="price_factual_extract",
        provider="World Bank Prospects Group",
        title="August 2026 Pink Sheet cocoa factual extract (four selected months)",
        source_url=(
            "https://thedocs.worldbank.org/en/doc/"
            "74e8be41ceb20fa0da750cda2f6b9e4e-0050012026/related/"
            "CMO-Historical-Data-Monthly.xlsx"
        ),
        landing_page_url="https://www.worldbank.org/en/research/commodity-markets",
        public_local_name="world-bank-cocoa-monthly-factual-extract-2026-08.csv",
        external_upstream_name="world-bank-pink-sheet-monthly-2026-08.xlsx",
        extract_method="scripts/source_extracts.py::extract_world_bank_cocoa",
        extractor=extract_world_bank_cocoa,
        license=(
            "World Bank dataset catalog lists CC BY 4.0; cocoa series is attributed to ICCO; "
            "upstream workbook is not relicensed or redistributed"
        ),
        source_effective_period="selected observations 2026-01, 2026-02, 2026-03, and 2026-07",
        source_availability=(
            "August 2026 edition states updated 2026-08-04; exact publication time not asserted"
        ),
        original_unit="nominal U.S. dollars per kilogram for cocoa",
        notes=(
            "Public file is a four-row factual extract sufficient for the Q1-to-July calculation. "
            "The source attributes the cocoa series to the International Cocoa Organization."
        ),
    ),
)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def download(url: str) -> bytes:
    if not url.startswith("https://"):
        raise ValueError(f"refusing non-HTTPS source URL: {url}")
    request = urllib.request.Request(  # noqa: S310 - scheme is restricted above
        url,
        headers={"User-Agent": "cocoa-positioning-regime-study/1.0 (research replication)"},
    )
    with urllib.request.urlopen(request, timeout=90) as response:  # noqa: S310
        payload: bytes = response.read()
        return payload


def _validated_retrieval_time(value: str | None, *, existing_mode: bool) -> str:
    if value is None:
        if existing_mode:
            raise ValueError("--retrieved-at-utc is required with --from-existing-external")
        return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValueError("--retrieved-at-utc must be an explicit UTC timestamp")
    return parsed.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _store_upstream(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() != payload:
        raise RuntimeError(
            f"Refusing to overwrite changed upstream snapshot: {path}. "
            "Archive it under a new name and create a new manifest record."
        )
    if not path.exists():
        path.write_bytes(payload)


def _public_path(source: Source) -> Path:
    return RAW_DIR / source.public_local_name


def _upstream_path(source: Source) -> Path:
    if source.external_upstream_name is None:
        return _public_path(source)
    return EXTERNAL_DIR / source.external_upstream_name


def acquire(*, from_existing_external: bool, retrieved_at_utc: str | None) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    EXTERNAL_DIR.mkdir(parents=True, exist_ok=True)
    retrieved_at = _validated_retrieval_time(retrieved_at_utc, existing_mode=from_existing_external)
    rows: list[dict[str, str | int]] = []

    for source in SOURCES:
        upstream_path = _upstream_path(source)
        if from_existing_external:
            if not upstream_path.is_file():
                raise FileNotFoundError(upstream_path)
            upstream_payload = upstream_path.read_bytes()
        else:
            upstream_payload = download(source.source_url)
            _store_upstream(upstream_path, upstream_payload)

        public_payload = (
            upstream_payload
            if source.extractor is None
            else source.extractor(upstream_payload, source.source_url)
        )
        public_path = _public_path(source)
        if source.extractor is not None:
            public_path.write_bytes(public_payload)

        rows.append(
            {
                "source_id": source.source_id,
                "source_role": source.source_role,
                "provider": source.provider,
                "title": source.title,
                "source_url": source.source_url,
                "landing_page_url": source.landing_page_url,
                "public_local_path": public_path.relative_to(ROOT).as_posix(),
                "external_upstream_path": (
                    upstream_path.relative_to(ROOT).as_posix()
                    if source.external_upstream_name is not None
                    else ""
                ),
                "retrieved_at_utc": retrieved_at,
                "upstream_byte_count": len(upstream_payload),
                "upstream_sha256": sha256_bytes(upstream_payload),
                "public_byte_count": len(public_payload),
                "public_sha256": sha256_bytes(public_payload),
                "extract_method": source.extract_method,
                "upstream_redistributed": str(source.upstream_redistributed).lower(),
                "source_effective_period": source.source_effective_period,
                "source_availability": source.source_availability,
                "original_unit": source.original_unit,
                "license": source.license,
                "notes": source.notes,
            }
        )

    fields = tuple(rows[0])
    with MANIFEST_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--from-existing-external",
        action="store_true",
        help="rebuild extracts from existing local source bytes without network access",
    )
    parser.add_argument(
        "--retrieved-at-utc",
        help="retrieval timestamp to retain in migration mode, for example 2026-08-20T11:22:31Z",
    )
    args = parser.parse_args()
    try:
        acquire(
            from_existing_external=args.from_existing_external,
            retrieved_at_utc=args.retrieved_at_utc,
        )
    except Exception as exc:  # pragma: no cover - acquisition/migration command only
        print(f"acquisition failed: {exc}", file=sys.stderr)
        return 1
    print(f"wrote {MANIFEST_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
