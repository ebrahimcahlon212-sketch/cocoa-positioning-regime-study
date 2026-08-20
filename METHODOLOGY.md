# Methodology

## Research question

How did cocoa positioning, the official balance sheet, regional processing demand and West African
weather evolve into August 2026, and did a frozen prior-only positioning-reversal condition historically
precede positive public-proxy returns?

The study combines descriptive research with a retrospective event test and a hypothetical,
defined-risk trade expression. It does not claim causality, forecast skill, executable profit and
loss or a live track record. The frozen protocol is in `PREREGISTRATION.md`.

## Data scope

### CFTC positioning

- Dataset: CFTC Disaggregated Commitments of Traders, Futures-Only.
- Contract: Cocoa, CFTC contract market code `073732`.
- Descriptive headline window: January 2, 2024 through August 11, 2026.
- Signal-history window: September 1, 2009 through August 11, 2026 (live-era disaggregated reports).
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

### Physical balance and regional demand

The physical layer retains official ICCO cocoa-balance vintages and regional grinding releases as
separate observations. It records production, grindings, the provider's published surplus/deficit,
ending stocks and stocks-to-grindings with original units, release time, retrieval time, URL and
source hash. Revisions append a later vintage; they do not replace the earlier estimate.

The current headline vintage is not a complete physical-flow model. It lacks licensed daily port
arrivals, exchange-certified stocks, farm-level conditions and a full prospective archive of every
historical release. Regional grinding comparators also retain association-specific methodology and
revision caveats.

### Weather and scientific evidence

The weather layer uses NASA POWER daily location proxies for Daloa, Côte d'Ivoire, and Kumasi,
Ghana. These are provisional gridded values for two points—not crop-area-weighted production
exposure or farm microclimate. Rainfall anomalies, dry days and dry-spell measures remain features;
they are never converted mechanically into cocoa tonnes or price direction. Kumasi's extreme June
model-grid accumulation requires a second-source check and is ineligible for the trade gate.

The scientific registry records source, design, geography, mechanism and external-validity limits.
Studies select plausible mechanisms and lags; they do not supply a transferable trading coefficient.
For example, excess wetness can support plant growth while increasing black-pod pressure. That
ambiguity is preserved rather than collapsed into a bullish or bearish rule.

The two-page memo displays three studies with mechanisms closest to a near-term crop discussion.
The fourth registry record is a long-horizon suitability projection; it remains in the auditable
registry but is not presented as support for a Dec-26 trade.

### Public price-response proxy

Twenty-three World Bank monthly cocoa observations provide only the available endpoints required for the
registered historical response study. A separate four-value extract—January, February, March and
July 2026—supports the original descriptive note. The upstream workbook expresses the series in
U.S. dollars per kilogram and attributes it to the International Cocoa Organization. Neither
extract is the return on a specific futures contract or includes roll, basis, transaction costs,
margin or execution.

The public repository does not redistribute the full workbook or upstream pages. For the historical
event study, it retains only the 23 attributed monthly endpoints required by the frozen `m+1` to
`m+4` response calculation, plus official URLs and upstream SHA-256 hashes. The four-row extract
used by the original note remains separate. Because the August 2026 workbook is a current snapshot,
not a complete historical publication-vintage archive, the response study is labelled retrospective
and pseudo-out-of-sample rather than a latency-grade point-in-time backtest.

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
schedules can change the normal Friday timing. Retained official 2025 special-release and 2026
schedule facts override ordinary dates. Older ordinary dates are explicitly rule-modelled.

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

### Positioning event and response

For each release `t`:

```text
x_t = managed_money_net_contracts / open_interest_contracts
Q10_t = prior-only empirical nearest-rank 10th percentile of x
event_t = (x_(t-1) <= Q10_t) and (x_t > x_(t-1))
```

Evaluation begins only after 156 strictly earlier releases. Events are suppressed for 91 elapsed
days measured between timezone-aware availability timestamps. This creates a real daylight-saving
boundary: the 23 May 2017 report is only 90 days 23 hours after the prior signal's publication, so
the next eligible event is 30 May.

