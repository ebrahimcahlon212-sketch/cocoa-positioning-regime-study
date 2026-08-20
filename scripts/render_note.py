"""Render deterministic charts and the one-page cocoa positioning research note."""

from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass
from datetime import datetime
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

NAVY = "#183348"
BLUE = "#2C6E91"
GOLD = "#C5922D"
RED = "#B84A4A"
INK = "#1D2932"
MID = "#5C6972"
RULE = "#D7DEE3"
PALE_BLUE = "#ECF4F7"
PALE_GOLD = "#FBF4E6"
PALE_RED = "#FAECEC"
PALE_GREY = "#F6F8F9"
WHITE = "#FFFFFF"
REPO_URL = "https://github.com/ebrahimcahlon212-sketch/cocoa-positioning-regime-study"
COMPANION_URL = "https://github.com/ebrahimcahlon212-sketch/market-intelligence-research-platform"


@dataclass(frozen=True)
class PositionRow:
    """One effective-dated CFTC cocoa observation."""

    effective_at: datetime
    available_at: datetime
    net_contracts: int
    open_interest_contracts: int
    availability_method: str


@dataclass(frozen=True)
class PriceRow:
    """One World Bank monthly cocoa price observation."""

    month: datetime
    usd_per_kg: float


@dataclass(frozen=True)
class SummaryCheckpoint:
    """One checkpoint read from the deterministic study summary."""

    report_date: datetime
    available_at: datetime
    net_contracts: int
    open_interest_contracts: int


@dataclass(frozen=True)
class StudySummary:
    """Typed headline values produced by the analytical pipeline."""

    peak: SummaryCheckpoint
    trough: SummaryCheckpoint
    latest: SummaryCheckpoint
    oi_peak: SummaryCheckpoint
    oi_trough: SummaryCheckpoint
    peak_to_trough_change_contracts: int
    peak_to_trough_swing_magnitude_tonnes: int
    trough_to_latest_change_contracts: int
    oi_peak_to_trough_pct: float
    latest_oi_vs_peak_pct: float
    q1_2026_price_display: float
    q1_2026_price_unrounded: float
    july_2026_price: float
    july_vs_q1_pct: float
    july_vs_q1_full_precision_pct: float
    cutoff_local: datetime


@dataclass(frozen=True)
class Headline:
    """Summary-backed checkpoints and rows selected for the chart."""

    peak: PositionRow
    trough: PositionRow
    latest: PositionRow
    oi_peak: PositionRow
    oi_trough: PositionRow
    delayed_example: PositionRow
    summary: StudySummary


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"derived table is empty: {path}")
    return rows


def _find_table(root: Path, required_fields: set[str]) -> tuple[Path, list[dict[str, str]]]:
    matches: list[tuple[Path, list[dict[str, str]]]] = []
    for path in sorted((root / "data" / "derived").glob("*.csv")):
        rows = _read_csv(path)
        if required_fields <= set(rows[0]):
            matches.append((path, rows))
    if len(matches) != 1:
        paths = [str(path) for path, _ in matches]
        raise ValueError(
            f"expected one derived table with {sorted(required_fields)}; found {paths}"
        )
    return matches[0]


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"timestamp must be timezone-aware: {value}")
    return parsed


def _parse_effective_date(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d")


def _parse_month(value: str) -> datetime:
    for template in ("%Y-%m-%d", "%Y-%m"):
        try:
            return datetime.strptime(value, template)
        except ValueError:
            continue
    raise ValueError(f"unsupported month value: {value}")


def _as_mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{label} must be a JSON object with string keys")
    return cast(dict[str, object], value)


def _mapping_at(mapping: dict[str, object], key: str) -> dict[str, object]:
    if key not in mapping:
        raise ValueError(f"summary is missing object: {key}")
    return _as_mapping(mapping[key], key)


def _string_at(mapping: dict[str, object], key: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str):
        raise ValueError(f"summary field {key!r} must be a string")
    return value


def _integer_at(mapping: dict[str, object], key: str) -> int:
    value = mapping.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"summary field {key!r} must be an integer")
    return value


