"""Defined-risk, hypothetical Dec-26 cocoa call-spread research mechanics.

This module calculates candidate structure economics only.  It contains no order
routing, broker connection, live market-data client, or instruction to trade.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import ROUND_FLOOR, Decimal, InvalidOperation
from typing import Final, TypeAlias

DEC26_CONTRACT_LABEL: Final = "Dec-26"
CONTRACT_SIZE_METRIC_TONNES: Final = Decimal("10")
MAX_PORTFOLIO_RISK_FRACTION: Final = Decimal("0.005")
MAX_DEBIT_FRACTION_OF_WIDTH: Final = Decimal("0.40")
DESIGN_FREEZE_UTC: Final = datetime(2026, 8, 20, 23, 59, 59, 999999, tzinfo=UTC)
TRADE_RULE_ID: Final = "hypothetical_dec26_call_spread_v1"
MAX_HOLDING_TRADING_SESSIONS: Final = 40
EXIT_BEFORE_LAST_TRADING_DAY_SESSIONS: Final = 10
EVIDENCE_GATE_RULE_ID: Final = "physical_deterioration_v1"
PHYSICAL_SURPLUS_DECLINE_KT: Final = Decimal("25")
PHYSICAL_ENDING_STOCKS_DECLINE_KT: Final = Decimal("25")
PHYSICAL_STOCKS_TO_GRIND_DECLINE_PP: Final = Decimal("0.5")
PHYSICAL_MAX_AGE: Final = timedelta(days=120)

Numeric: TypeAlias = Decimal | int | float | str


def _as_decimal(value: Numeric, *, label: str) -> Decimal:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be numeric, not boolean")
    try:
        parsed = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{label} is not a valid decimal: {value!r}") from exc
    if not parsed.is_finite():
        raise ValueError(f"{label} must be finite")
    return parsed


def _normalise_utc(value: datetime, *, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")
    return value.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class CallSpreadSpec:
    """Exact economics for one hypothetical European-style call spread.

    Premiums and strikes are in USD per metric tonne.  ICE cocoa futures use ten
    metric tonnes per contract; the size remains an explicit field for audit.
    """

    observed_at_utc: datetime
    long_strike_usd_per_tonne: Decimal
    short_strike_usd_per_tonne: Decimal
    net_debit_usd_per_tonne: Decimal
    round_trip_fees_usd_per_contract: Decimal = Decimal(0)
    contracts: int = 1
    contract_size_metric_tonnes: Decimal = CONTRACT_SIZE_METRIC_TONNES
    contract_label: str = DEC26_CONTRACT_LABEL
    hypothetical: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "observed_at_utc",
            _normalise_utc(self.observed_at_utc, label="observed_at_utc"),
        )
        for field_name in (
            "long_strike_usd_per_tonne",
            "short_strike_usd_per_tonne",
            "net_debit_usd_per_tonne",
            "round_trip_fees_usd_per_contract",
            "contract_size_metric_tonnes",
        ):
            object.__setattr__(
                self,
                field_name,
                _as_decimal(getattr(self, field_name), label=field_name),
            )
        if self.contract_label != DEC26_CONTRACT_LABEL:
            raise ValueError(f"contract label must be {DEC26_CONTRACT_LABEL!r}")
        if not self.hypothetical:
            raise ValueError("this public module accepts hypothetical structures only")
        if isinstance(self.contracts, bool) or not isinstance(self.contracts, int):
            raise ValueError("contracts must be an integer")
        if self.contracts < 1:
            raise ValueError("contracts must be positive")
        if self.long_strike_usd_per_tonne <= 0:
            raise ValueError("long strike must be positive")
        if self.short_strike_usd_per_tonne <= self.long_strike_usd_per_tonne:
            raise ValueError("short strike must be above long strike")
        if self.net_debit_usd_per_tonne <= 0:
            raise ValueError("net debit must be positive")
        if self.net_debit_usd_per_tonne >= self.width_usd_per_tonne:
            raise ValueError("net debit must be smaller than spread width")
        if self.round_trip_fees_usd_per_contract < 0:
            raise ValueError("round-trip fees cannot be negative")
        if self.contract_size_metric_tonnes <= 0:
            raise ValueError("contract size must be positive")

    @property
    def width_usd_per_tonne(self) -> Decimal:
        return self.short_strike_usd_per_tonne - self.long_strike_usd_per_tonne

    @property
    def debit_fraction_of_width(self) -> Decimal:
        return self.net_debit_usd_per_tonne / self.width_usd_per_tonne

    @property
    def breakeven_usd_per_tonne(self) -> Decimal:
        return (
            self.long_strike_usd_per_tonne
            + self.net_debit_usd_per_tonne
            + self.round_trip_fees_usd_per_contract / self.contract_size_metric_tonnes
        )

    @property
    def max_loss_per_contract_usd(self) -> Decimal:
        return (
            self.net_debit_usd_per_tonne * self.contract_size_metric_tonnes
            + self.round_trip_fees_usd_per_contract
        )

    @property
    def max_gain_per_contract_usd(self) -> Decimal:
        return (
            self.width_usd_per_tonne - self.net_debit_usd_per_tonne
        ) * self.contract_size_metric_tonnes - self.round_trip_fees_usd_per_contract

    @property
    def total_max_loss_usd(self) -> Decimal:
        return self.max_loss_per_contract_usd * Decimal(self.contracts)

    @property
    def total_max_gain_usd(self) -> Decimal:
        return self.max_gain_per_contract_usd * Decimal(self.contracts)


@dataclass(frozen=True, slots=True)
class CallSpreadScenario:
    """Exact expiry payoff and net P&L at one futures settlement level."""

    expiry_futures_price_usd_per_tonne: Decimal
    long_call_intrinsic_usd_per_tonne: Decimal
    short_call_intrinsic_usd_per_tonne: Decimal
    spread_payoff_usd_per_tonne: Decimal
    premium_paid_usd: Decimal
    gross_payoff_usd: Decimal
    round_trip_fees_usd: Decimal
    net_pnl_usd: Decimal
    state: str


def call_spread_expiry_scenario(
    spec: CallSpreadSpec,
    expiry_futures_price_usd_per_tonne: Numeric,
) -> CallSpreadScenario:
    """Calculate exact intrinsic payoff and net P&L at option expiry.

    ``PnL = contracts * (tonnes * (max(F-K1, 0) - max(F-K2, 0) - debit) - fees)``.
    This excludes taxes, margin interest, early-exit slippage, and any option exercise
    or assignment operational costs.
    """

    expiry_price = _as_decimal(
        expiry_futures_price_usd_per_tonne,
        label="expiry futures price",
    )
    if expiry_price < 0:
        raise ValueError("expiry futures price cannot be negative")
    long_intrinsic = max(expiry_price - spec.long_strike_usd_per_tonne, Decimal(0))
    short_intrinsic = max(expiry_price - spec.short_strike_usd_per_tonne, Decimal(0))
    spread_payoff = long_intrinsic - short_intrinsic
    multiplier = spec.contract_size_metric_tonnes * Decimal(spec.contracts)
    premium_paid = spec.net_debit_usd_per_tonne * multiplier
    gross_payoff = spread_payoff * multiplier
    fees = spec.round_trip_fees_usd_per_contract * Decimal(spec.contracts)
    pnl = gross_payoff - premium_paid - fees
    if expiry_price < spec.long_strike_usd_per_tonne:
        state = "below_long_strike"
    elif expiry_price < spec.breakeven_usd_per_tonne:
        state = "between_long_and_breakeven"
    elif expiry_price < spec.short_strike_usd_per_tonne:
        state = "between_breakeven_and_short"
    else:
        state = "at_or_above_short_strike"
    return CallSpreadScenario(
        expiry_futures_price_usd_per_tonne=expiry_price,
        long_call_intrinsic_usd_per_tonne=long_intrinsic,
        short_call_intrinsic_usd_per_tonne=short_intrinsic,
        spread_payoff_usd_per_tonne=spread_payoff,
        premium_paid_usd=premium_paid,
        gross_payoff_usd=gross_payoff,
        round_trip_fees_usd=fees,
        net_pnl_usd=pnl,
        state=state,
    )


def scenario_table(
    spec: CallSpreadSpec,
    expiry_futures_prices_usd_per_tonne: Iterable[Numeric],
) -> tuple[CallSpreadScenario, ...]:
    """Build a sorted, duplicate-free table of exact expiry scenarios."""

    prices = {
        _as_decimal(value, label="scenario expiry futures price")
        for value in expiry_futures_prices_usd_per_tonne
    }
    if not prices:
        raise ValueError("at least one scenario price is required")
    return tuple(call_spread_expiry_scenario(spec, value) for value in sorted(prices))


def standard_scenario_table(spec: CallSpreadSpec) -> tuple[CallSpreadScenario, ...]:
    """Return five transparent anchor scenarios, including exact breakeven."""

    quarter_width = spec.width_usd_per_tonne / Decimal(4)
    return scenario_table(
        spec,
        (
            max(Decimal(0), spec.long_strike_usd_per_tonne - quarter_width),
            spec.long_strike_usd_per_tonne,
            spec.breakeven_usd_per_tonne,
            spec.short_strike_usd_per_tonne,
            spec.short_strike_usd_per_tonne + quarter_width,
        ),
    )


@dataclass(frozen=True, slots=True)
class RiskSizingResult:
    """Whole-contract size under a fixed maximum-loss budget."""

    portfolio_value_usd: Decimal
    risk_fraction: Decimal
    risk_budget_usd: Decimal
    max_loss_per_contract_usd: Decimal
    contracts: int
    total_max_loss_usd: Decimal
    actual_portfolio_risk_fraction: Decimal
    unused_risk_budget_usd: Decimal


@dataclass(frozen=True, slots=True)
class PhysicalRevisionEvidence:
    """Latest-vs-prior official balance revision used by the frozen evidence gate."""

    surplus_deficit_revision_kt: Decimal
    ending_stocks_revision_kt: Decimal
    stocks_to_grindings_revision_percentage_points: Decimal
    latest_available_at_utc: datetime
    evaluated_at_utc: datetime

    def __post_init__(self) -> None:
        for field_name in (
            "surplus_deficit_revision_kt",
            "ending_stocks_revision_kt",
            "stocks_to_grindings_revision_percentage_points",
        ):
            object.__setattr__(
                self,
                field_name,
                _as_decimal(getattr(self, field_name), label=field_name),
            )
        for field_name in ("latest_available_at_utc", "evaluated_at_utc"):
            object.__setattr__(
                self,
                field_name,
                _normalise_utc(getattr(self, field_name), label=field_name),
            )
        if self.latest_available_at_utc > self.evaluated_at_utc:
            raise ValueError("physical revision is unavailable at the evaluation time")


@dataclass(frozen=True, slots=True)
class EvidenceGateDecision:
    """Deterministic evidence state; never a price forecast or trading action."""

    rule_id: str
    physical_deterioration: bool
    registered_evidence_deterioration: bool
    weather_context_status: str
    reasons: tuple[str, ...]
    warnings: tuple[str, ...]


def evaluate_evidence_deterioration(
    physical: PhysicalRevisionEvidence,
) -> EvidenceGateDecision:
    """Evaluate the exact version-1 physical deterioration state.

    Thresholds are frozen design-era hypotheses. They are not calibrated yield or price
    coefficients. Weather remains context-only in version 1 and cannot activate the gate.
    """

    reasons: list[str] = []
    warnings: list[str] = [
        "Thresholds were selected during the retrospective design period and are not evidence of alpha."
    ]
    physical_current = (
        physical.evaluated_at_utc - physical.latest_available_at_utc <= PHYSICAL_MAX_AGE
    )
    if not physical_current:
        warnings.append("latest physical revision is older than the 120-day freshness limit")
    if physical_current:
        if physical.surplus_deficit_revision_kt <= -PHYSICAL_SURPLUS_DECLINE_KT:
            reasons.append("official_surplus_revision_down_at_least_25kt")
        if physical.ending_stocks_revision_kt <= -PHYSICAL_ENDING_STOCKS_DECLINE_KT:
            reasons.append("official_ending_stocks_revision_down_at_least_25kt")
        if (
            physical.stocks_to_grindings_revision_percentage_points
            <= -PHYSICAL_STOCKS_TO_GRIND_DECLINE_PP
        ):
            reasons.append("official_stocks_to_grindings_revision_down_at_least_0_5pp")
    physical_triggered = bool(reasons)

    warnings.append(
        "Weather is context-only and ineligible for the version-1 trade gate; a separately "
        "frozen rule and independent dataset are required."
    )
    return EvidenceGateDecision(
        rule_id=EVIDENCE_GATE_RULE_ID,
        physical_deterioration=physical_triggered,
        registered_evidence_deterioration=physical_triggered,
        weather_context_status="CONTEXT_ONLY_NOT_REGISTERED_V1",
        reasons=tuple(reasons),
        warnings=tuple(dict.fromkeys(warnings)),
    )


def size_by_max_loss(
    spec: CallSpreadSpec,
    portfolio_value_usd: Numeric,
    *,
    risk_fraction: Numeric = MAX_PORTFOLIO_RISK_FRACTION,
) -> RiskSizingResult:
    """Floor to whole contracts so premium-at-risk never exceeds the budget."""

    portfolio = _as_decimal(portfolio_value_usd, label="portfolio value")
    fraction = _as_decimal(risk_fraction, label="risk fraction")
    if portfolio <= 0:
        raise ValueError("portfolio value must be positive")
    if not Decimal(0) < fraction <= MAX_PORTFOLIO_RISK_FRACTION:
        raise ValueError(f"risk fraction must be in (0, {MAX_PORTFOLIO_RISK_FRACTION}]")
    budget = portfolio * fraction
    per_contract = spec.max_loss_per_contract_usd
    contracts = int((budget / per_contract).to_integral_value(rounding=ROUND_FLOOR))
    total_risk = per_contract * Decimal(contracts)
    return RiskSizingResult(
        portfolio_value_usd=portfolio,
        risk_fraction=fraction,
        risk_budget_usd=budget,
        max_loss_per_contract_usd=per_contract,
        contracts=contracts,
        total_max_loss_usd=total_risk,
        actual_portfolio_risk_fraction=total_risk / portfolio,
        unused_risk_budget_usd=budget - total_risk,
    )


@dataclass(frozen=True, slots=True)
class ExitPolicyInputs:
    """One eligible-close snapshot for the frozen hypothetical exit policy."""

    evaluated_at_utc: datetime
    trading_sessions_elapsed: int
    trading_sessions_until_option_last_trading_day: int
    entry_normalized_net: Decimal
    current_normalized_net: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "evaluated_at_utc",
            _normalise_utc(self.evaluated_at_utc, label="evaluated_at_utc"),
        )
        for field_name in ("entry_normalized_net", "current_normalized_net"):
            value = _as_decimal(getattr(self, field_name), label=field_name)
            if not Decimal(-1) <= value <= Decimal(1):
                raise ValueError(f"{field_name} must be in [-1, 1]")
            object.__setattr__(self, field_name, value)
        for field_name in (
            "trading_sessions_elapsed",
            "trading_sessions_until_option_last_trading_day",
        ):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")


@dataclass(frozen=True, slots=True)
class ExitPolicyDecision:
    """Exit-state audit result; it does not create or submit an order."""

    evaluated_at_utc: datetime
    exit_due: bool
    reasons: tuple[str, ...]


def evaluate_hypothetical_exit_policy(inputs: ExitPolicyInputs) -> ExitPolicyDecision:
    """Evaluate the four frozen exit conditions at one eligible close.

    Calling this function sequentially at each close makes the first ``exit_due``
    observation the registered exit.  The function has no execution side effect.
    """

    reasons: list[str] = []
    if inputs.trading_sessions_elapsed >= MAX_HOLDING_TRADING_SESSIONS:
        reasons.append("40_trading_session_time_exit")
    if inputs.current_normalized_net >= 0:
        reasons.append("normalized_net_non_negative")
    if inputs.current_normalized_net < inputs.entry_normalized_net:
        reasons.append("fresh_short_invalidation_below_entry_normalized_net")
    if (
        inputs.trading_sessions_until_option_last_trading_day
        <= EXIT_BEFORE_LAST_TRADING_DAY_SESSIONS
    ):
        reasons.append("ten_sessions_before_option_last_trading_day")
    return ExitPolicyDecision(
        evaluated_at_utc=inputs.evaluated_at_utc,
        exit_due=bool(reasons),
        reasons=tuple(reasons),
    )


@dataclass(frozen=True, slots=True)
class TradeRuleInputs:
    """Auditable conditions for the frozen hypothetical structure rule."""

    evaluated_at_utc: datetime
    positioning_reversal_signal: bool
    registered_physical_deterioration: bool
    prior_20_session_high_confirmation: bool
    call_spread: CallSpreadSpec | None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "evaluated_at_utc",
            _normalise_utc(self.evaluated_at_utc, label="evaluated_at_utc"),
        )
        if (
            self.call_spread is not None
            and self.call_spread.observed_at_utc > self.evaluated_at_utc
        ):
            raise ValueError("call-spread snapshot is not available at the evaluation time")


@dataclass(frozen=True, slots=True)
class TradeRuleDecision:
    """Research decision label; never an order or recommendation."""

    rule_id: str
    status: str
    evaluated_at_utc: datetime
    market_conditions_met: bool
    forward_holdout_eligible: bool
    hypothetical_candidate: bool
    debit_fraction_of_width: Decimal | None
    failed_conditions: tuple[str, ...]
    warnings: tuple[str, ...]


def evaluate_dec26_call_spread_rule(inputs: TradeRuleInputs) -> TradeRuleDecision:
    """Evaluate the registered candidate rule without performing any action."""

    failures: list[str] = []
    if not inputs.positioning_reversal_signal:
        failures.append("no registered CFTC positioning-reversal signal")
    if not inputs.registered_physical_deterioration:
        failures.append("no registered physical-balance deterioration state")
    if not inputs.prior_20_session_high_confirmation:
        failures.append("Dec-26 future has not exceeded its prior 20 available settlements")

    debit_fraction: Decimal | None = None
    if inputs.call_spread is None:
        failures.append("licensed Dec-26 option-chain snapshot not supplied")
    else:
        debit_fraction = inputs.call_spread.debit_fraction_of_width
        if debit_fraction > MAX_DEBIT_FRACTION_OF_WIDTH:
            failures.append(
                f"conservative debit exceeds {MAX_DEBIT_FRACTION_OF_WIDTH:.0%} of spread width"
            )

    conditions_met = not failures
    forward_eligible = inputs.evaluated_at_utc > DESIGN_FREEZE_UTC
    candidate = conditions_met and forward_eligible
    if inputs.call_spread is None:
        status = "NOT_EVALUATED_LICENSED_MARKET_INPUTS"
    elif not forward_eligible:
        status = "RETROSPECTIVE_ONLY"
    elif candidate:
        status = "FORWARD_HYPOTHETICAL_CANDIDATE"
    else:
        status = "NO_CANDIDATE"
    return TradeRuleDecision(
        rule_id=TRADE_RULE_ID,
        status=status,
        evaluated_at_utc=inputs.evaluated_at_utc,
        market_conditions_met=conditions_met,
        forward_holdout_eligible=forward_eligible,
        hypothetical_candidate=candidate,
        debit_fraction_of_width=debit_fraction,
        failed_conditions=tuple(failures),
        warnings=(
            "HYPOTHETICAL RESEARCH ONLY — no broker connection, order, or trade recommendation.",
            "Option quotes and futures settlements must come from a permitted licensed snapshot.",
            "Sizing caps premium at risk at 0.5% but does not model all operational or liquidity risks.",
            "Only evaluations after 2026-08-20 belong to the registered forward holdout.",
        ),
    )
