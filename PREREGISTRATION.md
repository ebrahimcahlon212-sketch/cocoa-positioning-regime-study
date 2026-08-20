# Trading-research preregistration

Version 1 was frozen on **2026-08-20** before any observation from the forward
evaluation period.  Everything dated on or before that day is design or retrospective
data.  The first genuine forward-holdout observation must be available after
2026-08-20.  Changing a rule below creates a separately named version; it must not be
silently substituted into version 1.

This is a research protocol, not a trading instruction or performance claim.

## 1. Positioning event

The weekly variable is

`x_t = CFTC Managed Money net contracts / total open interest contracts`.

Releases are sorted by their timezone-aware **`available_at` eligibility timestamps**,
not their Tuesday report dates.  These are retained actual publication times for
officially covered exceptions/schedules and explicitly rule-modelled ordinary Friday
15:30 ET eligibility times for older history.  Every output retains its availability
basis and source reference.  For the release at time `t`:

1. Require at least 156 strictly earlier releases.
2. Calculate `Q10_t` from every strictly earlier `x` using the empirical nearest-rank
   tenth percentile, with no interpolation.
3. Emit a bullish positioning-reversal event if and only if
   `x_(t-1) <= Q10_t` and `x_t > x_(t-1)`.
4. After an emitted event, suppress further events for 91 elapsed days (13 weeks),
   measured between these eligibility timestamps.

There is no persistent “armed” state: the immediately preceding release itself must
meet the extreme condition.  The threshold is expanding and prior-only.  It is never
re-estimated using the current or a future observation.

## 2. Public proxy response

The public response study uses the World Bank monthly cocoa series only as a
**non-tradable proxy**.  For a signal available in calendar month `m`, the one primary
response is:

`R_(m+1,m+4) = price_(m+4) / price_(m+1) - 1`.

Using `m+1` as the first endpoint avoids treating a full-month average that overlaps
the weekly event as an executable entry.  It still does not make the monthly benchmark
tradable.  If either endpoint is missing, or `m+4` is later than the declared last
complete month, the event remains in the output as **censored**.  It is never silently
dropped or filled.

Report the event count, complete count, censored count, arithmetic mean, median,
strictly-positive response rate, and a 95% circular-block bootstrap interval for the
mean.  The registered bootstrap uses block length 4, 10,000 replications, and seed
20,260,820.  With fewer than 20 complete events, the result is explicitly described as
especially underpowered.  No alternative horizon becomes “primary” after seeing the
result.

This evaluation is retrospective/pseudo-out-of-sample: historical thresholds obey the
information order, but the rule was designed after historical data existed.  It is not
a live track record, proof of causality, or evidence of alpha.

## 3. Physical deterioration gate

The version-1 evidence gate is evaluated from the latest two visible official ICCO vintages for
the same crop year. It is true when at least one latest-vs-prior revision is:

- published surplus/deficit down by at least 25kt;
- ending stocks down by at least 25kt; or
- stocks-to-grindings down by at least 0.5 percentage points.

The state is recomputed on every newer visible ICCO vintage and expires at the earlier of that
superseding release or 120 elapsed days after the current vintage became available. These round
thresholds are retrospective design hypotheses selected after the May revision was already known,
not calibrated price coefficients. The current -27kt surplus, -27kt ending-stocks and -0.7pp
stocks/grind revisions are therefore design evidence, not a forward result. Only a new qualifying
revision first available after the freeze can provide a genuine forward evaluation.

Weather is **context only** in version 1. NASA POWER observations, including the unconfirmed Kumasi
extreme, cannot activate this gate. A future weather gate requires a separately named and frozen
version that specifies the independent dataset, coordinates or crop weights, baseline, anomaly
method, confirmation tolerance, window, freshness and reset rule before evaluation. This avoids
turning a provisional two-location diagnostic into an after-the-fact signal.

## 4. Hypothetical Dec-26 structure

The instrument research is a defined-risk **Dec-26 cocoa call spread**, evaluated only
from a permitted licensed futures and options snapshot.  The public repository never
contains or reconstructs live ICE quotes.

A version-1 forward hypothetical candidate requires all of the following:

1. the registered CFTC positioning-reversal event;
2. the exact version-1 physical deterioration gate above is true;
3. the latest visible Dec-26 futures settlement strictly above each of the prior 20
   settlements available at that time;
4. a licensed Dec-26 call chain observed no later than the evaluation time;
5. the first listed call strike at or above the Dec-26 settlement as the long leg;
6. the first listed call strike at or above 115% of that long strike as the short leg;
7. conservative net debit (`long ask - short bid`) no greater than 40% of spread width.

No mid-market fill is assumed. If licensed settlement history or the option-chain snapshot is
absent, the structure is labelled **not evaluated**, rather than populated with invented prices,
strikes or premiums.

For expiry futures price `F`, lower strike `K1`, upper strike `K2`, debit `D` in USD per
metric tonne, round-trip per-spread fees `C`, 10 tonnes per contract, and `N` contracts:

`payoff/t = max(F-K1, 0) - max(F-K2, 0)`

`P&L = N * (10 * (payoff/t - D) - C)`

`maximum loss = N * (10 * D + C)`

`maximum gain = N * (10 * (K2 - K1 - D) - C)`

`breakeven = K1 + D + C / 10`.

Whole-contract sizing floors `portfolio value * 0.5% / maximum loss per contract`.
Zero contracts is the correct result when one spread exceeds the risk budget.  The
0.5% cap does not represent all liquidity, exercise, assignment, slippage, tax, margin, or
operational risks. The public workbook's $20 fee assumption and all strikes/premiums are
illustrative—not observed ICE inputs or an executable cost estimate.

The hypothetical exit is the earliest registered condition observed at an eligible
close: 40 trading sessions have elapsed; normalized managed-money net `x >= 0`; `x`
falls strictly below its entry value (fresh-short invalidation); or 10 trading sessions
remain before the option's last trading day.  The licensed contract master must supply
the last trading day; this repository does not invent it.  This is an audit rule only
and does not submit or simulate an order.

## 5. Forward holdout and governance

- Data through 2026-08-20 may be used for design and retrospective diagnostics only.
- The first untouched forward period begins after 2026-08-20.
- Censored outcomes remain censored until both registered endpoints become available.
- Failed or absent signals are recorded; the rule is not re-tuned to manufacture a
  trade.
- Any change to lookback, percentile, cooldown, horizon, the evidence-gate thresholds or
  freshness, weather eligibility, price-confirmation rule, strike-selection rule, debit limit, or
  risk cap is a new version disclosed before evaluation.
- Results must retain the warnings “PUBLIC PROXY — NOT TRADABLE”, “HYPOTHETICAL”, and
  “RETROSPECTIVE / PSEUDO-OUT-OF-SAMPLE” wherever applicable.
