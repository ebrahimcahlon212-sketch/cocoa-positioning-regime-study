"""Pre-registered point-in-time signals and a public-price proxy event study.

The functions in this module are deliberately independent of execution or broker
systems.  CFTC releases are ordered by point-in-time eligibility timestamps.  Those
timestamps are retained actual publication times where available and explicitly
rule-modelled publication times otherwise.  All thresholds use earlier releases only.
"""

from __future__ import annotations

import random
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_CEILING, Decimal, InvalidOperation
from typing import Final, Literal, Protocol, TypeAlias

MIN_PRIOR_RELEASES: Final = 156
Q10: Final = Decimal("0.10")
SIGNAL_COOLDOWN: Final = timedelta(weeks=13)
SIGNAL_RULE_ID: Final = "cftc_normalized_net_q10_reversal_v1"
PRIMARY_PROXY_RESPONSE: Final = "world_bank_monthly_proxy_m_plus_1_to_m_plus_4"
DEFAULT_BOOTSTRAP_SEED: Final = 20_260_820
DEFAULT_BOOTSTRAP_ITERATIONS: Final = 10_000
DEFAULT_BOOTSTRAP_BLOCK_LENGTH: Final = 4

Numeric: TypeAlias = Decimal | int | float | str
OutcomeStatus: TypeAlias = Literal["COMPLETE", "CENSORED"]


class CftcObservationLike(Protocol):
    """Structural type needed to adapt the existing pipeline observations."""

    report_date: date
    available_at_utc: datetime
    managed_money_net_contracts: int
    open_interest_contracts: int
    availability_basis: str
    availability_source_id: str


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
class PositioningRelease:
    """Minimal CFTC release record needed by the signal rule."""

    report_date: date
    available_at_utc: datetime
    managed_money_net_contracts: int
    open_interest_contracts: int
    source_ref: str = ""
    availability_basis: str = ""
    availability_source_ref: str = ""

    def __post_init__(self) -> None:
        if isinstance(self.managed_money_net_contracts, bool):
            raise ValueError("managed-money net contracts must be an integer")
        if isinstance(self.open_interest_contracts, bool) or self.open_interest_contracts <= 0:
            raise ValueError("open interest must be a positive integer")
        if abs(self.managed_money_net_contracts) > self.open_interest_contracts:
            raise ValueError("absolute managed-money net cannot exceed open interest")
        object.__setattr__(
            self,
            "available_at_utc",
            _normalise_utc(self.available_at_utc, label="available_at_utc"),
        )

    @property
    def normalized_net(self) -> Decimal:
        """Managed-money net contracts divided by total open interest."""

        return Decimal(self.managed_money_net_contracts) / Decimal(self.open_interest_contracts)


@dataclass(frozen=True, slots=True)
class PositioningEvaluation:
    """One eligible release evaluated against the frozen signal rule."""

    rule_id: str
    report_date: date
    available_at_utc: datetime
    prior_release_count: int
    normalized_net: Decimal
    previous_normalized_net: Decimal
    prior_q10: Decimal
    previous_was_q10_extreme: bool
    positive_reversal: bool
    cooldown_eligible: bool
    signal_emitted: bool
    availability_basis: str
    availability_source_ref: str


@dataclass(frozen=True, slots=True)
class PositioningSignal:
    """A signal emitted at the current release's point-in-time eligibility time."""

    rule_id: str
    report_date: date
    available_at_utc: datetime
    prior_release_count: int
    normalized_net: Decimal
    previous_normalized_net: Decimal
    prior_q10: Decimal
    availability_basis: str
    availability_source_ref: str


@dataclass(frozen=True, slots=True)
class SignalStudySummary:
    """Compact, serialization-friendly signal diagnostic."""

    rule_id: str
    release_count: int
    eligible_evaluation_count: int
    signal_count: int
    latest_available_at_utc: datetime | None
    latest_normalized_net: Decimal | None
    latest_prior_q10: Decimal | None
    latest_signal_at_utc: datetime | None
    warnings: tuple[str, ...]


