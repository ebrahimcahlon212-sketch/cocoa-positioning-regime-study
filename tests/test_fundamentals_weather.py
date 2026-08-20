"""Offline tests for the public physical, weather, event, and evidence layer."""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Protocol

import pytest

from cocoa_positioning_study.evidence import (
    build_evidence_guardrails,
    build_evidence_outputs,
    evidence_for_signal,
    load_evidence_registry,
    materialize_evidence,
)
from cocoa_positioning_study.fundamentals import (
    balance_revision,
    build_fundamentals_outputs,
    build_fundamentals_snapshot,
    latest_grinds_as_of,
    latest_reported_balance,
    load_balance_vintages,
    load_grinding_releases,
    load_official_events,
    materialize_fundamentals,
    visible_balance_as_of,
    visible_events_as_of,
)
from cocoa_positioning_study.weather import (
    build_weather_outputs,
    build_weather_signals,
    build_weather_snapshot,
    load_weather_records,
    materialize_weather,
    visible_weather_as_of,
)

ROOT = Path(__file__).resolve().parents[1]
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class SourceRecord(Protocol):
    @property
    def source_url(self) -> str: ...

    @property
    def source_sha256(self) -> str: ...

    @property
    def retrieved_at_utc(self) -> datetime: ...


def _assert_provenance(records: Iterable[SourceRecord]) -> None:
    for record in records:
        assert record.source_url.startswith("https://")
        assert SHA256.fullmatch(record.source_sha256)
        assert record.retrieved_at_utc.tzinfo is not None
        assert record.retrieved_at_utc.utcoffset() is not None


def test_balance_vintages_are_revision_aware_and_point_in_time() -> None:
    records = load_balance_vintages(ROOT)
    assert len(records) == 9
    assert not visible_balance_as_of(records, datetime(2025, 5, 30, 23, 59, 58, tzinfo=UTC))

    august = visible_balance_as_of(records, datetime(2025, 8, 30, tzinfo=UTC))
    withheld = next(record for record in august if record.crop_year == "2024/25")
    assert withheld.data_status == "withheld"
    assert withheld.production_kt is None
    with pytest.raises(ValueError, match="no reported balance"):
        latest_reported_balance(records, "2024/25", datetime(2025, 8, 30, tzinfo=UTC))

    latest = latest_reported_balance(records, "2024/25", datetime(2026, 8, 20, tzinfo=UTC))
    assert latest.release_id == "icco_qbcs_2026_05"
    assert latest.production_kt == Decimal("4723")
    assert latest.grindings_kt == Decimal("4628")
    assert latest.surplus_deficit_kt == Decimal("48")
    assert latest.ending_stocks_kt == Decimal("1320")
    assert latest.stocks_to_grindings_pct == Decimal("28.5")

    revision = balance_revision(records, "2024/25", datetime(2026, 8, 20, tzinfo=UTC))
    assert revision["production_revision_kt"] == -5.0
    assert revision["grindings_revision_kt"] == 22.0
    assert revision["surplus_deficit_revision_kt"] == -27.0
    assert revision["ending_stocks_revision_kt"] == -27.0
    assert revision["stocks_to_grindings_revision_percentage_points"] == -0.7


def test_regional_grinds_preserve_release_timing_and_comparability() -> None:
    records = load_grinding_releases(ROOT)
    assert len(records) == 6

    midday = {
        record.region: record
        for record in latest_grinds_as_of(records, datetime(2026, 7, 16, 12, tzinfo=UTC))
    }
    assert midday["Asia"].period == "2026-Q2"
    assert midday["Europe"].period == "2026-Q1"
    assert midday["North America"].period == "2026-Q1"

    latest = {
        record.region: record
        for record in latest_grinds_as_of(records, datetime(2026, 7, 17, tzinfo=UTC))
    }
    assert latest["Europe"].grind_tonnes == 316_366
    assert latest["Europe"].yoy_pct_reported == Decimal("-4.6")
    assert latest["Asia"].grind_tonnes == 224_646
    assert latest["Asia"].yoy_pct_reported == Decimal("25.07")
    assert latest["Asia"].comparability_flag == "membership_basis_changed_during_2025"
    assert latest["North America"].grind_tonnes == 109_659
    assert latest["North America"].yoy_pct_reported == Decimal("7.65")
    assert latest["North America"].comparability_flag == ("new_reporting_companies_added_q3_2025")


def test_official_event_ledger_obeys_availability_time() -> None:
    records = load_official_events(ROOT)
    assert len(records) == 8
    before = visible_events_as_of(records, datetime(2025, 8, 29, 23, 59, 58, tzinfo=UTC))
    after = visible_events_as_of(records, datetime(2025, 8, 30, tzinfo=UTC))
    assert "icco_2025_08_withholding" not in {record.event_id for record in before}
    assert "icco_2025_08_withholding" in {record.event_id for record in after}
    assert all(record.available_at_utc >= record.effective_at_utc for record in records)


def test_fundamentals_snapshot_keeps_balance_and_demand_definitions_separate() -> None:
    snapshot = build_fundamentals_snapshot(ROOT)
    latest = snapshot["balance"]["latest_2024_25"]
    assert latest["production_kt"] == 4723.0
    assert latest["grindings_kt"] == 4628.0
    assert latest["surplus_deficit_kt"] == 48.0
    assert snapshot["demand_breadth"] == {
        "positive_regions": 2,
        "negative_regions": 1,
        "region_count": 3,
        "warning": (
            "Do not sum association series or infer global demand: coverage and reporting-company "
            "composition differ, and CAA/NCA disclose comparability changes."
        ),
    }
    assert "net crop after loss in weight" in snapshot["balance"]["interpretation_guardrail"]


