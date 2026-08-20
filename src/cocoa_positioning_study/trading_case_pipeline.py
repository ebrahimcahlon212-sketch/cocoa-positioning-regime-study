"""Compose the public cocoa trading-research case from retained offline facts.

The public proxy and the hypothetical option structure are deliberately separate:
World Bank monthly values are not executable futures prices, while ICE inputs remain
licensed, local-only and absent from this public build.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
from collections.abc import Iterable, Mapping
from datetime import UTC, date, datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Final, cast

from cocoa_positioning_study.evidence import build_evidence_outputs
from cocoa_positioning_study.fundamentals import build_fundamentals_outputs
from cocoa_positioning_study.signals import (
    PositioningRelease,
    PositioningSignal,
    ProxyEventOutcome,
    cftc_reversal_signals,
    evaluate_public_proxy_events,
    summarize_public_proxy_events,
    summarize_signal_study,
)
from cocoa_positioning_study.trade import (
    PHYSICAL_ENDING_STOCKS_DECLINE_KT,
    PHYSICAL_MAX_AGE,
    PHYSICAL_STOCKS_TO_GRIND_DECLINE_PP,
    PHYSICAL_SURPLUS_DECLINE_KT,
    PhysicalRevisionEvidence,
    evaluate_evidence_deterioration,
)
from cocoa_positioning_study.weather import build_weather_outputs

TRADING_SUMMARY_PATH: Final = Path("data/derived/trading_case_summary.json")
SIGNAL_EVENTS_PATH: Final = Path("data/derived/cftc_positioning_reversal_events.csv")
PROXY_OUTCOMES_PATH: Final = Path("data/derived/public_proxy_event_outcomes.csv")
TRADING_MANIFEST_PATH: Final = Path("data/trading_source_manifest.csv")
INFORMATION_CUTOFF_UTC: Final = datetime(2026, 8, 20, 12, 57, 28, tzinfo=UTC)
POSITIONING_CUTOFF_UTC: Final = datetime(2026, 8, 14, 19, 31, tzinfo=UTC)

CFTC_FIELDS: Final = (
    "report_date",
    "cftc_contract_market_code",
    "market_and_exchange_names",
    "open_interest_contracts",
    "managed_money_long_contracts",
    "managed_money_short_contracts",
    "managed_money_spread_contracts",
    "contract_units_original",
    "report_type",
    "source_id",
)
PRICE_FIELDS: Final = (
    "original_period_label",
    "period",
    "price_usd_per_kg",
    "endpoint_uses",
    "source_vintage_updated_date",
    "availability_precision",
    "original_series_name",
    "original_unit",
    "provider",
    "underlying_series_attribution",
    "source_id",
)
EXPECTED_SIGNAL_DATES: Final = (
    "2017-02-21",
    "2017-05-30",
    "2017-08-29",
    "2018-01-02",
    "2018-10-16",
    "2019-04-02",
    "2019-09-10",
    "2020-07-21",
    "2021-12-14",
    "2022-07-12",
    "2022-10-11",
    "2025-12-09",
    "2026-06-16",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_exact_csv(path: Path, fields: tuple[str, ...]) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != list(fields):
            raise ValueError(f"unexpected columns in {path.name}: {reader.fieldnames}")
        rows = list(reader)
    if not rows or any(None in row for row in rows):
        raise ValueError(f"empty or malformed retained CSV: {path.name}")
    return rows


def _load_generated_json(outputs: Mapping[Path, bytes], filename: str) -> dict[str, Any]:
    matches = [payload for path, payload in outputs.items() if path.name == filename]
    if len(matches) != 1:
        raise ValueError(f"expected one generated {filename} payload")
    value: Any = json.loads(matches[0].decode("utf-8"))
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"expected a generated JSON object in {filename}")
    return cast(dict[str, Any], value)


def _load_trading_manifest(root: Path) -> dict[str, dict[str, str]]:
    path = root / TRADING_MANIFEST_PATH
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 2:
        raise ValueError("trading source manifest must contain exactly two records")
    records: dict[str, dict[str, str]] = {}
    for row in rows:
        source_id = row["source_id"]
        if source_id in records:
            raise ValueError(f"duplicate trading source id: {source_id}")
        public_path = (root / row["public_local_path"]).resolve()
        if not public_path.is_relative_to(root.resolve()) or not public_path.is_file():
            raise ValueError(f"unsafe or missing public source: {source_id}")
        if public_path.stat().st_size != int(row["public_byte_count"]):
            raise ValueError(f"public byte-count mismatch: {source_id}")
        if _sha256(public_path) != row["public_sha256"]:
            raise ValueError(f"public SHA-256 mismatch: {source_id}")
        retrieved = datetime.fromisoformat(row["retrieved_at_utc"].replace("Z", "+00:00"))
        if retrieved.tzinfo is None or retrieved.utcoffset() != timedelta(0):
            raise ValueError(f"retrieval timestamp is not UTC: {source_id}")
        records[source_id] = row
    return records


def _exact_release_overrides(root: Path) -> dict[date, tuple[date, str, str]]:
    overrides: dict[date, tuple[date, str, str]] = {}
    schedule_path = root / "data/raw/cftc-cot-release-schedule-through-2026-08-14.csv"
    for row in _read_exact_csv(
        schedule_path,
        (
            "report_date",
            "release_date",
            "release_time",
            "release_timezone",
            "federal_holiday_delay",
            "source_url",
        ),
    ):
        if row["release_time"] != "15:30" or row["release_timezone"] != "America/New_York":
            raise ValueError("unexpected retained CFTC 2026 release semantics")
        report = date.fromisoformat(row["report_date"])
        overrides[report] = (
            date.fromisoformat(row["release_date"]),
            "official_2026_release_schedule",
            row["source_url"],
        )
    special_path = root / "data/raw/cftc-cot-special-release-facts-2025-2026.csv"
    for row in _read_exact_csv(
        special_path,
        (
            "report_date",
            "release_date",
            "release_time",
            "release_timezone",
            "reason",
            "source_url",
        ),
    ):
        if row["release_time"] != "15:30" or row["release_timezone"] != "America/New_York":
            raise ValueError("unexpected retained CFTC special-release semantics")
        report = date.fromisoformat(row["report_date"])
        overrides[report] = (
            date.fromisoformat(row["release_date"]),
            "official_special_release_schedule",
            row["source_url"],
        )
    return overrides


def _availability_for_report(
    report_date: date,
    overrides: Mapping[date, tuple[date, str, str]],
) -> tuple[datetime, str, str]:
    override = overrides.get(report_date)
    if override is not None:
        release_date, basis, source_ref = override
    else:
        if report_date.weekday() == 1:
            release_date = report_date + timedelta(days=3)
        elif report_date.weekday() == 0:
            release_date = report_date + timedelta(days=4)
        else:
            raise ValueError(f"unexpected CFTC report weekday: {report_date}")
        basis = "ordinary_friday_1530_et_rule_model_not_holiday_verified"
        source_ref = "cftc_publication_methodology"
    march_first = date(release_date.year, 3, 1)
    second_sunday_march = march_first + timedelta(days=(6 - march_first.weekday()) % 7 + 7)
    november_first = date(release_date.year, 11, 1)
    first_sunday_november = november_first + timedelta(days=(6 - november_first.weekday()) % 7)
    in_daylight_time = second_sunday_march <= release_date < first_sunday_november
    eastern_offset = timezone(timedelta(hours=-4 if in_daylight_time else -5))
    local = datetime.combine(release_date, time(15, 30), tzinfo=eastern_offset)
    return local.astimezone(UTC), basis, source_ref


def _load_positioning_releases(
    root: Path,
    manifest: Mapping[str, Mapping[str, str]],
) -> tuple[tuple[PositioningRelease, ...], tuple[dict[str, str], ...]]:
    source = manifest["cftc_cocoa_selected_history_2009_2026"]
    rows = _read_exact_csv(root / source["public_local_path"], CFTC_FIELDS)
    overrides = _exact_release_overrides(root)
    releases: list[PositioningRelease] = []
    for row in rows:
        report_date = date.fromisoformat(row["report_date"])
        available_at, basis, availability_source = _availability_for_report(report_date, overrides)
        if available_at > POSITIONING_CUTOFF_UTC:
            raise ValueError(f"CFTC row is unavailable at the positioning cutoff: {report_date}")
        if row["cftc_contract_market_code"] != "073732" or row["report_type"] != "FutOnly":
            raise ValueError("retained CFTC history contains an unexpected market or report type")
        net = int(row["managed_money_long_contracts"]) - int(row["managed_money_short_contracts"])
        releases.append(
            PositioningRelease(
                report_date=report_date,
                available_at_utc=available_at,
                managed_money_net_contracts=net,
                open_interest_contracts=int(row["open_interest_contracts"]),
                source_ref=row["source_id"],
                availability_basis=basis,
                availability_source_ref=availability_source,
            )
        )
    if len(releases) != 885:
        raise ValueError("retained CFTC history must contain 885 live-era observations")
    return tuple(releases), tuple(rows)


def _load_proxy_prices(
    root: Path,
    manifest: Mapping[str, Mapping[str, str]],
) -> dict[str, Decimal]:
    source = manifest["world_bank_cocoa_event_endpoints_2026_08"]
    rows = _read_exact_csv(root / source["public_local_path"], PRICE_FIELDS)
    prices: dict[str, Decimal] = {}
    for row in rows:
        period = row["period"]
        price = Decimal(row["price_usd_per_kg"])
        if price <= 0 or period in prices:
            raise ValueError("invalid or duplicate World Bank proxy endpoint")
        prices[period] = price
    if len(prices) != 23:
        raise ValueError("retained World Bank proxy extract must contain 23 endpoints")
    return prices


def _serialise(value: object) -> object:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, tuple):
        return [_serialise(item) for item in value]
    if isinstance(value, list):
        return [_serialise(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _serialise(item) for key, item in value.items()}
    return value


def _signal_csv(
    signals: tuple[PositioningSignal, ...],
    releases: tuple[PositioningRelease, ...],
) -> bytes:
    by_date = {release.report_date: release for release in releases}
    output = io.StringIO(newline="")
    fields = (
        "rule_id",
        "report_date",
        "available_at_utc",
        "availability_basis",
        "availability_source_ref",
        "prior_release_count",
        "normalized_net",
        "previous_normalized_net",
        "prior_q10",
    )
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for signal in signals:
        release = by_date[signal.report_date]
        writer.writerow(
            {
                "rule_id": signal.rule_id,
                "report_date": signal.report_date.isoformat(),
                "available_at_utc": signal.available_at_utc.isoformat().replace("+00:00", "Z"),
                "availability_basis": release.availability_basis,
                "availability_source_ref": release.availability_source_ref,
                "prior_release_count": signal.prior_release_count,
                "normalized_net": signal.normalized_net,
                "previous_normalized_net": signal.previous_normalized_net,
                "prior_q10": signal.prior_q10,
            }
        )
    return output.getvalue().encode("utf-8")


def _proxy_outcome_csv(
    outcomes: tuple[ProxyEventOutcome, ...],
    signals: tuple[PositioningSignal, ...],
) -> bytes:
    signal_by_time = {signal.available_at_utc: signal for signal in signals}
    output = io.StringIO(newline="")
    fields = (
        "response_id",
        "signal_report_date",
        "signal_available_at_utc",
        "event_period",
        "entry_period",
        "exit_period",
        "status",
        "entry_price_usd_per_kg",
        "exit_price_usd_per_kg",
        "response_return",
        "censor_reason",
    )
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for outcome in outcomes:
        signal = signal_by_time[outcome.signal_available_at_utc]
        writer.writerow(
            {
                "response_id": outcome.response_id,
                "signal_report_date": signal.report_date.isoformat(),
                "signal_available_at_utc": outcome.signal_available_at_utc.isoformat().replace(
                    "+00:00", "Z"
                ),
                "event_period": outcome.event_period,
                "entry_period": outcome.entry_period,
                "exit_period": outcome.exit_period,
                "status": outcome.status,
                "entry_price_usd_per_kg": (
                    outcome.entry_price if outcome.entry_price is not None else ""
                ),
                "exit_price_usd_per_kg": (
                    outcome.exit_price if outcome.exit_price is not None else ""
                ),
                "response_return": (
                    outcome.response_return if outcome.response_return is not None else ""
                ),
                "censor_reason": outcome.censor_reason if outcome.censor_reason is not None else "",
            }
        )
    return output.getvalue().encode("utf-8")


def _physical_fragment(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    balance_block = cast(Mapping[str, Any], snapshot["balance"])
    balance = cast(Mapping[str, Any], balance_block["latest_2024_25"])
    return {
        "latest_balance": {
            "crop_year": balance["crop_year"],
            "published_at": balance["available_at_utc"],
            "production_kt": balance["production_kt"],
            "grindings_kt": balance["grindings_kt"],
            "surplus_kt": balance["surplus_deficit_kt"],
            "ending_stocks_kt": balance["ending_stocks_kt"],
            "stocks_to_grind_pct": balance["stocks_to_grindings_pct"],
            "source_url": balance["source_url"],
            "source_sha256": balance["source_sha256"],
        },
        "vintage_changes": [balance_block["latest_revision"]],
        "grindings": snapshot["latest_regional_grinds"],
        "demand_breadth": snapshot["demand_breadth"],
        "official_events": snapshot["latest_official_events"],
        "interpretation_guardrail": balance_block["interpretation_guardrail"],
    }


def _weather_fragment(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    proxies = cast(
        list[dict[str, Any]], snapshot["trailing_three_reported_months_or_partial_month"]
    )
    anomalies = [Decimal(str(item["precip_anomaly_pct"])) for item in proxies]
    dry_days = [int(item["dry_days_lt_1mm"]) for item in proxies]
    second_source_required = snapshot.get("quality_gate") == "SECOND_SOURCE_REQUIRED"
    state = (
        "PROVISIONAL / SECOND-SOURCE CHECK REQUIRED"
        if second_source_required
        else "PROVISIONAL WET-LEANING"
        if all(value > 20 for value in anomalies)
        else "MIXED"
    )
    return {
        "risk_label": state,
        "rainfall_anomaly_display": (f"{min(anomalies):+.1f}% to {max(anomalies):+.1f}%"),
        "dry_spell_days_display": f"{min(dry_days)}-{max(dry_days)}",
        "scope": "Daloa and Kumasi location proxies; not crop-area weighted",
        "as_of": snapshot["as_of_utc"],
        "data_status": snapshot["data_status"],
        "quality_gate": snapshot.get("quality_gate", "PROVISIONAL_SINGLE_SOURCE"),
        "trade_signal_eligible": False,
        "quality_warning": (
            "Kumasi's June extreme model-grid accumulation must be confirmed against a second "
            "dataset; weather is not admitted into the trade gate."
            if second_source_required
            else "Weather remains a provisional single-source location proxy."
        ),
        "location_proxies": proxies,
        "limitations": snapshot["limitations"],
    }


def _evidence_gate_fragment(fundamentals: Mapping[str, Any]) -> dict[str, Any]:
    balance = cast(Mapping[str, Any], fundamentals["balance"])
    revision = cast(Mapping[str, Any], balance["latest_revision"])
    decision = evaluate_evidence_deterioration(
        PhysicalRevisionEvidence(
            surplus_deficit_revision_kt=Decimal(str(revision["surplus_deficit_revision_kt"])),
            ending_stocks_revision_kt=Decimal(str(revision["ending_stocks_revision_kt"])),
            stocks_to_grindings_revision_percentage_points=Decimal(
                str(revision["stocks_to_grindings_revision_percentage_points"])
            ),
            latest_available_at_utc=datetime.fromisoformat(
                str(revision["latest_available_at_utc"]).replace("Z", "+00:00")
            ),
            evaluated_at_utc=INFORMATION_CUTOFF_UTC,
        )
    )
    return {
        "rule_id": decision.rule_id,
        "physical_deterioration": decision.physical_deterioration,
        "registered_evidence_deterioration": decision.registered_evidence_deterioration,
        "weather_context_status": decision.weather_context_status,
        "weather_trade_signal_eligible": False,
        "reasons": list(decision.reasons),
        "warnings": list(decision.warnings),
        "thresholds": {
            "physical_surplus_decline_kt": float(PHYSICAL_SURPLUS_DECLINE_KT),
            "physical_ending_stocks_decline_kt": float(PHYSICAL_ENDING_STOCKS_DECLINE_KT),
            "physical_stocks_to_grind_decline_pp": float(PHYSICAL_STOCKS_TO_GRIND_DECLINE_PP),
            "physical_max_age_days": PHYSICAL_MAX_AGE.days,
        },
        "interpretation": (
            "The registered version-1 physical gate is true at this design snapshot. Weather "
            "is context-only and cannot activate the gate; a separately frozen rule and an "
            "independent dataset would be required."
        ),
    }


def _science_fragment(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    records = cast(list[dict[str, Any]], snapshot["records"])
    by_id = {str(record["evidence_id"]): record for record in records}
    selected = (
        by_id["asitoakor_2022"],
        by_id["montero_sanchez_2025"],
        by_id["gateau_rey_2018"],
    )
    return {
        "claims": [
            {
                "label": record["citation_short"],
                "mechanism": record["mechanism_use"],
                "limitation": record["external_validity_limits"],
                "source_url": record["source_url"],
                "doi": record["doi"],
                "study_type": record["study_type"],
            }
            for record in selected
        ],
        "record_count": snapshot["record_count"],
        "selection_rationale": (
            "The memo shows three near-term mechanism studies. The fourth registry record is a "
            "long-horizon suitability projection and remains context-only rather than being "
            "presented as evidence for a Dec-26 trade."
        ),
        "translation_guardrails": snapshot["translation_guardrails"],
    }


def _illustrative_trade_fragment() -> dict[str, Any]:
    long_strike = Decimal("5500")
    short_strike = Decimal("6350")
    debit = Decimal("300")
    fees = Decimal("20")
    tonnes = Decimal("10")

    def pnl(price: Decimal) -> Decimal:
        payoff = max(price - long_strike, Decimal(0)) - max(price - short_strike, Decimal(0))
        return payoff * tonnes - debit * tonnes - fees

    prices = tuple(
        Decimal(value) for value in (3500, 4500, 5300, 5500, 5800, 6300, 6350, 7200, 8500)
    )
    curve = [
        {"expiry_futures_price_usd_per_tonne": float(price), "net_pnl_usd": float(pnl(price))}
        for price in prices
    ]
    return {
        "instrument": "ICE Futures U.S. cocoa call spread",
        "contract_month": "Dec-26",
        "structure": (
            "Long first listed call at/above the licensed settlement; short first listed call "
            "at/above 115% of the long strike; conservative ask-minus-bid debit."
        ),
        "entry_rule": (
            "Next eligible session after positioning reversal, registered physical deterioration "
            "and a prior-20-session settlement breakout; licensed inputs required."
        ),
        "exit_rule": (
            "Earliest of 40 sessions, normalized net >= 0, normalized net below entry, or "
            "10 sessions before option last trading day."
        ),
        "max_portfolio_risk_pct": 0.5,
        "evaluation_status": "NOT_EVALUATED_LICENSED_MARKET_INPUTS",
        "illustrative_input_classification": "ILLUSTRATIVE_NOT_MARKET_DATA",
        "illustrative_assumptions": {
            "paper_nav_usd": 1_000_000,
            "futures_reference_usd_per_tonne": float(long_strike),
            "long_strike_usd_per_tonne": float(long_strike),
            "short_strike_usd_per_tonne": float(short_strike),
            "net_debit_usd_per_tonne": float(debit),
            "round_trip_fees_usd_per_spread": float(fees),
            "contract_size_metric_tonnes": float(tonnes),
        },
        "illustrative_max_loss_usd": float(-pnl(Decimal(0))),
        "illustrative_max_gain_usd": float(pnl(short_strike)),
        "illustrative_breakeven_usd_per_tonne": float(long_strike + debit + fees / tonnes),
        "scenario_rows": [
            {
                "scenario": "Downside / thesis fails",
                "expiry_futures_price_usd_per_tonne": 4500,
                "net_pnl_usd": float(pnl(Decimal(4500))),
                "thesis_state": "maximum defined loss",
            },
            {
                "scenario": "Near breakeven",
                "expiry_futures_price_usd_per_tonne": 5802,
                "net_pnl_usd": float(pnl(Decimal(5802))),
                "thesis_state": "fees recovered",
            },
            {
                "scenario": "Upside shock",
                "expiry_futures_price_usd_per_tonne": 7200,
                "net_pnl_usd": float(pnl(Decimal(7200))),
                "thesis_state": "maximum capped gain",
            },
        ],
        "payoff_curve": curve,
        "scenario_workbook": "outputs/cocoa-trading-v2/cocoa-trade-scenario.xlsx",
        "warnings": [
            "Illustrative strikes, debit and NAV are not observed market data.",
            "Licensed Dec-26 settlement history and option-chain quotes are both absent.",
            "No broker connection, order routing, recommendation or executable P&L.",
            "Early-exit value needs licensed option quotes and is not fabricated.",
        ],
    }


def _source_summary(
    root: Path, trading_manifest: Mapping[str, Mapping[str, str]]
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for manifest_path in (root / "data/source_manifest.csv", root / TRADING_MANIFEST_PATH):
        with manifest_path.open(encoding="utf-8", newline="") as handle:
            for record in csv.DictReader(handle):
                rows.append(
                    {
                        "source_id": record["source_id"],
                        "source_url": record["source_url"],
                        "public_sha256": record["public_sha256"],
                    }
                )
    if set(trading_manifest) != {
        "cftc_cocoa_selected_history_2009_2026",
        "world_bank_cocoa_event_endpoints_2026_08",
    }:
        raise ValueError("unexpected trading manifest source set")
    return rows


def build_trading_case_outputs(root: Path) -> dict[Path, bytes]:
    """Build deterministic summary and event tables from retained local files."""

    manifest = _load_trading_manifest(root)
    releases, raw_rows = _load_positioning_releases(root, manifest)
    prices = _load_proxy_prices(root, manifest)
    signals = cftc_reversal_signals(releases)
    if tuple(signal.report_date.isoformat() for signal in signals) != EXPECTED_SIGNAL_DATES:
        raise ValueError("signal event dates do not match the frozen preregistration fixture")
    outcomes = evaluate_public_proxy_events(
        (signal.available_at_utc for signal in signals),
        prices,
        last_complete_period="2026-07",
    )
    signal_summary = summarize_signal_study(releases)
    proxy_summary = summarize_public_proxy_events(outcomes)
    interval = proxy_summary.mean_block_bootstrap_95_interval
    if interval is None:
        raise ValueError("proxy summary unexpectedly lacks a bootstrap interval")

    fundamentals = _load_generated_json(
        build_fundamentals_outputs(root), "fundamentals_snapshot.json"
    )
    weather = _load_generated_json(build_weather_outputs(root), "weather_snapshot.json")
    evidence = _load_generated_json(build_evidence_outputs(root), "evidence_guardrails.json")

    latest = raw_rows[-1]
    latest_net = int(latest["managed_money_long_contracts"]) - int(
        latest["managed_money_short_contracts"]
    )
    exact_basis_count = sum(
        release.availability_basis.startswith("official_") for release in releases
    )
    summary: dict[str, Any] = {
        "schema_version": 1,
        "study": "Cocoa trading research case",
        "cutoff": {
            "utc": INFORMATION_CUTOFF_UTC.isoformat().replace("+00:00", "Z"),
            "local": "2026-08-20T13:57:28+01:00",
            "positioning_utc": POSITIONING_CUTOFF_UTC.isoformat().replace("+00:00", "Z"),
            "forward_holdout_begins_utc": "2026-08-21T00:00:00Z",
        },
        "positioning": {
            "latest_net": latest_net,
            "latest_open_interest": int(latest["open_interest_contracts"]),
            "peak_to_trough": -105_656,
            "release_count": signal_summary.release_count,
            "eligible_evaluation_count": signal_summary.eligible_evaluation_count,
            "signal_count": signal_summary.signal_count,
            "signal_report_dates": list(EXPECTED_SIGNAL_DATES),
            "latest_normalized_net_pct": float(
                Decimal(latest_net) / Decimal(int(latest["open_interest_contracts"])) * 100
            ),
            "latest_prior_q10_pct": (
                float(signal_summary.latest_prior_q10 * 100)
                if signal_summary.latest_prior_q10 is not None
                else None
            ),
            "exact_schedule_release_count": exact_basis_count,
            "rule_modelled_release_count": len(releases) - exact_basis_count,
            "availability_warning": (
                "2009-2024 and uncovered 2025 ordinary dates use the CFTC Friday 15:30 ET "
                "rule model; retained official schedules override covered 2025-2026 exceptions."
            ),
            "warnings": list(signal_summary.warnings),
        },
        "physical": _physical_fragment(fundamentals),
        "weather": _weather_fragment(weather),
        "evidence_gate": _evidence_gate_fragment(fundamentals),
        "signal": {
            "public_proxy": {
                "rule_id": signal_summary.rule_id,
                "event_count": proxy_summary.total_event_count,
                "complete_event_count": proxy_summary.complete_event_count,
                "censored_event_count": proxy_summary.censored_event_count,
                "mean_return_pct": float(proxy_summary.mean_response_return * 100)
                if proxy_summary.mean_response_return is not None
                else None,
                "median_return_pct": float(proxy_summary.median_response_return * 100)
                if proxy_summary.median_response_return is not None
                else None,
                "hit_rate_pct": float(proxy_summary.positive_response_rate * 100)
                if proxy_summary.positive_response_rate is not None
                else None,
                "ci_low_pct": float(interval.lower * 100),
                "ci_high_pct": float(interval.upper * 100),
                "horizon": "World Bank monthly proxy: m+1 to m+4",
                "status": "INCONCLUSIVE / UNDERPOWERED",
                "warnings": [
                    *proxy_summary.warnings,
                    "The August-2026 workbook is a current value snapshot, not a replay of "
                    "historical monthly price vintages.",
                ],
            }
        },
        "trade": _illustrative_trade_fragment(),
        "science": _science_fragment(evidence),
        "sources": _source_summary(root, manifest),
    }
    summary_payload = (
        json.dumps(_serialise(summary), indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    ).encode("utf-8")
    return {
        root / TRADING_SUMMARY_PATH: summary_payload,
        root / SIGNAL_EVENTS_PATH: _signal_csv(signals, releases),
        root / PROXY_OUTCOMES_PATH: _proxy_outcome_csv(outcomes, signals),
    }


def materialize_trading_case(root: Path, *, check: bool = False) -> None:
    """Write outputs or fail when committed outputs are stale."""

    mismatches: list[str] = []
    for path, payload in build_trading_case_outputs(root).items():
        if check:
            if not path.exists() or path.read_bytes() != payload:
                mismatches.append(path.relative_to(root).as_posix())
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
    if mismatches:
        raise ValueError("derived trading-case outputs are stale: " + ", ".join(mismatches))


def public_proxy_returns(root: Path) -> tuple[Decimal, ...]:
    """Return complete proxy responses for transparent independent checks."""

    outputs = build_trading_case_outputs(root)
    payload = outputs[root / PROXY_OUTCOMES_PATH].decode("utf-8")
    returns: list[Decimal] = []
    for row in csv.DictReader(io.StringIO(payload)):
        if row["status"] == "COMPLETE":
            returns.append(Decimal(row["response_return"]))
    return tuple(returns)


def iter_source_fingerprints(root: Path) -> Iterable[tuple[str, str]]:
    """Yield public source IDs and verified hashes for the release audit."""

    manifest = _load_trading_manifest(root)
    for source_id, record in sorted(manifest.items()):
        yield source_id, record["public_sha256"]