def adapt_cftc_observations(
    observations: Iterable[CftcObservationLike],
) -> tuple[PositioningRelease, ...]:
    """Adapt existing pipeline observations without weakening timestamp semantics."""

    return tuple(
        PositioningRelease(
            report_date=item.report_date,
            available_at_utc=item.available_at_utc,
            managed_money_net_contracts=item.managed_money_net_contracts,
            open_interest_contracts=item.open_interest_contracts,
            source_ref=f"CFTC:{item.report_date.isoformat()}",
            availability_basis=item.availability_basis,
            availability_source_ref=item.availability_source_id,
        )
        for item in observations
    )


def empirical_nearest_rank(values: Sequence[Decimal], quantile: Decimal) -> Decimal:
    """Return the empirical nearest-rank quantile with no interpolation."""

    if not values:
        raise ValueError("at least one value is required")
    if not Decimal(0) < quantile <= Decimal(1):
        raise ValueError("quantile must be in (0, 1]")
    ordered = sorted(values)
    rank = int((Decimal(len(ordered)) * quantile).to_integral_value(rounding=ROUND_CEILING))
    return ordered[max(rank, 1) - 1]


def _ordered_releases(
    releases: Iterable[PositioningRelease],
) -> tuple[PositioningRelease, ...]:
    ordered = tuple(sorted(releases, key=lambda item: item.available_at_utc))
    timestamps = [item.available_at_utc for item in ordered]
    if len(timestamps) != len(set(timestamps)):
        raise ValueError("CFTC releases must have unique eligibility timestamps")
    report_dates = [item.report_date for item in ordered]
    if len(report_dates) != len(set(report_dates)):
        raise ValueError("CFTC releases must have unique report dates")
    return ordered


def evaluate_cftc_reversal_rule(
    releases: Iterable[PositioningRelease],
) -> tuple[PositioningEvaluation, ...]:
    """Evaluate the fixed expanding-window Q10 reversal rule.

    At release ``t``, ``Q10_t`` uses all normalized-net observations whose eligibility
    timestamp is strictly earlier than ``t``.  A timestamp is retained actual
    publication time where available and explicitly rule-modelled otherwise.  A signal
    is eligible only when there are at least 156 prior releases,
    ``x_(t-1) <= Q10_t``, and ``x_t > x_(t-1)``.  An emitted signal starts a 91-day
    cooldown measured on those point-in-time eligibility timestamps.
    """

    ordered = _ordered_releases(releases)
    normalized = tuple(item.normalized_net for item in ordered)
    evaluations: list[PositioningEvaluation] = []
    last_signal_at: datetime | None = None

    for index in range(MIN_PRIOR_RELEASES, len(ordered)):
        current = ordered[index]
        prior_q10 = empirical_nearest_rank(normalized[:index], Q10)
        previous = normalized[index - 1]
        current_value = normalized[index]
        previous_was_extreme = previous <= prior_q10
        positive_reversal = current_value > previous
        cooldown_eligible = (
            last_signal_at is None or current.available_at_utc - last_signal_at >= SIGNAL_COOLDOWN
        )
        emitted = previous_was_extreme and positive_reversal and cooldown_eligible
        if emitted:
            last_signal_at = current.available_at_utc
        evaluations.append(
            PositioningEvaluation(
                rule_id=SIGNAL_RULE_ID,
                report_date=current.report_date,
                available_at_utc=current.available_at_utc,
                prior_release_count=index,
                normalized_net=current_value,
                previous_normalized_net=previous,
                prior_q10=prior_q10,
                previous_was_q10_extreme=previous_was_extreme,
                positive_reversal=positive_reversal,
                cooldown_eligible=cooldown_eligible,
                signal_emitted=emitted,
                availability_basis=current.availability_basis,
                availability_source_ref=current.availability_source_ref,
            )
        )
    return tuple(evaluations)


def cftc_reversal_signals(
    releases: Iterable[PositioningRelease],
) -> tuple[PositioningSignal, ...]:
    """Return only emitted signals from :func:`evaluate_cftc_reversal_rule`."""

    return tuple(
        PositioningSignal(
            rule_id=item.rule_id,
            report_date=item.report_date,
            available_at_utc=item.available_at_utc,
            prior_release_count=item.prior_release_count,
            normalized_net=item.normalized_net,
            previous_normalized_net=item.previous_normalized_net,
            prior_q10=item.prior_q10,
            availability_basis=item.availability_basis,
            availability_source_ref=item.availability_source_ref,
        )
        for item in evaluate_cftc_reversal_rule(releases)
        if item.signal_emitted
    )


