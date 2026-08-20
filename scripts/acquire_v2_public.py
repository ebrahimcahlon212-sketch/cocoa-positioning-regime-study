"""Explicitly refresh the small NASA POWER weather factual extract.

This command is intentionally networked and is never called by tests or the offline
reproduction path.  ICCO, ECA, CAA, NCA, and journal rows remain human-reviewed
factual extracts because their tables and comparability notes require judgement.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import urllib.parse
import urllib.request
from calendar import monthrange
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Final

from cocoa_positioning_study.weather import WEATHER_PATH, materialize_weather

BASE_URL: Final = "https://power.larc.nasa.gov/api/temporal"
PARAMETERS: Final = "PRECTOTCORR,T2M,T2M_MAX,RH2M"
MONTH_NAMES: Final = (
    "JAN",
    "FEB",
    "MAR",
    "APR",
    "MAY",
    "JUN",
    "JUL",
    "AUG",
    "SEP",
    "OCT",
    "NOV",
    "DEC",
)


@dataclass(frozen=True)
class Location:
    site_id: str
    site_name: str
    country: str
    latitude: str
    longitude: str


LOCATIONS: Final = (
    Location("daloa_ci_proxy", "Daloa cocoa-belt proxy", "Cote d'Ivoire", "6.877", "-6.45"),
    Location("kumasi_gh_proxy", "Kumasi cocoa-belt proxy", "Ghana", "6.688", "-1.624"),
)

FIELDS: Final = (
    "site_id",
    "site_name",
    "country",
    "latitude",
    "longitude",
    "record_type",
    "period",
    "month",
    "period_start",
    "period_end",
    "effective_at_utc",
    "available_at_utc",
    "availability_basis",
    "availability_precision",
    "days_observed",
    "precip_value",
    "precip_unit",
    "t2m_c",
    "t2m_max_c",
    "rh2m_pct",
    "dry_days_lt_1mm",
    "longest_dry_spell_days",
    "heavy_rain_days_ge_20mm",
    "source_url",
    "source_sha256",
    "retrieved_at_utc",
    "source_api_version",
    "source_data_sources",
    "quality_flag",
    "notes",
)


def _url(service: str, location: Location, start: str, end: str) -> str:
    query = urllib.parse.urlencode(
        {
            "parameters": PARAMETERS,
            "community": "AG",
            "longitude": location.longitude,
            "latitude": location.latitude,
            "start": start,
            "end": end,
            "format": "JSON",
        },
        safe=",",
    )
    return f"{BASE_URL}/{service}/point?{query}"


def _fetch(url: str) -> tuple[dict[str, Any], str, str]:
    if not url.startswith("https://power.larc.nasa.gov/"):
        raise ValueError(f"unexpected acquisition host: {url}")
    request = urllib.request.Request(  # noqa: S310 - fixed HTTPS host
        url,
        headers={"User-Agent": "cocoa-positioning-regime-study/0.2 provenance capture"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 - fixed HTTPS host
        payload = response.read()
    retrieved_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    parsed: Any = json.loads(payload)
    if not isinstance(parsed, dict):
        raise ValueError("NASA POWER response is not a JSON object")
    return parsed, hashlib.sha256(payload).hexdigest(), retrieved_at


def _metadata(payload: dict[str, Any]) -> tuple[str, str]:
    header = payload["header"]
    version = str(header["api"]["version"])
    sources = "|".join(str(value) for value in header["sources"])
    return version, sources


def _base_row(location: Location) -> dict[str, object]:
    return {
        "site_id": location.site_id,
        "site_name": location.site_name,
        "country": location.country,
        "latitude": location.latitude,
        "longitude": location.longitude,
        "availability_basis": "current_snapshot_first_observed_at_retrieval",
        "availability_precision": "retrieval_timestamp",
    }


def _climatology_rows(location: Location) -> list[dict[str, object]]:
    url = _url("climatology", location, "2001", "2020")
    payload, fingerprint, retrieved_at = _fetch(url)
    version, sources = _metadata(payload)
    parameters = payload["properties"]["parameter"]
    rows: list[dict[str, object]] = []
    for month, label in enumerate(MONTH_NAMES, start=1):
        rows.append(
            {
                **_base_row(location),
                "record_type": "climatology_2001_2020",
                "period": f"climatology-month-{month:02d}",
                "month": month,
                "period_start": "2001-01-01",
                "period_end": "2020-12-31",
                "effective_at_utc": "2020-12-31T23:59:59Z",
                "available_at_utc": retrieved_at,
                "days_observed": "",
                "precip_value": f"{float(parameters['PRECTOTCORR'][label]):.2f}",
                "precip_unit": "mm/day",
                "t2m_c": f"{float(parameters['T2M'][label]):.2f}",
                "t2m_max_c": f"{float(parameters['T2M_MAX'][label]):.2f}",
                "rh2m_pct": f"{float(parameters['RH2M'][label]):.2f}",
                "dry_days_lt_1mm": "",
                "longest_dry_spell_days": "",
                "heavy_rain_days_ge_20mm": "",
                "source_url": url,
                "source_sha256": fingerprint,
                "retrieved_at_utc": retrieved_at,
                "source_api_version": version,
                "source_data_sources": sources,
                "quality_flag": "climatology_mixed_merra2_power",
                "notes": "Grid-cell proxy; not farm or crop-area weighted",
            }
        )
    return rows


def _daily_rows(location: Location, start: date, end: date) -> list[dict[str, object]]:
    url = _url("daily", location, start.strftime("%Y%m%d"), end.strftime("%Y%m%d"))
    payload, fingerprint, retrieved_at = _fetch(url)
    version, sources = _metadata(payload)
    parameters = payload["properties"]["parameter"]
    grouped: dict[str, list[tuple[date, float, float, float, float]]] = defaultdict(list)
    for label, precip_value in parameters["PRECTOTCORR"].items():
        observed_date = datetime.strptime(label, "%Y%m%d").date()
        grouped[observed_date.strftime("%Y-%m")].append(
            (
                observed_date,
                float(precip_value),
                float(parameters["T2M"][label]),
                float(parameters["T2M_MAX"][label]),
                float(parameters["RH2M"][label]),
            )
        )
    rows: list[dict[str, object]] = []
    for period, values in sorted(grouped.items()):
        values.sort(key=lambda item: item[0])
        current_dry_spell = 0
        longest_dry_spell = 0
        for _, precip, _, _, _ in values:
            if precip < 1.0:
                current_dry_spell += 1
                longest_dry_spell = max(longest_dry_spell, current_dry_spell)
            else:
                current_dry_spell = 0
        period_start = values[0][0]
        period_end = values[-1][0]
        rows.append(
            {
                **_base_row(location),
                "record_type": "observed_daily_aggregate",
                "period": period,
                "month": period_start.month,
                "period_start": period_start.isoformat(),
                "period_end": period_end.isoformat(),
                "effective_at_utc": f"{period_end.isoformat()}T23:59:59Z",
                "available_at_utc": retrieved_at,
                "days_observed": len(values),
                "precip_value": f"{sum(item[1] for item in values):.2f}",
                "precip_unit": "mm/month_or_partial_month",
                "t2m_c": f"{sum(item[2] for item in values) / len(values):.2f}",
                "t2m_max_c": f"{sum(item[3] for item in values) / len(values):.2f}",
                "rh2m_pct": f"{sum(item[4] for item in values) / len(values):.2f}",
                "dry_days_lt_1mm": sum(item[1] < 1.0 for item in values),
                "longest_dry_spell_days": longest_dry_spell,
                "heavy_rain_days_ge_20mm": sum(item[1] >= 20.0 for item in values),
                "source_url": url,
                "source_sha256": fingerprint,
                "retrieved_at_utc": retrieved_at,
                "source_api_version": version,
                "source_data_sources": sources,
                "quality_flag": "provisional_nrt_mixed_sources",
                "notes": (
                    "Partial final month; current snapshot is not a release-vintage archive"
                    if period_end.day != monthrange(period_end.year, period_end.month)[1]
                    else "Daily values aggregated deterministically; current snapshot is not a release-vintage archive"
                ),
            }
        )
    return rows


def acquire(root: Path, start: date, end: date) -> Path:
    if end < start:
        raise ValueError("weather acquisition end precedes start")
    rows: list[dict[str, object]] = []
    for location in LOCATIONS:
        rows.extend(_climatology_rows(location))
        rows.extend(_daily_rows(location, start, end))
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    path = root / WEATHER_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(output.getvalue(), encoding="utf-8", newline="")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--start", type=date.fromisoformat, default=date(2026, 1, 1))
    parser.add_argument("--end", type=date.fromisoformat, default=date(2026, 8, 14))
    parser.add_argument("--no-derived", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    path = acquire(root, args.start, args.end)
    if not args.no_derived:
        materialize_weather(root)
    print(f"wrote {path.relative_to(root)}")
    print(
        "Review provisional NASA POWER values against a second weather source before interpretation."
    )


if __name__ == "__main__":
    main()
