"""Offline integration tests for the public cocoa trading-research case."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from datetime import datetime
from itertools import pairwise
from pathlib import Path
from typing import Any, cast

import pytest

from cocoa_positioning_study.trading_case_pipeline import (
    EXPECTED_SIGNAL_DATES,
    PROXY_OUTCOMES_PATH,
    SIGNAL_EVENTS_PATH,
    TRADING_SUMMARY_PATH,
    build_trading_case_outputs,
    iter_source_fingerprints,
    materialize_trading_case,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def outputs() -> dict[Path, bytes]:
    return build_trading_case_outputs(ROOT)


@pytest.fixture(scope="module")
def summary(outputs: dict[Path, bytes]) -> dict[str, Any]:
    value: Any = json.loads(outputs[ROOT / TRADING_SUMMARY_PATH])
    assert isinstance(value, dict)
    return cast(dict[str, Any], value)


def test_trading_manifest_binds_exact_public_files() -> None:
    fingerprints = dict(iter_source_fingerprints(ROOT))
    assert set(fingerprints) == {
        "cftc_cocoa_selected_history_2009_2026",
        "world_bank_cocoa_event_endpoints_2026_08",
    }
    assert all(re.fullmatch(r"[0-9a-f]{64}", value) for value in fingerprints.values())

    with (ROOT / "data/trading_source_manifest.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 2
    for row in rows:
        path = ROOT / row["public_local_path"]
        assert path.is_file()
        assert path.stat().st_size == int(row["public_byte_count"])
        assert hashlib.sha256(path.read_bytes()).hexdigest() == row["public_sha256"]


def test_signal_dates_use_availability_time_and_dst_cooldown(
    outputs: dict[Path, bytes],
) -> None:
    rows = list(csv.DictReader(io.StringIO(outputs[ROOT / SIGNAL_EVENTS_PATH].decode("utf-8"))))
    assert tuple(row["report_date"] for row in rows) == EXPECTED_SIGNAL_DATES
    assert rows[1]["report_date"] == "2017-05-30"
    assert "2017-05-23" not in {row["report_date"] for row in rows}

    available = [
        datetime.fromisoformat(row["available_at_utc"].replace("Z", "+00:00")) for row in rows
    ]
    assert all(
        (current - previous).total_seconds() >= 91 * 86_400
        for previous, current in pairwise(available)
    )


def test_public_proxy_result_is_retained_as_inconclusive(
    outputs: dict[Path, bytes], summary: dict[str, Any]
) -> None:
    proxy = summary["signal"]["public_proxy"]
    assert proxy["event_count"] == 13
    assert proxy["complete_event_count"] == 12
    assert proxy["censored_event_count"] == 1
    assert proxy["mean_return_pct"] == pytest.approx(0.6135905473513348)
    assert proxy["median_return_pct"] == pytest.approx(1.8109394734285391)
    assert proxy["hit_rate_pct"] == pytest.approx(58.33333333333333)
    assert proxy["ci_low_pct"] == pytest.approx(-5.63824561239634)
    assert proxy["ci_high_pct"] == pytest.approx(5.835616009415757)
    assert proxy["status"] == "INCONCLUSIVE / UNDERPOWERED"

    outcomes = list(
        csv.DictReader(io.StringIO(outputs[ROOT / PROXY_OUTCOMES_PATH].decode("utf-8")))
    )
    assert len(outcomes) == 13
    assert sum(row["status"] == "COMPLETE" for row in outcomes) == 12
    assert sum(row["status"] == "CENSORED" for row in outcomes) == 1


def test_summary_keeps_physical_weather_science_and_trade_boundaries(
    summary: dict[str, Any],
) -> None:
    balance = summary["physical"]["latest_balance"]
    assert balance == {
        "crop_year": "2024/25",
        "ending_stocks_kt": 1320,
        "grindings_kt": 4628,
        "production_kt": 4723,
        "published_at": "2026-05-29T23:59:59Z",
        "source_sha256": balance["source_sha256"],
        "source_url": balance["source_url"],
        "stocks_to_grind_pct": 28.5,
        "surplus_kt": 48,
    }
    assert re.fullmatch(r"[0-9a-f]{64}", balance["source_sha256"])

    weather = summary["weather"]
    assert weather["risk_label"] == "PROVISIONAL / SECOND-SOURCE CHECK REQUIRED"
    assert weather["rainfall_anomaly_display"] == "+47.0% to +188.0%"
    assert weather["scope"] == "Daloa and Kumasi location proxies; not crop-area weighted"
    assert "provisional" in weather["data_status"]
    assert not weather["trade_signal_eligible"]
    assert "must be confirmed against a second dataset" in weather["quality_warning"]

    evidence_gate = summary["evidence_gate"]
    assert evidence_gate["physical_deterioration"]
    assert evidence_gate["registered_evidence_deterioration"]
    assert evidence_gate["weather_context_status"] == "CONTEXT_ONLY_NOT_REGISTERED_V1"
    assert not evidence_gate["weather_trade_signal_eligible"]
    assert evidence_gate["reasons"] == [
        "official_surplus_revision_down_at_least_25kt",
        "official_ending_stocks_revision_down_at_least_25kt",
        "official_stocks_to_grindings_revision_down_at_least_0_5pp",
    ]

    science = summary["science"]
    assert science["record_count"] == 4
    assert len(science["claims"]) == 3
    assert "long-horizon suitability projection" in science["selection_rationale"]
    assert all(claim["limitation"] for claim in science["claims"])

    trade = summary["trade"]
    assert trade["evaluation_status"] == "NOT_EVALUATED_LICENSED_MARKET_INPUTS"
    assert trade["illustrative_input_classification"] == "ILLUSTRATIVE_NOT_MARKET_DATA"
    assert trade["max_portfolio_risk_pct"] == 0.5
    assert trade["illustrative_max_loss_usd"] == 3020.0
    assert trade["illustrative_max_gain_usd"] == 5480.0
    assert trade["illustrative_breakeven_usd_per_tonne"] == 5802.0
    assert any("settlement history and option-chain" in warning for warning in trade["warnings"])
    assert any("No broker connection" in warning for warning in trade["warnings"])


def test_committed_trading_case_outputs_are_current() -> None:
    materialize_trading_case(ROOT, check=True)