def summarize_signal_study(
    releases: Iterable[PositioningRelease],
) -> SignalStudySummary:
    """Summarize coverage without turning a retrospective test into an alpha claim."""

    ordered = _ordered_releases(releases)
    evaluations = evaluate_cftc_reversal_rule(ordered)
    signals = tuple(item for item in evaluations if item.signal_emitted)
    latest = evaluations[-1] if evaluations else None
    warnings = [
        "RETROSPECTIVE / PSEUDO-OUT-OF-SAMPLE: thresholds expand through historical releases.",
        "No result before 2026-08-21 is evidence from the registered forward holdout.",
        "CFTC availability timing is controlled, but annual archives are not full value-vintage histories.",
        "A positioning event is a research condition, not a trading instruction or an alpha claim.",
    ]
    if len(ordered) < MIN_PRIOR_RELEASES + 1:
        warnings.append(
            f"Insufficient history: at least {MIN_PRIOR_RELEASES + 1} releases are needed "
            "for one eligible evaluation."
        )
    return SignalStudySummary(
        rule_id=SIGNAL_RULE_ID,
        release_count=len(ordered),
        eligible_evaluation_count=len(evaluations),
        signal_count=len(signals),
        latest_available_at_utc=ordered[-1].available_at_utc if ordered else None,
        latest_normalized_net=latest.normalized_net if latest else None,
        latest_prior_q10=latest.prior_q10 if latest else None,
        latest_signal_at_utc=signals[-1].available_at_utc if signals else None,
        warnings=tuple(warnings),
    )


_MONTH_PATTERN: Final = re.compile(r"^(?P<year>[0-9]{4})-(?P<month>0[1-9]|1[0-2])$")


def _parse_month(period: str) -> tuple[int, int]:
    match = _MONTH_PATTERN.fullmatch(period)
    if match is None:
        raise ValueError(f"month must use YYYY-MM: {period!r}")
    return int(match.group("year")), int(match.group("month"))


def _month_number(period: str) -> int:
    year, month = _parse_month(period)
    return year * 12 + month - 1


def _format_month(month_number: int) -> str:
    if month_number < 0:
        raise ValueError("month is outside the supported range")
    year, zero_based_month = divmod(month_number, 12)
    return f"{year:04d}-{zero_based_month + 1:02d}"


def month_offset(period: str, months: int) -> str:
    """Shift a YYYY-MM period by an integer number of months."""

    if isinstance(months, bool) or not isinstance(months, int):
        raise ValueError("months must be an integer")
    return _format_month(_month_number(period) + months)


def _normalise_monthly_prices(
    monthly_prices: Mapping[str, Numeric],
) -> dict[str, Decimal]:
    if not monthly_prices:
        raise ValueError("monthly price mapping is empty")
    normalised: dict[str, Decimal] = {}
    for period, raw_price in monthly_prices.items():
        _parse_month(period)
        price = _as_decimal(raw_price, label=f"price[{period}]")
        if price <= 0:
            raise ValueError(f"price[{period}] must be positive")
        normalised[period] = price
    return normalised


@dataclass(frozen=True, slots=True)
class ProxyEventOutcome:
    """One monthly public-proxy outcome; incomplete endpoints remain explicit."""

    response_id: str
    signal_available_at_utc: datetime
    event_period: str
    entry_period: str
    exit_period: str
    status: OutcomeStatus
    entry_price: Decimal | None
    exit_price: Decimal | None
    response_return: Decimal | None
    censor_reason: str | None


@dataclass(frozen=True, slots=True)
class BootstrapInterval:
    confidence_level: Decimal
    lower: Decimal
    upper: Decimal
    iterations: int
    requested_block_length: int
    effective_block_length: int
    seed: int


