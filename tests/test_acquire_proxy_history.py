"""Offline regression tests for the acquisition-time signal-event selection."""

from __future__ import annotations

import csv
import importlib
import sys
from collections.abc import Mapping
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Protocol, cast

ROOT = Path(__file__).resolve().parents[1]


class AcquisitionModule(Protocol):
    EXPECTED_SIGNAL_DATES: tuple[str, ...]

    def _release_overrides(self) -> dict[date, date]: ...

    def _publication_eligibility_utc(
        self,
        report_date: date,
        overrides: Mapping[date, date],
    ) -> datetime: ...

    def _signal_dates(self, rows: list[dict[str, str]]) -> list[SignalEventLike]: ...


class SignalEventLike(Protocol):
    report_date: date
    available_at_utc: datetime


sys.path.insert(0, str(ROOT / "scripts"))
try:
    ACQUISITION = cast(AcquisitionModule, importlib.import_module("acquire_proxy_history"))
finally:
    del sys.path[0]


def _retained_cftc_rows() -> list[dict[str, str]]:
    path = ROOT / "data/raw/cftc-cocoa-selected-history-2009-2026.csv"
    with path.open(encoding="utf-8", newline="") as handle:
        return cast(list[dict[str, str]], list(csv.DictReader(handle)))


def test_dst_sensitive_cooldown_suppresses_may_23_and_emits_may_30() -> None:
    overrides = ACQUISITION._release_overrides()
    first = ACQUISITION._publication_eligibility_utc(date(2017, 2, 21), overrides)
    suppressed = ACQUISITION._publication_eligibility_utc(date(2017, 5, 23), overrides)
    eligible = ACQUISITION._publication_eligibility_utc(date(2017, 5, 30), overrides)
    assert first.isoformat() == "2017-02-24T20:30:00+00:00"
    assert suppressed.isoformat() == "2017-05-26T19:30:00+00:00"
    assert eligible.isoformat() == "2017-06-02T19:30:00+00:00"
    assert suppressed - first == timedelta(days=90, hours=23)
    assert eligible - first == timedelta(days=97, hours=23)

    signals = ACQUISITION._signal_dates(_retained_cftc_rows())
    report_dates = [signal.report_date.isoformat() for signal in signals]
    assert tuple(report_dates) == ACQUISITION.EXPECTED_SIGNAL_DATES
    assert report_dates[:3] == ["2017-02-21", "2017-05-30", "2017-08-29"]
    assert "2017-05-23" not in report_dates
    assert signals[1].available_at_utc == eligible


def test_retained_official_schedules_override_the_ordinary_rule_model() -> None:
    overrides = ACQUISITION._release_overrides()
    delayed_2025 = ACQUISITION._publication_eligibility_utc(date(2025, 12, 9), overrides)
    holiday_2026 = ACQUISITION._publication_eligibility_utc(date(2026, 6, 16), overrides)
    assert delayed_2025.isoformat() == "2025-12-19T20:30:00+00:00"
    assert holiday_2026.isoformat() == "2026-06-22T19:30:00+00:00"


def test_public_proxy_endpoint_uses_freeze_corrected_signal_date() -> None:
    path = ROOT / "data/raw/world-bank-cocoa-event-endpoints-2017-2026.csv"
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 23
    by_period = {row["period"]: row["endpoint_uses"] for row in rows}
    may_signal = "2017-05-30@2017-06-02T19:30:00Z"
    august_signal = "2017-08-29@2017-09-01T19:30:00Z"
    assert f"{may_signal}:primary_entry_m_plus_1" in by_period["2017-07"]
    assert f"{may_signal}:primary_exit_m_plus_4" in by_period["2017-10"]
    assert f"{august_signal}:primary_entry_m_plus_1" in by_period["2017-10"]
    assert f"{august_signal}:primary_exit_m_plus_4" in by_period["2018-01"]
    text = path.read_text(encoding="utf-8")
    assert "2017-05-23:" not in text
    assert "999999999999" not in text
    assert "000000000000" not in text
    assert all(len(row["price_usd_per_kg"].partition(".")[2]) == 2 for row in rows)
