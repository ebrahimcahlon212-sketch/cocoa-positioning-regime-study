# Data sources and rights

This repository does not relicense upstream data. Code, original prose and original charts are
covered by the repository license; source data remains subject to its provider's terms.

## CFTC Commitments of Traders

The positioning series comes from the U.S. Commodity Futures Trading Commission's
Disaggregated Futures-Only dataset. U.S. federal government works are generally public domain,
and the CFTC requests appropriate acknowledgement. The project cites the CFTC as source and
preserves the exact download URL and SHA-256 hash in `data/source_manifest.csv`.

The public repository keeps the annual observation archives needed for the analysis. Full
CFTC methodology, schedule and announcement-page wrappers are not redistributed; compact
sanitized extracts preserve only the publication facts used by the temporal model, with official
URLs and upstream hashes in the manifest.

The extended signal study also keeps a rights-minimal selected-field CSV from CFTC's public
Socrata API for the live disaggregated-report era. Its manifest records both the upstream response
and public-extract hashes. It is a current retrieved-value snapshot and is not described as a full
archive of every later CFTC correction or reclassification.

- Dataset: <https://publicreporting.cftc.gov/Commitments-of-Traders/Disaggregated-Futures-Only/72hh-3qpy>
- Methodology: <https://publicreporting.cftc.gov/stories/s/COT-Help/p2fg-u73y/>
- CFTC web policy: <https://www.cftc.gov/WebPolicy/index.htm>

Do not imply CFTC endorsement of this analysis.

## World Bank commodity prices

The price context comes from the World Bank Commodity Price Data (the Pink Sheet). The World Bank
dataset catalog identifies the dataset under Creative Commons Attribution 4.0 (CC BY 4.0), while
the workbook attributes the cocoa series to the International Cocoa Organization. Both the World
Bank Prospects Group and ICCO are therefore acknowledged.

To keep the public artifact rights-minimal, this repository retains two factual extracts: the original
four attributed 2026 values and the 23 unique monthly endpoints required by the frozen event
study. It does not redistribute the full workbook or upstream pages, separately relicense ICCO
material, imply endorsement, or claim ownership of the source. The manifests keep the official
landing and artifact URLs plus the upstream SHA-256 hash. They also separate upstream and public
byte counts and hashes, identify the extraction method, and record that the upstream workbook is
not redistributed.

- Pink Sheet: <https://thedocs.worldbank.org/en/doc/74e8be41ceb20fa0da750cda2f6b9e4e-0050012026/world-bank-commodities-price-data-the-pink-sheet>
- World Bank data licensing: <https://datacatalog.worldbank.org/public-licenses>
- ICCO: <https://www.icco.org/>

## ICCO balance and regional grinding facts

The balance and grinding inputs are compact factual transcriptions from freely accessible official
release pages. Full ICCO bulletins, association PDFs and page wrappers are not copied into this
repository. Each row preserves the official URL, retrieval UTC, page hash, original unit and an
extraction note. The source providers retain all rights in their publications; project code and
original charts are not a relicensing of those sources.

- ICCO: <https://www.icco.org/>
- European Cocoa Association: <https://www.eurococoa.com/grind-stats/>
- Cocoa Association of Asia: <https://www.cocoaasia.org/grinding-figures>
- National Confectioners Association: <https://candyusa.com/cocoa-grinds-report>

## NASA POWER weather proxies

The retained weather rows are attributed outputs from NASA POWER. The project preserves query URLs,
retrieval UTC, source-product labels and hashes. They remain gridded location proxies and are not
presented as official farm measurements. NASA's data-use and acknowledgement requirements apply.

Acknowledgement: weather data were obtained from the NASA Langley Research Center POWER Project,
funded through the NASA Earth Science Directorate Applied Sciences Program. Data reference: NASA
POWER Web Services, API versions v2.9.6/v2.9.7, Daloa and Kumasi point queries, accessed 20 August
2026. Exact request URLs, product-source labels, timestamps and SHA-256 hashes are retained in
`data/raw/nasa-power-west-africa-weather.csv`.

- NASA Earthdata data-use policy: <https://www.earthdata.nasa.gov/engage/open-data-services-software/data-use-policy>
- NASA POWER: <https://power.larc.nasa.gov/>
- NASA POWER referencing guide: <https://power.larc.nasa.gov/docs/referencing/>

## Scientific evidence registry

The repository retains bibliographic facts and short original paraphrases, not article PDFs,
publisher figures or copied tables. Each record includes its DOI, source URL and the licence stated
for that article. A citation or open-access designation does not transfer ownership of the paper to
this project.

## Licensed exchange data

ICE futures and options data are not included. `data/licensed/` is ignored, and the public adapter
only defines a local schema and deterministic formulas. See `LICENSED_DATA.md`. Do not publish raw
or derived exchange data unless the applicable licence expressly permits that use.

## Derived outputs

Derived tables contain the minimum values needed to reproduce this analysis, with source
attribution and units. The cocoa extracts and physical/weather registries are project
transcriptions for this calculation, not official republications. Contract-unit equivalents are
analytical notionals, not physical inventory. Illustrative option values are conspicuously
labelled and are not exchange observations.

If provider terms or attribution requirements change, the minimal extract can be removed while
retaining upstream provenance and its checksum.
