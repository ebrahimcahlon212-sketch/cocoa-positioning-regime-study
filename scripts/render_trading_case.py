"""Render the cocoa trading research case.

The report consumes ``data/derived/trading_case_summary.json`` when it is
available. Optional evidence is never silently imputed: missing licensed or
public inputs are rendered as explicit ``NOT YET AVAILABLE`` states.
"""

from __future__ import annotations

import csv
import html
import json
import math
import textwrap
from dataclasses import dataclass
from datetime import datetime
from itertools import pairwise
from pathlib import Path
from typing import cast

import matplotlib

matplotlib.use("Agg")

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph

NAVY = "#173249"
BLUE = "#27718F"
CYAN = "#73AFC1"
GOLD = "#C28D2C"
GREEN = "#3D7865"
RED = "#B34C4C"
INK = "#1D2932"
MID = "#5D6A73"
RULE = "#D7DFE4"
PALE_BLUE = "#EAF3F6"
PALE_GOLD = "#FBF3E3"
PALE_GREEN = "#EAF3EF"
PALE_RED = "#FAECEC"
PALE_GREY = "#F4F7F8"
WHITE = "#FFFFFF"

REPO_URL = "https://github.com/ebrahimcahlon212-sketch/cocoa-positioning-regime-study"
CFTC_URL = "https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm"
ICCO_URL = "https://www.icco.org/may-2026-quarterly-bulletin-of-cocoa-statistics/"
ECA_URL = "https://www.eurococoa.com/grind-stats/"
CAA_URL = "https://www.cocoaasia.org/grinding-figures"
NCA_URL = "https://candyusa.com/cocoa-grinds-report"
NASA_POWER_URL = "https://power.larc.nasa.gov/"
WORLD_BANK_PINK_SHEET_URL = (
    "https://thedocs.worldbank.org/en/doc/"
    "74e8be41ceb20fa0da750cda2f6b9e4e-0050012026/related/"
    "CMO-Historical-Data-Monthly.xlsx"
)
DEFAULT_STRUCTURE = (
    "Defined-risk call spread; strike selection and premium require a permitted "
    "option-chain input and a separately frozen rule."
)
DEFAULT_EXIT_RULE = (
    "Earliest of 40 sessions, CFTC normalized net at or above zero, normalized net below "
    "its entry level, or 10 sessions before option last trading day."
)


@dataclass(frozen=True)
class SummaryDocument:
    """Validated top-level report input and its availability state."""

    data: dict[str, object]
    used_trading_summary: bool


@dataclass(frozen=True)
class PositionRow:
    """One retained point-in-time positioning observation."""

    report_date: datetime
    net_contracts: int
    open_interest_contracts: int


@dataclass(frozen=True)
class PriceRow:
    """One retained public monthly price-proxy observation."""

    period: datetime
    usd_per_kg: float


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _as_mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{label} must be a JSON object with string keys")
    return cast(dict[str, object], value)


def _mapping_at(mapping: dict[str, object], key: str) -> dict[str, object]:
    value = mapping.get(key)
    if value is None:
        return {}
    return _as_mapping(value, key)


def _list_at(mapping: dict[str, object], key: str) -> list[object]:
    value = mapping.get(key)
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{key} must be a JSON array")
    return value


def _string_at(mapping: dict[str, object], key: str) -> str | None:
    value = mapping.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value


def _number_at(mapping: dict[str, object], key: str) -> float | None:
    value = mapping.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{key} must be numeric")
    return float(value)


def _integer_at(mapping: dict[str, object], key: str) -> int | None:
    value = mapping.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    return value


def _boolean_at(mapping: dict[str, object], key: str) -> bool | None:
    value = mapping.get(key)
    if value is None:
        return None
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be a boolean")
    return value


def _fallback_document(root: Path) -> dict[str, object]:
    """Build a minimal, clearly labelled document from the original study."""

    cutoff: dict[str, object] = {"local": "not yet available", "utc": "not yet available"}
    positioning: dict[str, object] = {
        "source_note": "Original point-in-time CFTC study; V2 summary not yet materialized."
    }
    original = root / "data" / "derived" / "study_summary.json"
    if original.exists():
        raw: object = json.loads(original.read_text(encoding="utf-8"))
        study = _as_mapping(raw, "study_summary")
        cutoff = _mapping_at(study, "cutoff") or cutoff
        findings = _mapping_at(study, "findings")
        latest = _mapping_at(findings, "latest_cftc")
        changes = _mapping_at(findings, "changes")
        positioning.update(
            {
                "latest_net": latest.get("managed_money_net_contracts"),
                "latest_oi": latest.get("open_interest_contracts"),
                "peak_to_trough": changes.get("managed_money_peak_to_trough_change_contracts"),
            }
        )
    return {
        "study": "Cocoa Trading Research Case",
        "cutoff": cutoff,
        "positioning": positioning,
        "physical": {},
        "weather": {},
        "signal": {},
        "trade": {},
        "science": {},
        "sources": [],
    }


def _load_summary(root: Path) -> SummaryDocument:
    path = root / "data" / "derived" / "trading_case_summary.json"
    if not path.exists():
        return SummaryDocument(_fallback_document(root), used_trading_summary=False)
    raw: object = json.loads(path.read_text(encoding="utf-8"))
    document = _as_mapping(raw, "trading_case_summary")
    if not isinstance(document.get("study"), str):
        raise ValueError("trading_case_summary.study must be a string")
    cutoff = document.get("cutoff")
    if cutoff is None:
        raise ValueError("trading_case_summary.cutoff is required")
    _as_mapping(cutoff, "cutoff")
    for key in (
        "evidence_gate",
        "positioning",
        "physical",
        "weather",
        "signal",
        "trade",
        "science",
    ):
        if key in document:
            _as_mapping(document[key], key)
    if "sources" in document:
        _list_at(document, "sources")
    return SummaryDocument(document, used_trading_summary=True)


def _load_positions(root: Path) -> list[PositionRow]:
    path = root / "data" / "derived" / "cocoa_cot_positioning.csv"
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        raw = list(csv.DictReader(handle))
    rows = [
        PositionRow(
            report_date=datetime.strptime(row["report_date"], "%Y-%m-%d"),
            net_contracts=int(row["managed_money_net_contracts"]),
            open_interest_contracts=int(row["open_interest_contracts"]),
        )
        for row in raw
    ]
    if rows != sorted(rows, key=lambda item: item.report_date):
        raise ValueError("positioning table must be sorted by report_date")
    return rows