def _number_at(mapping: dict[str, object], key: str) -> float:
    value = mapping.get(key)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"summary field {key!r} must be numeric")
    return float(value)


def _summary_checkpoint(findings: dict[str, object], key: str) -> SummaryCheckpoint:
    record = _mapping_at(findings, key)
    return SummaryCheckpoint(
        report_date=_parse_effective_date(_string_at(record, "report_date")),
        available_at=_parse_datetime(_string_at(record, "available_at_utc")),
        net_contracts=_integer_at(record, "managed_money_net_contracts"),
        open_interest_contracts=_integer_at(record, "open_interest_contracts"),
    )


def _load_summary(root: Path) -> StudySummary:
    path = root / "data" / "derived" / "study_summary.json"
    raw: object = json.loads(path.read_text(encoding="utf-8"))
    document = _as_mapping(raw, "study_summary")
    findings = _mapping_at(document, "findings")
    changes = _mapping_at(findings, "changes")
    price = _mapping_at(findings, "price")
    cutoff = _mapping_at(document, "cutoff")
    return StudySummary(
        peak=_summary_checkpoint(findings, "managed_money_net_peak"),
        trough=_summary_checkpoint(findings, "managed_money_net_trough"),
        latest=_summary_checkpoint(findings, "latest_cftc"),
        oi_peak=_summary_checkpoint(findings, "open_interest_peak"),
        oi_trough=_summary_checkpoint(findings, "open_interest_trough"),
        peak_to_trough_change_contracts=_integer_at(
            changes, "managed_money_peak_to_trough_change_contracts"
        ),
        peak_to_trough_swing_magnitude_tonnes=_integer_at(
            changes,
            "managed_money_peak_to_trough_swing_magnitude_contract_unit_metric_tonnes",
        ),
        trough_to_latest_change_contracts=_integer_at(
            changes, "managed_money_trough_to_latest_change_contracts"
        ),
        oi_peak_to_trough_pct=_number_at(changes, "open_interest_peak_to_trough_pct"),
        latest_oi_vs_peak_pct=_number_at(changes, "latest_open_interest_vs_peak_pct"),
        q1_2026_price_display=_number_at(price, "average_q1_2026"),
        q1_2026_price_unrounded=_number_at(price, "average_q1_2026_unrounded"),
        july_2026_price=_number_at(price, "july_2026"),
        july_vs_q1_pct=_number_at(price, "july_vs_q1_pct"),
        july_vs_q1_full_precision_pct=_number_at(price, "july_vs_q1_full_precision_pct"),
        cutoff_local=_parse_datetime(_string_at(cutoff, "local")),
    )


def _load_positions(root: Path) -> list[PositionRow]:
    required = {
        "report_date",
        "available_at_utc",
        "managed_money_net_contracts",
        "open_interest_contracts",
    }
    _, raw_rows = _find_table(root, required)
    rows = [
        PositionRow(
            effective_at=_parse_effective_date(row["report_date"]),
            available_at=_parse_datetime(row["available_at_utc"]),
            net_contracts=int(row["managed_money_net_contracts"]),
            open_interest_contracts=int(row["open_interest_contracts"]),
            availability_method=row.get("availability_basis", ""),
        )
        for row in raw_rows
    ]
    if rows != sorted(rows, key=lambda row: row.effective_at):
        raise ValueError("positioning rows must be sorted by report_date")
    return rows


def _load_prices(root: Path) -> list[PriceRow]:
    required = {"period_start", "price_usd_per_kg"}
    _, raw_rows = _find_table(root, required)
    rows = [
        PriceRow(
            month=_parse_month(row["period_start"]),
            usd_per_kg=float(row["price_usd_per_kg"]),
        )
        for row in raw_rows
    ]
    if rows != sorted(rows, key=lambda row: row.month):
        raise ValueError("price rows must be sorted by month")
    return rows


