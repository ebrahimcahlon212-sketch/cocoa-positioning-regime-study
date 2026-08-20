"""Local-only adapters for licensed Dec-26 futures and option snapshots.

The adapters perform schema and point-in-time validation.  They intentionally do
not download data, contact a vendor, connect to a broker, or write derived public
outputs containing licensed quotes.
"""

from __future__ import annotations

import csv
import hashlib
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Final, Literal, TypeAlias

from cocoa_positioning_study.trade import (
    DEC26_CONTRACT_LABEL,
    CallSpreadSpec,
)

SYNTHETIC_CLASSIFICATION: Final = "SYNTHETIC_TEST_ONLY"
LICENSED_CLASSIFICATION: Final = "LICENSED_CONFIDENTIAL"
EXPECTED_CURRENCY: Final = "USD"
EXPECTED_QUOTE_UNIT: Final = "USD_PER_METRIC_TONNE"
SHORT_STRIKE_TARGET_MULTIPLE: Final = Decimal("1.15")
PRICE_CONFIRMATION_LOOKBACK: Final = 20

Classification: TypeAlias = Literal["SYNTHETIC_TEST_ONLY", "LICENSED_CONFIDENTIAL"]

OPTION_COLUMNS: Final = (
    "observed_at_utc",
    "contract_label",
    "option_type",
    "strike_usd_per_metric_tonne",
    "bid_usd_per_metric_tonne",
    "ask_usd_per_metric_tonne",
    "currency",
    "quote_unit",
    "vendor",
    "license_reference",
    "data_classification",
)

SETTLEMENT_COLUMNS: Final = (
    "session_date",
    "available_at_utc",
    "contract_label",
    "settlement_usd_per_metric_tonne",
    "currency",
    "quote_unit",
    "vendor",
    "license_reference",
    "data_classification",
)


def _as_decimal(value: str, *, label: str) -> Decimal:
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"{label} is not a valid decimal: {value!r}") from exc
    if not parsed.is_finite():
        raise ValueError(f"{label} must be finite")
    return parsed


def _parse_utc(value: str, *, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} is not a valid ISO-8601 timestamp") from exc
    offset = parsed.utcoffset()
    if parsed.tzinfo is None or offset is None:
        raise ValueError(f"{label} must be timezone-aware")
    if offset.total_seconds() != 0:
        raise ValueError(f"{label} must be normalized to UTC")
    return parsed.astimezone(UTC)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_exact_csv(path: Path, columns: tuple[str, ...]) -> list[dict[str, str]]:
    if not path.is_file():
        raise FileNotFoundError(path)
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != list(columns):
            raise ValueError(f"unexpected columns in {path.name}: {reader.fieldnames}")
        rows = list(reader)
    if not rows:
        raise ValueError(f"licensed-data adapter received an empty file: {path.name}")
    if any(None in row for row in rows):
        raise ValueError(f"malformed row in {path.name}")
    return rows


def _classification(raw: str) -> Classification:
    if raw == SYNTHETIC_CLASSIFICATION:
        return "SYNTHETIC_TEST_ONLY"
    if raw == LICENSED_CLASSIFICATION:
        return "LICENSED_CONFIDENTIAL"
    raise ValueError(f"unexpected data classification: {raw!r}")


def _validate_file_scope(
    path: Path,
    classifications: set[Classification],
    *,
    allow_synthetic: bool,
    licensed_root: Path | None,
) -> Classification:
    if len(classifications) != 1:
        raise ValueError("one file cannot mix synthetic and licensed rows")
    classification = next(iter(classifications))
    if classification == "SYNTHETIC_TEST_ONLY":
        if not allow_synthetic:
            raise ValueError("synthetic fixture requires allow_synthetic=True")
        return classification
    if licensed_root is None:
        raise ValueError("licensed_root is required for confidential input")
    resolved_path = path.resolve()
    resolved_root = licensed_root.resolve()
    if not resolved_path.is_relative_to(resolved_root):
        raise ValueError("confidential market-data file must remain under licensed_root")
    return classification


def _validate_common_fields(
    *,
    contract_label: str,
    currency: str,
    quote_unit: str,
    vendor: str,
    license_reference: str,
) -> None:
    if contract_label != DEC26_CONTRACT_LABEL:
        raise ValueError(f"adapter requires contract label {DEC26_CONTRACT_LABEL!r}")
    if currency != EXPECTED_CURRENCY or quote_unit != EXPECTED_QUOTE_UNIT:
        raise ValueError("licensed input must use USD per metric tonne")
    if not vendor.strip() or not license_reference.strip():
        raise ValueError("vendor and license reference must be retained")