@dataclass(frozen=True, slots=True)
class ProxyEventStudySummary:
    """Aggregate public-proxy statistics with mandatory research warnings."""

    response_id: str
    total_event_count: int
    complete_event_count: int
    censored_event_count: int
    mean_response_return: Decimal | None
    median_response_return: Decimal | None
    positive_response_rate: Decimal | None
    mean_block_bootstrap_95_interval: BootstrapInterval | None
    warnings: tuple[str, ...]


def evaluate_public_proxy_events(
    signal_available_times: Iterable[datetime],
    monthly_prices: Mapping[str, Numeric],
    *,
    last_complete_period: str | None = None,
) -> tuple[ProxyEventOutcome, ...]:
    """Evaluate the pre-registered World Bank monthly ``m+1`` to ``m+4`` response.

    The World Bank benchmark is a monthly, non-tradable public proxy.  The entry
    endpoint is the monthly observation one month after the signal month and the
    exit endpoint is the observation four months after it.  A missing or not-yet-
    complete endpoint is retained as a censored outcome rather than dropped.
    """

    prices = _normalise_monthly_prices(monthly_prices)
    price_periods = sorted(prices, key=_month_number)
    cutoff = last_complete_period or price_periods[-1]
    _parse_month(cutoff)
    cutoff_number = _month_number(cutoff)
    times = tuple(
        sorted(
            _normalise_utc(value, label="signal availability timestamp")
            for value in signal_available_times
        )
    )
    if len(times) != len(set(times)):
        raise ValueError("signal availability timestamps must be unique")

    outcomes: list[ProxyEventOutcome] = []
    for signal_at in times:
        event_period = f"{signal_at.year:04d}-{signal_at.month:02d}"
        entry_period = month_offset(event_period, 1)
        exit_period = month_offset(event_period, 4)
        entry_price = prices.get(entry_period)
        exit_price = prices.get(exit_period)
        censor_reason: str | None = None
        if _month_number(exit_period) > cutoff_number:
            censor_reason = "exit period is after the declared last complete month"
        elif entry_price is None:
            censor_reason = "entry-period proxy price is missing within declared coverage"
        elif exit_price is None:
            censor_reason = "exit-period proxy price is missing within declared coverage"

        if censor_reason is not None:
            outcomes.append(
                ProxyEventOutcome(
                    response_id=PRIMARY_PROXY_RESPONSE,
                    signal_available_at_utc=signal_at,
                    event_period=event_period,
                    entry_period=entry_period,
                    exit_period=exit_period,
                    status="CENSORED",
                    entry_price=entry_price,
                    exit_price=exit_price,
                    response_return=None,
                    censor_reason=censor_reason,
                )
            )
            continue

        if entry_price is None or exit_price is None:  # pragma: no cover - narrowed above
            raise AssertionError("complete proxy outcome is missing an endpoint")
        outcomes.append(
            ProxyEventOutcome(
                response_id=PRIMARY_PROXY_RESPONSE,
                signal_available_at_utc=signal_at,
                event_period=event_period,
                entry_period=entry_period,
                exit_period=exit_period,
                status="COMPLETE",
                entry_price=entry_price,
                exit_price=exit_price,
                response_return=exit_price / entry_price - Decimal(1),
                censor_reason=None,
            )
        )
    return tuple(outcomes)


def _mean(values: Sequence[Decimal]) -> Decimal:
    if not values:
        raise ValueError("mean requires at least one value")
    return sum(values, start=Decimal(0)) / Decimal(len(values))


def _median(values: Sequence[Decimal]) -> Decimal:
    if not values:
        raise ValueError("median requires at least one value")
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / Decimal(2)


def _nearest_rank_percentile(values: Sequence[Decimal], percentile: Decimal) -> Decimal:
    return empirical_nearest_rank(values, percentile)