def _load_prices(root: Path) -> list[PriceRow]:
    path = root / "data" / "derived" / "cocoa_price_monthly.csv"
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        raw = list(csv.DictReader(handle))
    return [
        PriceRow(
            period=datetime.strptime(row["period_start"], "%Y-%m-%d"),
            usd_per_kg=float(row["price_usd_per_kg"]),
        )
        for row in raw
    ]


def _safe(value: object) -> str:
    return html.escape(str(value), quote=True)


def _shorten(value: str, width: int) -> str:
    return textwrap.shorten(value, width=width, placeholder="...")


def _human_label(value: str) -> str:
    exact = {
        "ILLUSTRATIVE_NOT_MARKET_DATA": "ILLUSTRATIVE / NOT MARKET DATA",
        "NOT_EVALUATED_LICENSED_MARKET_INPUTS": (
            "NOT EVALUATED - LICENSED SETTLEMENT HISTORY AND OPTION CHAIN ARE ABSENT"
        ),
        "CONTEXT_ONLY_NOT_REGISTERED_V1": "CONTEXT ONLY / INELIGIBLE FOR V1 GATE",
    }
    return exact.get(value, value.replace("_", " "))


def _source_url(
    document: SummaryDocument,
    source_id_fragment: str,
    fallback: str,
) -> str:
    fragment = source_id_fragment.lower()
    for index, value in enumerate(_list_at(document.data, "sources")):
        record = _as_mapping(value, f"sources[{index}]")
        source_id = _string_at(record, "source_id")
        source_url = _string_at(record, "source_url")
        if source_id is not None and source_url is not None and fragment in source_id.lower():
            return source_url
    return fallback


def _display_number(value: float | int | None, template: str) -> str:
    if value is None:
        return "NOT YET AVAILABLE"
    return template.format(value)


def _display_date(value: str | None) -> str:
    if value is None or value.lower().startswith("not yet"):
        return "not yet available"
    if len(value) == 10:
        try:
            return datetime.strptime(value, "%Y-%m-%d").strftime("%d %b %Y")
        except ValueError:
            return value
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    timezone = ""
    offset = parsed.utcoffset()
    if offset is not None:
        timezone = " UTC" if offset.total_seconds() == 0 else parsed.strftime(" %z")
    return f"{parsed.strftime('%d %b %Y')} {parsed.strftime('%H:%M')}{timezone}"


def _hex(value: str) -> colors.Color:
    return colors.HexColor(value)


def _paragraph(
    pdf: canvas.Canvas,
    text: str,
    *,
    x: float,
    y: float,
    width: float,
    height: float,
    font_size: float = 7.2,
    leading: float = 8.8,
    color: str = INK,
    font_name: str = "Helvetica",
) -> None:
    style = ParagraphStyle(
        name="body",
        fontName=font_name,
        fontSize=font_size,
        leading=leading,
        textColor=_hex(color),
        alignment=TA_LEFT,
        spaceAfter=0,
        spaceBefore=0,
    )
    paragraph = Paragraph(text, style)
    _, used_height = paragraph.wrap(width, height)
    if used_height > height:
        raise ValueError(f"text block exceeds allocated height: {text!r}")
    paragraph.drawOn(pdf, x, y + height - used_height)


def _badge(
    pdf: canvas.Canvas,
    text: str,
    *,
    x: float,
    y: float,
    fill: str = PALE_BLUE,
    color: str = BLUE,
    font_size: float = 5.8,
) -> float:
    label = text.upper()
    width = stringWidth(label, "Helvetica-Bold", font_size) + 14
    pdf.setFillColor(_hex(fill))
    pdf.roundRect(x, y, width, 15, 7.5, fill=1, stroke=0)
    pdf.setFillColor(_hex(color))
    pdf.setFont("Helvetica-Bold", font_size)
    pdf.drawString(x + 7, y + 5, label)
    return width


def _section_label(pdf: canvas.Canvas, text: str, *, x: float, y: float) -> None:
    pdf.setFillColor(_hex(NAVY))
    pdf.setFont("Helvetica-Bold", 8.1)
    pdf.drawString(x, y, text.upper())


def _metric_card(
    pdf: canvas.Canvas,
    *,
    x: float,
    y: float,
    width: float,
    title: str,
    value: str,
    note: str,
    accent: str,
    fill: str,
) -> None:
    pdf.setFillColor(_hex(fill))
    pdf.roundRect(x, y, width, 58, 7, fill=1, stroke=0)
    pdf.setFillColor(_hex(accent))
    pdf.rect(x, y, 3.5, 58, fill=1, stroke=0)
    pdf.setFillColor(_hex(MID))
    pdf.setFont("Helvetica-Bold", 5.8)
    pdf.drawString(x + 11, y + 44, title.upper())
    pdf.setFillColor(_hex(accent))
    pdf.setFont("Helvetica-Bold", 12.1 if len(value) < 20 else 8.4)
    pdf.drawString(x + 11, y + 27, value)
    _paragraph(
        pdf,
        note,
        x=x + 11,
        y=y + 7,
        width=width - 18,
        height=15,
        font_size=5.7,
        leading=6.6,
        color=MID,
    )


def _page_header(
    pdf: canvas.Canvas,
    *,
    eyebrow: str,
    title: str,
    subtitle: str,
    as_of: str,
) -> None:
    width, height = A4
    pdf.setFillColor(_hex(NAVY))
    pdf.rect(0, height - 105, width, 105, fill=1, stroke=0)
    pdf.setFillColor(_hex(CYAN))
    pdf.setFont("Helvetica-Bold", 6.8)
    pdf.drawString(36, height - 24, eyebrow.upper())
    pdf.setFillColor(_hex(WHITE))
    pdf.setFont("Helvetica-Bold", 18.5)
    pdf.drawString(36, height - 52, title)
    pdf.setFont("Helvetica", 8.4)
    pdf.drawString(36, height - 72, subtitle)
    pdf.setFont("Helvetica-Bold", 6.3)
    pdf.drawRightString(width - 36, height - 91, f"AS OF: {as_of}")


def _link(
    pdf: canvas.Canvas,
    label: str,
    url: str,
    *,
    x: float,
    y: float,
    font_size: float = 5.7,
) -> float:
    pdf.setFillColor(_hex(BLUE))
    pdf.setFont("Helvetica-Bold", font_size)
    pdf.drawString(x, y, label)
    width = stringWidth(label, "Helvetica-Bold", font_size)
    pdf.linkURL(url, (x, y - 2, x + width, y + font_size + 2), relative=0, thickness=0)
    return width


