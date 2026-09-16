# Cocoa positioning study

I tested whether a reversal from unusually short cocoa positioning was followed by higher prices,
then compared it with the physical balance and weather evidence available in August 2026.

The historical result is inconclusive. Of 13 events, 12 have complete monthly responses: the mean
is +0.6%, with a 95% bootstrap interval of -5.6% to +5.8%. The World Bank price proxy does not
measure a tradable futures return.

## Read the research

- [One-page positioning note](reports/cocoa-positioning-note.docx)
- [Two-page research memo](reports/cocoa-research-memo.docx)
- [Scenario workbook](outputs/cocoa-trading-v2/cocoa-trade-scenario.xlsx)

The Word documents are editable. Their information cutoffs remain 14 August and 20 August 2026;
this documentation update does not refresh the market data.

## Findings

Managed-money net positioning recovered from -23,084 contracts in June to -6,667 on 11 August.
ICCO's May vintage cut the 2024/25 surplus estimate from 75kt to 48kt. Q2 grindings weakened in
Europe but rose in Asia and North America, with reporting changes limiting comparisons.

The conditional upside case still needs a new positioning reversal and price confirmation.
The hypothetical call spread is **NOT EVALUATED** because licensed ICE prices and option quotes
are absent. Workbook strikes and premiums are illustrative. Weather uses two provisional location
proxies and cannot activate the registered trade rule.

## Reproduce

Requires Python 3.11 or later. Activate the environment before installing:

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install -e ".[dev,report]"
python scripts/reproduce.py --check
pytest
ruff check .
ruff format --check .
mypy
```

The rebuild checks retained data and generates charts and local PDF exports. Word notes are
edited separately; tests check their figures and source links. PDF exports are ignored by Git.
All tests run offline.

See [methodology](METHODOLOGY.md), the [frozen protocol](PREREGISTRATION.md),
[source rights](DATA_LICENSE.md), [licensed-input requirements](LICENSED_DATA.md) and
[AI use](AI_USAGE.md). Data, release calendars, hashes and derived results are retained under
`data/`. This is historical and hypothetical research, with no broker connection or trading action.
