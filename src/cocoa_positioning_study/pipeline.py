"""Deterministic, offline build for the cocoa positioning regime study."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import zipfile
from calendar import monthrange
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, time, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any, Final

CFTC_CODE: Final = "073732"
STUDY_START: Final = date(2024, 1, 2)
STUDY_CUTOFF_LOCAL: Final = "2026-08-14T15:31:00-04:00"
STUDY_CUTOFF_UTC: Final = datetime(2026, 8, 14, 19, 31, tzinfo=UTC)
WB_VINTAGE_DATE: Final = date(2026, 8, 4)

EXPECTED_CFTC: Final = {
    "managed_money_net_peak": (date(2024, 1, 23), 82_572),
    "managed_money_net_trough": (date(2026, 6, 9), -23_084),
    "latest": (date(2026, 8, 11), -6_667, 190_891),
    "open_interest_peak": (date(2024, 1, 23), 333_669),
    "open_interest_trough": (date(2025, 4, 22), 86_919),
    "managed_money_peak_to_trough_change_contracts": -105_656,
    "managed_money_peak_to_trough_swing_magnitude_contracts": 105_656,
    "managed_money_peak_to_trough_contract_unit_metric_tonnes_change": -1_056_560,
    "managed_money_peak_to_trough_swing_magnitude_contract_unit_metric_tonnes": 1_056_560,
    "managed_money_trough_to_latest_change_contracts": 16_417,
    "latest_open_interest_vs_peak_pct": Decimal("-42.8"),
    "open_interest_peak_to_trough_pct": Decimal("-74.0"),
}

EXPECTED_WB: Final = {
    "average_q1_2026": Decimal("3.93"),
    "july_2026": Decimal("5.61"),
    "july_vs_q1_pct": Decimal("42.6"),
}
EXPECTED_WB_MONTHLY: Final = {
    "2026-01": Decimal("4.97"),
    "2026-02": Decimal("3.59"),
    "2026-03": Decimal("3.24"),
    "2026-07": Decimal("5.61"),
}


@dataclass(frozen=True)
class ManifestRecord:
    source_id: str
    source_role: str
    source_url: str
    public_local_path: str
    external_upstream_path: str
    retrieved_at_utc: str
    upstream_byte_count: int
    upstream_sha256: str
    public_byte_count: int
    public_sha256: str
    extract_method: str
    upstream_redistributed: bool
    original_unit: str
    license: str


@dataclass(frozen=True)
class CftcObservation:
    market_name: str
    cftc_contract_market_code: str
    report_date: date
    report_date_weekday: str
    release_date: date
    release_at_et: str
    available_at_utc: datetime
    availability_basis: str
    availability_source_id: str
    open_interest_contracts: int
    managed_money_long_contracts: int
    managed_money_short_contracts: int
    managed_money_spread_contracts: int
    managed_money_net_contracts: int
    managed_money_net_pct_open_interest: Decimal
    contract_unit_original: str
    source_id: str
    source_upstream_sha256: str
    source_public_sha256: str
    source_retrieved_at_utc: str


@dataclass(frozen=True)
class PriceObservation:
    original_period_label: str
    period: str
    period_start: date
    period_end: date
    price_usd_per_kg: Decimal
    original_series_name: str
    original_unit: str
    series_description: str
    source_vintage_updated_date: date
    source_vintage_available_at_utc: None
    availability_precision: str
    source_id: str
    source_upstream_sha256: str
    source_public_sha256: str


@dataclass(frozen=True)
class StudyData:
    cftc_all: tuple[CftcObservation, ...]
    cftc_visible: tuple[CftcObservation, ...]
    prices: tuple[PriceObservation, ...]
    summary: dict[str, Any]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest(root: Path) -> dict[str, ManifestRecord]:
    path = root / "data" / "source_manifest.csv"
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError("source manifest is empty")

    manifest: dict[str, ManifestRecord] = {}
    for raw in rows:
        record = ManifestRecord(
            source_id=raw["source_id"],
            source_role=raw["source_role"],
            source_url=raw["source_url"],
            public_local_path=raw["public_local_path"],
            external_upstream_path=raw["external_upstream_path"],
            retrieved_at_utc=raw["retrieved_at_utc"],
            upstream_byte_count=int(raw["upstream_byte_count"]),
            upstream_sha256=raw["upstream_sha256"],
            public_byte_count=int(raw["public_byte_count"]),
            public_sha256=raw["public_sha256"],
            extract_method=raw["extract_method"],
            upstream_redistributed={"true": True, "false": False}[raw["upstream_redistributed"]],
            original_unit=raw["original_unit"],
            license=raw["license"],
        )
        retrieved_at = datetime.fromisoformat(record.retrieved_at_utc.replace("Z", "+00:00"))
        if retrieved_at.tzinfo is None or retrieved_at.utcoffset() != timedelta(0):
            raise ValueError(f"retrieval timestamp is not UTC: {record.source_id}")
        if not record.source_url.startswith("https://"):
            raise ValueError(f"source URL is not HTTPS: {record.source_id}")
        for label, fingerprint in (
            ("upstream", record.upstream_sha256),
            ("public", record.public_sha256),
        ):
            if re.fullmatch(r"[0-9a-f]{64}", fingerprint) is None:
                raise ValueError(f"invalid {label} SHA-256 in manifest: {record.source_id}")
        if record.source_id in manifest:
            raise ValueError(f"duplicate source id: {record.source_id}")
        source_path = root / record.public_local_path
        if not source_path.resolve().is_relative_to(root.resolve()):
            raise ValueError(f"public source path escapes repository: {record.source_id}")
        if not source_path.is_file():
            raise FileNotFoundError(source_path)
        if source_path.stat().st_size != record.public_byte_count:
            raise ValueError(f"public byte-count mismatch for {record.source_id}")
        if _sha256(source_path) != record.public_sha256:
            raise ValueError(f"public SHA-256 mismatch for {record.source_id}")
        if record.upstream_byte_count <= 0 or record.public_byte_count <= 0:
            raise ValueError(f"non-positive source byte count: {record.source_id}")
        if record.upstream_redistributed:
            if record.external_upstream_path or record.extract_method != "retained_verbatim":
                raise ValueError(f"invalid retained-source metadata: {record.source_id}")
            if (
                record.upstream_byte_count != record.public_byte_count
                or record.upstream_sha256 != record.public_sha256
            ):
                raise ValueError(f"retained source differs from upstream: {record.source_id}")
        else:
            if not record.external_upstream_path or record.extract_method == "retained_verbatim":
                raise ValueError(f"invalid extracted-source metadata: {record.source_id}")
            if source_path.suffix.lower() in {".html", ".htm", ".xlsx"}:
                raise ValueError(
                    f"non-minimal source is present in public data: {record.source_id}"
                )
        manifest[record.source_id] = record
    return manifest


def _source_path(root: Path, manifest: dict[str, ManifestRecord], source_id: str) -> Path:
    try:
        return root / manifest[source_id].public_local_path
    except KeyError as exc:
        raise ValueError(f"missing source manifest entry: {source_id}") from exc


def _csv_extract_rows(payload: bytes, fields: tuple[str, ...]) -> list[dict[str, str]]:
    table = list(csv.reader(io.StringIO(payload.decode("utf-8"))))
    if not table or table[0] != list(fields):
        raise ValueError("factual extract has unexpected columns")
    rows: list[dict[str, str]] = []
    for raw in table[1:]:
        if len(raw) != len(fields):
            raise ValueError("factual extract has a malformed row")
        rows.append(dict(zip(fields, raw, strict=True)))
    if not rows:
        raise ValueError("factual extract is empty")
    return rows


def _validate_release_fields(row: dict[str, str], source_url: str) -> None:
    if row["release_time"] != "15:30" or row["release_timezone"] != "America/New_York":
        raise ValueError("release extract has unexpected time semantics")
    if row["source_url"] != source_url:
        raise ValueError("release extract source URL disagrees with manifest")


def _parse_special_release_schedule(payload: bytes, source_url: str) -> dict[date, date]:
    fields = (
        "report_date",
        "release_date",
        "release_time",
        "release_timezone",
        "reason",
        "source_url",
    )
    parsed: dict[date, date] = {}
    for row in _csv_extract_rows(payload, fields):
        _validate_release_fields(row, source_url)
        report = date.fromisoformat(row["report_date"])
        release = date.fromisoformat(row["release_date"])
        if report in parsed:
            raise ValueError(f"duplicate special-release report date: {report}")
        parsed[report] = release

    expected = {
        date(2025, 1, 7): date(2025, 1, 13),
        date(2025, 9, 30): date(2025, 11, 19),
        date(2025, 10, 7): date(2025, 11, 21),
        date(2025, 10, 14): date(2025, 11, 25),
        date(2025, 10, 21): date(2025, 12, 2),
        date(2025, 10, 28): date(2025, 12, 5),
        date(2025, 11, 4): date(2025, 12, 9),
        date(2025, 11, 10): date(2025, 12, 10),
        date(2025, 11, 18): date(2025, 12, 12),
        date(2025, 11, 25): date(2025, 12, 15),
        date(2025, 12, 2): date(2025, 12, 17),
        date(2025, 12, 9): date(2025, 12, 19),
        date(2025, 12, 16): date(2025, 12, 23),
        date(2025, 12, 23): date(2025, 12, 29),
    }
    if parsed != expected:
        raise ValueError("official CFTC special-release extract does not match expected dates")
    return parsed


def _parse_2026_schedule(payload: bytes, source_url: str) -> dict[date, date]:
    fields = (
        "report_date",
        "release_date",
        "release_time",
        "release_timezone",
        "federal_holiday_delay",
        "source_url",
    )
    parsed: dict[date, date] = {}
    for row in _csv_extract_rows(payload, fields):
        _validate_release_fields(row, source_url)
        if row["federal_holiday_delay"] not in {"true", "false"}:
            raise ValueError("2026 release extract has invalid holiday-delay flag")
        report = date.fromisoformat(row["report_date"])
        release = date.fromisoformat(row["release_date"])
        if report in parsed:
            raise ValueError(f"duplicate 2026 report date: {report}")
        parsed[report] = release

    expected_through_cutoff = (
        date(2026, 1, 5),
        date(2026, 1, 9),
        date(2026, 1, 16),
        date(2026, 1, 23),
        date(2026, 1, 30),
        date(2026, 2, 6),
        date(2026, 2, 13),
        date(2026, 2, 20),
        date(2026, 2, 27),
        date(2026, 3, 6),
        date(2026, 3, 13),
        date(2026, 3, 20),
        date(2026, 3, 27),
        date(2026, 4, 3),
        date(2026, 4, 10),
        date(2026, 4, 17),
        date(2026, 4, 24),
        date(2026, 5, 1),
        date(2026, 5, 8),
        date(2026, 5, 15),
        date(2026, 5, 22),
        date(2026, 5, 29),
        date(2026, 6, 5),
        date(2026, 6, 12),
        date(2026, 6, 22),
        date(2026, 6, 26),
        date(2026, 7, 6),
        date(2026, 7, 10),
        date(2026, 7, 17),
        date(2026, 7, 24),
        date(2026, 7, 31),
        date(2026, 8, 7),
        date(2026, 8, 14),
    )
    expected = {_report_date_for_release(release): release for release in expected_through_cutoff}
    if parsed != expected:
        raise ValueError("official CFTC 2026 release schedule does not match expected dates")
    return parsed


def _report_date_for_release(release_date: date) -> date:
    if release_date.weekday() == 0:  # delayed Monday publication
        return release_date - timedelta(days=6)
    if release_date.weekday() == 4:  # ordinary Friday publication
        return release_date - timedelta(days=3)
    raise ValueError(f"unexpected official release weekday: {release_date}")


def _second_sunday_in_march(year: int) -> date:
    first = date(year, 3, 1)
    return first + timedelta(days=(6 - first.weekday()) % 7 + 7)


def _first_sunday_in_november(year: int) -> date:
    first = date(year, 11, 1)
    return first + timedelta(days=(6 - first.weekday()) % 7)


def _eastern_release_datetimes(release_date: date) -> tuple[str, datetime]:
    in_dst = (
        _second_sunday_in_march(release_date.year)
        <= release_date
        < _first_sunday_in_november(release_date.year)
    )
    offset = timezone(timedelta(hours=-4 if in_dst else -5))
    local = datetime.combine(release_date, time(15, 30), tzinfo=offset)
    local_text = local.isoformat()
    return local_text, local.astimezone(UTC)


def _release_semantics(
    report_date: date,
    special_releases: dict[date, date],
    official_2026: dict[date, date],
) -> tuple[date, str, str]:
    if report_date in special_releases:
        return (
            special_releases[report_date],
            (
                "cftc_official_special_announcement"
                if report_date == date(2025, 1, 7)
                else "cftc_official_appropriations_catch_up"
            ),
            "cftc_cot_special_announcements_2026_08",
        )
    if report_date in official_2026:
        return (
            official_2026[report_date],
            "cftc_official_2026_schedule",
            "cftc_cot_release_schedule_2026_08",
        )
    if report_date.weekday() != 1:
        raise ValueError(f"unmapped non-Tuesday CFTC report date: {report_date}")
    return (
        report_date + timedelta(days=3),
        "cftc_ordinary_rule_estimate_not_holiday_verified",
        "cftc_cot_methodology_page_2026_08",
    )


def _parse_int(raw: dict[str, str], field: str) -> int:
    try:
        return int(raw[field].strip())
    except (KeyError, ValueError) as exc:
        raise ValueError(f"invalid CFTC integer field {field!r}: {raw.get(field)!r}") from exc


def load_cftc_observations(
    root: Path, manifest: dict[str, ManifestRecord]
) -> tuple[CftcObservation, ...]:
    methodology_id = "cftc_cot_methodology_page_2026_08"
    methodology_record = manifest[methodology_id]
    methodology: Any = json.loads(_source_path(root, manifest, methodology_id).read_text("utf-8"))
    expected_methodology = {
        "extract_scope": "sanitized factual summary; upstream HTML wrapper is not redistributed",
        "observation_day": "Tuesday",
        "ordinary_release_day": "Friday",
        "release_time": "15:30",
        "release_timezone": "America/New_York",
        "source_url": methodology_record.source_url,
    }
    if methodology != expected_methodology:
        raise ValueError("CFTC methodology factual extract disagrees with expected semantics")

    special_id = "cftc_cot_special_announcements_2026_08"
    special_record = manifest[special_id]
    special_releases = _parse_special_release_schedule(
        _source_path(root, manifest, special_id).read_bytes(), special_record.source_url
    )

    schedule_id = "cftc_cot_release_schedule_2026_08"
    schedule_record = manifest[schedule_id]
    official_2026 = _parse_2026_schedule(
        _source_path(root, manifest, schedule_id).read_bytes(), schedule_record.source_url
    )

    required = {
        "Market_and_Exchange_Names",
        "Report_Date_as_YYYY-MM-DD",
        "CFTC_Contract_Market_Code",
        "Open_Interest_All",
        "M_Money_Positions_Long_All",
        "M_Money_Positions_Short_All",
        "M_Money_Positions_Spread_All",
        "Tot_Rept_Positions_Long_All",
        "Tot_Rept_Positions_Short_All",
        "NonRept_Positions_Long_All",
        "NonRept_Positions_Short_All",
        "Contract_Units",
        "FutOnly_or_Combined",
    }
    observations: list[CftcObservation] = []
    for year in (2024, 2025, 2026):
        source_id = f"cftc_disagg_futures_only_{year}"
        record = manifest[source_id]
        path = root / record.public_local_path
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            if names != ["f_year.txt"]:
                raise ValueError(f"unexpected archive members in {source_id}: {names}")
            with archive.open("f_year.txt") as binary:
                with io.TextIOWrapper(binary, encoding="utf-8-sig", newline="") as text:
                    reader = csv.DictReader(text)
                    if reader.fieldnames is None or not required.issubset(reader.fieldnames):
                        raise ValueError(f"missing required CFTC columns in {source_id}")
                    for raw in reader:
                        if raw["CFTC_Contract_Market_Code"].strip() != CFTC_CODE:
                            continue
                        if raw["FutOnly_or_Combined"].strip() != "FutOnly":
                            raise ValueError("non-futures-only record in futures-only archive")
                        report_date = date.fromisoformat(raw["Report_Date_as_YYYY-MM-DD"].strip())
                        if report_date < STUDY_START:
                            continue
                        open_interest = _parse_int(raw, "Open_Interest_All")
                        total_long = _parse_int(raw, "Tot_Rept_Positions_Long_All")
                        total_short = _parse_int(raw, "Tot_Rept_Positions_Short_All")
                        nonreportable_long = _parse_int(raw, "NonRept_Positions_Long_All")
                        nonreportable_short = _parse_int(raw, "NonRept_Positions_Short_All")
                        if total_long + nonreportable_long != open_interest:
                            raise ValueError(f"CFTC long-side identity failed for {report_date}")
                        if total_short + nonreportable_short != open_interest:
                            raise ValueError(f"CFTC short-side identity failed for {report_date}")
                        mm_long = _parse_int(raw, "M_Money_Positions_Long_All")
                        mm_short = _parse_int(raw, "M_Money_Positions_Short_All")
                        mm_spread = _parse_int(raw, "M_Money_Positions_Spread_All")
                        release_date, basis, availability_source = _release_semantics(
                            report_date, special_releases, official_2026
                        )
                        release_at_et, available_at_utc = _eastern_release_datetimes(release_date)
                        contract_unit = raw["Contract_Units"].strip()
                        if contract_unit != "(CONTRACTS OF 10 METRIC TONS)":
                            raise ValueError(f"unexpected cocoa contract unit: {contract_unit}")
                        observations.append(
                            CftcObservation(
                                market_name=raw["Market_and_Exchange_Names"].strip(),
                                cftc_contract_market_code=CFTC_CODE,
                                report_date=report_date,
                                report_date_weekday=report_date.strftime("%A"),
                                release_date=release_date,
                                release_at_et=release_at_et,
                                available_at_utc=available_at_utc,
                                availability_basis=basis,
                                availability_source_id=availability_source,
                                open_interest_contracts=open_interest,
                                managed_money_long_contracts=mm_long,
                                managed_money_short_contracts=mm_short,
                                managed_money_spread_contracts=mm_spread,
                                managed_money_net_contracts=mm_long - mm_short,
                                managed_money_net_pct_open_interest=(
                                    Decimal(mm_long - mm_short)
                                    / Decimal(open_interest)
                                    * Decimal(100)
                                ),
                                contract_unit_original=contract_unit,
                                source_id=source_id,
                                source_upstream_sha256=record.upstream_sha256,
                                source_public_sha256=record.public_sha256,
                                source_retrieved_at_utc=record.retrieved_at_utc,
                            )
                        )

    observations.sort(key=lambda item: item.report_date)
    dates = [item.report_date for item in observations]
    if len(dates) != len(set(dates)):
        raise ValueError("duplicate CFTC cocoa report dates")
    if len(observations) != 137 or dates[0] != STUDY_START or dates[-1] != date(2026, 8, 11):
        raise ValueError("unexpected CFTC cocoa study coverage")
    return tuple(observations)


def visible_as_of(
    observations: Iterable[CftcObservation], cutoff_utc: datetime
) -> tuple[CftcObservation, ...]:
    if cutoff_utc.tzinfo is None:
        raise ValueError("cutoff must be timezone-aware")
    normalized = cutoff_utc.astimezone(UTC)
    return tuple(item for item in observations if item.available_at_utc <= normalized)


def load_price_observations(
    root: Path, manifest: dict[str, ManifestRecord]
) -> tuple[PriceObservation, ...]:
    source_id = "world_bank_pink_sheet_monthly_august_2026"
    record = manifest[source_id]
    fields = (
        "original_period_label",
        "period",
        "price_usd_per_kg",
        "original_series_name",
        "original_unit",
        "source_vintage_updated_date",
        "availability_precision",
        "provider",
        "underlying_series_attribution",
        "source_url",
    )
    rows = _csv_extract_rows(_source_path(root, manifest, source_id).read_bytes(), fields)

    prices: list[PriceObservation] = []
    for row in rows:
        label = row["original_period_label"]
        period = row["period"]
        if label != f"{period[:4]}M{period[-2:]}":
            raise ValueError(f"period labels disagree in World Bank extract: {label}")
        if row["original_series_name"] != "Cocoa" or row["original_unit"] != "($/kg)":
            raise ValueError("unexpected World Bank cocoa series or unit")
        if row["source_vintage_updated_date"] != WB_VINTAGE_DATE.isoformat():
            raise ValueError("unexpected World Bank source vintage")
        if row["availability_precision"] != "date_only_exact_time_not_asserted":
            raise ValueError("unexpected World Bank availability precision")
        if row["provider"] != "World Bank Prospects Group":
            raise ValueError("unexpected World Bank extract provider")
        if row["underlying_series_attribution"] != "International Cocoa Organization (ICCO)":
            raise ValueError("World Bank extract is missing ICCO attribution")
        if row["source_url"] != record.source_url:
            raise ValueError("World Bank extract source URL disagrees with manifest")
        year, month = (int(value) for value in period.split("-"))
        start = date(year, month, 1)
        end = date(year, month, monthrange(year, month)[1])
        prices.append(
            PriceObservation(
                original_period_label=label,
                period=period,
                period_start=start,
                period_end=end,
                price_usd_per_kg=Decimal(row["price_usd_per_kg"]),
                original_series_name=row["original_series_name"],
                original_unit=row["original_unit"],
                series_description=(
                    "Cocoa; underlying series attributed to " + row["underlying_series_attribution"]
                ),
                source_vintage_updated_date=WB_VINTAGE_DATE,
                source_vintage_available_at_utc=None,
                availability_precision=row["availability_precision"],
                source_id=source_id,
                source_upstream_sha256=record.upstream_sha256,
                source_public_sha256=record.public_sha256,
            )
        )
    prices.sort(key=lambda item: item.period)
    by_period = {item.period: item.price_usd_per_kg for item in prices}
    if len(prices) != len(by_period) or by_period != EXPECTED_WB_MONTHLY:
        raise ValueError("unexpected World Bank cocoa price coverage")
    return tuple(prices)


def _mean(values: Iterable[Decimal]) -> Decimal:
    items = tuple(values)
    if not items:
        raise ValueError("cannot average an empty sequence")
    return sum(items, Decimal(0)) / Decimal(len(items))


def _round(value: Decimal, places: str) -> Decimal:
    return value.quantize(Decimal(places), rounding=ROUND_HALF_UP)


def _iso_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _cftc_snapshot(item: CftcObservation) -> dict[str, Any]:
    return {
        "report_date": item.report_date.isoformat(),
        "release_at_et": item.release_at_et,
        "available_at_utc": _iso_utc(item.available_at_utc),
        "availability_basis": item.availability_basis,
        "managed_money_net_contracts": item.managed_money_net_contracts,
        "open_interest_contracts": item.open_interest_contracts,
    }


def _assert_headlines(
    visible: tuple[CftcObservation, ...], prices: tuple[PriceObservation, ...]
) -> dict[str, Any]:
    mm_peak = max(visible, key=lambda item: item.managed_money_net_contracts)
    mm_trough = min(visible, key=lambda item: item.managed_money_net_contracts)
    oi_peak = max(visible, key=lambda item: item.open_interest_contracts)
    oi_trough = min(visible, key=lambda item: item.open_interest_contracts)
    latest = visible[-1]

    if (mm_peak.report_date, mm_peak.managed_money_net_contracts) != EXPECTED_CFTC[
        "managed_money_net_peak"
    ]:
        raise ValueError("CFTC managed-money peak disagrees with expected source result")
    if (mm_trough.report_date, mm_trough.managed_money_net_contracts) != EXPECTED_CFTC[
        "managed_money_net_trough"
    ]:
        raise ValueError("CFTC managed-money trough disagrees with expected source result")
    if (latest.report_date, latest.managed_money_net_contracts, latest.open_interest_contracts) != (
        EXPECTED_CFTC["latest"]
    ):
        raise ValueError("CFTC latest observation disagrees with expected source result")
    if (oi_peak.report_date, oi_peak.open_interest_contracts) != EXPECTED_CFTC[
        "open_interest_peak"
    ]:
        raise ValueError("CFTC open-interest peak disagrees with expected source result")
    if (oi_trough.report_date, oi_trough.open_interest_contracts) != EXPECTED_CFTC[
        "open_interest_trough"
    ]:
        raise ValueError("CFTC open-interest trough disagrees with expected source result")

    by_period = {item.period: item.price_usd_per_kg for item in prices}
    q1_2026_raw = _mean(by_period[period] for period in ("2026-01", "2026-02", "2026-03"))
    q1_2026 = _round(q1_2026_raw, "0.01")
    july_2026 = by_period["2026-07"]
    july_vs_q1_full_precision = (july_2026 / q1_2026_raw - Decimal(1)) * Decimal(100)
    july_vs_q1 = _round(july_vs_q1_full_precision, "0.1")
    results = {
        "average_q1_2026": q1_2026,
        "average_q1_2026_unrounded": q1_2026_raw,
        "july_2026": july_2026,
        "july_vs_q1_full_precision_pct": july_vs_q1_full_precision,
        "july_vs_q1_pct": july_vs_q1,
    }
    for key, expected in EXPECTED_WB.items():
        if results[key] != expected:
            raise ValueError(f"World Bank result {key} disagrees with expected source result")

    mm_peak_to_trough = mm_trough.managed_money_net_contracts - mm_peak.managed_money_net_contracts
    mm_peak_to_trough_tonnes = mm_peak_to_trough * 10
    mm_trough_to_latest = latest.managed_money_net_contracts - mm_trough.managed_money_net_contracts
    latest_oi_vs_peak = _round(
        (
            Decimal(latest.open_interest_contracts) / Decimal(oi_peak.open_interest_contracts)
            - Decimal(1)
        )
        * Decimal(100),
        "0.1",
    )
    oi_compression = _round(
        (
            Decimal(oi_trough.open_interest_contracts) / Decimal(oi_peak.open_interest_contracts)
            - Decimal(1)
        )
        * Decimal(100),
        "0.1",
    )
    change_results = {
        "managed_money_peak_to_trough_change_contracts": mm_peak_to_trough,
        "managed_money_peak_to_trough_swing_magnitude_contracts": abs(mm_peak_to_trough),
        "managed_money_peak_to_trough_contract_unit_metric_tonnes_change": mm_peak_to_trough_tonnes,
        "managed_money_peak_to_trough_swing_magnitude_contract_unit_metric_tonnes": abs(
            mm_peak_to_trough_tonnes
        ),
        "managed_money_trough_to_latest_change_contracts": mm_trough_to_latest,
        "latest_open_interest_vs_peak_pct": latest_oi_vs_peak,
        "open_interest_peak_to_trough_pct": oi_compression,
    }
    for key, value in change_results.items():
        if value != EXPECTED_CFTC[key]:
            raise ValueError(f"CFTC headline change {key} disagrees with expected source result")
    return {
        "managed_money_net_peak": _cftc_snapshot(mm_peak),
        "managed_money_net_trough": _cftc_snapshot(mm_trough),
        "latest_cftc": _cftc_snapshot(latest),
        "open_interest_peak": _cftc_snapshot(oi_peak),
        "open_interest_trough": _cftc_snapshot(oi_trough),
        "changes": {
            "managed_money_peak_to_trough_change_contracts": mm_peak_to_trough,
            "managed_money_peak_to_trough_swing_magnitude_contracts": abs(mm_peak_to_trough),
            "managed_money_peak_to_trough_contract_unit_metric_tonnes_change": (
                mm_peak_to_trough_tonnes
            ),
            "managed_money_peak_to_trough_swing_magnitude_contract_unit_metric_tonnes": abs(
                mm_peak_to_trough_tonnes
            ),
            "managed_money_trough_to_latest_change_contracts": mm_trough_to_latest,
            "latest_open_interest_vs_peak_pct": float(latest_oi_vs_peak),
            "open_interest_peak_to_trough_pct": float(oi_compression),
        },
        "price": {key: float(_round(value, "0.0001")) for key, value in results.items()},
    }


def assemble_study(root: Path) -> StudyData:
    manifest = load_manifest(root)
    cftc_all = load_cftc_observations(root, manifest)
    cftc_visible = visible_as_of(cftc_all, STUDY_CUTOFF_UTC)
    prices = load_price_observations(root, manifest)
    findings = _assert_headlines(cftc_visible, prices)
    summary: dict[str, Any] = {
        "study": "Cocoa Positioning Regime Study",
        "market": "Cocoa - ICE Futures U.S.",
        "cftc_contract_market_code": CFTC_CODE,
        "cutoff": {
            "local": STUDY_CUTOFF_LOCAL,
            "timezone": "America/New_York",
            "utc": _iso_utc(STUDY_CUTOFF_UTC),
            "rule": "include only records with available_at_utc less than or equal to cutoff",
        },
        "coverage": {
            "cftc_first_report_date": cftc_visible[0].report_date.isoformat(),
            "cftc_last_report_date": cftc_visible[-1].report_date.isoformat(),
            "cftc_observation_count": len(cftc_visible),
            "world_bank_first_period": prices[0].period,
            "world_bank_last_period": prices[-1].period,
            "world_bank_observation_count": len(prices),
        },
        "availability_notes": {
            "cftc": (
                "Tuesday report dates are separated from publication. Exact official dates are used "
                "for the 2025 appropriation-lapse catch-up and the covered 2026 schedule; ordinary "
                "2024 weeks and uncovered 2025 weeks are explicitly labelled rule-based estimates "
                "because CFTC does not publish a complete historical release-date list. The values "
                "come from annual compressed archive snapshots retrieved on 2026-08-20 and tied to "
                "their hashes; those archives can contain later corrections or reclassifications. "
                "This models release-time eligibility, not a complete value-revision vintage history, "
                "which would require retained weekly snapshots."
            ),
            "world_bank": (
                "The retained four-row factual extract comes from the August 2026 workbook, which "
                "states Updated on August 04, 2026. Its exact publication time is not asserted, so "
                "availability precision remains date-only. The full upstream workbook is not "
                "redistributed; its URL, retrieval timestamp, byte count, and SHA-256 remain in the "
                "manifest alongside the public extract fingerprint."
            ),
        },
        "findings": findings,
        "sources": [
            {
                "source_id": record.source_id,
                "source_role": record.source_role,
                "source_url": record.source_url,
                "retrieved_at_utc": record.retrieved_at_utc,
                "upstream_byte_count": record.upstream_byte_count,
                "upstream_sha256": record.upstream_sha256,
                "public_byte_count": record.public_byte_count,
                "public_sha256": record.public_sha256,
                "extract_method": record.extract_method,
                "upstream_redistributed": record.upstream_redistributed,
                "external_upstream_path": record.external_upstream_path,
                "original_unit": record.original_unit,
                "license": record.license,
            }
            for record in sorted(manifest.values(), key=lambda item: item.source_id)
        ],
        "interpretation_limits": [
            "Managed Money is a CFTC trader classification, not a synonym for all speculators.",
            "Open interest and positions are contracts; each cocoa contract is 10 metric tons.",
            "The World Bank factual extract is a monthly nominal USD/kg benchmark attributed in the source workbook to ICCO.",
            "This is a descriptive regime audit, not a return backtest, consensus-surprise study, or trade instruction.",
        ],
    }
    return StudyData(cftc_all=cftc_all, cftc_visible=cftc_visible, prices=prices, summary=summary)


def _cftc_csv(observations: tuple[CftcObservation, ...]) -> bytes:
    output = io.StringIO(newline="")
    fields = (
        "market_name",
        "cftc_contract_market_code",
        "report_date",
        "report_date_weekday",
        "release_date",
        "release_at_et",
        "available_at_utc",
        "availability_basis",
        "availability_source_id",
        "open_interest_contracts",
        "managed_money_long_contracts",
        "managed_money_short_contracts",
        "managed_money_spread_contracts",
        "managed_money_net_contracts",
        "managed_money_net_pct_open_interest",
        "contract_unit_original",
        "source_id",
        "source_upstream_sha256",
        "source_public_sha256",
        "source_retrieved_at_utc",
    )
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for item in observations:
        raw = asdict(item)
        raw["report_date"] = item.report_date.isoformat()
        raw["release_date"] = item.release_date.isoformat()
        raw["available_at_utc"] = _iso_utc(item.available_at_utc)
        raw["managed_money_net_pct_open_interest"] = str(
            _round(item.managed_money_net_pct_open_interest, "0.0001")
        )
        writer.writerow(raw)
    return output.getvalue().encode("utf-8")


def _price_csv(prices: tuple[PriceObservation, ...]) -> bytes:
    output = io.StringIO(newline="")
    fields = (
        "original_period_label",
        "period",
        "period_start",
        "period_end",
        "price_usd_per_kg",
        "original_series_name",
        "original_unit",
        "series_description",
        "source_vintage_updated_date",
        "source_vintage_available_at_utc",
        "availability_precision",
        "source_id",
        "source_upstream_sha256",
        "source_public_sha256",
    )
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for item in prices:
        raw = asdict(item)
        raw["period_start"] = item.period_start.isoformat()
        raw["period_end"] = item.period_end.isoformat()
        raw["price_usd_per_kg"] = f"{item.price_usd_per_kg:.2f}"
        raw["source_vintage_updated_date"] = item.source_vintage_updated_date.isoformat()
        raw["source_vintage_available_at_utc"] = ""
        writer.writerow(raw)
    return output.getvalue().encode("utf-8")


def build_outputs(root: Path) -> dict[Path, bytes]:
    study = assemble_study(root)
    derived = root / "data" / "derived"
    return {
        derived / "cocoa_cot_positioning.csv": _cftc_csv(study.cftc_visible),
        derived / "cocoa_price_monthly.csv": _price_csv(study.prices),
        derived / "study_summary.json": (
            json.dumps(study.summary, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
        ).encode("utf-8"),
    }


def materialize(root: Path, *, check: bool = False) -> None:
    outputs = build_outputs(root)
    mismatches: list[str] = []
    for path, payload in outputs.items():
        if check:
            if not path.exists() or path.read_bytes() != payload:
                mismatches.append(str(path.relative_to(root)))
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
    if mismatches:
        raise ValueError("derived outputs are stale: " + ", ".join(mismatches))
