"""Create rights-minimal factual extracts from retained upstream source snapshots."""

from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from datetime import date, datetime, timedelta
from html.parser import HTMLParser
from pathlib import PurePosixPath
from xml.etree import ElementTree

_SS_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL_DOC_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_REL_PKG_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tables: list[list[list[str]]] = []
        self._table: list[list[str]] | None = None
        self._row: list[str] | None = None
        self._cell_parts: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag == "table":
            self._table = []
        elif tag == "tr" and self._table is not None:
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell_parts = []

    def handle_data(self, data: str) -> None:
        if self._cell_parts is not None:
            self._cell_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._cell_parts is not None and self._row is not None:
            self._row.append(_clean("".join(self._cell_parts)))
            self._cell_parts = None
        elif tag == "tr" and self._row is not None and self._table is not None:
            if any(self._row):
                self._table.append(self._row)
            self._row = None
        elif tag == "table" and self._table is not None:
            if self._table:
                self.tables.append(self._table)
            self._table = None


def _clean(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split())


def _tables(payload: bytes) -> list[list[list[str]]]:
    parser = _TableParser()
    parser.feed(payload.decode("utf-8", errors="replace"))
    return parser.tables


def _csv_bytes(fields: tuple[str, ...], rows: list[dict[str, str]]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


def extract_cftc_methodology(payload: bytes, source_url: str) -> bytes:
    text = _clean(payload.decode("utf-8", errors="replace")).lower()
    required = ("3:30 pm eastern time", "preceding tuesday", "generally published each friday")
    if not all(value in text for value in required):
        raise ValueError("CFTC methodology page no longer supports the expected publication facts")
    document = {
        "extract_scope": "sanitized factual summary; upstream HTML wrapper is not redistributed",
        "observation_day": "Tuesday",
        "ordinary_release_day": "Friday",
        "release_time": "15:30",
        "release_timezone": "America/New_York",
        "source_url": source_url,
    }
    return (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")


def extract_cftc_2026_schedule(payload: bytes, source_url: str) -> bytes:
    month_numbers = {
        "January": 1,
        "February": 2,
        "March": 3,
        "April": 4,
        "May": 5,
        "June": 6,
        "July": 7,
        "August": 8,
        "September": 9,
        "October": 10,
        "November": 11,
        "December": 12,
    }
    release_cells: list[tuple[date, bool]] = []
    for table in _tables(payload):
        if not table or table[0][:2] != ["Month", "Dates"]:
            continue
        candidate: list[tuple[date, bool]] = []
        for row in table[1:]:
            if not row or row[0] not in month_numbers:
                continue
            for cell in row[1:]:
                match = re.search(r"\d{2}", cell)
                if match:
                    release = date(2026, month_numbers[row[0]], int(match.group()))
                    candidate.append((release, "*" in cell))
        if len(candidate) > len(release_cells):
            release_cells = candidate

    rows: list[dict[str, str]] = []
    for release, delayed in release_cells:
        if release > date(2026, 8, 14):
            continue
        if release.weekday() == 0:
            report = release - timedelta(days=6)
        elif release.weekday() == 4:
            report = release - timedelta(days=3)
        else:
            raise ValueError(f"unexpected CFTC release weekday: {release}")
        rows.append(
            {
                "report_date": report.isoformat(),
                "release_date": release.isoformat(),
                "release_time": "15:30",
                "release_timezone": "America/New_York",
                "federal_holiday_delay": "true" if delayed else "false",
                "source_url": source_url,
            }
        )
    if len(rows) != 33 or rows[-1]["report_date"] != "2026-08-11":
        raise ValueError("unexpected CFTC 2026 schedule coverage")
    return _csv_bytes(
        (
            "report_date",
            "release_date",
            "release_time",
            "release_timezone",
            "federal_holiday_delay",
            "source_url",
        ),
        rows,
    )


def _parse_date_cell(value: str) -> date:
    return datetime.strptime(value.strip(), "%m/%d/%Y").date()


def extract_cftc_exceptions(payload: bytes, source_url: str) -> bytes:
    candidates: list[dict[date, date]] = []
    for table in _tables(payload):
        if not table or len(table[0]) < 3 or table[0][0] != "COT Report Date":
            continue
        mapping: dict[date, date] = {}
        for row in table[1:]:
            if len(row) < 3:
                continue
            report_match = re.search(r"\d{2}/\d{2}/\d{4}", row[0])
            release_match = re.search(r"\d{2}/\d{2}/\d{4}", row[2])
            if report_match and release_match:
                mapping[_parse_date_cell(report_match.group())] = _parse_date_cell(
                    release_match.group()
                )
        if mapping:
            candidates.append(mapping)
    expected = {
        date(2025, 9, 30): date(2025, 11, 19),
        date(2025, 10, 7): date(2025, 11, 21),
        date(2025, 10, 14): date(2025, 11, 25),
        date(2025, 10, 21): date(2025, 12, 2),
        date(2025, 10, 28): date(2025, 12, 5),
        date(2025, 11, 4): date(2025, 12, 9),
        date(2025, 11, 10): date(2025, 12, 10),
        date(2025, 11, 18): date(2025, 12, 12),
        date(2025, 11, 25): date(2025, 12, 15),
        date(2025, 12, 2): date(2025, 12, 17),
        date(2025, 12, 9): date(2025, 12, 19),
        date(2025, 12, 16): date(2025, 12, 23),
        date(2025, 12, 23): date(2025, 12, 29),
    }
    if expected not in candidates:
        raise ValueError("official CFTC final catch-up schedule does not match expected dates")
    text = _clean(payload.decode("utf-8", errors="replace"))
    if "released on Monday, January 13, 2025" not in text:
        raise ValueError("CFTC January 2025 special-release fact is missing")

    rows = [
        {
            "report_date": date(2025, 1, 7).isoformat(),
            "release_date": date(2025, 1, 13).isoformat(),
            "release_time": "15:30",
            "release_timezone": "America/New_York",
            "reason": "National Day of Mourning delay",
            "source_url": source_url,
        }
    ]
    rows.extend(
        {
            "report_date": report.isoformat(),
            "release_date": release.isoformat(),
            "release_time": "15:30",
            "release_timezone": "America/New_York",
            "reason": "2025 lapse-in-appropriations catch-up schedule",
            "source_url": source_url,
        }
        for report, release in sorted(expected.items())
    )
    return _csv_bytes(
        (
            "report_date",
            "release_date",
            "release_time",
            "release_timezone",
            "reason",
            "source_url",
        ),
        rows,
    )


def _xlsx_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))  # noqa: S314
    return [
        "".join(node.text or "" for node in item.iter(f"{{{_SS_NS}}}t"))
        for item in root.findall(f"{{{_SS_NS}}}si")
    ]


