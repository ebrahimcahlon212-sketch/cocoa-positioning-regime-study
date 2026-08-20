"""Offline regression tests against the retained official source snapshots."""

from __future__ import annotations

import csv
import hashlib
import io
import subprocess
import sys
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from pypdf import PdfReader

from cocoa_positioning_study.pipeline import (
    STUDY_CUTOFF_UTC,
    assemble_study,
    build_outputs,
    load_manifest,
    materialize,
    visible_as_of,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def study():  # type: ignore[no-untyped-def]
    return assemble_study(ROOT)


def test_manifest_fingerprints_upstreams_and_public_extracts() -> None:
    manifest = load_manifest(ROOT)
    assert len(manifest) == 7
    assert manifest["cftc_disagg_futures_only_2024"].upstream_sha256 == (
        "5e40f60993120d26c116ab347beaf93702f5da60c7bdccbbee43cb3d0a91d01a"
    )
    assert manifest["cftc_disagg_futures_only_2025"].upstream_sha256 == (
        "17ac2fef1b53303d01e486bbf5768a4e062308a3c34a2970871f3eab89829cbc"
    )
    assert manifest["cftc_disagg_futures_only_2026"].upstream_sha256 == (
        "38e104b6ba1a1d1d017e37fb7a93e7604e0a72d30f913ee9c3a8d3e4d6026c5e"
    )
    world_bank = manifest["world_bank_pink_sheet_monthly_august_2026"]
    assert world_bank.upstream_sha256 == (
        "7902a77505ebdc5d202ce65f666c2ee1b04b626f042d7738ed3e6f7d112c8433"
    )
    assert world_bank.upstream_byte_count == 577_979
    assert world_bank.public_sha256 == (
        "1ebd84e402776be302cd86fefb467e3baf4bcb07fd3c4a2f9c0d0d17f0508363"
    )
    assert world_bank.public_byte_count == 1_254
    assert not world_bank.upstream_redistributed


def test_public_source_set_excludes_html_and_workbooks() -> None:
    manifest = load_manifest(ROOT)
    public_paths = [ROOT / record.public_local_path for record in manifest.values()]
    assert len(public_paths) == 7
    assert all(path.parent == ROOT / "data" / "raw" for path in public_paths)
    assert not any(path.suffix.lower() in {".html", ".htm", ".xlsx"} for path in public_paths)
    assert not list((ROOT / "data" / "raw").glob("*.html"))
    assert not list((ROOT / "data" / "raw").glob("*.xlsx"))
    assert "data/external/" in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "data/external/" in (ROOT / ".ignore").read_text(encoding="utf-8").splitlines()
    extracted = [record for record in manifest.values() if not record.upstream_redistributed]
    assert len(extracted) == 4
    assert all(record.external_upstream_path.startswith("data/external/") for record in extracted)


def test_cftc_coverage_and_headlines(study) -> None:  # type: ignore[no-untyped-def]
    assert len(study.cftc_visible) == 137
    mm_peak = max(study.cftc_visible, key=lambda item: item.managed_money_net_contracts)
    mm_trough = min(study.cftc_visible, key=lambda item: item.managed_money_net_contracts)
    oi_peak = max(study.cftc_visible, key=lambda item: item.open_interest_contracts)
    oi_trough = min(study.cftc_visible, key=lambda item: item.open_interest_contracts)
    latest = study.cftc_visible[-1]
    assert (mm_peak.report_date, mm_peak.managed_money_net_contracts) == (
        date(2024, 1, 23),
        82_572,
    )
    assert (mm_trough.report_date, mm_trough.managed_money_net_contracts) == (
        date(2026, 6, 9),
        -23_084,
    )
    assert (oi_peak.report_date, oi_peak.open_interest_contracts) == (
        date(2024, 1, 23),
        333_669,
    )
    assert (oi_trough.report_date, oi_trough.open_interest_contracts) == (
        date(2025, 4, 22),
        86_919,
    )
    assert (
        latest.report_date,
        latest.managed_money_net_contracts,
        latest.open_interest_contracts,
    ) == (
        date(2026, 8, 11),
        -6_667,
        190_891,
    )


def test_managed_money_net_is_long_minus_short(study) -> None:  # type: ignore[no-untyped-def]
    for item in study.cftc_all:
        assert item.managed_money_net_contracts == (
            item.managed_money_long_contracts - item.managed_money_short_contracts
        )


def test_shutdown_report_is_not_visible_before_actual_catch_up_release(study) -> None:  # type: ignore[no-untyped-def]
    before = visible_as_of(study.cftc_all, datetime(2025, 11, 19, 20, 29, tzinfo=UTC))
    after = visible_as_of(study.cftc_all, datetime(2025, 11, 19, 20, 31, tzinfo=UTC))
    assert date(2025, 9, 30) not in {item.report_date for item in before}
    assert date(2025, 9, 30) in {item.report_date for item in after}
    item = next(value for value in study.cftc_all if value.report_date == date(2025, 9, 30))
    assert item.release_at_et == "2025-11-19T15:30:00-05:00"
    assert item.availability_basis == "cftc_official_appropriations_catch_up"


def test_latest_report_respects_august_cutoff_boundary(study) -> None:  # type: ignore[no-untyped-def]
    before = visible_as_of(study.cftc_all, datetime(2026, 8, 14, 19, 29, tzinfo=UTC))
    at_release = visible_as_of(study.cftc_all, datetime(2026, 8, 14, 19, 30, tzinfo=UTC))
    at_study_cutoff = visible_as_of(study.cftc_all, STUDY_CUTOFF_UTC)
    assert before[-1].report_date == date(2026, 8, 4)
    assert at_release[-1].report_date == date(2026, 8, 11)
    assert at_study_cutoff[-1].report_date == date(2026, 8, 11)
    assert at_release[-1].release_at_et == "2026-08-14T15:30:00-04:00"


def test_2026_holiday_delays_come_from_official_schedule(study) -> None:  # type: ignore[no-untyped-def]
    by_date = {item.report_date: item for item in study.cftc_all}
    assert by_date[date(2026, 6, 16)].release_date == date(2026, 6, 22)
    assert by_date[date(2026, 6, 30)].release_date == date(2026, 7, 6)
    assert by_date[date(2026, 6, 16)].availability_basis == "cftc_official_2026_schedule"


def test_uncovered_normal_release_dates_are_labelled_estimates(study) -> None:  # type: ignore[no-untyped-def]
    by_date = {item.report_date: item for item in study.cftc_all}
    assert by_date[date(2024, 1, 23)].release_date == date(2024, 1, 26)
    assert by_date[date(2024, 1, 23)].availability_basis == (
        "cftc_ordinary_rule_estimate_not_holiday_verified"
    )
    assert by_date[date(2025, 4, 22)].release_date == date(2025, 4, 25)
    assert by_date[date(2025, 4, 22)].availability_basis == (
        "cftc_ordinary_rule_estimate_not_holiday_verified"
    )


def test_world_bank_price_results(study) -> None:  # type: ignore[no-untyped-def]
    findings = study.summary["findings"]["price"]
    assert "average_2024" not in findings
    assert "average_2025" not in findings
    assert findings["average_q1_2026"] == 3.93
    assert findings["july_2026"] == 5.61
    assert findings["july_vs_q1_full_precision_pct"] == 42.6271
    assert findings["july_vs_q1_pct"] == 42.6
    assert [item.period for item in study.prices] == [
        "2026-01",
        "2026-02",
        "2026-03",
        "2026-07",
    ]
    assert [item.price_usd_per_kg for item in study.prices] == [
        Decimal("4.97"),
        Decimal("3.59"),
        Decimal("3.24"),
        Decimal("5.61"),
    ]
    assert study.prices[-1].price_usd_per_kg == Decimal("5.61")
    assert study.prices[-1].source_vintage_available_at_utc is None


def test_recruiter_headline_changes_are_materialized(study) -> None:  # type: ignore[no-untyped-def]
    changes = study.summary["findings"]["changes"]
    assert changes == {
        "managed_money_peak_to_trough_change_contracts": -105_656,
        "managed_money_peak_to_trough_swing_magnitude_contracts": 105_656,
        "managed_money_peak_to_trough_contract_unit_metric_tonnes_change": -1_056_560,
        "managed_money_peak_to_trough_swing_magnitude_contract_unit_metric_tonnes": 1_056_560,
        "managed_money_trough_to_latest_change_contracts": 16_417,
        "latest_open_interest_vs_peak_pct": -42.8,
        "open_interest_peak_to_trough_pct": -74.0,
    }


def test_cutoff_must_be_timezone_aware(study) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ValueError, match="timezone-aware"):
        visible_as_of(study.cftc_all, datetime(2026, 8, 14, 19, 31))