For an event available in month `m`, the one primary response is:

```text
R_(m+1,m+4) = World_Bank_cocoa_(m+4) / World_Bank_cocoa_(m+1) - 1
```

Incomplete endpoints remain censored. The deterministic summary reports 13 events, 12 complete
responses, mean +0.614%, median +1.811%, 58.3% positive, and a 95% circular-block bootstrap interval
of -5.64% to +5.84%. The interval spans zero widely, so the registered historical result is
inconclusive and underpowered.

### Hypothetical call-spread mechanics

An actual Dec-26 call-spread evaluation requires permitted local ICE futures and option inputs.
When those are absent, status is `NOT_EVALUATED_LICENSED_MARKET_INPUTS`. The public scenario uses
clearly illustrative values only to demonstrate formulas, maximum-loss sizing and expiry outcomes.

For futures price `F`, strikes `K1 < K2`, debit `D`, per-spread fees `C` and 10 tonnes:

```text
net_expiry_pnl = 10 * (max(F-K1, 0) - max(F-K2, 0) - D) - C
max_loss = 10 * D + C
max_gain = 10 * (K2-K1-D) - C
breakeven = K1 + D + C/10
contracts = floor((paper_NAV * 0.5%) / max_loss)
```

The scenario workbook uses `K1=5,500`, `K2=6,350`, `D=300` USD/t and `C=$20`, producing
maximum loss $3,020, maximum gain $5,480 and breakeven $5,802/t. These are not market quotes.

The separate version-1 evidence gate is exact: an ICCO surplus or ending-stocks revision of at
least -25kt, or a stocks-to-grindings revision of at least -0.5pp, triggers it. It is recomputed at
each new visible ICCO vintage and expires after 120 days if not superseded. The current state is
true, but these thresholds were frozen after the May revision was already known, so this is design
evidence—not a forward result. Weather is context-only in version 1 and cannot activate the gate.
Any future weather rule must name and freeze its independent confirmation source, spatial method,
thresholds, window, freshness and reset before evaluation. Full rules are in `PREREGISTRATION.md`.

## Interpretation framework

The observed sequence is:

1. Managed-money net positioning reached an extreme long in January 2024.
2. It crossed into a net-short regime and reached its study-window trough in June 2026.
3. Positioning became less negative by August 11 while the July monthly price indicator stood
   above the Q1 2026 average.
4. Open interest had recovered from its 2025 trough but remained below the 2024 peak.

This supports a conditional event-risk question, not an unconditional forecast. The historical
proxy result does not promote that question into a signal.

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
- The registered pattern predicts returns; its public-proxy interval is wide and spans zero.
- The illustrative option structure survives actual fees, slippage, liquidity, exercise or margin.
- Physical supply has fully normalized.

## Reproducibility

Redistributable CFTC annual archives are retained without mutation. CFTC publication-calendar
and methodology evidence is stored as sanitized, attributed extracts rather than full web-page
wrappers. For the World Bank context, only two rights-minimal extracts are retained: the four values
used by the original note and the 23 unique endpoints required by the event study. The full
upstream workbook and pages are excluded from the public repository; the source manifest keeps
their official URLs, retrieval UTC, upstream byte counts and SHA-256 hashes, deterministic
extraction methods and public-extract fingerprints. Derived records are rebuilt deterministically,
and tests are local and network-blocked.

The CFTC annual archives are the current snapshots retrieved for this project. CFTC can issue
corrections or reclassifications, so those files do not reconstruct every earlier value vintage.
The source hashes make the analysis reproducible against the retrieved bytes. The temporal model
demonstrates when a report became public; it does not claim a complete historical replay of all
subsequent data corrections.

Run `python scripts/reproduce.py` to rebuild derived outputs, both reports and the trading-case
figures. `python scripts/reproduce.py --check` fails if committed derived data are stale before the
deterministic render.
