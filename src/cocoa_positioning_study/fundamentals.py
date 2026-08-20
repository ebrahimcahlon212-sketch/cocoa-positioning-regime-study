"""Revision-aware cocoa balance sheets, grind releases, and official events.

The retained CSVs are deliberately small factual extracts.  Every observation keeps
its economic period separate from the time at which the source became usable.
"""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Final

BALANCE_PATH: Final = Path("data/raw/icco-cocoa-balance-vintages.csv")
GRIND_PATH: Final = Path("data/raw/regional-cocoa-grind-releases.csv")
EVENT_PATH: Final = Path("data/raw/official-cocoa-event-ledger.csv")
SNAPSHOT_PATH: Final = Path("data/derived/fundamentals_snapshot.json")


def _utc(raw: str) -> datetime:
    parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"timestamp is not timezone-aware: {raw}")
    return parsed.astimezone(UTC)


def _require_aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("as-of timestamp must be timezone-aware")


def _optional_decimal(raw: str) -> Decimal | None:
    return None if raw == "" else Decimal(raw)


def _optional_int(raw: str) -> int | None:
    return None if raw == "" else int(raw)


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        values = list(csv.DictReader(handle))
    if not values:
        raise ValueError(f"factual extract is empty: {path}")
    return values


def _validate_provenance(source_url: str, source_sha256: str, retrieved_at: datetime) -> None:
    if not source_url.startswith("https://"):
        raise ValueError(f"source URL is not HTTPS: {source_url}")
    if len(source_sha256) != 64 or any(
        character not in "0123456789abcdef" for character in source_sha256
    ):
        raise ValueError(f"invalid upstream SHA-256: {source_sha256}")
    if retrieved_at.utcoffset() is None:
        raise ValueError("retrieval timestamp must be timezone-aware")


@dataclass(frozen=True)
class BalanceVintage:
    """One published estimate for one cocoa crop year."""

    release_id: str
    crop_year: str
    data_status: str
    effective_period_end: date
    available_at_utc: datetime
    availability_basis: str
    publication_date: date
    production_kt: Decimal | None
    grindings_kt: Decimal | None
    surplus_deficit_kt: Decimal | None
    ending_stocks_kt: Decimal | None
    stocks_to_grindings_pct: Decimal | None
    source_url: str
    source_sha256: str
    retrieved_at_utc: datetime
    extraction_method: str
    notes: str


@dataclass(frozen=True)
class GrindingRelease:
    """One region's grinding result as published in an association release."""

    release_id: str
    region: str
    association: str
    period: str
    period_start: date
    period_end: date
    available_at_utc: datetime
    availability_basis: str
    availability_precision: str
    grind_tonnes: int
    prior_year_tonnes: int
    yoy_pct_reported: Decimal
    reporting_plants: int | None
    comparability_flag: str
    revision_status: str
    source_url: str
    source_sha256: str
    retrieved_at_utc: datetime
    extraction_method: str
    notes: str

    @property
    def yoy_pct_calculated(self) -> Decimal:
        return (Decimal(self.grind_tonnes) / Decimal(self.prior_year_tonnes) - 1) * 100


@dataclass(frozen=True)
class OfficialEvent:
    """A source-backed event, separated into effective and available timestamps."""

    event_id: str
    category: str
    title: str
    effective_at_utc: datetime
    available_at_utc: datetime
    availability_basis: str
    direction_tag: str
    quantitative_fact: str
    source_url: str
    source_sha256: str
    retrieved_at_utc: datetime
    notes: str


