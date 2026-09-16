# Methodology

The study describes cocoa positioning and tests a reversal rule against a monthly price proxy.
It adds physical-balance revisions, regional grindings and weather context to a hypothetical
call-spread case. Exact rules remain in [PREREGISTRATION.md](PREREGISTRATION.md).

## Inputs

CFTC Disaggregated Futures-Only reports cover cocoa contract `073732`. The descriptive window
runs from 2 January 2024 to 11 August 2026; signal history starts on 1 September 2009. Managed-money
net is long contracts minus short contracts. Spread positions are excluded from directional net.
Open interest is the reported futures-only total. Contract-unit equivalents are not physical stocks,
and categories do not identify every participant or motive.

ICCO vintages retain production, grindings, published surplus/deficit, ending stocks and
stocks-to-grindings, with original units, URLs, release/capture times and hashes. Revisions append
new records. The published balance uses net crop after loss in weight, so gross production minus
grindings does not reproduce it. Regional grinds retain association-specific comparability warnings.
The dataset lacks a complete flow model, daily port arrivals, certified stocks and farm observations.

NASA POWER supplies provisional daily grid values for Daloa and Kumasi. The two locations are
not weighted by cocoa-growing area. Kumasi's extreme June accumulation needs independent
confirmation. Weather cannot activate version 1 of the trade rule or be converted directly into
production losses. NASA Langley Research Center POWER Project data, API v2.9.6/v2.9.7, were accessed
20 August 2026; request URLs, product sources, access times and hashes remain in the registry.

Four scientific records describe mechanisms, geography, study design and limits. Three concern
near-term drought, disease or crop-stage effects; the fourth projects climate effects on future yield.
They suggest hypotheses and lags without establishing a transferable price coefficient.

The World Bank extracts contain four descriptive values and 23 unique monthly endpoints for the
event study. The ICCO-attributed series is in USD/kg. It excludes futures rolls, basis, margin,
execution and transaction costs. Full upstream workbooks and page wrappers are not redistributed.

## Publication timing

`effective_at` describes the position date. `available_at` describes when the report could be used.
Historical selection requires `available_at <= cutoff`. Normal Tuesday COT observations become
eligible Friday at 15:30 New York time, with daylight saving handled in UTC.

Retained official 2025 special-release facts and the 2026 calendar override that rule. The report
dated 30 September 2025 was released on 19 November during the shutdown backlog. Ordinary 2024
and uncovered 2025 dates are explicitly modelled. These timestamps support research timing,
not precise execution latency.

CFTC annual files and the August 2026 World Bank workbook are retrieved snapshots. They may
include later corrections and do not reconstruct every earlier value vintage. Hashes identify
the exact bytes used. Results through 20 August 2026 are retrospective/pseudo-out-of-sample;
the registered forward holdout begins on 21 August 2026.

## Calculations

```text
net = managed_money_long_contracts - managed_money_short_contracts
absolute_change = new - old
percent_change = (new / old - 1) * 100
Q1_2026_average = mean(January_2026, February_2026, March_2026)
July_rebound_pct = (July_2026 / Q1_2026_average - 1) * 100
```

The pipeline selects the maximum net position, subsequent minimum and latest observation, and
the same checkpoints for open interest. The price comparison is 42.6271%, displayed as 42.6%;
rounded component values are not used in the calculation.

For each release `t`:

```text
x_t = managed_money_net_contracts / open_interest_contracts
Q10_t = prior-only empirical nearest-rank 10th percentile of x
event_t = (x_(t-1) <= Q10_t) and (x_t > x_(t-1))
R_(m+1,m+4) = World_Bank_cocoa_(m+4) / World_Bank_cocoa_(m+1) - 1
```

Evaluation requires 156 strictly earlier releases and 91 elapsed days between event publication
timestamps. Daylight saving matters: the 23 May 2017 report is only 90 days 23 hours after the
previous signal, so the next eligible event is 30 May. Missing future endpoints remain censored.

There are 13 events and 12 complete responses. Mean response is +0.614%, median +1.811%, and
58.3% are positive. The 95% circular-block bootstrap interval is -5.64% to +5.84%. This small
sample is inconclusive and does not establish return predictability.

## Hypothetical trade

The Dec-26 call spread requires licensed settlements and option quotes. Without them its status
is `NOT_EVALUATED_LICENSED_MARKET_INPUTS`. The workbook uses illustrative assumptions only.

For expiry futures price `F`, strikes `K1 < K2`, debit `D`, fees `C` and a 10-tonne contract:

```text
net_expiry_pnl = 10 * (max(F-K1, 0) - max(F-K2, 0) - D) - C
max_loss = 10 * D + C
max_gain = 10 * (K2-K1-D) - C
breakeven = K1 + D + C/10
contracts = floor((paper_NAV * 0.5%) / max_loss)
```

With `K1=5,500`, `K2=6,350`, `D=300` USD/t and `C=$20`, maximum loss is $3,020, maximum gain
is $5,480 and breakeven is $5,802/t. These are hypothetical expiry outcomes, not observed quotes
or tested early-exit returns. Slippage, liquidity, exercise and margin need separate evaluation.

The physical condition requires a decrease in ICCO surplus or ending stocks of at least 25kt,
or a fall in stocks-to-grindings of at least 0.5 percentage points. It resets with each new
visible vintage and expires after 120 days. It is true at the August design snapshot, but its
thresholds were selected after the May revision was known. Weather remains context only. A new
weather rule would need a frozen confirmation source, spatial method, thresholds, window,
freshness limit and reset before testing.

The upside hypothesis also needs a positioning reversal and price confirmation. Weaker demand,
a wider surplus, renewed price weakness or fresh shorts would weaken it. None of the evidence
establishes causality, crowding, full physical normalisation or an executable trading return.

## Reproduction

`python scripts/reproduce.py --check` verifies derived records before rendering figures and local
PDF exports. Source files remain unchanged. URLs, retrieval UTC, byte counts, upstream SHA-256
hashes, extraction methods and public-extract hashes remain in the manifests. Tests run offline.
Word reports are edited separately and checked against selected derived values and source links;
their file bytes are not deterministic build outputs.