def circular_block_bootstrap_mean_interval(
    values: Sequence[Decimal],
    *,
    iterations: int = DEFAULT_BOOTSTRAP_ITERATIONS,
    block_length: int = DEFAULT_BOOTSTRAP_BLOCK_LENGTH,
    seed: int = DEFAULT_BOOTSTRAP_SEED,
) -> BootstrapInterval:
    """Return a deterministic circular-block bootstrap interval for the mean."""

    if not values:
        raise ValueError("bootstrap requires at least one complete outcome")
    if isinstance(iterations, bool) or iterations < 1:
        raise ValueError("bootstrap iterations must be a positive integer")
    if isinstance(block_length, bool) or block_length < 1:
        raise ValueError("bootstrap block length must be a positive integer")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("bootstrap seed must be an integer")
    checked = tuple(_as_decimal(item, label="bootstrap value") for item in values)
    sample_size = len(checked)
    effective_block = min(block_length, sample_size)
    rng = random.Random(seed)  # noqa: S311 - deterministic statistical resampling, not security
    bootstrap_means: list[Decimal] = []
    for _ in range(iterations):
        sample: list[Decimal] = []
        while len(sample) < sample_size:
            start = rng.randrange(sample_size)
            for offset in range(effective_block):
                sample.append(checked[(start + offset) % sample_size])
                if len(sample) == sample_size:
                    break
        bootstrap_means.append(_mean(sample))
    return BootstrapInterval(
        confidence_level=Decimal("0.95"),
        lower=_nearest_rank_percentile(bootstrap_means, Decimal("0.025")),
        upper=_nearest_rank_percentile(bootstrap_means, Decimal("0.975")),
        iterations=iterations,
        requested_block_length=block_length,
        effective_block_length=effective_block,
        seed=seed,
    )


def summarize_public_proxy_events(
    outcomes: Iterable[ProxyEventOutcome],
    *,
    bootstrap_iterations: int = DEFAULT_BOOTSTRAP_ITERATIONS,
    bootstrap_block_length: int = DEFAULT_BOOTSTRAP_BLOCK_LENGTH,
    bootstrap_seed: int = DEFAULT_BOOTSTRAP_SEED,
) -> ProxyEventStudySummary:
    """Summarize complete outcomes while retaining a count of censored events."""

    ordered = tuple(sorted(outcomes, key=lambda item: item.signal_available_at_utc))
    complete_returns: list[Decimal] = []
    for item in ordered:
        if item.response_id != PRIMARY_PROXY_RESPONSE:
            raise ValueError(f"unexpected response id: {item.response_id}")
        if item.status == "COMPLETE":
            if item.response_return is None:
                raise ValueError("complete outcome has no response return")
            complete_returns.append(item.response_return)
        elif item.response_return is not None:
            raise ValueError("censored outcome must not contain a response return")

    interval = (
        circular_block_bootstrap_mean_interval(
            complete_returns,
            iterations=bootstrap_iterations,
            block_length=bootstrap_block_length,
            seed=bootstrap_seed,
        )
        if complete_returns
        else None
    )
    warnings = [
        "PUBLIC PROXY — NOT TRADABLE: World Bank monthly cocoa prices are not ICE execution prices.",
        "The primary response is the monthly proxy change from m+1 to m+4; it is not trade P&L.",
        "RETROSPECTIVE / PSEUDO-OUT-OF-SAMPLE: expanding thresholds do not create a live track record.",
        "Post-2026-08-20 observations are reserved for the registered forward holdout.",
        "The block-bootstrap interval describes this event sample and does not prove predictability.",
    ]
    if len(complete_returns) < 20:
        warnings.append("Fewer than 20 complete events: inference is especially underpowered.")
    if any(item.status == "CENSORED" for item in ordered):
        warnings.append(
            "Incomplete or missing m+4 outcomes are counted as censored, never silently dropped."
        )
    return ProxyEventStudySummary(
        response_id=PRIMARY_PROXY_RESPONSE,
        total_event_count=len(ordered),
        complete_event_count=len(complete_returns),
        censored_event_count=len(ordered) - len(complete_returns),
        mean_response_return=_mean(complete_returns) if complete_returns else None,
        median_response_return=_median(complete_returns) if complete_returns else None,
        positive_response_rate=(
            Decimal(sum(value > 0 for value in complete_returns)) / Decimal(len(complete_returns))
            if complete_returns
            else None
        ),
        mean_block_bootstrap_95_interval=interval,
        warnings=tuple(warnings),
    )