def _assert_checkpoint(
    row: PositionRow,
    checkpoint: SummaryCheckpoint,
    label: str,
) -> None:
    actual = (
        row.effective_at,
        row.available_at,
        row.net_contracts,
        row.open_interest_contracts,
    )
    expected = (
        checkpoint.report_date,
        checkpoint.available_at,
        checkpoint.net_contracts,
        checkpoint.open_interest_contracts,
    )
    if actual != expected:
        raise ValueError(f"{label} CSV row does not match study_summary.json")


def _headline(
    positions: list[PositionRow],
    prices: list[PriceRow],
    summary: StudySummary,
) -> Headline:
    peak = max(positions, key=lambda row: row.net_contracts)
    trough = min(
        (row for row in positions if row.effective_at > peak.effective_at),
        key=lambda row: row.net_contracts,
    )
    latest = positions[-1]
    oi_peak = max(positions, key=lambda row: row.open_interest_contracts)
    oi_trough = min(
        (row for row in positions if row.effective_at > oi_peak.effective_at),
        key=lambda row: row.open_interest_contracts,
    )
    q1_prices = [
        row.usd_per_kg for row in prices if row.month.year == 2026 and row.month.month in {1, 2, 3}
    ]
    if len(q1_prices) != 3:
        raise ValueError(f"expected three Q1 2026 prices, found {len(q1_prices)}")
    july = [row.usd_per_kg for row in prices if (row.month.year, row.month.month) == (2026, 7)]
    if len(july) != 1:
        raise ValueError(f"expected one July 2026 price, found {len(july)}")
    delayed = max(
        positions,
        key=lambda row: (row.available_at.date() - row.effective_at.date()).days,
    )
    _assert_checkpoint(peak, summary.peak, "managed-money peak")
    _assert_checkpoint(trough, summary.trough, "managed-money trough")
    _assert_checkpoint(latest, summary.latest, "latest CFTC")
    _assert_checkpoint(oi_peak, summary.oi_peak, "open-interest peak")
    _assert_checkpoint(oi_trough, summary.oi_trough, "open-interest trough")
    q1_from_csv = sum(q1_prices) / len(q1_prices)
    if not math.isclose(
        q1_from_csv,
        summary.q1_2026_price_unrounded,
        rel_tol=0,
        abs_tol=0.0001,
    ):
        raise ValueError("Q1 2026 price rows do not match study_summary.json")
    if not math.isclose(july[0], summary.july_2026_price, rel_tol=0, abs_tol=0.0001):
        raise ValueError("July 2026 price row does not match study_summary.json")
    if round(q1_from_csv, 2) != summary.q1_2026_price_display:
        raise ValueError("Q1 2026 displayed average does not match study_summary.json")
    if round(summary.july_vs_q1_full_precision_pct, 1) != summary.july_vs_q1_pct:
        raise ValueError("summary price percentage display is internally inconsistent")
    delayed_lag = (delayed.available_at.date() - delayed.effective_at.date()).days
    if delayed_lag <= 3 or "official" not in delayed.availability_method:
        raise ValueError("expected a documented delayed CFTC release in the study window")
    return Headline(
        peak=peak,
        trough=trough,
        latest=latest,
        oi_peak=oi_peak,
        oi_trough=oi_trough,
        delayed_example=delayed,
        summary=summary,
    )


def _chart_style() -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 7.5,
            "axes.edgecolor": RULE,
            "axes.labelcolor": MID,
            "axes.titlecolor": INK,
            "axes.titleweight": "bold",
            "axes.titlesize": 9.5,
            "axes.unicode_minus": False,
            "xtick.color": MID,
            "ytick.color": MID,
        }
    )


def _signed_thousands(value: int) -> str:
    return f"{value / 1000:+.1f}k"


def _rounded_thousands(value: int) -> str:
    return f"{value / 1000:.0f}k"


def _short_date(value: datetime) -> str:
    return f"{value.strftime('%b')} {value.day}"


