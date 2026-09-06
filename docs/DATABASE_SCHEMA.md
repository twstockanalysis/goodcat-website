# Database Schema

## ETF constituent snapshots

`etf_constituent_snapshot` preserves one immutable ETF holdings disclosure for
an effective date and source. It stores provenance, fetch time, disclosed total
weight and row count. `etf_constituent_position` stores constituent identifiers,
names, disclosed weights and optional ranks. The snapshot/date/source key and
per-snapshot constituent identifier are unique; both tables cascade from the
ETF master record.

## M11 decision profile

`decision_profile` is a singleton table whose primary key is constrained to
`id = 1`. It stores the public site's fixed monthly after-tax target, analysis
and history windows, nullable cash-deduction assumption and TWD currency.

`etf_daily_close` stores official positive close prices by ETF, trade date and
source. The existing performance Pipeline upserts every downloaded TWSE daily
record before portfolio use.

`manual_holding` uses `etf_code` as its primary key and foreign key to
`etf_master`. Units must be a positive integer. `unit_price`,
`price_as_of_date` and `price_source_id` are copied from the latest stored
official close by the batch API and remain `NULL` together when unavailable.
Deleting an ETF master row cascades only its local price and holding rows.

`decision_record` is an append-only M11-4 snapshot table. It stores candidate
identity, analysis status, stable outcome and canonical JSON for the original
request, complete analysis, rationale, exclusions, alternatives and risk
notes. Candidate identity is intentionally copied rather than foreign-keyed so
a historical record remains readable if ETF master data later changes.

## Database

Development database:

```text
SQLite
database/tw_etf.db
UTF-8
foreign_keys = ON
```

Application connections use
`backend.app.database.connection.get_connection` and return `sqlite3.Row`.

## Initialization and upgrades

Run from the project root:

```powershell
python -m backend.app.database.init_db
```

Initialization executes `backend/app/database/schema.sql` and then runs the
idempotent upgrade sequence:

1. `migrate_performance_metric`
2. `migrate_dividend_component_basis`
3. `migrate_dividend_source_document`
4. `migrate_dividend_review_queue`
5. `migrate_dividend_summary_metric`
6. `migrate_manual_holding_market_price`

This order supports both a fresh database and databases created by earlier
milestones. Initialization does not delete user data.

## Tables

### `etf_master`

Primary key:

```text
code
```

Main fields:

- `name`
- `is_active`
- `is_bond`
- `listing_date`
- `fund_size`
- `expense_ratio`

Deleting an ETF cascades to its performance and dividend history.

### `import_batch`

Tracks Pipeline execution:

- Running, success or failed state
- Raw, accepted, rejected, inserted and updated counts
- Checksums and artifact paths
- Completion timestamp and error message

### `etf_performance`

Uniqueness:

```text
etf_code
+ as_of_date
+ period_code
+ metric_code
+ source_id
```

`metric_code` accepts:

```text
PRICE_RETURN
TOTAL_RETURN
NAV_RETURN
```

### `etf_daily_close`

Uniqueness:

```text
etf_code + trade_date + source_id
```

Close prices are positive and retain the official source identifier.

Daily-close upserts count distinct `(etf_code, trade_date, source_id)` input
keys; the last record for a repeated key wins. An existing key counts as an
update even when its price is unchanged. Existing-key counts use batches of
at most 300 keys and indexed lookups rather than loading the historical table.
Counting and writing share a `BEGIN IMMEDIATE` transaction so another writer
cannot invalidate the summary between the read and write. This reserves the
SQLite writer slot earlier; lock contention follows the connection's existing
timeout behavior. Any failure rolls back the entire batch. Empty input returns
zero counts without opening a database. Price storage and missing-data semantics
are unchanged.

### `etf_dividend`

Uniqueness:

```text
source_id + source_event_id
```

The table requires at least one event date and prevents a payment date earlier
than the ex-dividend date.

### `etf_dividend_component`

Uniqueness:

```text
dividend_id
+ component_basis
+ component_code
+ source_id
```

`component_basis` accepts `ESTIMATED` or `ACTUAL`. At least one of
`amount_per_unit` and `ratio_pct` is required. Ratios are constrained to
0–100.

Deleting the parent dividend event cascades to its components.

### `etf_dividend_summary_metric`

Stores one nullable, traceable summary record per dividend event:

```text
distribution_period + distribution_period_source_id
yield_pct + yield_basis + yield_source_id
reference_trade_date + reference_close_price
```

Official distribution periods accept only `YYYYQ1`–`YYYYQ4`. `yield_basis`
accepts `OFFICIAL` or `CALCULATED`. Calculated yields require a reference trade
date and positive close; official yields prohibit those fallback fields.
Deleting the parent dividend event cascades to this row.

### `dividend_source_document`

Stores official-document versions and parsing results.

Unique keys:

```text
source_id + source_document_id + version_number
source_id + source_document_id + checksum_sha256
```

Parse states:

```text
downloaded
parsed
rejected
failed
```

### `dividend_source_review_queue`

Uniqueness:

```text
dividend_id + issue_type
```

The table references `etf_dividend` and optionally the source document that
resolved the issue.

## Expected table set after M8

```text
etf_master
import_batch
etf_performance
etf_dividend
etf_dividend_component
dividend_source_document
dividend_source_review_queue
```

## Verification

Run automated schema and Migration tests:

```powershell
python -m unittest `
    tests.test_database `
    tests.test_analysis_schema `
    tests.test_performance_metric_migration `
    tests.test_dividend_component_migration `
    tests.test_dividend_source_document_repository `
    tests.test_dividend_review_queue_migration `
    tests.test_m8_architecture_smoke `
    -v
```

Inspect the development database:

```powershell
python -m backend.app.database.check_schema
```

Automated tests use temporary databases and do not modify
`database/tw_etf.db`.
