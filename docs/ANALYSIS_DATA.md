# ETF Analysis Data

## Purpose

Milestone 8 adds time-varying ETF performance, dividend composition and data
quality records. Time-varying values are stored outside `etf_master`.

## Tables

### `etf_performance`

One row represents one ETF performance snapshot.

Uniqueness:

```text
ETF code
+ as-of date
+ period
+ metric
+ source
```

Schema-supported periods:

```text
1D  1W  1M  3M  6M  1Y  3Y  5Y
```

Current calculated periods:

```text
1M  3M  6M  1Y
```

Metric codes:

```text
PRICE_RETURN
TOTAL_RETURN
NAV_RETURN
```

The current TWSE closing-price Pipeline writes `PRICE_RETURN`. It does not
include cash distributions or dividend reinvestment.

### `etf_dividend`

One row represents one distribution event. A source event is unique by:

```text
source_id + source_event_id
```

Stored fields include announcement, ex-dividend, record and payment dates,
amount per unit, currency, source and import batch.

### `etf_dividend_component`

One row represents one disclosed component for a distribution event.

Uniqueness:

```text
dividend_id
+ component_basis
+ component_code
+ source_id
```

`component_basis` is one of:

```text
ESTIMATED
ACTUAL
```

A component must provide an amount per unit, a ratio, or both.

### `dividend_source_document`

Stores immutable versions of official actual-composition source documents.

A version is identified by:

```text
source_id
+ source_document_id
+ SHA-256 checksum
```

Changed content creates a new version. Identical content reuses the existing
version.

### `dividend_source_review_queue`

Tracks unresolved actual-composition and source-document coverage issues.

Issue types:

```text
MISSING_ACTUAL_COMPONENTS
MISSING_SOURCE_DOCUMENT
```

States:

```text
PENDING
IN_REVIEW
RESOLVED
SKIPPED
```

One dividend event can have one row per issue type.

## Performance calculation

The multi-period price Pipeline:

1. Selects non-bond ETF candidates by default; a detail-page coverage run may
   explicitly include bond ETFs.
2. Downloads each ETF price history once.
3. Reuses that history for all requested periods.
4. Writes only periods with sufficient price history.
5. Records insufficient history separately from execution failures.
6. Ranks each period and metric independently.

Default download windows:

| Period | Download months |
| --- | ---: |
| 1M | 3 |
| 3M | 5 |
| 6M | 8 |
| 1Y | 14 |

A missing return is never converted to `0%`.

Run:

```powershell
python -m backend.app.data_sources.performance_pipeline
```

For a V5 detail-page universe refresh, include bond ETFs explicitly:

```powershell
python -m backend.app.data_sources.performance_pipeline --include-bond
```

The dividend-yield fallback reuses saved official daily closes before making a
new request. This preserves the same TWSE source semantics and avoids fetching
the same price fact twice; absence of a pre-ex-dividend close remains missing.

## Dividend composition policy

TWSE ETF e添富 percentages are stored as estimated categories:

```text
EST_DIVIDEND
EST_INTEREST
EST_EQUALIZATION
EST_REALIZED_CAPITAL_GAIN
EST_OTHER
```

The estimated realized-capital-gain category is not an official tax-source
code and is never converted to `76W`.

Only an explicitly actual source can create:

```text
component_basis = ACTUAL
component_code = 76W
```

A formally disclosed `76W = 0%` is an available record. Absence of an ACTUAL
76W row is missing data, not zero.

### Composite component data

`backend.app.services.dividend_component_data` is the shared source-selection
boundary for every component-dependent calculation, the dividend-event detail
API and the 76W/capital-gain analysis. For each event it emits exactly one
complete mix:

1. prefer one complete `ACTUAL` event whose ratios total about 100%;
2. otherwise use one complete e添富 `ESTIMATED` event and label the output
   `ESTIMATED_FALLBACK`;
3. never combine rows from the two bases to manufacture 100%.

