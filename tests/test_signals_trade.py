"""Offline tests for the pre-registered signal, proxy, and hypothetical trade layer."""

from __future__ import annotations

import csv
import re
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from cocoa_positioning_study.licensed_market_data import (
    load_dec26_option_chain,
    load_dec26_settlements,
    prior_20_session_high_confirmation,
    select_registered_call_spread,
)
from cocoa_positioning_study.signals import (
    MIN_PRIOR_RELEASES,
    SIGNAL_COOLDOWN,
    PositioningRelease,
    cftc_reversal_signals,
    circular_block_bootstrap_mean_interval,
    evaluate_cftc_reversal_rule,
    evaluate_public_proxy_events,
    summarize_public_proxy_events,
    summarize_signal_study,
)
from cocoa_positioning_study.trade import (
    DESIGN_FREEZE_UTC,
    EXIT_BEFORE_LAST_TRADING_DAY_SESSIONS,
    MAX_HOLDING_TRADING_SESSIONS,
    CallSpreadSpec,
    ExitPolicyInputs,
    PhysicalRevisionEvidence,
    TradeRuleInputs,
    call_spread_expiry_scenario,
    evaluate_dec26_call_spread_rule,
    evaluate_evidence_deterioration,
    evaluate_hypothetical_exit_policy,
    size_by_max_loss,
    standard_scenario_table,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"


def _synthetic_positioning_releases() -> tuple[PositioningRelease, ...]:
    count = 170
    normalized_net_thousandths = [200] * count
    normalized_net_thousandths[155] = -200
    normalized_net_thousandths[156] = -100
    normalized_net_thousandths[157] = -50
    for index in range(158, 168):
        normalized_net_thousandths[index] = -50
    normalized_net_thousandths[168] = -200
    normalized_net_thousandths[169] = -100
    first_available = datetime(2022, 1, 7, 20, 30, tzinfo=UTC)
    return tuple(
        PositioningRelease(
            report_date=date(2022, 1, 4) + timedelta(weeks=index),
            available_at_utc=first_available + timedelta(weeks=index),
            managed_money_net_contracts=normalized_net_thousandths[index],
            open_interest_contracts=1_000,
            source_ref="SYNTHETIC_TEST_ONLY",
            availability_basis="synthetic_weekly_schedule",
            availability_source_ref="tests/fixtures/SYNTHETIC_TEST_ONLY",
        )
        for index in range(count)
    )


def _synthetic_monthly_prices() -> dict[str, Decimal]:
    path = FIXTURES / "synthetic_world_bank_proxy.csv"
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows
    assert all(row["data_classification"] == "SYNTHETIC_TEST_ONLY" for row in rows)
    return {row["period"]: Decimal(row["price_usd_per_kg"]) for row in rows}


def _spread(*, observed_at: datetime | None = None) -> CallSpreadSpec:
    return CallSpreadSpec(
        observed_at_utc=observed_at or datetime(2026, 8, 21, 21, tzinfo=UTC),
        long_strike_usd_per_tonne=Decimal("5500"),
        short_strike_usd_per_tonne=Decimal("6350"),
        net_debit_usd_per_tonne=Decimal("320"),
    )


def test_expanding_q10_reversal_is_prior_only_and_uses_eligibility_time() -> None:
    releases = _synthetic_positioning_releases()
    evaluations = evaluate_cftc_reversal_rule(reversed(releases))
    assert len(evaluations) == len(releases) - MIN_PRIOR_RELEASES

    first = evaluations[0]
    assert first.prior_release_count == 156
    assert first.prior_q10 == Decimal("0.2")
    assert first.previous_normalized_net == Decimal("-0.2")
    assert first.normalized_net == Decimal("-0.1")
    assert first.signal_emitted
    assert first.availability_basis == "synthetic_weekly_schedule"

    second = evaluations[1]
    assert second.previous_was_q10_extreme
    assert second.positive_reversal
    assert not second.cooldown_eligible
    assert not second.signal_emitted

    signals = cftc_reversal_signals(releases)
    assert len(signals) == 2
    assert signals[1].available_at_utc - signals[0].available_at_utc == SIGNAL_COOLDOWN
    assert signals[0].availability_source_ref.endswith("SYNTHETIC_TEST_ONLY")


def test_signal_requires_156_strictly_prior_releases_and_aware_time() -> None:
    releases = _synthetic_positioning_releases()
    assert not evaluate_cftc_reversal_rule(releases[:MIN_PRIOR_RELEASES])
    summary = summarize_signal_study(releases[:MIN_PRIOR_RELEASES])
    assert summary.eligible_evaluation_count == 0
    assert any("Insufficient history" in warning for warning in summary.warnings)
    with pytest.raises(ValueError, match="timezone-aware"):
        PositioningRelease(
            report_date=date(2026, 1, 1),
            available_at_utc=datetime(2026, 1, 2, 20, 30),
            managed_money_net_contracts=0,
            open_interest_contracts=1_000,
        )


def test_public_proxy_uses_m_plus_1_to_m_plus_4_and_censors() -> None:
    prices = _synthetic_monthly_prices()
    outcomes = evaluate_public_proxy_events(
        (
            datetime(2020, 1, 17, 20, 30, tzinfo=UTC),
            datetime(2020, 8, 14, 20, 30, tzinfo=UTC),
            datetime(2020, 11, 13, 20, 30, tzinfo=UTC),
        ),
        prices,
        last_complete_period="2020-12",
    )
    assert outcomes[0].entry_period == "2020-02"
    assert outcomes[0].exit_period == "2020-05"
    assert outcomes[0].response_return == Decimal("0.20")
    assert outcomes[1].response_return == Decimal("0.10")
    assert outcomes[2].status == "CENSORED"
    assert outcomes[2].response_return is None
    assert outcomes[2].censor_reason == "exit period is after the declared last complete month"


def test_proxy_summary_bootstrap_is_deterministic_and_warns() -> None:
    outcomes = evaluate_public_proxy_events(
        (
            datetime(2020, 1, 17, 20, 30, tzinfo=UTC),
            datetime(2020, 8, 14, 20, 30, tzinfo=UTC),
            datetime(2020, 11, 13, 20, 30, tzinfo=UTC),
        ),
        _synthetic_monthly_prices(),
        last_complete_period="2020-12",
    )
    first = summarize_public_proxy_events(
        outcomes,
        bootstrap_iterations=500,
        bootstrap_block_length=2,
        bootstrap_seed=12345,
    )
    second = summarize_public_proxy_events(
        outcomes,
        bootstrap_iterations=500,
        bootstrap_block_length=2,
        bootstrap_seed=12345,
    )
    assert first == second
    assert first.total_event_count == 3
    assert first.complete_event_count == 2
    assert first.censored_event_count == 1
    assert first.mean_response_return == Decimal("0.15")
    assert first.positive_response_rate == Decimal(1)
    assert first.mean_block_bootstrap_95_interval is not None
    assert any("PUBLIC PROXY" in warning for warning in first.warnings)
    assert any("underpowered" in warning for warning in first.warnings)


def test_proxy_missing_endpoint_is_censored_not_dropped() -> None:
    prices = _synthetic_monthly_prices()
    del prices["2020-05"]
    outcomes = evaluate_public_proxy_events(
        (datetime(2020, 1, 17, 20, 30, tzinfo=UTC),),
        prices,
        last_complete_period="2020-12",
    )
    assert len(outcomes) == 1
    assert outcomes[0].status == "CENSORED"
    assert (
        outcomes[0].censor_reason == "exit-period proxy price is missing within declared coverage"
    )


def test_block_bootstrap_validates_parameters() -> None:
    with pytest.raises(ValueError, match="at least one"):
        circular_block_bootstrap_mean_interval(())
    with pytest.raises(ValueError, match="iterations"):
        circular_block_bootstrap_mean_interval((Decimal("0.1"),), iterations=0)


def test_call_spread_exact_expiry_payoff_and_scenarios() -> None:
    spec = _spread()
    assert spec.width_usd_per_tonne == Decimal("850")
    assert spec.breakeven_usd_per_tonne == Decimal("5820")
    assert spec.max_loss_per_contract_usd == Decimal("3200")
    assert spec.max_gain_per_contract_usd == Decimal("5300")

    below = call_spread_expiry_scenario(spec, Decimal("5000"))
    breakeven = call_spread_expiry_scenario(spec, Decimal("5820"))
    capped = call_spread_expiry_scenario(spec, Decimal("7000"))
    assert below.net_pnl_usd == Decimal("-3200")
    assert breakeven.net_pnl_usd == 0
    assert capped.net_pnl_usd == Decimal("5300")
    assert capped.gross_payoff_usd == Decimal("8500")
    assert len(standard_scenario_table(spec)) == 5


def test_risk_sizing_floors_whole_contracts_at_half_percent() -> None:
    result = size_by_max_loss(_spread(), Decimal("1000000"))
    assert result.risk_budget_usd == Decimal("5000.000")
    assert result.contracts == 1
    assert result.total_max_loss_usd == Decimal("3200")
    assert result.actual_portfolio_risk_fraction == Decimal("0.0032")
    assert result.unused_risk_budget_usd == Decimal("1800.000")
    with pytest.raises(ValueError, match="risk fraction"):
        size_by_max_loss(_spread(), Decimal("1000000"), risk_fraction=Decimal("0.006"))


def test_forward_candidate_rule_never_promotes_retrospective_design_data() -> None:
    retrospective_spec = _spread(observed_at=datetime(2026, 8, 20, 20, tzinfo=UTC))
    retrospective = evaluate_dec26_call_spread_rule(
        TradeRuleInputs(
            evaluated_at_utc=DESIGN_FREEZE_UTC,
            positioning_reversal_signal=True,
            registered_physical_deterioration=True,
            prior_20_session_high_confirmation=True,
            call_spread=retrospective_spec,
        )
    )
    assert retrospective.market_conditions_met
    assert not retrospective.forward_holdout_eligible
    assert not retrospective.hypothetical_candidate
    assert retrospective.status == "RETROSPECTIVE_ONLY"

    forward = evaluate_dec26_call_spread_rule(
        TradeRuleInputs(
            evaluated_at_utc=datetime(2026, 8, 21, 22, tzinfo=UTC),
            positioning_reversal_signal=True,
            registered_physical_deterioration=True,
            prior_20_session_high_confirmation=True,
            call_spread=_spread(),
        )
    )
    assert forward.hypothetical_candidate
    assert forward.status == "FORWARD_HYPOTHETICAL_CANDIDATE"
    assert any("no broker" in warning for warning in forward.warnings)


def test_registered_exit_policy_constants_and_conditions() -> None:
    assert MAX_HOLDING_TRADING_SESSIONS == 40
    assert EXIT_BEFORE_LAST_TRADING_DAY_SESSIONS == 10
    no_exit = evaluate_hypothetical_exit_policy(
        ExitPolicyInputs(
            evaluated_at_utc=datetime(2026, 9, 1, 20, tzinfo=UTC),
            trading_sessions_elapsed=12,
            trading_sessions_until_option_last_trading_day=30,
            entry_normalized_net=Decimal("-0.20"),
            current_normalized_net=Decimal("-0.10"),
        )
    )
    assert not no_exit.exit_due

    all_triggers = evaluate_hypothetical_exit_policy(
        ExitPolicyInputs(
            evaluated_at_utc=datetime(2026, 10, 1, 20, tzinfo=UTC),
            trading_sessions_elapsed=40,
            trading_sessions_until_option_last_trading_day=10,
            entry_normalized_net=Decimal("0.10"),
            current_normalized_net=Decimal("0.05"),
        )
    )
    assert all_triggers.exit_due
    assert all_triggers.reasons == (
        "40_trading_session_time_exit",
        "normalized_net_non_negative",
        "fresh_short_invalidation_below_entry_normalized_net",
        "ten_sessions_before_option_last_trading_day",
    )


def test_local_only_licensed_adapters_accept_only_explicit_synthetic_fixture() -> None:
    option_path = FIXTURES / "synthetic_dec26_call_chain.csv"
    with pytest.raises(ValueError, match="allow_synthetic"):
        load_dec26_option_chain(option_path)
    chain = load_dec26_option_chain(option_path, allow_synthetic=True)
    assert chain.data_classification == "SYNTHETIC_TEST_ONLY"
    assert re.fullmatch(r"[0-9a-f]{64}", chain.source_sha256)
    spec = select_registered_call_spread(chain, Decimal("5490"))
    assert spec.long_strike_usd_per_tonne == Decimal("5500")
    assert spec.short_strike_usd_per_tonne == Decimal("6350")
    assert spec.net_debit_usd_per_tonne == Decimal("320")

    settlement_path = FIXTURES / "synthetic_dec26_settlements.csv"
    with pytest.raises(ValueError, match="allow_synthetic"):
        load_dec26_settlements(settlement_path)
    series = load_dec26_settlements(settlement_path, allow_synthetic=True)
    assert len(series.settlements) == 21
    assert prior_20_session_high_confirmation(
        series.settlements,
        datetime(2026, 8, 17, 22, tzinfo=UTC),
    )
    with pytest.raises(ValueError, match="at least 21"):
        prior_20_session_high_confirmation(
            series.settlements,
            datetime(2026, 8, 14, 22, tzinfo=UTC),
        )


def test_all_committed_market_like_fixtures_are_conspicuously_synthetic() -> None:
    fixtures = tuple(FIXTURES.glob("*.csv"))
    assert fixtures
    assert all(path.name.startswith("synthetic_") for path in fixtures)
    for path in fixtures:
        with path.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        assert rows
        assert "data_classification" in rows[0]
        assert all(row["data_classification"] == "SYNTHETIC_TEST_ONLY" for row in rows)


def test_registered_evidence_gate_is_physical_only_and_expires() -> None:
    physical = PhysicalRevisionEvidence(
        surplus_deficit_revision_kt=Decimal("-27"),
        ending_stocks_revision_kt=Decimal("-27"),
        stocks_to_grindings_revision_percentage_points=Decimal("-0.7"),
        latest_available_at_utc=datetime(2026, 5, 29, 23, 59, 59, tzinfo=UTC),
        evaluated_at_utc=datetime(2026, 8, 20, 12, 57, 28, tzinfo=UTC),
    )
    decision = evaluate_evidence_deterioration(physical)
    assert decision.physical_deterioration
    assert decision.registered_evidence_deterioration
    assert decision.weather_context_status == "CONTEXT_ONLY_NOT_REGISTERED_V1"
    assert decision.reasons == (
        "official_surplus_revision_down_at_least_25kt",
        "official_ending_stocks_revision_down_at_least_25kt",
        "official_stocks_to_grindings_revision_down_at_least_0_5pp",
    )
    assert any("Weather is context-only" in warning for warning in decision.warnings)

    stale_physical = PhysicalRevisionEvidence(
        surplus_deficit_revision_kt=Decimal("-100"),
        ending_stocks_revision_kt=Decimal("-100"),
        stocks_to_grindings_revision_percentage_points=Decimal("-2"),
        latest_available_at_utc=datetime(2026, 1, 1, tzinfo=UTC),
        evaluated_at_utc=datetime(2026, 8, 20, tzinfo=UTC),
    )
    stale = evaluate_evidence_deterioration(stale_physical)
    assert not stale.registered_evidence_deterioration
    assert any("120-day freshness" in warning for warning in stale.warnings)


def test_call_spread_fees_are_included_in_risk_and_payoff() -> None:
    spec = CallSpreadSpec(
        observed_at_utc=datetime(2026, 8, 20, 20, tzinfo=UTC),
        long_strike_usd_per_tonne=Decimal("5500"),
        short_strike_usd_per_tonne=Decimal("6350"),
        net_debit_usd_per_tonne=Decimal("300"),
        round_trip_fees_usd_per_contract=Decimal("20"),
    )
    assert spec.breakeven_usd_per_tonne == Decimal("5802")
    assert spec.max_loss_per_contract_usd == Decimal("3020")
    assert spec.max_gain_per_contract_usd == Decimal("5480")
    assert call_spread_expiry_scenario(spec, Decimal("4500")).net_pnl_usd == Decimal("-3020")