@dataclass(frozen=True, slots=True)
class OptionQuote:
    observed_at_utc: datetime
    contract_label: str
    option_type: str
    strike_usd_per_metric_tonne: Decimal
    bid_usd_per_metric_tonne: Decimal
    ask_usd_per_metric_tonne: Decimal
    currency: str
    quote_unit: str
    vendor: str
    license_reference: str
    data_classification: Classification


@dataclass(frozen=True, slots=True)
class OptionChain:
    quotes: tuple[OptionQuote, ...]
    source_path: Path
    source_sha256: str
    data_classification: Classification

    @property
    def observed_at_utc(self) -> datetime:
        return self.quotes[0].observed_at_utc


def load_dec26_option_chain(
    path: Path,
    *,
    allow_synthetic: bool = False,
    licensed_root: Path | None = None,
) -> OptionChain:
    """Load a local quote snapshot after validating provenance and quote units."""

    rows = _read_exact_csv(path, OPTION_COLUMNS)
    parsed: list[OptionQuote] = []
    classifications: set[Classification] = set()
    for row in rows:
        classification = _classification(row["data_classification"])
        classifications.add(classification)
        _validate_common_fields(
            contract_label=row["contract_label"],
            currency=row["currency"],
            quote_unit=row["quote_unit"],
            vendor=row["vendor"],
            license_reference=row["license_reference"],
        )
        if row["option_type"] != "CALL":
            raise ValueError("Dec-26 call-spread adapter accepts CALL rows only")
        strike = _as_decimal(row["strike_usd_per_metric_tonne"], label="option strike")
        bid = _as_decimal(row["bid_usd_per_metric_tonne"], label="option bid")
        ask = _as_decimal(row["ask_usd_per_metric_tonne"], label="option ask")
        if strike <= 0 or bid < 0 or ask < 0:
            raise ValueError("option strikes must be positive and quotes non-negative")
        if bid > ask:
            raise ValueError("option bid cannot exceed ask")
        parsed.append(
            OptionQuote(
                observed_at_utc=_parse_utc(row["observed_at_utc"], label="observed_at_utc"),
                contract_label=row["contract_label"],
                option_type=row["option_type"],
                strike_usd_per_metric_tonne=strike,
                bid_usd_per_metric_tonne=bid,
                ask_usd_per_metric_tonne=ask,
                currency=row["currency"],
                quote_unit=row["quote_unit"],
                vendor=row["vendor"],
                license_reference=row["license_reference"],
                data_classification=classification,
            )
        )

    classification = _validate_file_scope(
        path,
        classifications,
        allow_synthetic=allow_synthetic,
        licensed_root=licensed_root,
    )
    snapshots = {item.observed_at_utc for item in parsed}
    if len(snapshots) != 1:
        raise ValueError("option-chain rows must share one observed_at_utc snapshot")
    strikes = [item.strike_usd_per_metric_tonne for item in parsed]
    if len(strikes) != len(set(strikes)):
        raise ValueError("option-chain strikes must be unique")
    quotes = tuple(sorted(parsed, key=lambda item: item.strike_usd_per_metric_tonne))
    return OptionChain(
        quotes=quotes,
        source_path=path.resolve(),
        source_sha256=_sha256(path),
        data_classification=classification,
    )


def select_registered_call_spread(
    chain: OptionChain,
    underlying_settlement_usd_per_tonne: Decimal,
) -> CallSpreadSpec:
    """Select the frozen first-ATM/20%-higher-strike structure conservatively.

    The long leg is the first listed strike at or above the Dec-26 settlement.  The
    short leg is the first listed strike at or above 115% of the long strike.  Net
    debit uses long ask minus short bid; mid-market execution is never assumed.
    """

    if not underlying_settlement_usd_per_tonne.is_finite():
        raise ValueError("underlying settlement must be finite")
    if underlying_settlement_usd_per_tonne <= 0:
        raise ValueError("underlying settlement must be positive")
    long_quote = next(
        (
            item
            for item in chain.quotes
            if item.strike_usd_per_metric_tonne >= underlying_settlement_usd_per_tonne
        ),
        None,
    )
    if long_quote is None:
        raise ValueError("option chain has no strike at or above the underlying settlement")
    short_target = long_quote.strike_usd_per_metric_tonne * SHORT_STRIKE_TARGET_MULTIPLE
    short_quote = next(
        (item for item in chain.quotes if item.strike_usd_per_metric_tonne >= short_target),
        None,
    )
    if short_quote is None:
        raise ValueError("option chain has no strike at or above the registered short target")
    conservative_debit = long_quote.ask_usd_per_metric_tonne - short_quote.bid_usd_per_metric_tonne
    if conservative_debit <= 0:
        raise ValueError("conservative long-ask minus short-bid debit must be positive")
    return CallSpreadSpec(
        observed_at_utc=chain.observed_at_utc,
        long_strike_usd_per_tonne=long_quote.strike_usd_per_metric_tonne,
        short_strike_usd_per_tonne=short_quote.strike_usd_per_metric_tonne,
        net_debit_usd_per_tonne=conservative_debit,
    )