def _build_regime_chart(
    positions: list[PositionRow],
    headline: Headline,
    output: Path,
) -> None:
    dates = [row.effective_at for row in positions]
    nets = [row.net_contracts / 1000 for row in positions]
    oi = [row.open_interest_contracts / 1000 for row in positions]

    fig, (top, bottom) = plt.subplots(
        2,
        1,
        figsize=(7.25, 3.15),
        dpi=220,
        sharex=True,
        gridspec_kw={"height_ratios": [2.05, 0.88], "hspace": 0.08},
    )
    fig.patch.set_facecolor(WHITE)
    top.set_facecolor(WHITE)
    bottom.set_facecolor(WHITE)

    top.axhline(0, color=MID, linewidth=0.8)
    top.plot(dates, nets, color=BLUE, linewidth=1.9, zorder=3)
    top.fill_between(dates, nets, 0, where=[value >= 0 for value in nets], color=GOLD, alpha=0.28)
    top.fill_between(dates, nets, 0, where=[value < 0 for value in nets], color=RED, alpha=0.22)
    top.set_ylabel("Managed-money net (000 contracts)", fontsize=7)
    top.set_title("Extreme long positioning reversed, then partially rebuilt", loc="left", pad=5)
    top.grid(axis="y", color=RULE, linewidth=0.55)
    top.spines[["top", "right"]].set_visible(False)
    top.set_ylim(-38, 98)

    for row, text, offset, alignment in (
        (headline.peak, _signed_thousands(headline.peak.net_contracts), (-4, 9), "right"),
        (
            headline.trough,
            _signed_thousands(headline.trough.net_contracts),
            (-7, -15),
            "right",
        ),
        (headline.latest, _signed_thousands(headline.latest.net_contracts), (-3, 10), "right"),
    ):
        x = row.effective_at
        y = row.net_contracts / 1000
        top.scatter([x], [y], s=24, color=BLUE, edgecolors=WHITE, linewidths=0.8, zorder=5)
        top.annotate(
            text,
            (x, y),
            xytext=offset,
            textcoords="offset points",
            ha=alignment,
            fontsize=7.1,
            fontweight="bold",
            color=NAVY,
        )
    top.text(
        0.995,
        0.94,
        "CFTC weekly positions - contracts, not physical inventory",
        transform=top.transAxes,
        ha="right",
        va="top",
        fontsize=6.5,
        color=MID,
    )

    bottom.plot(dates, oi, color=NAVY, linewidth=1.6)
    bottom.fill_between(dates, oi, min(oi) - 10, color=BLUE, alpha=0.10)
    bottom.set_ylabel("Open interest\n(000 contracts)", fontsize=6.8)
    bottom.grid(axis="y", color=RULE, linewidth=0.55)
    bottom.spines[["top", "right"]].set_visible(False)
    bottom.set_ylim(60, 360)
    bottom.text(
        0.995,
        0.94,
        f"{headline.summary.oi_peak_to_trough_pct:.1f}% peak-to-trough | "
        f"latest {headline.summary.latest_oi_vs_peak_pct:.1f}% vs peak",
        transform=bottom.transAxes,
        ha="right",
        va="top",
        fontsize=6.4,
        color=MID,
    )
    for row, label, offset in (
        (
            headline.oi_peak,
            f"{_rounded_thousands(headline.oi_peak.open_interest_contracts)} peak",
            (3, -12),
        ),
        (
            headline.oi_trough,
            f"{_rounded_thousands(headline.oi_trough.open_interest_contracts)} trough",
            (3, 8),
        ),
        (
            headline.latest,
            f"{_rounded_thousands(headline.latest.open_interest_contracts)} latest",
            (-4, 8),
        ),
    ):
        x = row.effective_at
        y = row.open_interest_contracts / 1000
        bottom.scatter([x], [y], s=18, color=NAVY, edgecolors=WHITE, linewidths=0.7, zorder=4)
        bottom.annotate(
            label,
            (x, y),
            xytext=offset,
            textcoords="offset points",
            ha="right" if row is headline.latest else "left",
            fontsize=6.6,
            color=NAVY,
            fontweight="bold",
        )
    bottom.xaxis.set_major_locator(mdates.MonthLocator(interval=4))  # type: ignore[no-untyped-call]
    bottom.xaxis.set_major_formatter(
        mdates.DateFormatter("%b\n%Y")  # type: ignore[no-untyped-call]
    )
    bottom.tick_params(axis="x", labelsize=6.7)
    fig.subplots_adjust(left=0.085, right=0.98, top=0.91, bottom=0.16)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(
        output,
        bbox_inches="tight",
        facecolor=WHITE,
        metadata={"Software": "cocoa-positioning-regime-study"},
    )
    plt.close(fig)


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
    font_size: float = 8.0,
    leading: float = 9.8,
    color: str = INK,
    bold: bool = False,
) -> None:
    style = ParagraphStyle(
        name="body",
        fontName="Helvetica-Bold" if bold else "Helvetica",
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


def _metric_card(
    pdf: canvas.Canvas,
    *,
    x: float,
    y: float,
    width: float,
    title: str,
    metric: str,
    body: str,
    fill: str,
    accent: str,
) -> None:
    pdf.setFillColor(_hex(fill))
    pdf.roundRect(x, y, width, 66, 7, fill=1, stroke=0)
    pdf.setFillColor(_hex(accent))
    pdf.rect(x, y, 4, 66, fill=1, stroke=0)
    pdf.setFont("Helvetica-Bold", 6.9)
    pdf.setFillColor(_hex(MID))
    pdf.drawString(x + 11, y + 50, title.upper())
    pdf.setFont("Helvetica-Bold", 14)
    pdf.setFillColor(_hex(accent))
    pdf.drawString(x + 11, y + 31, metric)
    _paragraph(
        pdf,
        body,
        x=x + 11,
        y=y + 7,
        width=width - 19,
        height=20,
        font_size=6.6,
        leading=7.7,
    )


def _draw_timeline(
    pdf: canvas.Canvas,
    *,
    x: float,
    y: float,
    width: float,
    headline: Headline,
) -> None:
    pdf.setFillColor(_hex(PALE_GREY))
    pdf.roundRect(x, y, width, 145, 8, fill=1, stroke=0)
    pdf.setFillColor(_hex(NAVY))
    pdf.setFont("Helvetica-Bold", 8.2)
    pdf.drawString(x + 13, y + 126, "POINT-IN-TIME CONTROL")
    line_y = y + 99
    start_x = x + 36
    end_x = x + width - 36
    pdf.setStrokeColor(_hex(BLUE))
    pdf.setLineWidth(1.6)
    pdf.line(start_x, line_y, end_x, line_y)
    for dot_x, label, detail in (
        (start_x, "TUE", "positions effective"),
        ((start_x + end_x) / 2, "FRI 15:30 ET", "normally published"),
        (end_x, "AFTER", "usable in research"),
    ):
        pdf.setFillColor(_hex(WHITE))
        pdf.setStrokeColor(_hex(BLUE))
        pdf.circle(dot_x, line_y, 4, fill=1, stroke=1)
        pdf.setFillColor(_hex(NAVY))
        pdf.setFont("Helvetica-Bold", 5.8)
        pdf.drawCentredString(dot_x, line_y + 10, label)
        _paragraph(
            pdf,
            detail,
            x=dot_x - 34,
            y=line_y - 22,
            width=68,
            height=15,
            font_size=5.7,
            leading=6.5,
            color=MID,
        )
    lag_days = (
        headline.delayed_example.available_at.date() - headline.delayed_example.effective_at.date()
    ).days
    delayed_text = (
        f"<b>Real exception:</b> {headline.delayed_example.effective_at.strftime('%b %d, %Y')} "
        f"positions were available {lag_days} days later during the "
        f"{headline.delayed_example.effective_at.year} catch-up schedule. "
        "Actual delays are used where documented. Ordinary 2024 and uncovered 2025 dates are "
        "rule-modelled."
    )
    _paragraph(
        pdf,
        delayed_text,
        x=x + 13,
        y=y + 12,
        width=width - 26,
        height=51,
        font_size=6.6,
        leading=8.0,
        color=INK,
    )


def _render_pdf(root: Path, chart: Path, headline: Headline) -> Path:
    output = root / "output" / "pdf" / "cocoa-positioning-regime-shift.pdf"
    output.parent.mkdir(parents=True, exist_ok=True)
    width, height = A4
    pdf = canvas.Canvas(
        str(output),
        pagesize=A4,
        pageCompression=1,
        invariant=1,
    )
    pdf.setTitle("Cocoa Positioning Regime Shift")
    pdf.setAuthor("Ebrahim Cahlon")
    pdf.setSubject("Point-in-time cocoa futures positioning research")

    pdf.setFillColor(_hex(NAVY))
    pdf.rect(0, height - 100, width, 100, fill=1, stroke=0)
    pdf.setFillColor(_hex("#A6CAD6"))
    pdf.setFont("Helvetica-Bold", 7.7)
    pdf.drawString(36, height - 25, "POINT-IN-TIME COCOA POSITIONING STUDY")
    pdf.setFillColor(_hex(WHITE))
    pdf.setFont("Helvetica-Bold", 21)
    pdf.drawString(36, height - 51, "Cocoa Positioning Regime Shift")
    pdf.setFont("Helvetica", 11.5)
    pdf.drawString(36, height - 72, "From the 2024 positioning extreme to the 2026 rebuild")
    pdf.setFont("Helvetica", 7.4)
    cutoff = headline.summary.cutoff_local
    cutoff_label = f"Cutoff: {_short_date(cutoff)}, {cutoff.year}, {cutoff.strftime('%H:%M')} ET"
    pdf.drawRightString(width - 36, height - 89, cutoff_label)

    pdf.setFillColor(_hex(PALE_BLUE))
    pdf.roundRect(36, 658, width - 72, 69, 8, fill=1, stroke=0)
    pdf.setFillColor(_hex(BLUE))
    pdf.setFont("Helvetica-Bold", 7.6)
    pdf.drawString(49, 709, "VIEW")
    _paragraph(
        pdf,
        "Extreme long positioning became net short, then partially rebuilt. July's price "
        "rebound <b>coincided with</b> less-negative managed-money positioning - consistent "
        "with covering and/or re-risking, not proof of causality. Physical normalization "
        "remains uncertain.",
        x=49,
        y=666,
        width=width - 98,
        height=37,
        font_size=8.8,
        leading=10.8,
    )

    pdf.drawImage(ImageReader(chart), 34, 405, width=527, height=240, preserveAspectRatio=True)

    card_width = (width - 84) / 3
    _metric_card(
        pdf,
        x=36,
        y=332,
        width=card_width,
        title=(
            f"{headline.peak.effective_at.year} peak to {headline.trough.effective_at.year} trough"
        ),
        metric=f"{headline.summary.peak_to_trough_change_contracts:+,d}",
        body=(
            "Contracts; "
            f"{headline.summary.peak_to_trough_swing_magnitude_tonnes / 1_000_000:.2f}m "
            "tonnes equivalent is not physical inventory."
        ),
        fill=PALE_RED,
        accent=RED,
    )
    _metric_card(
        pdf,
        x=42 + card_width,
        y=332,
        width=card_width,
        title=(
            f"{headline.trough.effective_at.strftime('%B')} trough to "
            f"{_short_date(headline.latest.effective_at)}"
        ),
        metric=f"{headline.summary.trough_to_latest_change_contracts:+,d}",
        body="Partial short-covering and/or re-risking; motive is not observed.",
        fill=PALE_BLUE,
        accent=BLUE,
    )
    _metric_card(
        pdf,
        x=48 + 2 * card_width,
        y=332,
        width=card_width,
        title="July price vs Q1 2026",
        metric=f"{headline.summary.july_vs_q1_pct:+.1f}%",
        body=(
            f"${headline.summary.july_2026_price:.2f}/kg vs Jan-Mar mean "
            f"${headline.summary.q1_2026_price_unrounded:.3f}/kg; four-value retrospective extract."
        ),
        fill=PALE_GOLD,
        accent=GOLD,
    )

    box_y = 170
    interpretation_width = 322
    pdf.setFillColor(_hex(PALE_GREY))
    pdf.roundRect(36, box_y, interpretation_width, 145, 8, fill=1, stroke=0)
    pdf.setFillColor(_hex(NAVY))
    pdf.setFont("Helvetica-Bold", 8.2)
    pdf.drawString(49, box_y + 126, "CONDITIONAL EVENT-RISK POSTURE")
    _paragraph(
        pdf,
        "<b>Upside watch:</b> crop recovery disappoints while positioning remains short "
        "and price holds. Confirm with less-negative net positioning, expanding open "
        "interest and weaker official crop/balance estimates.",
        x=49,
        y=box_y + 67,
        width=interpretation_width - 26,
        height=48,
        font_size=7.2,
        leading=8.8,
    )
    pdf.setStrokeColor(_hex(RULE))
    pdf.line(49, box_y + 61, 36 + interpretation_width - 13, box_y + 61)
    _paragraph(
        pdf,
        "<b>Invalidate / downside:</b> demand or grindings weaken, an official surplus "
        "grows, price rolls over or fresh shorts build with participation.",
        x=49,
        y=box_y + 14,
        width=interpretation_width - 26,
        height=39,
        font_size=7.2,
        leading=8.8,
    )
    _draw_timeline(
        pdf,
        x=372,
        y=box_y,
        width=width - 408,
        headline=headline,
    )

    pdf.setStrokeColor(_hex(RULE))
    pdf.line(36, 150, width - 36, 150)
    _paragraph(
        pdf,
        "<b>Sources:</b> CFTC Futures-Only COT, cocoa code 073732; attributed CFTC "
        "publication-calendar extracts; four-value World Bank cocoa extract, source series "
        "attributed to ICCO. <b>Rights:</b> CFTC public domain; full upstream World Bank "
        "workbook/pages are not redistributed. Official URLs and upstream SHA-256 hashes: "
        "<font name='Courier'>data/source_manifest.csv</font>.",
        x=36,
        y=105,
        width=width - 72,
        height=37,
        font_size=6.5,
        leading=7.8,
        color=MID,
    )
    _paragraph(
        pdf,
        "Historical research only. No causality, crowding, alpha, price forecast, "
        "executable futures P&amp;L or physical-inventory equivalence. Current retrieved CFTC "
        "snapshots - not full value-vintage replay or latency-grade data. AI assisted review; "
        "deterministic Python produced every displayed number.",
        x=36,
        y=70,
        width=width - 72,
        height=29,
        font_size=6.4,
        leading=7.7,
        color=MID,
    )

    pdf.setFillColor(_hex(NAVY))
    pdf.setFont("Helvetica-Bold", 6.4)
    repo = REPO_URL.removeprefix("https://")
    companion = f"companion: {COMPANION_URL.removeprefix('https://')}"
    repo_x = 36.0
    companion_width = stringWidth(companion, "Helvetica-Bold", 6.4)
    companion_x = width - 36 - companion_width
    pdf.drawString(repo_x, 42, repo)
    pdf.drawString(companion_x, 42, companion)
    pdf.linkURL(
        REPO_URL,
        (repo_x, 39, repo_x + stringWidth(repo, "Helvetica-Bold", 6.4), 50),
        relative=0,
        thickness=0,
    )
    pdf.linkURL(
        COMPANION_URL,
        (companion_x, 39, companion_x + companion_width, 50),
        relative=0,
        thickness=0,
    )
    pdf.setFont("Helvetica", 5.9)
    footer = (
        "Ebrahim Cahlon | Current through COT effective "
        f"{_short_date(headline.latest.effective_at)}, {headline.latest.effective_at.year}"
    )
    pdf.drawString(36, 28, footer)
    page = "1 / 1"
    pdf.drawString(width - 36 - stringWidth(page, "Helvetica", 5.9), 28, page)

    pdf.showPage()
    pdf.save()
    return output


def main() -> int:
    root = _repo_root()
    positions = _load_positions(root)
    prices = _load_prices(root)
    summary = _load_summary(root)
    headline = _headline(positions, prices, summary)
    _chart_style()
    chart = root / "output" / "figures" / "cocoa-positioning-regime.png"
    _build_regime_chart(positions, headline, chart)
    pdf = _render_pdf(root, chart, headline)
    print(f"wrote: {chart}")
    print(f"wrote: {pdf}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
