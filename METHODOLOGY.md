# Methodology

## Research question

How did cocoa futures positioning and participation change between the 2024 high-price regime
and the partial 2026 rebuild, and what could a historical researcher have known at each point?

The study is descriptive. It does not test a trading rule, claim causality, infer physical
inventory, forecast price or estimate executable profit and loss.

## Data scope

### CFTC positioning

- Dataset: CFTC Disaggregated Commitments of Traders, Futures-Only.
- Contract: Cocoa, CFTC contract market code `073732`.
- Window: January 2, 2024 through August 11, 2026.
- Managed-money net: managed-money long contracts minus managed-money short contracts.
- Open interest: total futures-only open interest reported for the contract.
- Unit: futures contracts.

The study uses the futures-only report to avoid silently mixing futures and options exposure.
Spread positions are not added to directional long or short positions. Gross categories and
trader classifications can change even when market exposure has not changed one-for-one, so
the analysis is a positioning lens rather than a complete map of beneficial ownership.

The optional contract-unit equivalent multiplies contracts by the exchange contract unit used
in the pipeline. It is a notional comparison only. It is never described as physical beans,
deliverable stock, warehouse inventory or supply.

### Price context

Four World Bank monthly cocoa observations - January, February, March and July 2026 - provide
limited retrospective price context. The upstream workbook expresses the series in U.S. dollars
per kilogram and attributes it to the International Cocoa Organization. The retained extract is
not the return on a specific futures contract and does not include roll, basis, transaction
costs, margin or execution.

The public repository does not redistribute the full workbook or upstream pages. It retains the
four attributed values required for the calculation plus official URLs and upstream SHA-256
hashes. Because it does not contain a complete archive of historical publication vintages, the
price observations are used retrospectively and are not admitted into a point-in-time backtest.

## Temporal model

COT reports generally contain positions as of Tuesday and are published Friday at 15:30 U.S.
Eastern Time. The data model therefore keeps two distinct concepts:

- `effective_at`: the date to which the positions relate; and
- `available_at`: the first modeled time at which the report could be used.

Historical selection is performed on `available_at <= cutoff`, never on the report date alone.
For example, an observation effective Tuesday, August 11, 2026 is modeled as available only at
the corresponding Friday publication time. The precise UTC offset is timezone-aware and follows
New York daylight-saving rules.

"Generally" matters. Holidays, delayed publications, corrections and exceptional CFTC release
schedules can change the normal Friday timing. The source manifest and pipeline should record an
explicit release time when available; a production study would validate every date against the
official release calendar.

A concrete leakage trap occurred during the 2025 U.S. government shutdown backlog: the COT
observation dated September 30 was not published until November 19. The pipeline maps that row to
the documented catch-up release, rather than a synthetic October 3 Friday timestamp. Official
2025 special announcements and the 2026 release schedule are used where available. Ordinary 2024
and uncovered 2025 dates are rule-modelled because an equivalent complete release calendar was
not established for those observations. The resulting timestamps support research controls, not
latency-grade execution.

Official special announcement:
<https://www.cftc.gov/MarketReports/CommitmentsofTraders/HistoricalSpecialAnnouncements/index.htm>

## Deterministic calculations

For every COT observation:

```text
managed_money_net_contracts = managed_money_long_contracts - managed_money_short_contracts
```

For two values `old` and `new`:

```text
absolute_change = new - old
percent_change = (new / old - 1) * 100
```

The analytical checkpoints are selected deterministically from the derived series:

- maximum managed-money net position in the study window;
- minimum managed-money net position after that maximum;
- latest available observation;
- maximum open interest in the study window;
- minimum open interest after that maximum; and
- latest open interest.

The price comparison is:

```text
Q1_2026_average = mean(January_2026, February_2026, March_2026)
July_rebound_pct = (July_2026 / Q1_2026_average - 1) * 100
```

The full-precision comparison, retained in the derived summary, is 42.6271% and rounds to 42.6%.
Displayed component values are rounded separately and are not used to calculate the percentage.

Every headline number in the note is asserted against the pipeline's derived outputs before the
PDF renders. Language models do not perform these calculations.

## Interpretation framework

The observed sequence is:

1. Managed-money net positioning reached an extreme long in January 2024.
2. It crossed into a net-short regime and reached its study-window trough in June 2026.
3. Positioning became less negative by August 11 while the July monthly price indicator stood
   above the Q1 2026 average.
4. Open interest had recovered from its 2025 trough but remained below the 2024 peak.

This supports a conditional event-risk question, not an unconditional forecast.

**Upside confirmation:** official crop or balance estimates disappoint recovery expectations,
price holds the rebound, managed-money net becomes less negative, and open interest expands.

**Downside confirmation / upside invalidation:** demand or grindings weaken, an official surplus
widens, price rolls over, or shorts rebuild alongside expanding participation.

## What the evidence cannot establish

- Weekly positioning caused the monthly price move.
- The market was mechanically crowded.
- A net-short category is equivalent to aggregate market bearishness.
- Contract-unit equivalents are physical cocoa stocks.
- The July price indicator was tradeable at that exact level.
- The pattern predicts returns or survives fees, slippage, basis and contract rolls.
- Physical supply has fully normalized.

## Reproducibility

Redistributable CFTC annual archives are retained without mutation. CFTC publication-calendar
and methodology evidence is stored as sanitized, attributed extracts rather than full web-page
wrappers. For the World Bank context, only the four required cocoa values are retained. The full
upstream workbook and pages are excluded from the public repository; the source manifest keeps
their official URLs, retrieval UTC, upstream byte counts and SHA-256 hashes, deterministic
extraction methods and public-extract fingerprints. Derived records are rebuilt deterministically,
and tests are local and network-blocked.

The CFTC annual archives are the current snapshots retrieved for this project. CFTC can issue
corrections or reclassifications, so those files do not reconstruct every earlier value vintage.
The source hashes make the analysis reproducible against the retrieved bytes. The temporal model
demonstrates when a report became public; it does not claim a complete historical replay of all
subsequent data corrections.

Run `python scripts/reproduce.py` to rebuild derived outputs, charts and the one-page note.
