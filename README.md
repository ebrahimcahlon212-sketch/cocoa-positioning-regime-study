# Cocoa Positioning Regime Shift

**From the 2024 positioning extreme to the 2026 rebuild**

A point-in-time study of cocoa futures positioning and participation using official CFTC
Commitments of Traders data, with a four-value World Bank cocoa extract for recent price context.

**[Open the one-page research note](output/pdf/cocoa-positioning-regime-shift.pdf)**

The result is a change in market structure, not a backtested trading claim. Managed-money net
positioning moved from a peak of **+82,572 contracts** on January 23, 2024 to **-23,084** on
June 9, 2026. It then recovered to **-6,667** by August 11, 2026. July's World Bank cocoa
indicator was **$5.61/kg**, 42.6% above the Q1 2026 average, and coincided with part of that
positioning recovery.

The word "coincided" is deliberate: weekly positions and a monthly price indicator do not
establish causality, crowding or alpha.

## What changed

| Observation | Verified result | Interpretation boundary |
|---|---:|---|
| Managed-money peak to trough | -105,656 contracts | A positioning regime change, not physical inventory |
| June trough to August 11 | +16,417 contracts | Consistent with partial covering and/or re-risking; the data cannot separate them |
| Open-interest peak to trough | -74.0% | Participation contracted materially; this is not a liquidity-cost estimate |
| Latest open interest vs 2024 peak | -42.8% | Participation rebuilt, but remained below the earlier extreme |
| July price vs Q1 2026 average | +42.6% | Retrospective context, not a tradeable futures return |

## Market view

The 2024 extreme-long regime had reversed into a net-short regime by 2026. The rebound from
June's short extreme, alongside July's price recovery, suggests the one-way normalization
story became less comfortable. Physical normalization remains uncertain because neither CFTC
positions nor the World Bank price indicator directly measures the cocoa balance sheet.

This creates a **conditional upside event-risk watch** if crop recovery disappoints while net
positioning remains short and price confirms. The downside case is weaker demand or grindings,
a larger surplus and renewed short formation. This is a falsifiable research posture, not a
price forecast or trade recommendation.

## The point-in-time control

COT observations describe positions as of Tuesday and are generally published on Friday at
15:30 Eastern Time. The pipeline stores those as separate effective and available timestamps.
A historical query can use a row only after its publication time; treating Tuesday's positions
as known on Tuesday would leak future information.

The failure mode is real, not theoretical: positions dated September 30, 2025 were not actually
published until November 19 during the CFTC shutdown backlog. The pipeline uses the documented
catch-up schedule instead of assigning a normal Friday release.

Ordinary 2024 and uncovered 2025 publication dates are explicitly rule-modelled where a complete
official schedule was not established. These are research controls, not latency-grade timestamps.

Price context is deliberately minimal: only January, February, March and July 2026 values are
retained. They are used retrospectively because this project does not possess a complete archive
of historical publication vintages. The full upstream workbook and source pages are not
redistributed; official URLs and upstream hashes are retained in the source manifest.

The annual CFTC files are the snapshots retrieved for this study and can contain later CFTC
corrections or reclassifications. Their hashes bind the calculation to exact bytes, but this is
publication-time leakage control rather than full historical value-vintage replay.

## What this demonstrates

- commodity positioning and participation analysis;
- point-in-time controls for an easily missed COT publication lag;
- deterministic calculations with preserved sources, hashes and units;
- a market view with explicit confirmation, invalidation and asymmetric event risks; and
- AI-assisted research without model-generated facts, arithmetic or trading actions.

## Repository map

- `output/pdf/cocoa-positioning-regime-shift.pdf` - one-page recruiter-facing note
- `output/figures/` - deterministic charts used in the note
- `data/source_manifest.csv` - official URLs, retrieval UTC, upstream hashes, extraction methods
  and public-extract fingerprints
- `data/derived/` - auditable analytical outputs, including the four-value price extract
- `src/` - deterministic parsing, temporal controls and calculations
- `tests/` - offline tests for source integrity, units and look-ahead prevention

## Reproduce

Requires Python 3.11 or later.

```bash
python -m venv .venv
python -m pip install -e ".[dev,report]"
python scripts/reproduce.py
pytest
ruff check .
ruff format --check .
mypy
```

Acquisition is kept separate from deterministic analysis. Tests do not access the network.

## Official sources

- [CFTC Disaggregated Futures-Only data](https://publicreporting.cftc.gov/Commitments-of-Traders/Disaggregated-Futures-Only/72hh-3qpy)
- [CFTC COT methodology](https://publicreporting.cftc.gov/stories/s/COT-Help/p2fg-u73y/)
- [CFTC historical special announcements](https://www.cftc.gov/MarketReports/CommitmentsofTraders/HistoricalSpecialAnnouncements/index.htm)
- [World Bank Commodity Price Data](https://thedocs.worldbank.org/en/doc/74e8be41ceb20fa0da750cda2f6b9e4e-0050012026/world-bank-commodities-price-data-the-pink-sheet)

See [METHODOLOGY.md](METHODOLOGY.md), [DATA_LICENSE.md](DATA_LICENSE.md) and
[AI_USAGE.md](AI_USAGE.md) for the full boundaries.

This repository contains historical research only. It is not investment advice, a return
backtest, an executable signal, or an automated trading system.

## Related infrastructure

The companion [Point-in-Time Market Data Ledger](https://github.com/ebrahimcahlon212-sketch/market-intelligence-research-platform)
shows the generic audit and storage controls behind this study.
