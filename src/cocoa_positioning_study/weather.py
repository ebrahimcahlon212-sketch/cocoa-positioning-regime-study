"""Conservative weather-proxy transforms for two West African grid cells."""

from __future__ import annotations

import csv
import io
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any, Final

WEATHER_PATH: Final = Path("data/raw/nasa-power-west-africa-weather.csv")
SIGNAL_PATH: Final = Path("data/derived/weather_signal_monthly.csv")
SNAPSHOT_PATH: Final = Path("data/derived/weather_snapshot.json")
DRY_DAY_THRESHOLD_MM: Final = Decimal("1.0")
HEAVY_RAIN_THRESHOLD_MM: Final = Decimal("20.0")


def _utc(raw: str) -> datetime:
    parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"timestamp is not timezone-aware: {raw}")
    return parsed.astimezone(UTC)


def _optional_int(raw: str) -> int | None:
    return None if raw == "" else int(raw)


def _round(value: Decimal, quantum: str = "0.01") -> Decimal:
    return value.quantize(Decimal(quantum), rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class WeatherRecord:
    site_id: str
    site_name: str
    country: str
    latitude: Decimal
    longitude: Decimal
    record_type: str
    period: str
    month: int
    period_start: date
    period_end: date
    effective_at_utc: datetime
    available_at_utc: datetime
    availability_basis: str
    availability_precision: str
    days_observed: int | None
    precip_value: Decimal
    precip_unit: str
    t2m_c: Decimal
    t2m_max_c: Decimal
    rh2m_pct: Decimal
    dry_days_lt_1mm: int | None
    longest_dry_spell_days: int | None
    heavy_rain_days_ge_20mm: int | None
    source_url: str
    source_sha256: str
    retrieved_at_utc: datetime
    source_api_version: str
    source_data_sources: str
    quality_flag: str
    notes: str


@dataclass(frozen=True)
class WeatherSignal:
    site_id: str
    site_name: str
    country: str
    period: str
    period_start: date
    period_end: date
    available_at_utc: datetime
    days_observed: int
    observed_precip_mm: Decimal
    climatology_precip_mm: Decimal
    precip_anomaly_pct: Decimal
    observed_t2m_c: Decimal
    climatology_t2m_c: Decimal
    t2m_anomaly_c: Decimal
    observed_t2m_max_c: Decimal
    climatology_t2m_max_c: Decimal
    t2m_max_anomaly_c: Decimal
    observed_rh2m_pct: Decimal
    climatology_rh2m_pct: Decimal
    rh2m_anomaly_percentage_points: Decimal
    dry_days_lt_1mm: int
    longest_dry_spell_days: int
    heavy_rain_days_ge_20mm: int
    precipitation_state: str
    temperature_state: str
    quality_flag: str
    quality_note: str
    source_url: str
    source_sha256: str


def load_weather_records(root: Path) -> tuple[WeatherRecord, ...]:
    path = root / WEATHER_PATH
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError("NASA POWER factual extract is empty")
    records: list[WeatherRecord] = []
    seen: set[tuple[str, str, str]] = set()
    for raw in rows:
        record = WeatherRecord(
            site_id=raw["site_id"],
            site_name=raw["site_name"],
            country=raw["country"],
            latitude=Decimal(raw["latitude"]),
            longitude=Decimal(raw["longitude"]),
            record_type=raw["record_type"],
            period=raw["period"],
            month=int(raw["month"]),
            period_start=date.fromisoformat(raw["period_start"]),
            period_end=date.fromisoformat(raw["period_end"]),
            effective_at_utc=_utc(raw["effective_at_utc"]),
            available_at_utc=_utc(raw["available_at_utc"]),
            availability_basis=raw["availability_basis"],
            availability_precision=raw["availability_precision"],
            days_observed=_optional_int(raw["days_observed"]),
            precip_value=Decimal(raw["precip_value"]),
            precip_unit=raw["precip_unit"],
            t2m_c=Decimal(raw["t2m_c"]),
            t2m_max_c=Decimal(raw["t2m_max_c"]),
            rh2m_pct=Decimal(raw["rh2m_pct"]),
            dry_days_lt_1mm=_optional_int(raw["dry_days_lt_1mm"]),
            longest_dry_spell_days=_optional_int(raw["longest_dry_spell_days"]),
            heavy_rain_days_ge_20mm=_optional_int(raw["heavy_rain_days_ge_20mm"]),
            source_url=raw["source_url"],
            source_sha256=raw["source_sha256"],
            retrieved_at_utc=_utc(raw["retrieved_at_utc"]),
            source_api_version=raw["source_api_version"],
            source_data_sources=raw["source_data_sources"],
            quality_flag=raw["quality_flag"],
            notes=raw["notes"],
        )
        key = (record.site_id, record.record_type, record.period)
        if key in seen:
            raise ValueError(f"duplicate weather record: {key}")
        seen.add(key)
        if record.source_url.startswith("https://") is False:
            raise ValueError(f"weather source URL is not HTTPS: {key}")
        if len(record.source_sha256) != 64:
            raise ValueError(f"weather source hash is invalid: {key}")
        if record.effective_at_utc.date() != record.period_end:
            raise ValueError(f"weather effective timestamp disagrees with period end: {key}")
        if record.available_at_utc < record.effective_at_utc:
            raise ValueError(f"weather record is available before it is effective: {key}")
        if record.record_type == "climatology_2001_2020":
            if record.precip_unit != "mm/day" or record.days_observed is not None:
                raise ValueError(f"invalid climatology row: {key}")
        elif record.record_type == "observed_daily_aggregate":
            counts = (
                record.days_observed,
                record.dry_days_lt_1mm,
                record.longest_dry_spell_days,
                record.heavy_rain_days_ge_20mm,
            )
            if record.precip_unit != "mm/month_or_partial_month" or any(
                value is None for value in counts
            ):
                raise ValueError(f"invalid observed weather row: {key}")
        else:
            raise ValueError(f"unknown weather record type: {record.record_type}")
        records.append(record)
    return tuple(sorted(records, key=lambda item: (item.site_id, item.record_type, item.period)))


def visible_weather_as_of(
    records: tuple[WeatherRecord, ...], as_of: datetime
) -> tuple[WeatherRecord, ...]:
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("as-of timestamp must be timezone-aware")
    cutoff = as_of.astimezone(UTC)
    return tuple(record for record in records if record.available_at_utc <= cutoff)


def _precipitation_state(anomaly_pct: Decimal) -> str:
    if anomaly_pct >= 50:
        return "much_wetter_than_2001_2020_monthly_baseline"
    if anomaly_pct >= 20:
        return "wetter_than_2001_2020_monthly_baseline"
    if anomaly_pct <= -50:
        return "much_drier_than_2001_2020_monthly_baseline"
    if anomaly_pct <= -20:
        return "drier_than_2001_2020_monthly_baseline"
    return "near_2001_2020_monthly_baseline"


def _temperature_state(anomaly_c: Decimal) -> str:
    if anomaly_c >= 1:
        return "warmer_than_2001_2020_monthly_baseline"
    if anomaly_c <= -1:
        return "cooler_than_2001_2020_monthly_baseline"
    return "near_2001_2020_monthly_baseline"


def build_weather_signals(records: tuple[WeatherRecord, ...]) -> tuple[WeatherSignal, ...]:
    climatology: dict[tuple[str, int], WeatherRecord] = {}
    observed: list[WeatherRecord] = []
    for record in records:
        if record.record_type == "climatology_2001_2020":
            climatology[(record.site_id, record.month)] = record
        else:
            observed.append(record)
    signals: list[WeatherSignal] = []
    for record in observed:
        baseline = climatology.get((record.site_id, record.month))
        if baseline is None:
            raise ValueError(f"missing weather climatology: {record.site_id} month {record.month}")
        if record.days_observed is None:
            raise ValueError(f"missing weather day count: {record.site_id} {record.period}")
        expected_precip = baseline.precip_value * record.days_observed
        if expected_precip <= 0:
            raise ValueError(f"non-positive weather baseline: {record.site_id} {record.period}")
        precip_anomaly = (record.precip_value / expected_precip - 1) * 100
        t2m_anomaly = record.t2m_c - baseline.t2m_c
        dry_days = record.dry_days_lt_1mm
        longest = record.longest_dry_spell_days
        heavy_days = record.heavy_rain_days_ge_20mm
        if dry_days is None or longest is None or heavy_days is None:
            raise ValueError(f"missing daily weather indices: {record.site_id} {record.period}")
        signals.append(
            WeatherSignal(
                site_id=record.site_id,
                site_name=record.site_name,
                country=record.country,
                period=record.period,
                period_start=record.period_start,
                period_end=record.period_end,
                available_at_utc=record.available_at_utc,
                days_observed=record.days_observed,
                observed_precip_mm=record.precip_value,
                climatology_precip_mm=_round(expected_precip),
                precip_anomaly_pct=_round(precip_anomaly),
                observed_t2m_c=record.t2m_c,
                climatology_t2m_c=baseline.t2m_c,
                t2m_anomaly_c=_round(t2m_anomaly),
                observed_t2m_max_c=record.t2m_max_c,
                climatology_t2m_max_c=baseline.t2m_max_c,
                t2m_max_anomaly_c=_round(record.t2m_max_c - baseline.t2m_max_c),
                observed_rh2m_pct=record.rh2m_pct,
                climatology_rh2m_pct=baseline.rh2m_pct,
                rh2m_anomaly_percentage_points=_round(record.rh2m_pct - baseline.rh2m_pct),
                dry_days_lt_1mm=dry_days,
                longest_dry_spell_days=longest,
                heavy_rain_days_ge_20mm=heavy_days,
                precipitation_state=_precipitation_state(precip_anomaly),
                temperature_state=_temperature_state(t2m_anomaly),
                quality_flag=record.quality_flag,
                quality_note=record.notes,
                source_url=record.source_url,
                source_sha256=record.source_sha256,
            )
        )
    return tuple(sorted(signals, key=lambda item: (item.period_end, item.site_id)))


def _signal_csv(signals: tuple[WeatherSignal, ...]) -> bytes:
    fields = (
        "site_id",
        "site_name",
        "country",
        "period",
        "period_start",
        "period_end",
        "available_at_utc",
        "days_observed",
        "observed_precip_mm",
        "climatology_precip_mm",
        "precip_anomaly_pct",
        "observed_t2m_c",
        "climatology_t2m_c",
        "t2m_anomaly_c",
        "observed_t2m_max_c",
        "climatology_t2m_max_c",
        "t2m_max_anomaly_c",
        "observed_rh2m_pct",
        "climatology_rh2m_pct",
        "rh2m_anomaly_percentage_points",
        "dry_days_lt_1mm",
        "longest_dry_spell_days",
        "heavy_rain_days_ge_20mm",
        "precipitation_state",
        "temperature_state",
        "quality_flag",
        "quality_note",
        "source_url",
        "source_sha256",
    )
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for signal in signals:
        row: dict[str, object] = {field: getattr(signal, field) for field in fields}
        row["period_start"] = signal.period_start.isoformat()
        row["period_end"] = signal.period_end.isoformat()
        row["available_at_utc"] = signal.available_at_utc.isoformat().replace("+00:00", "Z")
        writer.writerow(row)
    return output.getvalue().encode("utf-8")


def build_weather_snapshot(signals: tuple[WeatherSignal, ...]) -> dict[str, Any]:
    if not signals:
        raise ValueError("weather snapshot requires at least one visible signal")
    by_site: dict[str, list[WeatherSignal]] = defaultdict(list)
    for signal in signals:
        by_site[signal.site_id].append(signal)
    trailing: list[dict[str, Any]] = []
    for site_id, site_signals in sorted(by_site.items()):
        selected = sorted(site_signals, key=lambda item: item.period_end)[-3:]
        observed_precip = sum((item.observed_precip_mm for item in selected), Decimal(0))
        expected_precip = sum((item.climatology_precip_mm for item in selected), Decimal(0))
        total_days = sum(item.days_observed for item in selected)
        mean_t2m = (
            sum((item.observed_t2m_c * item.days_observed for item in selected), Decimal(0))
            / total_days
        )
        baseline_t2m = (
            sum((item.climatology_t2m_c * item.days_observed for item in selected), Decimal(0))
            / total_days
        )
        anomaly = (observed_precip / expected_precip - 1) * 100
        quality_notes = tuple(sorted({item.quality_note for item in selected if item.quality_note}))
        requires_secondary_confirmation = any(
            "must be confirmed against a second dataset" in note.lower() for note in quality_notes
        )
        trailing.append(
            {
                "site_id": site_id,
                "site_name": selected[-1].site_name,
                "country": selected[-1].country,
                "window_start": selected[0].period_start.isoformat(),
                "window_end": selected[-1].period_end.isoformat(),
                "available_at_utc": selected[-1]
                .available_at_utc.isoformat()
                .replace("+00:00", "Z"),
                "days_observed": total_days,
                "observed_precip_mm": float(_round(observed_precip)),
                "climatology_precip_mm": float(_round(expected_precip)),
                "precip_anomaly_pct": float(_round(anomaly)),
                "mean_t2m_c": float(_round(mean_t2m)),
                "t2m_anomaly_c": float(_round(mean_t2m - baseline_t2m)),
                "dry_days_lt_1mm": sum(item.dry_days_lt_1mm for item in selected),
                "heavy_rain_days_ge_20mm": sum(item.heavy_rain_days_ge_20mm for item in selected),
                "max_within_month_dry_spell_days": max(
                    item.longest_dry_spell_days for item in selected
                ),
                "precipitation_state": _precipitation_state(anomaly),
                "quality_flag": selected[-1].quality_flag,
                "quality_flags": sorted({item.quality_flag for item in selected}),
                "quality_notes": list(quality_notes),
                "requires_secondary_confirmation": requires_secondary_confirmation,
                "source_url": selected[-1].source_url,
                "source_sha256": selected[-1].source_sha256,
            }
        )
    secondary_confirmation_required = any(
        bool(item["requires_secondary_confirmation"]) for item in trailing
    )
    return {
        "as_of_utc": max(item.available_at_utc for item in signals)
        .isoformat()
        .replace("+00:00", "Z"),
        "data_status": "provisional_location_proxy",
        "quality_gate": (
            "SECOND_SOURCE_REQUIRED"
            if secondary_confirmation_required
            else "PROVISIONAL_SINGLE_SOURCE"
        ),
        "coverage": {
            "site_count": len(by_site),
            "first_period": min(item.period for item in signals),
            "last_period": max(item.period for item in signals),
            "observation_count": len(signals),
        },
        "trailing_three_reported_months_or_partial_month": trailing,
        "thresholds": {
            "dry_day": f"daily precipitation < {DRY_DAY_THRESHOLD_MM} mm",
            "heavy_rain_day": f"daily precipitation >= {HEAVY_RAIN_THRESHOLD_MM} mm",
            "state_labels": "descriptive comparison bands, not crop-damage thresholds",
        },
        "limitations": [
            "Two NASA POWER grid cells are location proxies, not cocoa-area-weighted farm observations.",
            "NASA POWER meteorology is model/assimilation output at roughly 0.5 x 0.625 degree native resolution.",
            "Near-real-time values can be replaced by improved climate-quality data after two to three months.",
            "The retained snapshot was first observed at retrieval time; it is not a historical release-vintage archive.",
            "Kumasi's June extreme model-grid accumulation requires confirmation against a second dataset before weather-signal use.",
            "No weather anomaly is converted mechanically into cocoa tonnes, price direction, or a trading signal.",
        ],
    }


def build_weather_outputs(root: Path) -> dict[Path, bytes]:
    signals = build_weather_signals(load_weather_records(root))
    snapshot = (
        json.dumps(build_weather_snapshot(signals), indent=2, sort_keys=True, ensure_ascii=True)
        + "\n"
    )
    return {
        root / SIGNAL_PATH: _signal_csv(signals),
        root / SNAPSHOT_PATH: snapshot.encode("utf-8"),
    }


def materialize_weather(root: Path, *, check: bool = False) -> None:
    mismatches: list[str] = []
    for path, payload in build_weather_outputs(root).items():
        if check:
            if not path.exists() or path.read_bytes() != payload:
                mismatches.append(str(path.relative_to(root)))
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
    if mismatches:
        raise ValueError("derived weather outputs are stale: " + ", ".join(mismatches))