def _footer(pdf: canvas.Canvas, page_number: int) -> None:
    width, _ = A4
    pdf.setStrokeColor(_hex(RULE))
    pdf.setLineWidth(0.6)
    pdf.line(36, 44, width - 36, 44)
    _link(
        pdf,
        "github.com/ebrahimcahlon212-sketch/cocoa-positioning-regime-study",
        REPO_URL,
        x=36,
        y=27,
    )
    label = f"Ebrahim Cahlon | {page_number} / 2"
    pdf.setFillColor(_hex(MID))
    pdf.setFont("Helvetica", 5.8)
    pdf.drawRightString(width - 36, 27, label)


def _build_dashboard_chart(
    positions: list[PositionRow],
    prices: list[PriceRow],
    summary: SummaryDocument,
    output: Path,
) -> None:
    """Build a deterministic three-lens dashboard for page one."""

    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 7,
            "axes.edgecolor": RULE,
            "axes.labelcolor": MID,
            "axes.titlecolor": INK,
            "axes.titleweight": "bold",
            "axes.titlesize": 8.3,
            "axes.unicode_minus": False,
            "xtick.color": MID,
            "ytick.color": MID,
        }
    )
    fig = plt.figure(figsize=(7.45, 2.95), dpi=220, facecolor=WHITE)
    grid = fig.add_gridspec(2, 3, width_ratios=(1.52, 1.52, 1.0), hspace=0.15, wspace=0.24)
    top = fig.add_subplot(grid[0, :2])
    bottom = fig.add_subplot(grid[1, :2], sharex=top)
    right = fig.add_subplot(grid[:, 2])
    for axis in (top, bottom, right):
        axis.set_facecolor(WHITE)

    if positions:
        dates = [row.report_date for row in positions]
        date_values = [
            float(mdates.date2num(value))  # type: ignore[no-untyped-call]
            for value in dates
        ]
        net = [row.net_contracts / 1000 for row in positions]
        oi = [row.open_interest_contracts / 1000 for row in positions]
        top.axhline(0, color=MID, linewidth=0.65)
        top.plot(date_values, net, color=BLUE, linewidth=1.7)
        top.fill_between(
            date_values,
            net,
            0,
            where=[value >= 0 for value in net],
            color=GOLD,
            alpha=0.2,
        )
        top.fill_between(
            date_values,
            net,
            0,
            where=[value < 0 for value in net],
            color=RED,
            alpha=0.16,
        )
        top.scatter(
            [date_values[-1]],
            [net[-1]],
            color=BLUE,
            edgecolor=WHITE,
            linewidth=0.7,
            s=20,
            zorder=4,
        )
        top.annotate(
            f"{net[-1]:+.1f}k latest",
            (date_values[-1], net[-1]),
            xytext=(-5, 7),
            textcoords="offset points",
            ha="right",
            fontsize=6.2,
            fontweight="bold",
            color=NAVY,
        )
        bottom.plot(date_values, oi, color=NAVY, linewidth=1.4)
        bottom.fill_between(date_values, oi, min(oi) - 5, color=CYAN, alpha=0.16)
        bottom.scatter(
            [date_values[-1]],
            [oi[-1]],
            color=NAVY,
            edgecolor=WHITE,
            linewidth=0.6,
            s=17,
            zorder=4,
        )
        bottom.xaxis_date()
        bottom.xaxis.set_major_locator(mdates.MonthLocator(interval=5))  # type: ignore[no-untyped-call]
        bottom.xaxis.set_major_formatter(mdates.DateFormatter("%b\n%Y"))  # type: ignore[no-untyped-call]
    else:
        for axis in (top, bottom):
            axis.text(
                0.5,
                0.5,
                "NOT YET AVAILABLE",
                ha="center",
                va="center",
                color=MID,
                transform=axis.transAxes,
            )
            axis.set_xticks([])
            axis.set_yticks([])
    top.set_title("Positioning lens - release-time controlled", loc="left", pad=3)
    top.set_ylabel("Net (000)", fontsize=6.2)
    top.grid(axis="y", color=RULE, linewidth=0.45)
    top.tick_params(axis="x", labelbottom=False)
    bottom.set_ylabel("OI (000)", fontsize=6.2)
    bottom.grid(axis="y", color=RULE, linewidth=0.45)
    bottom.tick_params(axis="x", labelsize=5.7)
    for axis in (top, bottom):
        axis.spines[["top", "right"]].set_visible(False)

    physical = _mapping_at(summary.data, "physical")
    balance = _mapping_at(physical, "latest_balance")
    production = _number_at(balance, "production_kt")
    grindings = _number_at(balance, "grindings_kt")
    stocks = _number_at(balance, "ending_stocks_kt")
    labels: list[str] = []
    values: list[float] = []
    for label, value in (
        ("Production", production),
        ("Grindings", grindings),
        ("End stocks", stocks),
    ):
        if value is not None:
            labels.append(label)
            values.append(value)
    if values:
        positions_y = list(range(len(values)))[::-1]
        right.barh(positions_y, values, color=[BLUE, GOLD, GREEN][: len(values)], height=0.48)
        right.set_yticks(positions_y, labels, fontsize=6.1)
        right.set_xlabel("kt", fontsize=6)
        maximum = max(values)
        for y_value, value in zip(positions_y, values, strict=True):
            right.text(
                value + maximum * 0.02,
                y_value,
                f"{value:,.0f}",
                va="center",
                fontsize=6.1,
                color=INK,
            )
        right.set_xlim(0, maximum * 1.24)
        right.grid(axis="x", color=RULE, linewidth=0.45)
    else:
        right.text(
            0.5,
            0.55,
            "NOT YET AVAILABLE",
            ha="center",
            va="center",
            color=MID,
            transform=right.transAxes,
            fontweight="bold",
        )
        right.text(
            0.5,
            0.42,
            "No verified physical snapshot\nin summary JSON",
            ha="center",
            va="center",
            color=MID,
            transform=right.transAxes,
            fontsize=6.2,
        )
        right.set_xticks([])
        right.set_yticks([])
    right.set_title("Physical lens - public snapshot", loc="left", pad=6)
    right.spines[["top", "right", "left"]].set_visible(False)
    right.tick_params(axis="y", length=0)
    fig.subplots_adjust(left=0.07, right=0.98, top=0.89, bottom=0.17)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(
        output,
        facecolor=WHITE,
        bbox_inches="tight",
        metadata={"Software": "cocoa-positioning-regime-study"},
    )
    plt.close(fig)


