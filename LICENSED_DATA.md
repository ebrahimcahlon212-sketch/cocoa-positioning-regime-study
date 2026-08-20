# Licensed market-data boundary

The public study does not redistribute ICE futures settlements, option chains, vendor
symbology, or derived quote surfaces.  Licensed files belong only under
`data/licensed/`, which is excluded from Git.  The code provides a local adapter so an
authorized user can evaluate the frozen rule without weakening provenance or replacing
missing quotes with guesses.

The adapter has no network client, broker connection, order model, or execution action.

## Local option-chain schema

Create `data/licensed/dec26_call_chain.csv` with this exact header:

```text
observed_at_utc,contract_label,option_type,strike_usd_per_metric_tonne,bid_usd_per_metric_tonne,ask_usd_per_metric_tonne,currency,quote_unit,vendor,license_reference,data_classification
```

Requirements:

- `observed_at_utc` is an ISO-8601 UTC timestamp;
- `contract_label` is `Dec-26` and `option_type` is `CALL`;
- currency and unit are `USD` and `USD_PER_METRIC_TONNE`;
- every row is one snapshot, strikes are unique, and bid is no greater than ask;
- `vendor` and `license_reference` preserve the user's entitlement/provenance;
- real rows use `LICENSED_CONFIDENTIAL`.

## Local futures-settlement schema

Create `data/licensed/dec26_settlements.csv` with this exact header:

```text
session_date,available_at_utc,contract_label,settlement_usd_per_metric_tonne,currency,quote_unit,vendor,license_reference,data_classification
```

`available_at_utc` is when that settlement became usable to the researcher.  Historical
price confirmation filters on this timestamp, not merely `session_date`.  Real rows use
`LICENSED_CONFIDENTIAL` and retain the vendor and entitlement reference.

Pass the explicit `data/licensed/` path as `licensed_root` when loading confidential
files.  The adapter rejects confidential inputs stored outside that boundary and
rejects a file that mixes confidential and synthetic rows.

## Synthetic tests

The committed files under `tests/fixtures/` are conspicuously labelled
`SYNTHETIC_TEST_ONLY`.  They are invented solely to test formulas and schemas.  They are
not cocoa market observations, indicative quotes, or usable estimates.  Loading them
requires the explicit `allow_synthetic=True` switch.

Before sharing an output, confirm that it contains only rule status, aggregate research
statistics, and clearly hypothetical scenario mechanics permitted by the applicable
licence.  Do not publish quote rows, a reconstructed surface, or values whose
redistribution terms are uncertain.
