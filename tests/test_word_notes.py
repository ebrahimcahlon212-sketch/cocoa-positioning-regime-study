"""Check the published Word notes against retained research outputs."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
WORD = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"


def _read_note(name: str) -> tuple[str, set[str]]:
    with ZipFile(ROOT / "reports" / name) as document:
        body = ET.fromstring(document.read("word/document.xml"))  # noqa: S314 - repository-owned document
        rels = ET.fromstring(document.read("word/_rels/document.xml.rels"))  # noqa: S314 - repository-owned document
        assert body.find(f".//{WORD}ins") is None
        assert body.find(f".//{WORD}del") is None
        assert "word/comments.xml" not in document.namelist()
    text = " ".join(node.text or "" for node in body.iter(f"{WORD}t"))
    urls = {
        node.attrib["Target"]
        for node in rels.iter(f"{REL}Relationship")
        if node.attrib.get("Type", "").endswith("/hyperlink")
    }
    assert urls and all(url.startswith("https://") for url in urls)
    assert "\N{EM DASH}" not in text
    return text, urls


def test_word_positioning_note_matches_retained_findings() -> None:
    text, urls = _read_note("cocoa-positioning-note.docx")
    summary = json.loads((ROOT / "data/derived/study_summary.json").read_text(encoding="utf-8"))
    findings = summary["findings"]
    for key in ("managed_money_net_peak", "managed_money_net_trough", "latest_cftc"):
        assert f"{findings[key]['managed_money_net_contracts']:,}" in text
    assert f"${findings['price']['july_2026']:.2f}/kg" in text
    assert f"{findings['price']['july_vs_q1_pct']:.1f}%" in text
    assert "14 August 2026 at 19:31 UTC" in text
    assert "later corrections" in text
    assert "no claim of alpha" in text
    assert "https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm" in urls


def test_word_research_memo_matches_retained_results_and_limits() -> None:
    text, urls = _read_note("cocoa-research-memo.docx")
    summary = json.loads(
        (ROOT / "data/derived/trading_case_summary.json").read_text(encoding="utf-8")
    )
    proxy = summary["signal"]["public_proxy"]
    for key in (
        "mean_return_pct",
        "median_return_pct",
        "hit_rate_pct",
        "ci_low_pct",
        "ci_high_pct",
    ):
        assert f"{proxy[key]:.1f}%" in text
    assert f"{proxy['event_count']} events" in text
    assert f"{proxy['complete_event_count']} have complete" in text
    trade = summary["trade"]
    for key in (
        "illustrative_max_loss_usd",
        "illustrative_max_gain_usd",
        "illustrative_breakeven_usd_per_tonne",
    ):
        assert f"${trade[key]:,.0f}" in text
    balance = summary["physical"]["latest_balance"]
    for key in ("production_kt", "grindings_kt", "surplus_kt", "ending_stocks_kt"):
        assert f"{balance[key]:,.0f}kt" in text
    assert balance["source_url"] in urls
    assert "NOT EVALUATED" in text
    assert "illustrative inputs, not observed market quotes" in text
    assert "Weather cannot activate version 1" in text
    assert "thresholds were chosen after the May revision was known" in text
    assert "21 August 2026" in text
    assert "longer-term climate effects on yield" in text
    for record in summary["science"]["claims"]:
        assert record["source_url"] in urls