def _draw_physical_box(pdf: canvas.Canvas, document: SummaryDocument) -> None:
    physical = _mapping_at(document.data, "physical")
    balance = _mapping_at(physical, "latest_balance")
    pdf.setFillColor(_hex(PALE_GREY))
    pdf.roundRect(36, 128, 306, 163, 8, fill=1, stroke=0)
    _section_label(pdf, "Physical balance snapshot", x=49, y=270)
    _badge(
        pdf,
        "public snapshot - not full vintage history",
        x=184,
        y=262,
        fill=PALE_GOLD,
        color=GOLD,
        font_size=4.9,
    )
    crop_year = _string_at(balance, "crop_year") or "not yet available"
    published = _display_date(_string_at(balance, "published_at"))
    surplus = _number_at(balance, "surplus_kt")
    ratio = _number_at(balance, "stocks_to_grind_pct")
    _paragraph(
        pdf,
        f"<b>{_safe(crop_year)}</b> | published {_safe(published)}",
        x=49,
        y=240,
        width=280,
        height=17,
        font_size=6.7,
        leading=8,
    )
    fields = (
        ("Production", _number_at(balance, "production_kt"), "kt"),
        ("Grindings", _number_at(balance, "grindings_kt"), "kt"),
        ("Surplus", surplus, "kt"),
        ("Ending stocks", _number_at(balance, "ending_stocks_kt"), "kt"),
        ("Stocks / grind", ratio, "%"),
    )
    x_positions = (49, 108, 167, 226, 285)
    for x_pos, (label, value, unit) in zip(x_positions, fields, strict=True):
        pdf.setFillColor(_hex(MID))
        pdf.setFont("Helvetica-Bold", 5.1)
        pdf.drawString(x_pos, 226, label.upper())
        pdf.setFillColor(_hex(NAVY))
        pdf.setFont("Helvetica-Bold", 8.6 if value is not None else 5.3)
        if value is None:
            displayed = "N/A"
        elif label == "Stocks / grind":
            displayed = f"{value:,.1f}%"
        else:
            displayed = f"{value:,.0f}{unit}"
        pdf.drawString(x_pos, 212, displayed)
    revisions = _list_at(physical, "vintage_changes")
    grindings = _list_at(physical, "grindings")
    revision_text = (
        f"{len(revisions)} recorded balance {'revision' if len(revisions) == 1 else 'revisions'}"
        if revisions
        else "Balance revisions: not yet available"
    )
    grinding_text = (
        f"{len(grindings)} recorded regional grindings releases"
        if grindings
        else "Regional grindings: not yet available"
    )
    _paragraph(
        pdf,
        f"<b>Vintage discipline:</b> {_safe(revision_text)}. {_safe(grinding_text)}. "
        "A single official estimate anchors the view but cannot establish the historical signal alone.",
        x=49,
        y=155,
        width=280,
        height=44,
        font_size=6.3,
        leading=7.6,
        color=MID,
    )
    balance_url = _string_at(balance, "source_url") or ICCO_URL
    grinding_urls: dict[str, str] = {}
    for index, grinding_item in enumerate(grindings):
        record = _as_mapping(grinding_item, f"physical.grindings[{index}]")
        region = _string_at(record, "region")
        source_url = _string_at(record, "source_url")
        if region is not None and source_url is not None:
            grinding_urls[region] = source_url
    _link(pdf, "ICCO May", balance_url, x=49, y=139, font_size=4.9)
    _link(
        pdf,
        "Europe Q2",
        grinding_urls.get("Europe", ECA_URL),
        x=111,
        y=139,
        font_size=4.9,
    )
    _link(
        pdf,
        "Asia Q2",
        grinding_urls.get("Asia", CAA_URL),
        x=178,
        y=139,
        font_size=4.9,
    )
    _link(
        pdf,
        "N. America Q2",
        grinding_urls.get("North America", NCA_URL),
        x=234,
        y=139,
        font_size=4.9,
    )


def _draw_weather_box(pdf: canvas.Canvas, document: SummaryDocument) -> None:
    weather = _mapping_at(document.data, "weather")
    pdf.setFillColor(_hex(PALE_BLUE))
    pdf.roundRect(352, 128, 207, 163, 8, fill=1, stroke=0)
    _section_label(pdf, "Weather and event lens", x=365, y=270)
    risk = _string_at(weather, "risk_label") or "NOT YET AVAILABLE"
    quality_gate = _string_at(weather, "quality_gate")
    displayed_risk = (
        "SECOND-SOURCE CHECK REQUIRED" if quality_gate == "SECOND_SOURCE_REQUIRED" else risk
    )
    rainfall = _number_at(weather, "rainfall_anomaly_pct")
    dry_days = _number_at(weather, "dry_spell_days")
    scope = _string_at(weather, "scope") or "Location-proxy scope not yet available"
    as_of = _display_date(_string_at(weather, "as_of"))
    weather_window = "not yet available"
    proxies = _list_at(weather, "location_proxies")
    if proxies:
        first_proxy = _as_mapping(proxies[0], "weather.location_proxies[0]")
        weather_window = _display_date(_string_at(first_proxy, "window_end"))
    fill = PALE_RED if quality_gate == "SECOND_SOURCE_REQUIRED" else PALE_GOLD
    color = RED if quality_gate == "SECOND_SOURCE_REQUIRED" else GOLD
    _badge(pdf, displayed_risk, x=365, y=243, fill=fill, color=color, font_size=5.2)
    pdf.setFillColor(_hex(MID))
    pdf.setFont("Helvetica-Bold", 5.2)
    pdf.drawString(365, 229, "RAINFALL ANOMALY")
    pdf.drawString(454, 229, "DRY DAYS <1MM")
    pdf.setFillColor(_hex(NAVY))
    pdf.setFont("Helvetica-Bold", 10.5)
    rainfall_display = _string_at(weather, "rainfall_anomaly_display")
    if rainfall_display is None:
        rainfall_display = f"{rainfall:+.1f}%" if rainfall is not None else "N/A"
    dry_days_display = _string_at(weather, "dry_spell_days_display")
    if dry_days_display is None:
        dry_days_display = f"{dry_days:.0f}" if dry_days is not None else "N/A"
    pdf.setFont("Helvetica-Bold", 8.6 if len(rainfall_display) > 12 else 10.5)
    pdf.drawString(365, 213, rainfall_display)
    pdf.setFont("Helvetica-Bold", 8.6 if len(dry_days_display) > 12 else 10.5)
    pdf.drawString(454, 213, dry_days_display)
    _paragraph(
        pdf,
        f"<b>Scope:</b> {_safe(scope)}<br/><b>Window through:</b> {_safe(weather_window)} | "
        f"<b>Snapshot:</b> {_safe(as_of)}",
        x=365,
        y=173,
        width=181,
        height=31,
        font_size=5.9,
        leading=7.3,
        color=MID,
    )
    _paragraph(
        pdf,
        "NASA POWER location proxies. Kumasi's June extreme requires a second-source check; "
        "weather is context-only and ineligible for the v1 gate.",
        x=365,
        y=143,
        width=181,
        height=27,
        font_size=5.5,
        leading=6.7,
        color=INK,
    )
    proxy_urls: list[str] = []
    for index, value in enumerate(proxies[:2]):
        record = _as_mapping(value, f"weather.location_proxies[{index}]")
        source_url = _string_at(record, "source_url")
        if source_url is not None:
            proxy_urls.append(source_url)
    _link(
        pdf,
        "Daloa NASA POWER",
        proxy_urls[0] if proxy_urls else NASA_POWER_URL,
        x=365,
        y=132,
        font_size=4.8,
    )
    _link(
        pdf,
        "Kumasi NASA POWER",
        proxy_urls[1] if len(proxy_urls) > 1 else NASA_POWER_URL,
        x=455,
        y=132,
        font_size=4.8,
    )