def test_committed_outputs_are_reproducible() -> None:
    expected = build_outputs(ROOT)
    for path, payload in expected.items():
        if path.suffix != ".csv":
            continue
        header = next(csv.reader(io.StringIO(payload.decode("utf-8"))))
        assert "source_upstream_sha256" in header
        assert "source_public_sha256" in header
        assert "source_sha256" not in header
    for path, payload in expected.items():
        assert path.read_bytes() == payload
    materialize(ROOT, check=True)


def test_report_artifacts_are_byte_for_byte_deterministic() -> None:
    artifacts = (
        ROOT / "output" / "pdf" / "cocoa-positioning-regime-shift.pdf",
        ROOT / "output" / "figures" / "cocoa-positioning-regime.png",
    )
    fingerprints: list[tuple[str, ...]] = []
    for _ in range(2):
        result = subprocess.run(  # noqa: S603 - fixed interpreter and repository-owned script
            [sys.executable, str(ROOT / "scripts" / "reproduce.py"), "--check"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        fingerprints.append(
            tuple(hashlib.sha256(path.read_bytes()).hexdigest() for path in artifacts)
        )
    assert fingerprints[0] == fingerprints[1]


def test_pdf_footer_links_are_live() -> None:
    pdf = PdfReader(ROOT / "output" / "pdf" / "cocoa-positioning-regime-shift.pdf")
    assert len(pdf.pages) == 1
    annotations = pdf.pages[0].get("/Annots", [])
    uris: list[str] = []
    for reference in annotations:
        annotation = reference.get_object()
        action_reference = annotation.get("/A")
        if action_reference is None:
            continue
        action = action_reference.get_object()
        if action.get("/S") == "/URI":
            uris.append(str(action["/URI"]))
    assert sorted(uris) == sorted(
        [
            "https://github.com/ebrahimcahlon212-sketch/cocoa-positioning-regime-study",
            "https://github.com/ebrahimcahlon212-sketch/market-intelligence-research-platform",
        ]
    )
