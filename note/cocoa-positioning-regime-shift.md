# Cocoa Positioning Regime Shift

## From the 2024 positioning extreme to the 2026 rebuild

**Information cutoff:** August 14, 2026, after the normal COT publication time for positions
effective August 11.

### View

The market structure changed more decisively than the price narrative alone suggests.
Managed-money net cocoa positioning fell from +82,572 contracts in January 2024 to -23,084 in
June 2026, then recovered to -6,667 by August 11. July's $5.61/kg World Bank cocoa indicator was
42.6% above the Q1 2026 average and coincided with part of that recovery.

That combination is consistent with partial short-covering and/or re-risking. It does not prove
positioning caused the rebound, that the market was crowded, or that physical supply had
normalized. Open interest recovered from its April 2025 low but remained 42.8% below the
January 2024 peak.

### Conditional event-risk posture

The setup creates upside event risk if an official crop recovery disappoints while managed money
remains net short and price confirms. A firmer case would need the rebound to hold, net shorts to
become less negative and open interest to expand, indicating participation rather than only a
mechanical reduction in exposure.

The downside case is weaker demand or grindings, a larger official surplus, renewed price
weakness and fresh short formation. Those observations would invalidate the upside posture.

This is not a directional price forecast or trading recommendation. It specifies which evidence
would make the interpretation stronger or weaker.

### Point-in-time control

COT positions are effective Tuesday but generally become available Friday at 15:30 Eastern Time.
The pipeline filters on the modeled `available_at` timestamp. Letting Tuesday's row enter a
Tuesday decision would create look-ahead leakage.

A real exception makes the control tangible: positions dated September 30, 2025 were not
published until November 19 during the CFTC shutdown backlog. That row uses the documented
catch-up date; ordinary 2024 and uncovered 2025 dates are rule-modelled. The timestamps are
research controls, not latency-grade execution data.

### Boundaries

- Four monthly price values are used retrospectively; they are not a specific futures return.
- Contract-unit equivalents are not physical inventory.
- Category positioning does not identify every participant or motive.
- The study claims no causality, crowding, alpha, executable P&L or forecast accuracy.
- Physical normalization remains uncertain and must be tested with separate crop, grindings and
  balance-sheet evidence.
- CFTC annual files are current retrieved snapshots and may contain later corrections; hashes bind
  the analysis to those bytes, but this is not full historical value-vintage replay.

### Sources

CFTC Disaggregated Futures-Only Commitments of Traders and attributed publication-calendar
extracts; a four-value World Bank cocoa extract, whose source series is attributed to ICCO. Full
upstream workbook and page wrappers are not redistributed. Official URLs and upstream SHA-256
hashes are recorded in `data/source_manifest.csv`.
