# Cocoa Trading Research Case

**Positioning, the physical balance, regional demand, weather and a defined-risk expression**

The question I set out to answer: after cocoa positioning swung from an extreme long to net
short, did the physical, weather and historical return evidence justify a bullish reversal
trade? I tried to answer that without manufacturing a trading result.

- **[Open the two-page trading memo](output/pdf/cocoa-trading-research-case.pdf)**
- **[Open the scenario workbook](outputs/cocoa-trading-v2/cocoa-trade-scenario.xlsx)**
- [Original one-page positioning note](output/pdf/cocoa-positioning-regime-shift.pdf)

My honest answer is mixed. The physical recovery is real but not comfortable, demand is
regionally divergent, and managed money was still net short. Provisional West African location
proxies lean wet, but Kumasi's extreme accumulation needs a second source and is excluded from
the trade gate. The frozen retrospective public-proxy study comes out **inconclusive**: 12
completed events, a mean three-month response of **+0.6%**, a **58.3%** positive rate and a wide
**-5.6% to +5.8%** block-bootstrap interval. That is not evidence of alpha, and the report says
so.

## Decision view as of 20 August 2026

| Layer | Point-in-time observation | Trading interpretation boundary |
|---|---|---|
| Positioning | Managed-money net was -6,667 contracts on 11 August, after a June trough of -23,084 | A short base can amplify an upside event, but COT categories do not reveal motive or contract month |
| Physical balance | ICCO's May vintage put 2024/25 production at 4,723kt, grindings at 4,628kt, published surplus at 48kt, ending stocks at 1,320kt and stocks/grindings at 28.5% | Supply recovery, but the latest revision reduced the published surplus and stocks by 27kt |
| Regional demand | Q2 2026 grind releases: Europe -4.6% y/y, Asia +25.07%, North America +7.65% | Demand is divergent; comparator and methodology caveats are retained |
| Weather | Daloa was +47.0%; the Kumasi-driven upper reading of +188.0% is flagged for second-source confirmation | Provisional location proxies, not crop-area weights or a yield forecast; weather is not currently trade-gate eligible |
| Historical test | 13 events; 12 complete; mean +0.6%; median +1.8%; hit rate 58.3%; 95% CI -5.6% to +5.8% | Monthly World Bank data are a non-tradable response proxy and the result is underpowered/inconclusive |

So the conditional upside case is an **event-risk watch**, not a buy signal. The exact version-1
physical gate is currently true because the latest ICCO revision reduced the published surplus and
ending stocks by 27kt and stocks/grindings by 0.7pp. That state expires after 120 days or a newer
vintage. Weather is context-only and cannot activate version 1. A new positioning reversal and
licensed contract-price confirmation are still required. Weaker grindings, a wider official
surplus, improving crop conditions or renewed short formation invalidate the thesis.

## Hypothetical expression

The frozen research rule uses a defined-risk **Dec-26 cocoa call spread**, on the logic that a
weather or crop disappointment is asymmetric while the premium caps loss. Actual evaluation
requires licensed ICE settlement history and option-chain inputs stored outside Git. Neither is
present. The public report uses conspicuously illustrative inputs that are not market
observations, solely to make the mechanics auditable:

- long 5,500 / short 6,350 call;
- 300 USD/t net debit plus 20 USD round-trip fees per spread;
- maximum loss **$3,020**, maximum gain **$5,480**, breakeven **$5,802/t**;
- one spread for a $1m paper portfolio under a 0.5% maximum-loss budget; and
- earliest exit at 40 sessions, normalized positioning at or above zero, fresh-short invalidation,
  or ten sessions before the option's last trading day.

These are scenario assumptions, not observed quotes, a recommendation or executable P&L. Missing
licensed inputs produce **NOT EVALUATED**, never guessed prices.

## What makes the test point-in-time

CFTC positions are effective on Tuesday but normally become usable on Friday at 15:30 Eastern.
The pipeline sorts and applies its 91-day cooldown using the actual or explicitly modelled
publication timestamp rather than the report date. This matters around daylight-saving changes and
during exceptional schedules: the 30 September 2025 report was unavailable until the shutdown
catch-up on 19 November.

The event threshold is an expanding, prior-only tenth percentile with at least 156 earlier
releases. The response uses World Bank month `m+1` to `m+4`; missing future endpoints stay
censored. Because the rule was designed after historical data existed, every result through
20 August 2026 is labelled retrospective/pseudo-out-of-sample. The registered forward holdout
starts after that date.

## How scientific studies are used

The evidence registry records mechanism, geography, design and external-validity limits for four
primary studies. The papers justify candidate features including dry spells, heat, wetness/disease
pressure and fruit-set lags. They do **not** provide a transferable cocoa-price coefficient. Only
a separately registered point-in-time test can decide whether a feature has market relevance.

## Research controls and outputs

- a full commodity-research chain from official source to falsifiable trade expression;
- release-time controls that prevent a subtle COT look-ahead error;
- physical-balance and regional-demand reasoning with vintages and source hashes;
- provisional weather monitoring with explicit spatial and scientific limitations;
- a frozen retrospective test that reports a null/uncertain result honestly;
- exact call-spread payoff, bounded-loss sizing and scenario analysis; and
- AI-assisted source discovery and adversarial review, with deterministic Python producing every
  reported number.

## Repository map

- `output/pdf/cocoa-trading-research-case.pdf` - two-page trading research memo
- `outputs/cocoa-trading-v2/cocoa-trade-scenario.xlsx` - formula-driven scenario workbook
- `data/derived/trading_case_summary.json` - the report's primary narrative summary
- `data/derived/cocoa_cot_positioning.csv` and `cocoa_price_monthly.csv` - chart-series inputs
- `data/derived/cftc_positioning_reversal_events.csv` - point-in-time signal events
- `data/derived/public_proxy_event_outcomes.csv` - complete and censored proxy outcomes
- `data/derived/fundamentals_snapshot.json` - physical balance and grind-release vintages
- `data/derived/weather_snapshot.json` - provisional weather-proxy diagnostics
- `data/derived/evidence_guardrails.json` - scientific mechanisms and transfer limits
- `PREREGISTRATION.md` - frozen signal, response, trade and holdout rules
- `LICENSED_DATA.md` - local-only ICE input boundary
- `tests/` - offline tests for hashes, units, timing, formulas and deterministic rendering

## Reproduce

Requires Python 3.11 or later. Acquisition is separate from deterministic analysis; tests block
network access.

```bash
python -m venv .venv
python -m pip install -e ".[dev,report]"
python scripts/reproduce.py --check
pytest
ruff check .
ruff format --check .
mypy
```

See [METHODOLOGY.md](METHODOLOGY.md), [DATA_LICENSE.md](DATA_LICENSE.md),
[LICENSED_DATA.md](LICENSED_DATA.md), [PREREGISTRATION.md](PREREGISTRATION.md), and
[AI_USAGE.md](AI_USAGE.md) for the full boundaries.

NASA POWER acknowledgement: these weather proxies use NASA Langley Research Center POWER Project
data, POWER Web Services (API v2.9.6/v2.9.7), accessed 20 August 2026. Full request URLs, product
sources, access timestamps and hashes are retained in the weather registry.

This repository contains historical and hypothetical research only. It is not investment advice,
an executable signal, a live track record or an automated trading system. It has no broker
connection and performs no trading action.

## Related infrastructure

The companion [Point-in-Time Market Data Ledger](https://github.com/ebrahimcahlon212-sketch/market-intelligence-research-platform)
shows the generic audit and storage controls behind this applied case.