def _xlsx_sheet_paths(archive: zipfile.ZipFile) -> dict[str, str]:
    workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))  # noqa: S314
    relationships = ElementTree.fromstring(  # noqa: S314
        archive.read("xl/_rels/workbook.xml.rels")
    )
    targets = {
        rel.attrib["Id"]: rel.attrib["Target"]
        for rel in relationships.findall(f"{{{_REL_PKG_NS}}}Relationship")
    }
    output: dict[str, str] = {}
    for sheet in workbook.iter(f"{{{_SS_NS}}}sheet"):
        relationship_id = sheet.attrib[f"{{{_REL_DOC_NS}}}id"]
        output[sheet.attrib["name"]] = (PurePosixPath("xl") / targets[relationship_id]).as_posix()
    return output


def _column_number(reference: str) -> int:
    match = re.match(r"([A-Z]+)", reference)
    if not match:
        raise ValueError(f"invalid spreadsheet cell reference: {reference}")
    number = 0
    for character in match.group(1):
        number = number * 26 + ord(character) - ord("A") + 1
    return number


def _xlsx_cells(
    archive: zipfile.ZipFile, sheet_path: str, shared_strings: list[str]
) -> dict[tuple[int, int], str]:
    root = ElementTree.fromstring(archive.read(sheet_path))  # noqa: S314
    cells: dict[tuple[int, int], str] = {}
    for row in root.iter(f"{{{_SS_NS}}}row"):
        row_number = int(row.attrib["r"])
        for cell in row.findall(f"{{{_SS_NS}}}c"):
            value_node = cell.find(f"{{{_SS_NS}}}v")
            if value_node is None or value_node.text is None:
                continue
            value = value_node.text
            if cell.attrib.get("t") == "s":
                value = shared_strings[int(value)]
            cells[(row_number, _column_number(cell.attrib["r"]))] = value
    return cells


def extract_world_bank_cocoa(payload: bytes, source_url: str) -> bytes:
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        shared_strings = _xlsx_shared_strings(archive)
        paths = _xlsx_sheet_paths(archive)
        monthly = _xlsx_cells(archive, paths["Monthly Prices"], shared_strings)
    if monthly[(1, 1)] != "World Bank Commodity Price Data (The Pink Sheet)":
        raise ValueError("unexpected World Bank workbook title")
    if monthly[(4, 1)] != "Updated on August 04, 2026":
        raise ValueError("unexpected World Bank workbook vintage")
    if monthly[(5, 12)] != "Cocoa" or monthly[(6, 12)] != "($/kg)":
        raise ValueError("unexpected World Bank cocoa series or unit")

    wanted = {"2026M01", "2026M02", "2026M03", "2026M07"}
    extracted: dict[str, str] = {}
    for (row, column), value in monthly.items():
        if column == 1 and value in wanted:
            extracted[value] = monthly[(row, 12)]
    if set(extracted) != wanted:
        raise ValueError("World Bank workbook is missing a required cocoa month")
    rows = [
        {
            "original_period_label": label,
            "period": f"{label[:4]}-{label[-2:]}",
            "price_usd_per_kg": f"{float(extracted[label]):.2f}",
            "original_series_name": "Cocoa",
            "original_unit": "($/kg)",
            "source_vintage_updated_date": "2026-08-04",
            "availability_precision": "date_only_exact_time_not_asserted",
            "provider": "World Bank Prospects Group",
            "underlying_series_attribution": "International Cocoa Organization (ICCO)",
            "source_url": source_url,
        }
        for label in sorted(wanted)
    ]
    return _csv_bytes(
        (
            "original_period_label",
            "period",
            "price_usd_per_kg",
            "original_series_name",
            "original_unit",
            "source_vintage_updated_date",
            "availability_precision",
            "provider",
            "underlying_series_attribution",
            "source_url",
        ),
        rows,
    )
