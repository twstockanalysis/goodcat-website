# ETF Constituent Snapshot Contract

## Purpose

ETF constituent data is required before portfolio overlap can become an
automatic assessment input. User-entered overlap remains a scenario assumption
and must not be represented as issuer-sourced constituent overlap.

## Immutable snapshots

Each snapshot stores:

- ETF code
- Constituent-data effective date
- Source identifier and optional source URL
- Fetch timestamp
- Disclosed total weight and constituent count
- Constituent identifier, name, disclosed weight and optional rank

The `(etf_code, as_of_date, source_id)` tuple is unique. An existing snapshot is
never silently overwritten. A changed issuer file for the same effective date
must be investigated or preserved under a separately versioned source ID.

Constituent identifiers are normalized to uppercase. Duplicate identifiers and
total disclosed weights above `100.5%` are rejected. The small tolerance only
allows issuer rounding; it is not permission to normalize invalid source data.

## Weighted overlap

Historical evaluation selects the latest stored effective date **on or before**
the evaluation date (inclusive), consistently for the quality gate and both
pairwise and portfolio overlap. Future snapshots remain immutable but cannot
mask earlier eligible evidence or enter the calculation. With only future
snapshots, the gate retains `FUTURE_DATED_SNAPSHOT` and overlap remains null.
The selected snapshot still must pass freshness and disclosed-weight gates;
do not search further backwards to replace a failing selected snapshot.
This is an effective-date replay, not proof that a later-fetched disclosure was
available to investors at that historical time. Fetch timestamps remain stored.
Repository callers without a cutoff retain latest-overall retrieval.

Pairwise overlap uses:

```text
overlap = sum(min(left disclosed weight, right disclosed weight))
          for every shared constituent identifier
```

The method identifier is `SUM_MIN_DISCLOSED_WEIGHTS_V1`. Both snapshot dates,
both disclosed total weights, the shared constituent count and each shared
weight contribution remain in the result.

Weights are not normalized to 100% when an issuer discloses only part of a
portfolio. Normalization would hide incomplete coverage and could overstate
overlap. A later assessment integration must apply an explicit minimum coverage
and freshness gate before using overlap as a scored metric.

## Current scope

Yuanta ETF stock weights are fetched from the official `PCF/Daily` bridge used
by its product page. The adapter requires the returned ETF code to match the
request, uses the official PCF trading date, and rejects stock-weight coverage
below 90%. Futures, bonds and nested ETF positions are not mixed into equity
constituent overlap.

The shared HTML parser also defaults to 90%. Fubon's official fund-asset page
is the bounded exception: stock weight down to the calculation gate's 85% may
be accepted only when the same official response contains a separate non-stock
asset table. This preserves disclosed stock weight without normalizing it.
First's adapter ignores formally zero stock rows only after retaining their
zero semantics and still requires all positive positions to reconcile exactly
to the separately disclosed official stock-asset total.

Nomura has a separate bounded 85%-90% stock-weight path (Issue #120). It
requires a unique stock table with explicit columns and a same-date fund AUM
and unique asset-summary table. The summary must disclose exactly one TWD
stock amount; its formatted and raw amounts must agree. Summed disclosed
stock weights must reconcile to stock assets / fund AUM * 100 within 0.005
percentage points per disclosed row, capped at 0.25 percentage points. This
allowance covers rounding of weights reported to at most two decimal places;
it is not a proof of completeness below that precision. Missing, malformed or
unreconciled evidence fails closed. Stocks below 85% remain rejected; stocks
at or above 90% retain the prior source threshold. Nomura stock rows are no
longer silently skipped when malformed. Duplicate identifiers remain rejected.
Reported zero rows are preserved, not inferred. No non-stock row is imported
and no weights are normalized. Other issuer thresholds are unchanged.

Nomura retrieval optionally accepts an explicit historical `snapshot_on`,
posts it as ISO `SearchDate`, rejects a future request and requires the returned
stock date to match exactly. The default still requests latest data. Historical
retrieval does not bypass the caller's evaluation-date/freshness quality gate.
See `V5_3D_NOMURA_STOCK_RECOVERY.md` for local evidence and remaining gaps.

Twenty-one issuers now have adapters. Cathay resolves the API fund code through
the public catalog, verifies ETF identity, requests the latest disclosed asset
date and fetches stock rows for that date. Future or older-than-seven-day data,
known nested ETF/derivative rows, duplicate identifiers, and stock coverage
below 90% are rejected. Weights remain unnormalized. Latest-only retrieval is
not a historical backfill: a disclosure after the evaluation date is rejected.
See `V5_3E_CATHAY_OFFICIAL_RECOVERY.md` for the bounded live evidence and gaps.
BlackRock remains fail-closed because its tested official automation paths do
not return a reproducible usable response. JKO
has no current equity constituent portfolio.
The published Fugle Market Data and Sinopac Shioaji endpoint sets provide ETF
identity and market/account data but not ETF constituent weights. V2-10 adds
batch ingestion plus reusable freshness, disclosed-weight, ETF and issuer
coverage gates. This contract still does not expose a public constituent
endpoint or replace the manual overlap field; assessment integration remains a
separate milestone and must consume the gate result.

The all-issuer discovery result and exact automation status are maintained in
`ETF_CONSTITUENT_SOURCE_AUDIT.md`. A verified complete official response is
evidence for a future adapter, not permission to mark that issuer automated.
