"""Integrity checks for the recruiter-facing formula workbook."""

from __future__ import annotations

import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKBOOK = ROOT / "outputs" / "cocoa-trading-v2" / "cocoa-trade-scenario.xlsx"


def test_workbook_is_formula_driven_and_contains_no_external_links() -> None:
    assert WORKBOOK.is_file()
    with zipfile.ZipFile(WORKBOOK) as archive:
        names = set(archive.namelist())
        assert "xl/workbook.xml" in names
        assert "xl/worksheets/sheet2.xml" in names
        assert not any(name.startswith("xl/externalLinks/") for name in names)
        assert not any(name.endswith("vbaProject.bin") for name in names)

        workbook_xml = archive.read("xl/workbook.xml").decode("utf-8")
        for sheet in ("Cover", "Trade Inputs", "Scenario P&amp;L", "Checks", "Sources Audit"):
            assert f'name="{sheet}"' in workbook_xml

        input_xml = archive.read("xl/worksheets/sheet2.xml").decode("utf-8")
        assert "B10*B12+B11" in input_xml
        assert "(B18-B10)*B12-B11" in input_xml
        assert "B8+B10+B11/B12" in input_xml
        assert "INT(B19/B21)" in input_xml


def test_workbook_keeps_illustrative_and_no_broker_boundaries_visible() -> None:
    with zipfile.ZipFile(WORKBOOK) as archive:
        payload = b"\n".join(archive.read(name) for name in archive.namelist())
    text = payload.decode("utf-8", errors="ignore")
    assert "blue market-price cells are illustrative" in text
    assert "blue rule cells are frozen version-1 research parameters" in text
    assert "Registered physical-balance deterioration" in text
    assert "No order routing, no broker connection, no investment recommendation" in text
    assert "First listed strike at or above F0" in text
    assert "First listed strike at or above 115% of K1" in text
    assert "Nearest $50 strike" not in text
    assert "115% of F0" not in text
    assert not any(
        marker in text.lower()
        for marker in ("cocoa-intelligence", "c:\\users\\", "data/licensed/", "begin private")
    )
    assert not any(token in text for token in ("#REF!", "#DIV/0!", "#VALUE!", "#NAME?"))
