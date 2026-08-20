"""Acquire a rights-minimal CFTC history for the public proxy event study.

This script is deliberately separate from the offline reproduction path.  Network
acquisition is an explicit maintainer action; committed factual extracts are the
only inputs used by tests and report builds.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Final, cast
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import source_extracts

ROOT: Final = Path(__file__).resolve().parents[1]
CFTC_DATASET: Final = "https://publicreporting.cftc.gov/resource/72hh-3qpy.json"
CFTC_LANDING_PAGE: Final = (
    "https://www.cftc.gov/MarketReports/CommitmentsofTraders/HistoricalCompressed/index.htm"
)
CFTC_QUERY_FIELDS: Final = (
    "report_date_as_yyyy_mm_dd",
    "cftc_contract_market_code",
    "market_and_exchange_names",
    "open_interest_all",
    "m_money_positions_long_all",
    "m_money_positions_short_all",
    "m_money_positions_spread",
    "contract_units",
    "futonly_or_combined",
)
PUBLIC_FIELDS: Final = (
    "report_date",
    "cftc_contract_market_code",
    "market_and_exchange_names",
    "open_interest_contracts",
    "managed_money_long_contracts",
    "managed_money_short_contracts",
    "managed_money_spread_contracts",
    "contract_units_original",
    "report_type",
    "source_id",
)
PRICE_FIELDS: Final = (
    "original_period_label",
    "period",
    "price_usd_per_kg",
    "endpoint_uses",
    "source_vintage_updated_date",
    "availability_precision",
    "original_series_name",
    "original_unit",
    "provider",
    "underlying_series_attribution",
    "source_id",
)
EXPECTED_SIGNAL_DATES: Final = (
    "2017-02-21",
    "2017-05-30",
    "2017-08-29",
    "2018-01-02",
    "2018-10-16",
    "2019-04-02",
    "2019-09-10",
    "2020-07-21",
    "2021-12-14",
    "2022-07-12",
    "2022-10-11",
    "2025-12-09",
    "2026-06-16",
)

RELEASE_SCHEDULE_FIELDS: Final = (
    "report_date",
    "release_date",
    "release_time",
    "release_timezone",
    "federal_holiday_delay",
    "source_url",
)
SPECIAL_RELEASE_FIELDS: Final = (
    "report_date",
    "release_date",
    "release_time",
    "release_timezone",
    "reason",
    "source_url",
)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _query_url() -> str:
    params = {
        "$select": ",".join(CFTC_QUERY_FIELDS),
        "$where": (
            "cftc_contract_market_code='073732' "
            "AND report_date_as_yyyy_mm_dd>='2009-09-01T00:00:00.000' "
            "AND report_date_as_yyyy_mm_dd<='2026-08-11T00:00:00.000'"
        ),
        "$order": "report_date_as_yyyy_mm_dd",
        "$limit": "5000",
    }
    return f"{CFTC_DATASET}?{urlencode(params)}"


def _download(url: str) -> bytes:
    request = Request(  # noqa: S310 - fixed HTTPS endpoint above
        url,
        headers={"Accept": "application/json", "User-Agent": "cocoa-positioning-study/0.2"},
    )
    with urlopen(request, timeout=60) as response:  # noqa: S310 - fixed HTTPS endpoint above
        if response.status != 200:
            raise RuntimeError(f"CFTC API returned HTTP {response.status}")
        return cast(bytes, response.read())


def _parse_rows(payload: bytes) -> list[dict[str, str]]:
    decoded: Any = json.loads(payload)
    if not isinstance(decoded, list):
        raise ValueError("CFTC response is not a JSON list")
    output: list[dict[str, str]] = []
    seen_dates: set[str] = set()
    for raw in decoded:
        if not isinstance(raw, dict) or set(raw) != set(CFTC_QUERY_FIELDS):
            raise ValueError("CFTC response row has unexpected fields")
        row = {field: str(raw[field]).strip() for field in CFTC_QUERY_FIELDS}
        report_date = row["report_date_as_yyyy_mm_dd"][:10]
        if report_date in seen_dates:
            raise ValueError(f"duplicate CFTC cocoa report date: {report_date}")
        seen_dates.add(report_date)
        if row["cftc_contract_market_code"] != "073732":
            raise ValueError("CFTC response contains a non-cocoa contract")
        if row["futonly_or_combined"] != "FutOnly":
            raise ValueError("CFTC response contains a non-futures-only report")
        for field in (
            "open_interest_all",
            "m_money_positions_long_all",
            "m_money_positions_short_all",
            "m_money_positions_spread",
        ):
            if int(row[field]) < 0:
                raise ValueError(f"CFTC response contains a negative count: {field}")
        output.append(
            {
                "report_date": report_date,
                "cftc_contract_market_code": row["cftc_contract_market_code"],
                "market_and_exchange_names": row["market_and_exchange_names"],
                "open_interest_contracts": row["open_interest_all"],
                "managed_money_long_contracts": row["m_money_positions_long_all"],
                "managed_money_short_contracts": row["m_money_positions_short_all"],
                "managed_money_spread_contracts": row["m_money_positions_spread"],
                "contract_units_original": row["contract_units"],
                "report_type": row["futonly_or_combined"],
                "source_id": "cftc_cocoa_selected_history_2009_2026",
            }
        )
    if len(output) != 885:
        raise ValueError(f"expected 885 CFTC observations, received {len(output)}")
    if output[0]["report_date"] != "2009-09-01":
        raise ValueError("CFTC history does not start at the frozen live-report boundary")
    if output[-1]["report_date"] != "2026-08-11":
        raise ValueError("CFTC history does not end at the study cutoff observation")
    return output


def _csv_bytes(rows: list[dict[str, str]]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=PUBLIC_FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


def _release_overrides() -> dict[date, date]:
    """Load retained official exceptions before applying the ordinary-rule model."""

    overrides: dict[date, date] = {}
    sources = (
        (
            ROOT / "data/raw/cftc-cot-release-schedule-through-2026-08-14.csv",
            RELEASE_SCHEDULE_FIELDS,
        ),
        (
            ROOT / "data/raw/cftc-cot-special-release-facts-2025-2026.csv",
            SPECIAL_RELEASE_FIELDS,
        ),
    )
    for path, fields in sources:
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames != list(fields):
                raise ValueError(f"unexpected retained release columns in {path.name}")
            rows = list(reader)
        if not rows or any(None in row or None in row.values() for row in rows):
            raise ValueError(f"empty or malformed retained release schedule: {path.name}")
        for row in rows:
            if row["release_time"] != "15:30" or row["release_timezone"] != ("America/New_York"):
                raise ValueError(f"unexpected retained release semantics in {path.name}")
            report_date = date.fromisoformat(row["report_date"])
            release_date = date.fromisoformat(row["release_date"])
            if report_date in overrides:
                raise ValueError(f"duplicate retained release override: {report_date}")
            overrides[report_date] = release_date
    return overrides


def _publication_eligibility_utc(
    report_date: date,
    overrides: Mapping[date, date],
) -> datetime:
    """Return retained actual or explicitly rule-modelled 15:30 ET eligibility."""

    release_date = overrides.get(report_date)
    if release_date is None:
        if report_date.weekday() == 1:  # ordinary Tuesday observation
            release_date = report_date + timedelta(days=3)
        elif report_date.weekday() == 0:  # holiday-shifted Monday observation
            release_date = report_date + timedelta(days=4)
        else:
            raise ValueError(f"unexpected CFTC report weekday: {report_date}")

    march_first = date(release_date.year, 3, 1)
    second_sunday_march = march_first + timedelta(days=(6 - march_first.weekday()) % 7 + 7)
    november_first = date(release_date.year, 11, 1)
    first_sunday_november = november_first + timedelta(days=(6 - november_first.weekday()) % 7)
    in_us_daylight_time = second_sunday_march <= release_date < first_sunday_november
    eastern = timezone(timedelta(hours=-4 if in_us_daylight_time else -5))
    return datetime.combine(release_date, time(15, 30), tzinfo=eastern).astimezone(UTC)


@dataclass(frozen=True, slots=True)
class SignalEvent:
    """Report identity plus the timestamp that governs event-window eligibility."""

    report_date: date
    available_at_utc: datetime


def _signal_dates(rows: list[dict[str, str]]) -> list[SignalEvent]:
    """Return frozen signal events while retaining their eligibility timestamps."""

    overrides = _release_overrides()
    observations = [
        (
            report_date,
            _publication_eligibility_utc(report_date, overrides),
            Decimal(
                int(row["managed_money_long_contracts"]) - int(row["managed_money_short_contracts"])
            )
            / Decimal(int(row["open_interest_contracts"])),
        )
        for row in rows
        for report_date in (date.fromisoformat(row["report_date"]),)
    ]
    observations.sort(key=lambda item: item[1])
    availability_times = [available_at for _, available_at, _ in observations]
    if len(availability_times) != len(set(availability_times)):
        raise ValueError("CFTC releases must have unique publication-eligibility timestamps")
    signals: list[SignalEvent] = []
    last_signal_at: datetime | None = None
    for index in range(156, len(observations)):
        prior_values = sorted(value for _, _, value in observations[:index])
        nearest_rank_index = (len(prior_values) + 9) // 10 - 1
        threshold = prior_values[nearest_rank_index]
        _, _, previous = observations[index - 1]
        report_date, available_at, current = observations[index]
        if (
            previous <= threshold
            and current > previous
            and (last_signal_at is None or available_at - last_signal_at >= timedelta(days=91))
        ):
            signals.append(SignalEvent(report_date=report_date, available_at_utc=available_at))
            last_signal_at = available_at
    if tuple(signal.report_date.isoformat() for signal in signals) != EXPECTED_SIGNAL_DATES:
        raise ValueError("current CFTC value snapshot changes the frozen signal-event set")
    return signals


def _add_months(period: str, months: int) -> str:
    year, month = (int(part) for part in period.split("-"))
    zero_based = year * 12 + month - 1 + months
    return f"{zero_based // 12:04d}-{zero_based % 12 + 1:02d}"


def _event_price_extract(workbook_path: Path, signals: list[SignalEvent]) -> bytes:
    with zipfile.ZipFile(workbook_path) as archive:
        shared = source_extracts._xlsx_shared_strings(archive)
        paths = source_extracts._xlsx_sheet_paths(archive)
        cells = source_extracts._xlsx_cells(archive, paths["Monthly Prices"], shared)
    if cells[(1, 1)] != "World Bank Commodity Price Data (The Pink Sheet)":
        raise ValueError("unexpected World Bank workbook title")
    if cells[(4, 1)] != "Updated on August 04, 2026":
        raise ValueError("unexpected World Bank workbook vintage")
    if cells[(5, 12)] != "Cocoa" or cells[(6, 12)] != "($/kg)":
        raise ValueError("unexpected World Bank cocoa series or unit")

    prices: dict[str, str] = {}
    for (row_number, column_number), label in cells.items():
        if column_number != 1 or len(label) != 7 or label[4] != "M":
            continue
        price = cells.get((row_number, 12))
        if price is not None:
            # The workbook applies Excel's built-in 0.00 format to this series. Normalize
            # binary-float XML artifacts such as 2.2599999999999998 to that displayed
            # source precision instead of publishing implementation noise.
            prices[label.replace("M", "-")] = format(Decimal(price).quantize(Decimal("0.01")), "f")

    uses: dict[str, list[tuple[SignalEvent, str]]] = {}
    for signal in signals:
        signal_period = f"{signal.available_at_utc.year:04d}-{signal.available_at_utc.month:02d}"
        for role, offset in (("primary_entry_m_plus_1", 1), ("primary_exit_m_plus_4", 4)):
            endpoint = _add_months(signal_period, offset)
            if endpoint in prices:
                uses.setdefault(endpoint, []).append((signal, role))

    rows: list[dict[str, str]] = []
    for period, period_uses in sorted(uses.items()):
        rows.append(
            {
                "original_period_label": period.replace("-", "M"),
                "period": period,
                "price_usd_per_kg": prices[period],
                "endpoint_uses": ";".join(
                    (
                        f"{signal.report_date.isoformat()}@"
                        f"{signal.available_at_utc.isoformat().replace('+00:00', 'Z')}:"
                        f"{role}"
                    )
                    for signal, role in period_uses
                ),
                "source_vintage_updated_date": "2026-08-04",
                "availability_precision": "date_only_exact_time_not_asserted",
                "original_series_name": "Cocoa",
                "original_unit": "($/kg)",
                "provider": "World Bank Prospects Group",
                "underlying_series_attribution": "International Cocoa Organization (ICCO)",
                "source_id": "world_bank_cocoa_event_endpoints_2026_08",
            }
        )
    if len(rows) != 23:
        raise ValueError(f"expected 23 unique available event endpoints, found {len(rows)}")
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=PRICE_FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


def _load_existing_manifest_record(source_id: str) -> dict[str, str]:
    with (ROOT / "data" / "source_manifest.csv").open(encoding="utf-8", newline="") as handle:
        matches = [row for row in csv.DictReader(handle) if row["source_id"] == source_id]
    if len(matches) != 1:
        raise ValueError(f"expected one existing manifest record for {source_id}")
    return matches[0]


def _manifest_bytes(cftc: dict[str, object], price: dict[str, object]) -> bytes:
    fields = tuple(_load_existing_manifest_record("world_bank_pink_sheet_monthly_august_2026"))
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows((cftc, price))
    return output.getvalue().encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--retrieved-at",
        help="frozen UTC retrieval timestamp; defaults to the current UTC instant",
    )
    args = parser.parse_args()
    retrieved_at = (
        datetime.fromisoformat(args.retrieved_at.replace("Z", "+00:00"))
        if args.retrieved_at
        else datetime.now(UTC)
    )
    if retrieved_at.tzinfo is None or retrieved_at.utcoffset() != datetime.now(UTC).utcoffset():
        raise ValueError("retrieved-at must be timezone-aware UTC")

    source_url = _query_url()
    upstream = _download(source_url)
    rows = _parse_rows(upstream)
    public = _csv_bytes(rows)

    external_path = ROOT / "data" / "external" / "cftc-cocoa-selected-history.json"
    public_path = ROOT / "data" / "raw" / "cftc-cocoa-selected-history-2009-2026.csv"
    price_path = ROOT / "data" / "raw" / "world-bank-cocoa-event-endpoints-2017-2026.csv"
    workbook_path = ROOT / "data" / "external" / "world-bank-pink-sheet-monthly-2026-08.xlsx"
    external_path.parent.mkdir(parents=True, exist_ok=True)
    public_path.parent.mkdir(parents=True, exist_ok=True)
    external_path.write_bytes(upstream)
    public_path.write_bytes(public)

    signals = _signal_dates(rows)
    price_public = _event_price_extract(workbook_path, signals)
    price_path.write_bytes(price_public)

    record: dict[str, object] = {
        "source_id": "cftc_cocoa_selected_history_2009_2026",
        "source_role": "signal_observation_history",
        "provider": "U.S. Commodity Futures Trading Commission",
        "title": "Selected Disaggregated Futures Only cocoa facts, live-report era",
        "source_url": source_url,
        "landing_page_url": CFTC_LANDING_PAGE,
        "public_local_path": public_path.relative_to(ROOT).as_posix(),
        "external_upstream_path": external_path.relative_to(ROOT).as_posix(),
        "retrieved_at_utc": retrieved_at.astimezone(UTC)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
        "upstream_byte_count": len(upstream),
        "upstream_sha256": _sha256(upstream),
        "public_byte_count": len(public),
        "public_sha256": _sha256(public),
        "extract_method": "scripts/acquire_proxy_history.py::selected_cftc_facts",
        "upstream_redistributed": "false",
        "source_effective_period": "2009-09-01 through 2026-08-11",
        "source_availability": (
            "actual schedules where retained; otherwise ordinary Friday 15:30 ET rule-model"
        ),
        "original_unit": "contracts; cocoa contract is 10 metric tonnes",
        "license": "U.S. federal government factual data; public domain",
        "notes": (
            "Current API value snapshot. Historical revisions/reclassifications cannot be "
            "replayed; values are not a full value-vintage archive."
        ),
    }
    existing_world_bank = _load_existing_manifest_record(
        "world_bank_pink_sheet_monthly_august_2026"
    )
    price_record: dict[str, object] = {
        **existing_world_bank,
        "source_id": "world_bank_cocoa_event_endpoints_2026_08",
        "source_role": "public_proxy_event_endpoints",
        "title": "August 2026 Pink Sheet cocoa event-study endpoint facts",
        "public_local_path": price_path.relative_to(ROOT).as_posix(),
        "public_byte_count": len(price_public),
        "public_sha256": _sha256(price_public),
        "extract_method": "scripts/acquire_proxy_history.py::event_endpoint_extract",
        "source_effective_period": "23 unique monthly endpoints for 13 frozen CFTC signals",
        "notes": (
            "Rights-minimal factual extract. Includes only the m+1 and available m+4 monthly "
            "price-proxy endpoints indexed from each signal's publication-eligibility month."
        ),
    }
    manifest_path = ROOT / "data" / "trading_source_manifest.csv"
    manifest_path.write_bytes(_manifest_bytes(record, price_record))
    print(json.dumps({"cftc": record, "world_bank": price_record}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