@dataclass(frozen=True, slots=True)
class FuturesSettlement:
    session_date: date
    available_at_utc: datetime
    contract_label: str
    settlement_usd_per_metric_tonne: Decimal
    currency: str
    quote_unit: str
    vendor: str
    license_reference: str
    data_classification: Classification


@dataclass(frozen=True, slots=True)
class SettlementSeries:
    settlements: tuple[FuturesSettlement, ...]
    source_path: Path
    source_sha256: str
    data_classification: Classification


def load_dec26_settlements(
    path: Path,
    *,
    allow_synthetic: bool = False,
    licensed_root: Path | None = None,
) -> SettlementSeries:
    """Load local settlement history with actual availability timestamps."""

    rows = _read_exact_csv(path, SETTLEMENT_COLUMNS)
    parsed: list[FuturesSettlement] = []
    classifications: set[Classification] = set()
    for row in rows:
        classification = _classification(row["data_classification"])
        classifications.add(classification)
        _validate_common_fields(
            contract_label=row["contract_label"],
            currency=row["currency"],
            quote_unit=row["quote_unit"],
            vendor=row["vendor"],
            license_reference=row["license_reference"],
        )
        try:
            session_date = date.fromisoformat(row["session_date"])
        except ValueError as exc:
            raise ValueError("session_date is not a valid ISO date") from exc
        settlement = _as_decimal(
            row["settlement_usd_per_metric_tonne"],
            label="futures settlement",
        )
        if settlement <= 0:
            raise ValueError("futures settlement must be positive")
        parsed.append(
            FuturesSettlement(
                session_date=session_date,
                available_at_utc=_parse_utc(row["available_at_utc"], label="available_at_utc"),
                contract_label=row["contract_label"],
                settlement_usd_per_metric_tonne=settlement,
                currency=row["currency"],
                quote_unit=row["quote_unit"],
                vendor=row["vendor"],
                license_reference=row["license_reference"],
                data_classification=classification,
            )
        )

    classification = _validate_file_scope(
        path,
        classifications,
        allow_synthetic=allow_synthetic,
        licensed_root=licensed_root,
    )
    ordered = tuple(sorted(parsed, key=lambda item: item.available_at_utc))
    timestamps = [item.available_at_utc for item in ordered]
    dates = [item.session_date for item in ordered]
    if len(timestamps) != len(set(timestamps)) or len(dates) != len(set(dates)):
        raise ValueError("settlements require unique session dates and availability timestamps")
    return SettlementSeries(
        settlements=ordered,
        source_path=path.resolve(),
        source_sha256=_sha256(path),
        data_classification=classification,
    )


def prior_20_session_high_confirmation(
    settlements: Iterable[FuturesSettlement],
    as_of_utc: datetime,
) -> bool:
    """Test whether the latest visible settlement exceeds the prior 20 visible ones."""

    if as_of_utc.tzinfo is None or as_of_utc.utcoffset() is None:
        raise ValueError("as_of_utc must be timezone-aware")
    cutoff = as_of_utc.astimezone(UTC)
    visible = tuple(
        sorted(
            (item for item in settlements if item.available_at_utc <= cutoff),
            key=lambda item: item.available_at_utc,
        )
    )
    required = PRICE_CONFIRMATION_LOOKBACK + 1
    if len(visible) < required:
        raise ValueError(f"price confirmation requires at least {required} visible settlements")
    current = visible[-1].settlement_usd_per_metric_tonne
    prior = visible[-required:-1]
    return current > max(item.settlement_usd_per_metric_tonne for item in prior)