def _draw_source_strip(pdf: canvas.Canvas, document: SummaryDocument) -> None:
    _paragraph(
        pdf,
        "<b>Evidence hierarchy:</b> release-time positioning + the registered official physical gate + NASA POWER weather context + scientific mechanisms. Weather cannot activate v1; price and return results remain public proxies until licensed contract-level data are supplied.",
        x=36,
        y=64,
        width=523,
        height=42,
        font_size=6.2,
        leading=7.7,
        color=MID,
    )
    physical = _mapping_at(document.data, "physical")
    balance = _mapping_at(physical, "latest_balance")
    science_claims = _science_claims(document)
    science_url = (
        _string_at(science_claims[0], "source_url") if science_claims else None
    ) or REPO_URL
    weather = _mapping_at(document.data, "weather")
    proxies = _list_at(weather, "location_proxies")
    weather_url = NASA_POWER_URL
    if proxies:
        weather_url = (
            _string_at(_as_mapping(proxies[0], "weather.location_proxies[0]"), "source_url")
            or NASA_POWER_URL
        )
    links = (
        ("CFTC", CFTC_URL),
        ("ICCO balance", _string_at(balance, "source_url") or ICCO_URL),
        ("NASA POWER", weather_url),
        (
            "World Bank Pink Sheet",
            _source_url(document, "world_bank_pink_sheet", WORLD_BANK_PINK_SHEET_URL),
        ),
        ("science", science_url),
    )
    link_x = 36.0
    for label, url in links:
        link_x += _link(pdf, label, url, x=link_x, y=57, font_size=5.4) + 14


def _render_page_one(
    pdf: canvas.Canvas,
    chart: Path,
    document: SummaryDocument,
) -> None:
    cutoff = _mapping_at(document.data, "cutoff")
    as_of = _display_date(_string_at(cutoff, "local") or _string_at(cutoff, "utc"))
    _page_header(
        pdf,
        eyebrow="Cocoa trading research case | public / reproducible",
        title="Cocoa: Positioning Meets Physical Risk",
        subtitle="A release-time decision framework linking positioning, balance sheets and weather",
        as_of=as_of,
    )
    pdf.setFillColor(_hex(PALE_BLUE))
    pdf.roundRect(36, 645, 523, 73, 8, fill=1, stroke=0)
    _badge(
        pdf,
        "conditional thesis - not a forecast",
        x=49,
        y=692,
        fill=PALE_GOLD,
        color=GOLD,
        font_size=5.3,
    )
    thesis = (
        "<b>Watch for convex upside event risk</b> if crop recovery disappoints while managed money remains short and price confirms. "
        "The opposite case is weaker grindings, a larger official surplus, renewed price weakness and fresh short formation. "
        "This framework specifies evidence and invalidation; it does not claim causality or alpha."
    )
    _paragraph(pdf, thesis, x=49, y=655, width=497, height=32, font_size=7.4, leading=9.1)

    positioning = _mapping_at(document.data, "positioning")
    physical = _mapping_at(document.data, "physical")
    balance = _mapping_at(physical, "latest_balance")
    weather = _mapping_at(document.data, "weather")
    net = _integer_at(positioning, "latest_net")
    swing = _integer_at(positioning, "peak_to_trough")
    surplus = _number_at(balance, "surplus_kt")
    weather_risk = _string_at(weather, "risk_label") or "NOT YET AVAILABLE"
    if _string_at(weather, "quality_gate") == "SECOND_SOURCE_REQUIRED":
        weather_risk = "SECOND-SOURCE CHECK"
    card_width = (523 - 12) / 3
    _metric_card(
        pdf,
        x=36,
        y=574,
        width=card_width,
        title="Latest managed-money net",
        value=_display_number(net, "{:+,.0f} contracts"),
        note=f"Peak-to-trough shift: {_display_number(swing, '{:+,.0f}')} contracts.",
        accent=BLUE,
        fill=PALE_BLUE,
    )
    _metric_card(
        pdf,
        x=42 + card_width,
        y=574,
        width=card_width,
        title="Official physical anchor",
        value=_display_number(surplus, "{:+,.0f}kt balance"),
        note="Public snapshot; revision history shown only when captured.",
        accent=GOLD,
        fill=PALE_GOLD,
    )
    _metric_card(
        pdf,
        x=48 + 2 * card_width,
        y=574,
        width=card_width,
        title="Weather risk state",
        value=weather_risk.upper(),
        note="Context only; location proxies are not crop-area weighted or a production estimate.",
        accent=GREEN,
        fill=PALE_GREEN,
    )
    pdf.drawImage(ImageReader(chart), 32, 302, width=531, height=258, preserveAspectRatio=True)
    price_context = "Public monthly price context: not yet available"
    prices = _load_prices(_repo_root())
    if prices:
        latest_price = prices[-1]
        price_context = (
            f"World Bank Pink Sheet {latest_price.period.strftime('%b %Y')}: "
            f"{latest_price.usd_per_kg:.2f} USD/kg - PUBLIC MONTHLY PROXY, NOT A FUTURES RETURN"
        )
    pdf.setFillColor(_hex(MID))
    pdf.setFont("Helvetica-Bold", 5.0)
    pdf.drawCentredString(297.5, 296, price_context)
    _draw_physical_box(pdf, document)
    _draw_weather_box(pdf, document)
    _draw_source_strip(pdf, document)
    _footer(pdf, 1)
    pdf.showPage()


