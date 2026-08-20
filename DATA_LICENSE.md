# Data sources and rights

This repository does not relicense upstream data. Code, original prose and original charts are
covered by the repository license; source data remains subject to its provider's terms.

## CFTC Commitments of Traders

The positioning series comes from the U.S. Commodity Futures Trading Commission's
Disaggregated Futures-Only dataset. U.S. federal government works are generally public domain,
and the CFTC requests appropriate acknowledgement. The project cites the CFTC as source and
preserves the exact download URL and SHA-256 hash in `data/source_manifest.csv`.

The public repository retains the annual observation archives needed for the analysis. Full
CFTC methodology, schedule and announcement-page wrappers are not redistributed; compact
sanitized extracts preserve only the publication facts used by the temporal model, with official
URLs and upstream hashes in the manifest.

- Dataset: <https://publicreporting.cftc.gov/Commitments-of-Traders/Disaggregated-Futures-Only/72hh-3qpy>
- Methodology: <https://publicreporting.cftc.gov/stories/s/COT-Help/p2fg-u73y/>
- CFTC web policy: <https://www.cftc.gov/WebPolicy/index.htm>

Do not imply CFTC endorsement of this analysis.

## World Bank commodity prices

The price context comes from the World Bank Commodity Price Data (the Pink Sheet). The World Bank
dataset catalog identifies the dataset under Creative Commons Attribution 4.0 (CC BY 4.0), while
the workbook attributes the cocoa series to the International Cocoa Organization. Both the World
Bank Prospects Group and ICCO are therefore acknowledged.

For a rights-minimal public artifact, this repository retains only four attributed monthly values:
January, February, March and July 2026. It does not redistribute the full workbook or upstream
pages, separately relicense ICCO material, imply endorsement, or claim ownership of the source.
The manifest retains the official landing and artifact URLs plus the upstream SHA-256 hash.
It also separates upstream and public byte counts and hashes, identifies the extraction method,
and records whether the upstream artifact is redistributed.

- Pink Sheet: <https://thedocs.worldbank.org/en/doc/74e8be41ceb20fa0da750cda2f6b9e4e-0050012026/world-bank-commodities-price-data-the-pink-sheet>
- World Bank data licensing: <https://datacatalog.worldbank.org/public-licenses>
- ICCO: <https://www.icco.org/>

## Derived outputs

Derived tables contain the minimum values needed to reproduce this analysis, with source
attribution and units. The four-row cocoa extract is a project transcription for this calculation,
not an official CFTC, World Bank or ICCO publication. Contract-unit equivalents are analytical
notionals and are not physical inventory.

If provider terms or attribution requirements change, the minimal extract can be removed while
retaining upstream provenance and its checksum.