def load_balance_vintages(root: Path) -> tuple[BalanceVintage, ...]:
    records: list[BalanceVintage] = []
    seen: set[tuple[str, str]] = set()
    for raw in _rows(root / BALANCE_PATH):
        record = BalanceVintage(
            release_id=raw["release_id"],
            crop_year=raw["crop_year"],
            data_status=raw["data_status"],
            effective_period_end=date.fromisoformat(raw["effective_period_end"]),
            available_at_utc=_utc(raw["available_at_utc"]),
            availability_basis=raw["availability_basis"],
            publication_date=date.fromisoformat(raw["publication_date"]),
            production_kt=_optional_decimal(raw["production_kt"]),
            grindings_kt=_optional_decimal(raw["grindings_kt"]),
            surplus_deficit_kt=_optional_decimal(raw["surplus_deficit_kt"]),
            ending_stocks_kt=_optional_decimal(raw["ending_stocks_kt"]),
            stocks_to_grindings_pct=_optional_decimal(raw["stocks_to_grindings_pct"]),
            source_url=raw["source_url"],
            source_sha256=raw["source_sha256"],
            retrieved_at_utc=_utc(raw["retrieved_at_utc"]),
            extraction_method=raw["extraction_method"],
            notes=raw["notes"],
        )
        _validate_provenance(record.source_url, record.source_sha256, record.retrieved_at_utc)
        key = (record.release_id, record.crop_year)
        if key in seen:
            raise ValueError(f"duplicate balance vintage: {key}")
        seen.add(key)
        values = (
            record.production_kt,
            record.grindings_kt,
            record.surplus_deficit_kt,
            record.ending_stocks_kt,
            record.stocks_to_grindings_pct,
        )
        if record.data_status == "reported" and any(value is None for value in values):
            raise ValueError(f"reported balance row has missing values: {key}")
        if record.data_status == "withheld" and any(value is not None for value in values):
            raise ValueError(f"withheld balance row contains estimates: {key}")
        if record.available_at_utc.date() < record.publication_date:
            raise ValueError(f"balance availability predates publication: {key}")
        records.append(record)
    return tuple(sorted(records, key=lambda item: (item.available_at_utc, item.crop_year)))


def visible_balance_as_of(
    records: tuple[BalanceVintage, ...], as_of: datetime
) -> tuple[BalanceVintage, ...]:
    _require_aware(as_of)
    cutoff = as_of.astimezone(UTC)
    return tuple(record for record in records if record.available_at_utc <= cutoff)


def latest_reported_balance(
    records: tuple[BalanceVintage, ...], crop_year: str, as_of: datetime
) -> BalanceVintage:
    eligible = [
        record
        for record in visible_balance_as_of(records, as_of)
        if record.crop_year == crop_year and record.data_status == "reported"
    ]
    if not eligible:
        raise ValueError(f"no reported balance visible for {crop_year} at {as_of.isoformat()}")
    return max(eligible, key=lambda item: item.available_at_utc)


def balance_revision(
    records: tuple[BalanceVintage, ...], crop_year: str, as_of: datetime
) -> dict[str, Any]:
    eligible = sorted(
        (
            record
            for record in visible_balance_as_of(records, as_of)
            if record.crop_year == crop_year and record.data_status == "reported"
        ),
        key=lambda item: item.available_at_utc,
    )
    if len(eligible) < 2:
        raise ValueError(f"fewer than two balance vintages are visible for {crop_year}")
    previous, latest = eligible[-2:]

    def delta(field: str) -> float:
        latest_value = getattr(latest, field)
        previous_value = getattr(previous, field)
        if latest_value is None or previous_value is None:
            raise ValueError(f"cannot revise missing balance field: {field}")
        return float(latest_value - previous_value)

    return {
        "crop_year": crop_year,
        "previous_release_id": previous.release_id,
        "latest_release_id": latest.release_id,
        "previous_available_at_utc": previous.available_at_utc.isoformat().replace("+00:00", "Z"),
        "latest_available_at_utc": latest.available_at_utc.isoformat().replace("+00:00", "Z"),
        "production_revision_kt": delta("production_kt"),
        "grindings_revision_kt": delta("grindings_kt"),
        "surplus_deficit_revision_kt": delta("surplus_deficit_kt"),
        "ending_stocks_revision_kt": delta("ending_stocks_kt"),
        "stocks_to_grindings_revision_percentage_points": delta("stocks_to_grindings_pct"),
    }


