# Cocoa Trading Research Case

## Positioning, physical risk, weather and a defined-risk expression

**Information cutoff:** controlled by the release-time timestamps in
`data/derived/trading_case_summary.json`. Missing licensed market inputs make the rule **not
evaluated**; any illustrative mechanics remain separately and visibly labelled.

### Decision view

The case to watch is convex upside event risk: crop recovery disappoints while managed money is
still short and price confirms. The opposite case is weaker grindings, a larger official surplus,
renewed price weakness and fresh short formation. This is a conditional framework, not a
directional forecast.

The original positioning study established a material regime change and enforced the distinction
between a report's effective date and its actual publication time. This extension asks whether
that observation survives three harder tests:

1. Does the physical balance deteriorate in the official estimate vintage available at the time?
2. Do two provisional location-proxy weather features identify a credible crop-stage mechanism?
3. Does a frozen prior-only retrospective event rule precede returns in data usable at the time?

### Physical and weather evidence

The physical layer records production, grindings, surplus or deficit, ending stocks and
stocks-to-grindings for each official vintage. Revisions are appended as new observations; prior
estimates are not overwritten. Regional grindings releases are treated as separate demand
evidence.

The weather layer currently uses two provisional NASA POWER location proxies for Daloa and
Kumasi. They are not crop-area-weighted farm measurements or historical release vintages, and
weather is not translated mechanically into tonnes. Rain can support growth and also increase
disease pressure, so feature meaning depends on geography, crop stage and lag.

### Hypothetical trade rule

The preferred expression is a defined-risk cocoa call spread, activated only after:

- the registered physical-balance evidence deteriorates;
- managed-money positioning remains short but begins reversing; and
- price confirms rather than continuing lower.

The hypothetical structure buys the first listed call at or above the licensed settlement and
sells the first listed strike at or above 115% of that long strike. The frozen exit is the
earliest of 40 sessions, CFTC normalized net at or above zero, normalized net below its entry
level, or 10 sessions before the option's last trading day.

Because permitted ICE settlement history and option-chain inputs are absent, the report labels
the rule **not evaluated**. It separately shows conspicuously illustrative strikes, premium, fees
and scenario outcomes to make the mechanics auditable; they are not market observations or
executable P&L. It performs no broker action.

### Historical evaluation

The public study uses release-time eligibility and must keep thresholds inside an expanding or
walk-forward window. Event counts, median returns, hit rates and confidence intervals are
reported only when materialized by deterministic Python. World Bank monthly cocoa values are
public price context, not a tradable ICE futures return or executable P&L. A licensed
contract-level study remains separate and cannot be inferred from the proxy.

### Scientific evidence register

Scientific papers are used to define mechanisms and lags, not to import an effect size blindly.
Each claim should record geography, sample, method, crop stage, exposure, lag, uncertainty and
external-validity limitations. A paper is not presented in the report until those fields have
been extracted and checked.

### Risk and boundaries

- Historical and educational research only; not investment advice.
- Hypothetical trade; no broker connection or broker action.
- Public price proxy is not a tradable futures series.
- A single physical snapshot is not a full vintage-replay balance sheet.
- Weather features do not prove crop loss or causality.
- Positioning categories do not reveal every participant or motive.
- No claim of alpha, forecast accuracy or executable P&L is made without the required data.

### Primary sources

- CFTC Commitments of Traders: <https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm>
- World Bank Commodity Price Data (Pink Sheet): <https://thedocs.worldbank.org/en/doc/74e8be41ceb20fa0da750cda2f6b9e4e-0050012026/world-bank-commodities-price-data-the-pink-sheet>
- ICCO Quarterly Bulletin, May 2026: <https://www.icco.org/may-2026-quarterly-bulletin-of-cocoa-statistics/>
- NASA POWER meteorology: <https://power.larc.nasa.gov/>
- European Q2 2026 grindings: <https://www.eurococoa.com/wp-content/uploads/WEBSITE-REPORT-WESTERN-STATS-Q2-2026.pdf>
- Asian Q2 2026 grindings: <https://www.cocoaasia.org/_files/ugd/fba979_7e8a5c99b5474b05b1b03cbd363163c8.pdf>
- North American Q2 2026 grindings: <https://candyusa.com/wordpress/wp-content/uploads/2026/07/Q2-2026-Cocoa-Grinds.pdf>
- Ghana rainfall and black-pod mechanism: <https://cocoasoils.org/wp-content/uploads/2022/10/Asitoakor-et-al.-2022..pdf>
- Ghana crop-stage lag evidence: <https://www.cambridge.org/core/journals/experimental-agriculture/article/effects-of-climate-and-withintree-competition-on-cocoa-pod-production-in-ghana/2F9415457E7C6E28FC01F050F4A7049D>
- Severe-drought tail-risk evidence: <https://journals.plos.org/plosone/article?id=10.1371%2Fjournal.pone.0200454>