Raw rows and their original component codes remain stored for provenance. The
selected output supplies a usable composition to downstream algorithms without
relabelling estimated codes as formal `54C` or `76W`.

The 76W/capital-gain analysis applies this selection independently to every
dividend event. An ACTUAL selection contributes only its formal `76W` ratio; an
`ESTIMATED_FALLBACK` selection contributes only
`EST_REALIZED_CAPITAL_GAIN`. Formal coverage metrics remain ACTUAL-only even
when the fallback analysis is available.

### Planning freshness (Issue #122)

The owner-approved `select_planning_component_mix` is a separate planning
entry point used by market eligibility, portfolio projections and single-ETF
tax/reinvestment scenarios. It requires an explicit evaluation date and a
known payment date on or before evaluation. Within the existing 18-calendar-
month freshness window it selects the latest complete ACTUAL mix first, then
the latest complete estimated mix. The exact 18-month anniversary is included;
calendar month-end clipping uses the unchanged dividend-freshness helper.
Input row order does not determine which date is newest. No complete fresh
paid source means unavailable, not reuse of stale data or inferred zero.

When a complete historical ACTUAL mix is stale and a fresh estimate is used,
the selection retains that ACTUAL date for an explicit warning. Estimates
remain `ESTIMATED_FALLBACK` with their original estimated codes. The market
and portfolio issue code is `STALE_ACTUAL_COMPONENTS_FALLBACK`; this warning
does not independently exclude a candidate. Other eligibility gates still
apply. The single-ETF tax response exposes a `warnings` list rendered by the
existing detail page. Fresh ACTUAL still takes precedence over newer estimates.

Historical event detail, per-event capital-gain history, the undated legacy
compatibility selector and formal ACTUAL/76W coverage retain their original
semantics. This policy does not rewrite or import source rows. A planning
selection is not a declaration that the historical ACTUAL record is invalid.

## Actual source processing

### Human-reviewed JSON

```powershell
python -m backend.app.data_sources.actual_dividend_pipeline `
    --input .\data\imports\actual_dividend_notice.json
```

Matching requires ETF code, ex-dividend date and amount per unit. Record date
and payment date are additional exact checks when supplied.

### Verified Cathay announcement Adapter

```powershell
python -m backend.app.data_sources.cathay_actual_dividend_pipeline `
    --url "https://www.cathaysite.com.tw/announcement/5141" `
    --etf-code 00878 `
    --input-html .\data\imports\cathay_5141.html
```

The Adapter requires explicit actual-composition wording and rejects estimated
wording before the ACTUAL Pipeline is called.

## Coverage and review queue

Run:

```powershell
python -m backend.app.data_sources.actual_dividend_coverage_pipeline
```

Coverage measures:

- Dividend events with estimated components
- Dividend events with ACTUAL components
- Dividend events with ACTUAL `76W`
- Dividend events linked to parsed ACTUAL source documents
- Missing ACTUAL and source-document events

The review queue is synchronized idempotently. Supplying missing data can
resolve an item automatically. An unresolved `SKIPPED` item remains skipped.

## APIs

Performance:

```text
GET /api/v1/performance/ranking
GET /api/v1/performance/multi-period-ranking
GET /api/v1/etfs/{code}/performance
```

Dividends:

```text
GET /api/v1/etfs/{code}/dividends
GET /api/v1/etfs/{code}/dividends/76w
GET /api/v1/dividends/{dividend_id}
GET /api/v1/dividends/{dividend_id}/components
```

Data quality:

```text
GET /api/v1/data-quality/dividends/actual-coverage
GET /api/v1/data-quality/dividends/review-queue
GET /api/v1/data-quality/dividends/review-queue/{queue_id}
```

## Current limitations

- Production calculations currently provide market-price return only.
- Actual-composition coverage is limited by available verified documents.
- The source-review queue and Streamlit quality page are read-only.
- Pipelines are manually started; scheduling belongs to M12.
- Recommendation, comparison and portfolio decisions belong to M9–M11.
- Broker and third-party market-data integrations are deferred optional work.