def test_weather_records_are_retrieval_vintaged_and_no_lookahead_occurs() -> None:
    records = load_weather_records(ROOT)
    assert len(records) == 40
    before = visible_weather_as_of(records, datetime(2026, 8, 20, 12, 56, 56, tzinfo=UTC))
    assert before == ()

    daloa_only = visible_weather_as_of(
        records, datetime(2026, 8, 20, 12, 56, 58, 500_000, tzinfo=UTC)
    )
    assert {record.site_id for record in daloa_only} == {"daloa_ci_proxy"}
    assert len(build_weather_signals(daloa_only)) == 8

    with pytest.raises(ValueError, match="timezone-aware"):
        visible_weather_as_of(records, datetime(2026, 8, 20))


def test_weather_signal_values_and_partial_month_are_deterministic() -> None:
    signals = build_weather_signals(load_weather_records(ROOT))
    assert len(signals) == 16
    lookup = {(signal.site_id, signal.period): signal for signal in signals}

    daloa_june = lookup[("daloa_ci_proxy", "2026-06")]
    assert daloa_june.observed_precip_mm == Decimal("383.04")
    assert daloa_june.climatology_precip_mm == Decimal("215.10")
    assert daloa_june.precip_anomaly_pct == Decimal("78.08")
    assert daloa_june.dry_days_lt_1mm == 1
    assert daloa_june.heavy_rain_days_ge_20mm == 6

    kumasi_june = lookup[("kumasi_gh_proxy", "2026-06")]
    assert kumasi_june.observed_precip_mm == Decimal("913.85")
    assert kumasi_june.precip_anomaly_pct == Decimal("311.64")
    assert kumasi_june.quality_flag == "provisional_nrt_mixed_sources"
    assert "must be confirmed against a second dataset" in kumasi_june.quality_note

    august = lookup[("daloa_ci_proxy", "2026-08")]
    assert august.period_end.isoformat() == "2026-08-14"
    assert august.days_observed == 14


def test_weather_snapshot_is_descriptive_not_a_yield_model() -> None:
    snapshot = build_weather_snapshot(build_weather_signals(load_weather_records(ROOT)))
    assert snapshot["as_of_utc"] == "2026-08-20T12:56:59Z"
    assert snapshot["data_status"] == "provisional_location_proxy"
    assert snapshot["quality_gate"] == "SECOND_SOURCE_REQUIRED"
    assert snapshot["coverage"] == {
        "site_count": 2,
        "first_period": "2026-01",
        "last_period": "2026-08",
        "observation_count": 16,
    }
    trailing = {
        row["site_id"]: row for row in snapshot["trailing_three_reported_months_or_partial_month"]
    }
    assert trailing["daloa_ci_proxy"]["precip_anomaly_pct"] == 46.99
    assert trailing["daloa_ci_proxy"]["dry_days_lt_1mm"] == 5
    assert trailing["kumasi_gh_proxy"]["precip_anomaly_pct"] == 187.98
    assert trailing["kumasi_gh_proxy"]["dry_days_lt_1mm"] == 6
    assert trailing["kumasi_gh_proxy"]["requires_secondary_confirmation"]
    assert any(
        "must be confirmed against a second dataset" in note
        for note in trailing["kumasi_gh_proxy"]["quality_notes"]
    )
    assert any("No weather anomaly is converted" in item for item in snapshot["limitations"])


def test_scientific_registry_routes_mechanisms_and_discloses_limits() -> None:
    records = load_evidence_registry(ROOT)
    assert len(records) == 4
    assert {record.evidence_id for record in evidence_for_signal(records, "black_pod")} == {
        "asitoakor_2022",
        "montero_sanchez_2025",
    }
    drought = evidence_for_signal(records, "drought")
    assert {record.evidence_grade for record in drought} == {
        "natural_experiment",
        "model_projection",
    }
    payload = build_evidence_guardrails(records)
    assert payload["as_of_utc"] == "2026-08-20T12:57:05Z"
    assert payload["signal_index"]["rainfall"] == [
        "asitoakor_2022",
        "montero_sanchez_2025",
    ]
    assert any("mechanism priors" in item for item in payload["translation_guardrails"])


def test_all_retained_sources_have_https_hashes_and_utc_retrievals() -> None:
    _assert_provenance(load_balance_vintages(ROOT))
    _assert_provenance(load_grinding_releases(ROOT))
    _assert_provenance(load_official_events(ROOT))
    _assert_provenance(load_weather_records(ROOT))
    _assert_provenance(load_evidence_registry(ROOT))


def test_committed_public_layer_outputs_are_reproducible() -> None:
    expected = {
        **build_fundamentals_outputs(ROOT),
        **build_weather_outputs(ROOT),
        **build_evidence_outputs(ROOT),
    }
    for path, payload in expected.items():
        assert path.read_bytes() == payload
    materialize_fundamentals(ROOT, check=True)
    materialize_weather(ROOT, check=True)
    materialize_evidence(ROOT, check=True)