def _trade_scenarios(trade: dict[str, object]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index, value in enumerate(_list_at(trade, "scenario_rows")):
        rows.append(_as_mapping(value, f"scenario_rows[{index}]"))
    return rows


def _scenario_numeric(row: dict[str, object]) -> tuple[float | None, float | None]:
    price: float | None = None
    pnl: float | None = None
    for key in (
        "expiry_price",
        "expiry_futures_price_usd_per_tonne",
        "reference_price",
        "underlying_price",
        "price",
    ):
        price = _number_at(row, key)
        if price is not None:
            break
    for key in ("pnl", "pnl_usd", "net_pnl", "net_pnl_usd", "payoff"):
        pnl = _number_at(row, key)
        if pnl is not None:
            break
    return price, pnl


def _draw_payoff(pdf: canvas.Canvas, trade: dict[str, object]) -> None:
    x, y, width, height = 36.0, 415.0, 250.0, 178.0
    pdf.setFillColor(_hex(PALE_GREY))
    pdf.roundRect(x, y, width, height, 8, fill=1, stroke=0)
    _section_label(pdf, "Defined-risk payoff", x=x + 13, y=y + height - 20)
    curve_rows = [
        _as_mapping(value, f"payoff_curve[{index}]")
        for index, value in enumerate(_list_at(trade, "payoff_curve"))
    ]
    numeric: list[tuple[float, float]] = []
    for price, pnl in map(_scenario_numeric, curve_rows):
        if price is not None and pnl is not None:
            numeric.append((price, pnl))
    plot_x0, plot_y0 = x + 31, y + 38
    plot_w, plot_h = width - 49, height - 75
    pdf.setStrokeColor(_hex(RULE))
    pdf.line(plot_x0, plot_y0 + plot_h / 2, plot_x0 + plot_w, plot_y0 + plot_h / 2)
    pdf.line(plot_x0, plot_y0, plot_x0, plot_y0 + plot_h)
    if len(numeric) >= 2:
        numeric = sorted(numeric)
        prices = [item[0] for item in numeric]
        pnls = [item[1] for item in numeric]
        min_price, max_price = min(prices), max(prices)
        min_pnl, max_pnl = min(pnls), max(pnls)
        if math.isclose(min_price, max_price):
            max_price += 1
        if math.isclose(min_pnl, max_pnl):
            max_pnl += 1
        points = [
            (
                plot_x0 + (price - min_price) / (max_price - min_price) * plot_w,
                plot_y0 + (pnl - min_pnl) / (max_pnl - min_pnl) * plot_h,
            )
            for price, pnl in numeric
        ]
        pdf.setStrokeColor(_hex(BLUE))
        pdf.setLineWidth(2)
        for start, end in pairwise(points):
            pdf.line(start[0], start[1], end[0], end[1])
        for point in points:
            pdf.setFillColor(_hex(BLUE))
            pdf.circle(point[0], point[1], 2.3, fill=1, stroke=0)
        caption = "ILLUSTRATIVE PAYOFF - NOT MARKET DATA"
    else:
        points = [
            (plot_x0, plot_y0 + plot_h * 0.30),
            (plot_x0 + plot_w * 0.34, plot_y0 + plot_h * 0.30),
            (plot_x0 + plot_w * 0.70, plot_y0 + plot_h * 0.78),
            (plot_x0 + plot_w, plot_y0 + plot_h * 0.78),
        ]
        pdf.setStrokeColor(_hex(BLUE))
        pdf.setLineWidth(2)
        for start, end in pairwise(points):
            pdf.line(start[0], start[1], end[0], end[1])
        caption = "NORMALIZED CALL-SPREAD SCHEMATIC - NOT PRICED"
    pdf.setFillColor(_hex(MID))
    pdf.setFont("Helvetica-Bold", 5.0)
    pdf.drawCentredString(x + width / 2, y + 19, caption)
    pdf.setFont("Helvetica", 5.1)
    pdf.drawString(plot_x0 - 6, plot_y0 + plot_h + 5, "P&L")
    pdf.drawRightString(plot_x0 + plot_w, plot_y0 - 11, "UNDERLYING AT EXIT")


def _draw_trade_rules(pdf: canvas.Canvas, document: SummaryDocument) -> None:
    trade = _mapping_at(document.data, "trade")
    x, y, width, height = 296.0, 415.0, 263.0, 178.0
    pdf.setFillColor(_hex(PALE_BLUE))
    pdf.roundRect(x, y, width, height, 8, fill=1, stroke=0)
    _section_label(pdf, "Hypothetical trade rule", x=x + 13, y=y + height - 20)
    _badge(
        pdf,
        "hypothetical / no broker action",
        x=x + 13,
        y=y + height - 43,
        fill=PALE_RED,
        color=RED,
        font_size=5.0,
    )
    instrument = _string_at(trade, "instrument") or "Defined-risk cocoa call spread"
    month = _string_at(trade, "contract_month") or "contract month not selected"
    structure = _string_at(trade, "structure") or DEFAULT_STRUCTURE
    input_class = (
        _string_at(trade, "illustrative_input_classification")
        or "NOT YET AVAILABLE - no permitted option-chain input"
    )
    input_class = _human_label(input_class)
    entry = (
        _string_at(trade, "entry_rule")
        or "Activate only after registered physical deterioration, positioning reversal and "
        "licensed settlement breakout; weather is context-only."
    )
    exit_rule = _string_at(trade, "exit_rule") or DEFAULT_EXIT_RULE
    max_risk = _number_at(trade, "max_portfolio_risk_pct")
    risk = _display_number(max_risk, "{:.2f}%")
    _paragraph(
        pdf,
        f"<b>Instrument:</b> {_safe(instrument)} - {_safe(month)}<br/>"
        f"<b>Input class:</b> {_safe(input_class)}<br/>"
        f"<b>Structure:</b> {_safe(structure)}<br/>"
        f"<b>Entry:</b> {_safe(entry)}<br/>"
        f"<b>Exit / invalidation:</b> {_safe(exit_rule)}<br/>"
        f"<b>Maximum portfolio risk:</b> {_safe(risk)}",
        x=x + 13,
        y=y + 12,
        width=width - 26,
        height=115,
        font_size=6.0,
        leading=7.6,
    )


def _value_from_row(row: dict[str, object], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = row.get(key)
        if value is not None:
            if isinstance(value, float):
                return f"{value:,.2f}"
            return str(value)
    return "not yet available"


def _draw_scenario_table(pdf: canvas.Canvas, document: SummaryDocument) -> None:
    trade = _mapping_at(document.data, "trade")
    rows = _trade_scenarios(trade)
    x, y, width, height = 36.0, 306.0, 523.0, 92.0
    pdf.setFillColor(_hex(WHITE))
    pdf.setStrokeColor(_hex(RULE))
    pdf.roundRect(x, y, width, height, 8, fill=1, stroke=1)
    _section_label(
        pdf,
        "Scenario analysis - illustrative, hypothetical and non-executable",
        x=x + 13,
        y=y + height - 19,
    )
    columns = (x + 13, x + 136, x + 242, x + 359)
    headers = ("SCENARIO", "EXPIRY USD / TONNE", "NET P&L USD / SPREAD", "THESIS STATE")
    pdf.setFillColor(_hex(MID))
    pdf.setFont("Helvetica-Bold", 5.2)
    for x_pos, header in zip(columns, headers, strict=True):
        pdf.drawString(x_pos, y + height - 35, header)
    pdf.setStrokeColor(_hex(RULE))
    pdf.line(x + 13, y + height - 41, x + width - 13, y + height - 41)
    if not rows:
        _paragraph(
            pdf,
            "NOT YET AVAILABLE - licensed option inputs or explicitly hypothetical strike/premium assumptions have not been supplied.",
            x=x + 13,
            y=y + 16,
            width=width - 26,
            height=29,
            font_size=6.2,
            leading=7.8,
            color=MID,
        )
        return
    for index, row in enumerate(rows[:5]):
        row_y = y + height - 53 - index * 9
        values = (
            _value_from_row(row, ("scenario", "name", "label", "state")),
            _value_from_row(
                row,
                (
                    "expiry_price",
                    "expiry_futures_price_usd_per_tonne",
                    "reference_price",
                    "underlying_price",
                    "price",
                ),
            ),
            _value_from_row(
                row,
                ("pnl", "pnl_usd", "net_pnl", "net_pnl_usd", "payoff"),
            ),
            _value_from_row(row, ("thesis_state", "interpretation")),
        )
        pdf.setFillColor(_hex(INK))
        pdf.setFont("Helvetica", 5.4)
        for x_pos, value in zip(columns, values, strict=True):
            pdf.drawString(x_pos, row_y, value[:34])


def _draw_backtest_box(pdf: canvas.Canvas, document: SummaryDocument) -> None:
    signal = _mapping_at(document.data, "signal")
    proxy = _mapping_at(signal, "public_proxy")
    x, y, width, height = 36.0, 188.0, 523.0, 102.0
    pdf.setFillColor(_hex(PALE_GOLD))
    pdf.roundRect(x, y, width, height, 8, fill=1, stroke=0)
    _section_label(pdf, "Historical evaluation", x=x + 13, y=y + height - 19)
    _badge(
        pdf,
        "public proxy - not tradable",
        x=x + 134,
        y=y + height - 30,
        fill=PALE_RED,
        color=RED,
        font_size=4.9,
    )
    event_count = _integer_at(proxy, "event_count")
    complete_event_count = _integer_at(proxy, "complete_event_count")
    censored_event_count = _integer_at(proxy, "censored_event_count")
    median = _number_at(proxy, "median_return_pct")
    mean = _number_at(proxy, "mean_return_pct")
    hit_rate = _number_at(proxy, "hit_rate_pct")
    ci_low = _number_at(proxy, "ci_low_pct")
    ci_high = _number_at(proxy, "ci_high_pct")
    horizon = _string_at(proxy, "horizon") or "not yet available"
    displayed_events = _display_number(event_count, "{:.0f}")
    if complete_event_count is not None:
        displayed_events = f"{displayed_events} ({complete_event_count} complete)"
    metrics = (
        ("Eligible events", displayed_events),
        ("Median proxy return", _display_number(median, "{:+.1f}%")),
        ("Positive observations", _display_number(hit_rate, "{:.1f}%")),
        (
            "Mean bootstrap 95% CI",
            f"[{ci_low:+.1f}%, {ci_high:+.1f}%]"
            if ci_low is not None and ci_high is not None
            else "NOT YET AVAILABLE",
        ),
    )
    x_positions = (x + 13, x + 132, x + 260, x + 389)
    for x_pos, (label, value) in zip(x_positions, metrics, strict=True):
        pdf.setFillColor(_hex(MID))
        pdf.setFont("Helvetica-Bold", 5.1)
        pdf.drawString(x_pos, y + 53, label.upper())
        pdf.setFillColor(_hex(NAVY))
        pdf.setFont("Helvetica-Bold", 9.0 if len(value) < 18 else 6.0)
        pdf.drawString(x_pos, y + 37, value)
    status = _string_at(proxy, "status") or "Not evaluated; summary input is absent."
    censor_text = (
        f" | <b>Censored:</b> {censored_event_count}" if censored_event_count is not None else ""
    )
    _paragraph(
        pdf,
        f"<b>Mean proxy response:</b> {_safe(_display_number(mean, '{:+.2f}%'))} | "
        f"<b>Horizon:</b> {_safe(horizon)}{censor_text} | <b>Status:</b> {_safe(status)}. "
        "Release-time eligibility, expanding-window thresholds and an untouched forward holdout are required. "
        "Monthly World Bank context is not an ICE futures return or executable P&amp;L.",
        x=x + 13,
        y=y + 9,
        width=width - 26,
        height=25,
        font_size=5.8,
        leading=7.0,
        color=MID,
    )


def _science_claims(document: SummaryDocument) -> list[dict[str, object]]:
    science = _mapping_at(document.data, "science")
    claims: list[dict[str, object]] = []
    for index, value in enumerate(_list_at(science, "claims")):
        claims.append(_as_mapping(value, f"science.claims[{index}]"))
    return claims


def _draw_science_box(pdf: canvas.Canvas, document: SummaryDocument) -> None:
    x, y, width, height = 36.0, 63.0, 523.0, 109.0
    pdf.setFillColor(_hex(PALE_GREEN))
    pdf.roundRect(x, y, width, height, 8, fill=1, stroke=0)
    science = _mapping_at(document.data, "science")
    selection_rationale = _string_at(science, "selection_rationale")
    section_title = "Scientific evidence register - mechanism, use, limitation"
    if selection_rationale is not None:
        section_title = (
            "Scientific evidence - 3 near-term shown; 4th projection registry/context-only"
        )
    _section_label(pdf, section_title, x=x + 13, y=y + height - 19)
    claims = _science_claims(document)
    if not claims:
        _paragraph(
            pdf,
            "NOT YET AVAILABLE - peer-reviewed claims have not been materialized into the summary. The intended control records geography, crop stage, exposure, lag, method, result, uncertainty and external-validity limits before a feature is used.",
            x=x + 13,
            y=y + 26,
            width=width - 26,
            height=49,
            font_size=6.2,
            leading=7.8,
            color=MID,
        )
        return
    column_width = (width - 40) / 3
    for index, claim in enumerate(claims[:3]):
        col_x = x + 13 + index * (column_width + 7)
        label = (
            _string_at(claim, "label")
            or _string_at(claim, "citation_short")
            or _string_at(claim, "title")
            or f"Evidence {index + 1}"
        )
        mechanism = (
            _string_at(claim, "mechanism")
            or _string_at(claim, "mechanism_use")
            or _string_at(claim, "claim")
            or "mechanism not stated"
        )
        limitation = (
            _string_at(claim, "limitation")
            or _string_at(claim, "external_validity_limits")
            or "external-validity limit not stated"
        )
        label = _shorten(label, 60)
        mechanism = _shorten(mechanism, 140)
        limitation = _shorten(limitation, 155)
        _paragraph(
            pdf,
            f"<b>{_safe(label)}</b><br/>{_safe(mechanism)}<br/><font color='{MID}'>Limit: {_safe(limitation)}</font>",
            x=col_x,
            y=y + 14,
            width=column_width,
            height=66,
            font_size=5.6,
            leading=7.0,
        )
        source_url = _string_at(claim, "source_url") or _string_at(claim, "url")
        if source_url is not None:
            _link(pdf, "source", source_url, x=col_x, y=y + 8, font_size=4.9)


def _render_page_two(pdf: canvas.Canvas, document: SummaryDocument) -> None:
    cutoff = _mapping_at(document.data, "cutoff")
    as_of = _display_date(_string_at(cutoff, "local") or _string_at(cutoff, "utc"))
    _page_header(
        pdf,
        eyebrow="Trade expression | risk discipline | evidence quality",
        title="From Observation to a Falsifiable Trade Rule",
        subtitle="Specific structure, bounded loss, scenario logic and honest backtest limits",
        as_of=as_of,
    )
    trade = _mapping_at(document.data, "trade")
    inputs = (
        _string_at(trade, "inputs_status")
        or _string_at(trade, "evaluation_status")
        or "NOT YET AVAILABLE - no permitted settlement history or option-chain input"
    )
    inputs = _human_label(inputs)
    assumptions = _mapping_at(trade, "illustrative_assumptions")
    long_strike = _number_at(assumptions, "long_strike_usd_per_tonne")
    short_strike = _number_at(assumptions, "short_strike_usd_per_tonne")
    debit = _number_at(assumptions, "net_debit_usd_per_tonne")
    fees = _number_at(assumptions, "round_trip_fees_usd_per_spread")
    max_loss = _number_at(trade, "illustrative_max_loss_usd")
    max_gain = _number_at(trade, "illustrative_max_gain_usd")
    breakeven = _number_at(trade, "illustrative_breakeven_usd_per_tonne")
    illustrative_line = "ILLUSTRATIVE INPUTS NOT AVAILABLE - NO MARKET DATA OR EXECUTABLE P&L"
    if all(
        value is not None
        for value in (long_strike, short_strike, debit, fees, max_loss, max_gain, breakeven)
    ):
        illustrative_line = (
            f"ILLUSTRATIVE - NOT MARKET DATA: K1 {long_strike:,.0f} | K2 {short_strike:,.0f} | "
            f"debit {debit:,.0f}/t | fees ${fees:,.0f}/spread | max loss ${max_loss:,.0f} | "
            f"max gain ${max_gain:,.0f} | breakeven {breakeven:,.0f}/t"
        )
    pdf.setFillColor(_hex(PALE_RED))
    pdf.roundRect(36, 618, 523, 94, 8, fill=1, stroke=0)
    _badge(pdf, "decision gate", x=49, y=685, fill=PALE_RED, color=RED, font_size=5.1)
    evidence_gate = _mapping_at(document.data, "evidence_gate")
    registered_deterioration = _boolean_at(evidence_gate, "registered_evidence_deterioration")
    physical_state = (
        "MET"
        if registered_deterioration is True
        else "NOT MET"
        if registered_deterioration is False
        else "NOT YET AVAILABLE"
    )
    weather_context = _human_label(
        _string_at(evidence_gate, "weather_context_status") or "NOT_YET_AVAILABLE"
    )
    _paragraph(
        pdf,
        f"<b>Registered physical deterioration:</b> {_safe(physical_state)}. "
        f"<b>Weather:</b> {_safe(weather_context)}; it cannot activate the gate. "
        "A positioning reversal and licensed 20-session settlement breakout are also required. "
        f"<b>Input status:</b> {_safe(inputs)}.",
        x=49,
        y=645,
        width=497,
        height=35,
        font_size=7.1,
        leading=9.0,
    )
    pdf.setFillColor(_hex(WHITE))
    pdf.roundRect(49, 623, 497, 19, 5, fill=1, stroke=0)
    _paragraph(
        pdf,
        f"<b>{_safe(illustrative_line)}</b>",
        x=56,
        y=626,
        width=483,
        height=13,
        font_size=5.1,
        leading=6.1,
        color=RED,
    )
    _draw_payoff(pdf, trade)
    _draw_trade_rules(pdf, document)
    _draw_scenario_table(pdf, document)
    _draw_backtest_box(pdf, document)
    _draw_science_box(pdf, document)
    _footer(pdf, 2)
    pdf.showPage()


def _render_pdf(root: Path, chart: Path, document: SummaryDocument) -> Path:
    output = root / "output" / "pdf" / "cocoa-trading-research-case.pdf"
    output.parent.mkdir(parents=True, exist_ok=True)
    pdf = canvas.Canvas(str(output), pagesize=A4, pageCompression=1, invariant=1)
    pdf.setTitle("Cocoa Trading Research Case")
    pdf.setAuthor("Ebrahim Cahlon")
    pdf.setSubject("Point-in-time cocoa trading research with public-proxy limitations")
    _render_page_one(pdf, chart, document)
    _render_page_two(pdf, document)
    pdf.save()
    return output


def main() -> int:
    root = _repo_root()
    document = _load_summary(root)
    positions = _load_positions(root)
    prices = _load_prices(root)
    chart = root / "output" / "figures" / "cocoa-trading-research-case.png"
    _build_dashboard_chart(positions, prices, document, chart)
    pdf = _render_pdf(root, chart, document)
    source = (
        "trading_case_summary.json" if document.used_trading_summary else "explicit fallback states"
    )
    print(f"summary source: {source}")
    print(f"wrote: {chart}")
    print(f"wrote: {pdf}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