def load_grinding_releases(root: Path) -> tuple[GrindingRelease, ...]:
    records: list[GrindingRelease] = []
    seen: set[str] = set()
    for raw in _rows(root / GRIND_PATH):
        record = GrindingRelease(
            release_id=raw["release_id"],
            region=raw["region"],
            association=raw["association"],
            period=raw["period"],
            period_start=date.fromisoformat(raw["period_start"]),
            period_end=date.fromisoformat(raw["period_end"]),
            available_at_utc=_utc(raw["available_at_utc"]),
            availability_basis=raw["availability_basis"],
            availability_precision=raw["availability_precision"],
            grind_tonnes=int(raw["grind_tonnes"]),
            prior_year_tonnes=int(raw["prior_year_tonnes"]),
            yoy_pct_reported=Decimal(raw["yoy_pct_reported"]),
            reporting_plants=_optional_int(raw["reporting_plants"]),
            comparability_flag=raw["comparability_flag"],
            revision_status=raw["revision_status"],
            source_url=raw["source_url"],
            source_sha256=raw["source_sha256"],
            retrieved_at_utc=_utc(raw["retrieved_at_utc"]),
            extraction_method=raw["extraction_method"],
            notes=raw["notes"],
        )
        _validate_provenance(record.source_url, record.source_sha256, record.retrieved_at_utc)
        if record.release_id in seen:
            raise ValueError(f"duplicate grinding release: {record.release_id}")
        seen.add(record.release_id)
        if record.period_end < record.period_start:
            raise ValueError(f"grinding period is inverted: {record.release_id}")
        if abs(record.yoy_pct_calculated - record.yoy_pct_reported) > Decimal("0.06"):
            raise ValueError(f"reported grinding change does not reconcile: {record.release_id}")
        records.append(record)
    return tuple(sorted(records, key=lambda item: (item.available_at_utc, item.region)))


def latest_grinds_as_of(
    records: tuple[GrindingRelease, ...], as_of: datetime
) -> tuple[GrindingRelease, ...]:
    _require_aware(as_of)
    latest: dict[str, GrindingRelease] = {}
    for record in records:
        if record.available_at_utc <= as_of.astimezone(UTC):
            prior = latest.get(record.region)
            if prior is None or (record.period_end, record.available_at_utc) > (
                prior.period_end,
                prior.available_at_utc,
            ):
                latest[record.region] = record
    return tuple(latest[region] for region in sorted(latest))


def load_official_events(root: Path) -> tuple[OfficialEvent, ...]:
    records: list[OfficialEvent] = []
    seen: set[str] = set()
    for raw in _rows(root / EVENT_PATH):
        record = OfficialEvent(
            event_id=raw["event_id"],
            category=raw["category"],
            title=raw["title"],
            effective_at_utc=_utc(raw["effective_at_utc"]),
            available_at_utc=_utc(raw["available_at_utc"]),
            availability_basis=raw["availability_basis"],
            direction_tag=raw["direction_tag"],
            quantitative_fact=raw["quantitative_fact"],
            source_url=raw["source_url"],
            source_sha256=raw["source_sha256"],
            retrieved_at_utc=_utc(raw["retrieved_at_utc"]),
            notes=raw["notes"],
        )
        _validate_provenance(record.source_url, record.source_sha256, record.retrieved_at_utc)
        if record.event_id in seen:
            raise ValueError(f"duplicate official event: {record.event_id}")
        seen.add(record.event_id)
        if record.available_at_utc < record.effective_at_utc:
            raise ValueError(f"event is available before it is effective: {record.event_id}")
        records.append(record)
    return tuple(sorted(records, key=lambda item: item.available_at_utc))


def visible_events_as_of(
    records: tuple[OfficialEvent, ...], as_of: datetime
) -> tuple[OfficialEvent, ...]:
    _require_aware(as_of)
    cutoff = as_of.astimezone(UTC)
    return tuple(record for record in records if record.available_at_utc <= cutoff)


