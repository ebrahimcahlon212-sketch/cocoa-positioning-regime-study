"""Regression tests for the trading research report."""

from __future__ import annotations

import hashlib
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "render_trading_case.py"
PDF = ROOT / "output" / "pdf" / "cocoa-trading-research-case.pdf"
FIGURE = ROOT / "output" / "figures" / "cocoa-trading-research-case.png"


def _render() -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed interpreter and repository-owned script
        [sys.executable, str(SCRIPT)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _uris(reader: PdfReader) -> set[str]:
    urls: set[str] = set()
    for page in reader.pages:
        for reference in page.get("/Annots", []):
            annotation = reference.get_object()
            action_reference = annotation.get("/A")
            if action_reference is None:
                continue
            action = action_reference.get_object()
            if action.get("/S") == "/URI":
                urls.add(str(action["/URI"]))
    return urls


def test_trading_case_report_is_two_page_and_candid() -> None:
    result = _render()
    assert result.returncode == 0, result.stdout + result.stderr
    assert PDF.is_file()
    assert FIGURE.is_file()
    reader = PdfReader(PDF)
    assert len(reader.pages) == 2
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    normalized_text = " ".join(text.split())
    assert "Cocoa: Positioning Meets Physical Risk" in text
    assert (
        "Context only; location proxies are not crop-area weighted or a production estimate."
        in normalized_text
    )
    assert "Crop-area feature" not in text
    assert "1 recorded balance revision." in text
    assert "STOCKS / GRIND" in text
    assert "28.5%" in text
    assert "DRY DAYS <1MM" in text
    assert "DRY-SPELL DAYS" not in text
    assert "SCENARIO ANALYSIS - ILLUSTRATIVE, HYPOTHETICAL AND NON-EXECUTABLE" in text
    assert "SCENARIO RISK - GROSS" not in text
    assert "HYPOTHETICAL / NO BROKER ACTION" in text
    assert "PUBLIC PROXY - NOT TRADABLE" in text
    assert "not an ICE futures return" in text
    assert "115% of the long strike" in normalized_text
    assert "115% of the entry proxy" not in normalized_text
    assert "Earliest of 40 sessions" in text
    assert "K1 5,500" in text
    assert "K2 6,350" in text
    assert "max loss $3,020" in text
    assert "max gain $5,480" in text
    assert "breakeven 5,802/t" in text
    assert "debit 300/t" in text
    assert "fees $20/spread" in text
    assert "INCONCLUSIVE / UNDERPOWERED" in text
    assert "13 (12 complete)" in text
    assert "Mean proxy response: +0.61%" in text
    assert "+1.8%" in text
    assert "58.3%" in text
    assert "[-5.6%, +5.8%]" in text
    assert "ILLUSTRATIVE / NOT MARKET DATA" in text
    assert "Input status: NOT EVALUATED -" in text
    assert "LICENSED SETTLEMENT HISTORY AND OPTION CHAIN ARE ABSENT" in normalized_text
    assert "Registered physical deterioration: MET" in normalized_text
    assert "Weather: CONTEXT ONLY / INELIGIBLE FOR V1 GATE" in normalized_text
    assert "physical/weather evidence deteriorates" not in normalized_text
    assert "SECOND-SOURCE CHECK REQUIRED" in text
    assert "Kumasi's June extreme requires a second-source check" in normalized_text
    assert "weather is context-only and ineligible for the v1 gate" in normalized_text
    assert "3 NEAR-TERM SHOWN; 4TH PROJECTION REGISTRY/CONTEXT-ONLY" in normalized_text
    assert "1 / 2" in text
    assert "2 / 2" in text


def test_trading_case_report_links_primary_sources() -> None:
    result = _render()
    assert result.returncode == 0, result.stdout + result.stderr
    urls = _uris(PdfReader(PDF))
    assert "https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm" in urls
    assert "https://www.icco.org/may-2026-quarterly-bulletin-of-cocoa-statistics/" in urls
    assert "https://github.com/ebrahimcahlon212-sketch/cocoa-positioning-regime-study" in urls
    assert any(
        url.startswith("https://power.larc.nasa.gov/api/temporal/daily/point") for url in urls
    )
    assert (
        "https://www.eurococoa.com/wp-content/uploads/WEBSITE-REPORT-WESTERN-STATS-Q2-2026.pdf"
        in urls
    )
    assert (
        "https://www.cocoaasia.org/_files/ugd/fba979_7e8a5c99b5474b05b1b03cbd363163c8.pdf" in urls
    )
    assert (
        "https://candyusa.com/wordpress/wp-content/uploads/2026/07/Q2-2026-Cocoa-Grinds.pdf" in urls
    )
    assert (
        "https://thedocs.worldbank.org/en/doc/"
        "74e8be41ceb20fa0da750cda2f6b9e4e-0050012026/related/"
        "CMO-Historical-Data-Monthly.xlsx" in urls
    )
    assert "https://cocoasoils.org/wp-content/uploads/2022/10/Asitoakor-et-al.-2022..pdf" in urls
    assert (
        "https://www.cambridge.org/core/journals/experimental-agriculture/article/effects-of-climate-and-withintree-competition-on-cocoa-pod-production-in-ghana/2F9415457E7C6E28FC01F050F4A7049D"
        in urls
    )
    assert "https://journals.plos.org/plosone/article?id=10.1371%2Fjournal.pone.0200454" in urls
    assert not any("chc.ucsb.edu" in url or "climate.copernicus.eu" in url for url in urls)


def test_trading_case_report_is_byte_deterministic() -> None:
    fingerprints: list[tuple[str, str]] = []
    for _ in range(2):
        result = _render()
        assert result.returncode == 0, result.stdout + result.stderr
        fingerprints.append(
            (
                hashlib.sha256(PDF.read_bytes()).hexdigest(),
                hashlib.sha256(FIGURE.read_bytes()).hexdigest(),
            )
        )
    assert fingerprints[0] == fingerprints[1]


def test_report_sources_use_ascii_hyphens() -> None:
    texts = [SCRIPT.read_text(encoding="utf-8")]
    for path in sorted((ROOT / "reports").glob("*.docx")):
        with ZipFile(path) as document:
            root = ET.fromstring(document.read("word/document.xml"))  # noqa: S314 - repository-owned document
        texts.append(" ".join(root.itertext()))
    for text in texts:
        assert "\N{NON-BREAKING HYPHEN}" not in text
        assert "\N{EN DASH}" not in text
        assert "\N{EM DASH}" not in text