def _balance_dict(record: BalanceVintage) -> dict[str, Any]:
    return {
        "release_id": record.release_id,
        "crop_year": record.crop_year,
        "available_at_utc": record.available_at_utc.isoformat().replace("+00:00", "Z"),
        "production_kt": float(record.production_kt) if record.production_kt is not None else None,
        "grindings_kt": float(record.grindings_kt) if record.grindings_kt is not None else None,
        "surplus_deficit_kt": (
            float(record.surplus_deficit_kt) if record.surplus_deficit_kt is not None else None
        ),
        "ending_stocks_kt": (
            float(record.ending_stocks_kt) if record.ending_stocks_kt is not None else None
        ),
        "stocks_to_grindings_pct": (
            float(record.stocks_to_grindings_pct)
            if record.stocks_to_grindings_pct is not None
            else None
        ),
        "source_url": record.source_url,
        "source_sha256": record.source_sha256,
    }


def build_fundamentals_snapshot(
    root: Path, as_of: datetime = datetime(2026, 8, 20, 23, 59, 59, tzinfo=UTC)
) -> dict[str, Any]:
    balances = load_balance_vintages(root)
    latest_balance = latest_reported_balance(balances, "2024/25", as_of)
    grinds = latest_grinds_as_of(load_grinding_releases(root), as_of)
    events = visible_events_as_of(load_official_events(root), as_of)
    return {
        "as_of_utc": as_of.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "balance": {
            "latest_2024_25": _balance_dict(latest_balance),
            "latest_revision": balance_revision(balances, "2024/25", as_of),
            "interpretation_guardrail": (
                "ICCO gross production minus grindings does not equal the published balance because "
                "the balance uses net crop after loss in weight; use ICCO's published surplus/deficit."
            ),
        },
        "latest_regional_grinds": [
            {
                "region": record.region,
                "association": record.association,
                "period": record.period,
                "grind_tonnes": record.grind_tonnes,
                "prior_year_tonnes": record.prior_year_tonnes,
                "yoy_pct_reported": float(record.yoy_pct_reported),
                "yoy_pct_calculated": round(float(record.yoy_pct_calculated), 4),
                "comparability_flag": record.comparability_flag,
                "source_url": record.source_url,
                "source_sha256": record.source_sha256,
            }
            for record in grinds
        ],
        "demand_breadth": {
            "positive_regions": sum(record.yoy_pct_reported > 0 for record in grinds),
            "negative_regions": sum(record.yoy_pct_reported < 0 for record in grinds),
            "region_count": len(grinds),
            "warning": (
                "Do not sum association series or infer global demand: coverage and reporting-company "
                "composition differ, and CAA/NCA disclose comparability changes."
            ),
        },
        "visible_official_event_count": len(events),
        "latest_official_events": [
            {
                **asdict(record),
                "effective_at_utc": record.effective_at_utc.isoformat().replace("+00:00", "Z"),
                "available_at_utc": record.available_at_utc.isoformat().replace("+00:00", "Z"),
                "retrieved_at_utc": record.retrieved_at_utc.isoformat().replace("+00:00", "Z"),
            }
            for record in events[-6:]
        ],
    }


def build_fundamentals_outputs(root: Path) -> dict[Path, bytes]:
    payload = (
        json.dumps(build_fundamentals_snapshot(root), indent=2, sort_keys=True, ensure_ascii=True)
        + "\n"
    )
    return {root / SNAPSHOT_PATH: payload.encode("utf-8")}


def materialize_fundamentals(root: Path, *, check: bool = False) -> None:
    mismatches: list[str] = []
    for path, payload in build_fundamentals_outputs(root).items():
        if check:
            if not path.exists() or path.read_bytes() != payload:
                mismatches.append(str(path.relative_to(root)))
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
    if mismatches:
        raise ValueError("derived fundamentals outputs are stale: " + ", ".join(mismatches))
