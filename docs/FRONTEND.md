# Streamlit Frontend

## Shared numeric display

`frontend/ui/formatters.py` centralizes number, percentage, and amount display.
`None` uses the caller's missing-data label; finite zero remains a number.
Non-finite values (`NaN`, positive/negative infinity), invalid input, and
overflow during float conversion use the invalid-data label without adding
currency or percentage suffixes. Trailing-zero trimming applies only after
the decimal point: an integer display of `100` must remain `100`, never `1`.
Amounts (including prices, dividends, fund size, cash flow, and chart labels)
use integer display with grouping. Currency labels map ISO `TWD` to `NTD`;
API requests and responses retain `TWD`. Input formatting preserves numeric
values, following [Streamlit number_input guidance](https://docs.streamlit.io/develop/api-reference/widgets/st.number_input).
Percentages and unit counts retain their existing precision. Fractional amounts
may display as zero after rounding; missing amounts still use missing labels.
These rules affect display only; they do not change financial calculations
or ACTUAL, estimated, and formal `76W` data semantics.

## M11 decision profile and current-holding analysis page

The public navigation includes `我的條件與持有部位`. The page reads and writes
only through FastAPI and states that it is a single-user, manual-entry flow
with no broker connection. A native form saves fixed analysis conditions. The
holding section starts with zero rows and uses a dynamic two-column editor for
`股票代號` and `股數`; native controls add or remove rows before one batch save.
A static table shows the system-derived latest stored official close, date and
source as read-only context. Missing prices display as unavailable, never zero.

M11-2 adds an explicit `分析目前持倉` action on the same page. Native metric
cards show total saved value, historical annual gross cash, modeled after-tax
cash and target coverage. A static table keeps each ETF's historical cash and
annualized price-return facts visible. Missing results display `無法計算`, and
the page labels the output as a no-reinvestment scenario rather than a
recommendation or guarantee.

M11-3 adds a candidate ETF form beneath the saved portfolio analysis. It asks
for proposed units, a TWD reference price, optional overlap and whether payment-
month coverage is enabled. The result shows native before/after metrics, a
small static comparison table and every reused M10-5 inclusion, exclusion or
trade-off reason. Submitting the form does not save the candidate as a holding.

M11-4 adds an explicit `保存為決策紀錄` action after a candidate comparison.
The backend recomputes the submitted scenario and returns an immutable record.
The page lists record summaries, lets the user prepare one Excel file on
demand, and then exposes a native `st.download_button` with no download rerun.
The UI does not expose record overwrite or deletion.

## Architecture

```text
Browser
-> Streamlit page
-> frontend/api_client.py compatibility facade
-> frontend/api domain module
-> frontend/api/transport.py
-> FastAPI
-> Repository
-> SQLite
```

The frontend never reads SQLite directly.

`frontend/api_client.py` preserves the original public imports and test mock
path. New implementation belongs in focused modules under `frontend/api/`:

| Module | Responsibility |
| --- | --- |
| `errors.py` | Client exception types |
| `validators.py` | Shared response-field validation |
| `normalizers.py` | Query and filter normalization |
| `transport.py` | HTTP JSON/binary transport and errors |
| `health.py` | FastAPI health check |
| `etfs.py` | ETF list and detail |
| `performance.py` | ETF performance and rankings |
| `dividends.py` | Dividend events, components and monthly income |
| `dividend_quality.py` | ACTUAL/76W coverage and review queue |
| `system_overview.py` | Owner-only website administration overview |
| `data_profile.py` | ETF source coverage and freshness |
| `comparison.py` | Multi-ETF comparison |
| `decision_profile.py` | Conditions, holdings, analyses, records and export |

API domain modules may depend on shared errors, validators, normalizers and
transport, but must not import the compatibility facade. Existing callers may
continue importing from `frontend.api_client` during migration.

## Local startup

FastAPI terminal:

```powershell
python -m uvicorn backend.app.main:app --reload
```

Streamlit terminal:

```powershell
python -m streamlit run frontend/app.py
```

Default URLs:

```text
FastAPI   http://127.0.0.1:8000
Streamlit http://localhost:8501
```

Override the backend URL with:

```text
TW_ETF_API_URL
```

## Navigation and URL state

Page metadata is centralized in:

```text
frontend/navigation.py
```

Public pages:

```text
/
cash-flow-planner
etf-search
performance-ranking
etf-comparison
dividend-data-quality
```

Owner-unlocked pages:

```text
decision-profile
admin-overview
```

Hidden page:

```text
etf-detail
```

ETF search URLs preserve:

```text
keyword
active
bond
page
page_size
```

Performance ranking URLs preserve:

```text
period
active
bond
page
page_size
```

ETF detail URLs include `code`, the source page in `from`, and the source
page's canonical query state. Returning from detail therefore restores the
search or ranking context.

Invalid query values are normalized to safe defaults. Missing and zero values
retain their existing domain semantics.

Shared UI utilities are defined in:

```text
frontend/ui/formatters.py
frontend/ui/components.py
frontend/ui/states.py
```

They provide:

- Percentage, number, amount, date and datetime formatting
- Active/passive and bond/non-bond labels
- Full-row ETF detail links and pagination controls
- Loading, empty, not-found, warning and API-error presentation

Page modules keep small domain-specific wrappers when their missing-value text
must differ. All wrappers delegate numerical formatting to the shared layer, so
formal zero remains numerical zero while missing data remains unavailable.

Responsive typography is centralized in:

```text
frontend/ui/theme.py
```

It reduces oversized headings and metrics, allows metric values and page-link
labels to wrap instead of using ellipsis, and uses smaller sidebar text when
the navigation panel is open.

All frontend forms disable Enter-key submission. Users must choose a visible
submit action, so focused number and text inputs do not show or trigger the
`Press Enter to submit form` behavior.

## Pages

### Home

It shows:

- The `GoodCat 股利喵` brand and approved slogan
- One prominent link to the public cash-flow planner
- Secondary links to ETF search, performance ranking, comparison and data quality
- A small source and decision-responsibility notice

The homepage does not request operational data.

### Dividend Planner

The public `cash-flow-planner` route is titled `股利試算`. Its primary form
asks, in order, for an integer target amount, one or more payment months, the
intended holding period and optional current holdings. Month selection uses
native pills, so all twelve months remain visible without dropdown keyboard
instructions.

The frontend automatically requests the longest supported ten-year dividend
lookback and applies no separate allocation-stage cash deduction. Portfolio tax
and supplementary-premium estimates are generated with the main result. Default
tax assumptions remain transparent and can be adjusted in a collapsed advanced
section.

### Website Administration

The owner-unlocked page reads:

```text
GET /api/v1/system/overview
```

It shows ETF, performance and dividend counts, ACTUAL and official 76W
coverage, source-document coverage, dataset freshness and recent import batch
errors. A manual refresh clears only the short frontend cache.

Missing dates display `尚未取得`. A zero-event coverage ratio displays
`尚無資料`, while a formally calculated zero remains `0.00%`.

### ETF Search

Supports:

- Code/name keyword search
- Active/passive filter
- Bond/non-bond filter
- Page size and pagination
- Fully clickable ETF rows

### Performance Ranking

Supports:

- 1M, 3M, 6M and 1Y sort periods
- Active/passive and bond filters
- Pagination and fully clickable rows
- One clearly displayed return value for the currently selected sort period

The default and preferred sort period is `6M`. Changing the sort period changes
both ranking order and the one period displayed in each row. Other periods
remain available through the selector and remain simultaneously visible on ETF
detail and comparison pages.

Each row follows:

```text
rank and ETF code
-> display name
-> selected-period return
-> selected-period as-of date
-> active/passive
-> bond/non-bond
```

Ranking display names remove a trailing `(原名：...)` or `（原名：...）`
annotation. The original database and API names remain unchanged.

Missing selected-period data displays `歷史資料不足`; it is not converted to
zero.

The page reads:

```text
GET /api/v1/performance/multi-period-ranking
```

The response keeps all four period records available without N+1 requests, while
the ranking presentation shows only the selected period.

### ETF Comparison

The public comparison page uses:

```text
/etf-comparison?codes=0050,0056
```

It accepts 2–4 unique ETF codes and compares:

- Management and asset classifications
- Listing date, fund size and expense ratio
- Independent 1M, 3M, 6M and 1Y `PRICE_RETURN` values
- Dividend-event count and latest distribution summary
- ACTUAL 76W availability, latest ratio and average ratio
- Five-section data completeness

The `codes` query parameter is canonical, ordered and deduplicated. Return-state parameters are namespaced with `return_`, allowing the page to return to ETF search, performance ranking or ETF detail without losing the source page state.

Missing periods display `歷史資料不足`. Missing ACTUAL 76W displays `尚未取得`; an official `76W = 0%` displays `0.00%`. Data completeness describes available data sections only and is not an investment score.

The detail page displays one `現金股利組成` table from the shared composite-data
selector. A complete formal composition is shown when available; otherwise a
complete e添富 composition is used. The page never displays both sets together
or combines their rows. When a selected component has a ratio but no amount,
the amount is derived from `dividend amount per unit × selected ratio`.

Tax and reinvestment, portfolio projection and market eligibility apply the
same selector. The API retains `ACTUAL` or `ESTIMATED_FALLBACK` provenance for
downstream calculations even though the compact public table omits technical
source columns.

### ETF Detail

The detail page is hidden from sidebar navigation and opened through:

```text
/etf-detail?code=0050
```

M9-4 uses one fixed decision-oriented section order:

```text
ETF identity and classifications
-> core data overview
-> market-price performance
-> dividend summary
-> actual 76W
-> dividend events and components
-> data sources and freshness
-> ETF comparison entry
```

The page keeps each secondary API call isolated. A performance, dividend,
ACTUAL 76W or data-profile failure does not remove the ETF
identity and other successfully loaded sections.

The expanded dividend summary shows:

- Latest event metrics
- A dual-axis trend of cash dividend and per-event yield
- Official distribution period, cash dividend, yield, ex-dividend date and payment date
- Yield provenance, including the reference trading date and close for calculated fallback values

Distribution periods are never inferred from the ex-dividend date. Missing
official periods display `—`. Official yield is preferred; a missing official
value may be calculated as cash dividend divided by the previous trading-day
close and is labeled as a fallback.

The monthly-income API remains available at:

```text
GET /api/v1/etfs/{code}/monthly-income?lookback_years=3
```

It still returns January through December and uses only `payment_date` to assign
a dividend event to a month. The ETF detail page does not currently request or
render this distribution.

Data sources and freshness come from:

```text
GET /api/v1/etfs/{code}/data-profile
```

The profile shows source IDs and display names, latest data dates, latest
successful import times and record counts. ETF-master import time is explicitly
labeled as dataset-level freshness. Missing dates display `尚未取得`; they are
not replaced with the current date.

The comparison entry is enabled and carries the current ETF plus the detail page return state into the public comparison page.

### Dividend Data Quality

Shows:

- Global ACTUAL, 76W and source-document coverage
- Single-ETF coverage
- Review-queue filters and pagination
- Read-only queue-item details

## Data semantics

Missing values are displayed as text such as:

```text
尚無資料
歷史資料不足
尚未取得可用的正式 76W 或替代資本利得組成資料
```

Missing values are not converted to numerical zero.

A formal `ACTUAL + 76W` record with a disclosed ratio of zero is displayed as
`0.00%` and remains covered data.

Estimated realized capital gains retain the label:

```text
EST_REALIZED_CAPITAL_GAIN
```

The ETF detail section `資本利得組成 (76W) 統計` uses the shared composite
selector per dividend event. It visibly reports ACTUAL and e添富 fallback event
counts; fallback capital gain is never presented as a formal 76W record.

They are not displayed or counted as official `76W`.

## Caching and refresh

Pages use short `st.cache_data` TTLs. Refresh buttons clear relevant frontend
cache entries. They do not run backend Pipelines; data Pipelines must be run
separately.

## Tests

Frontend and AppTest coverage:

```powershell
python -m unittest `
    tests.test_frontend_api_client `
    tests.test_frontend_etf_api_client `
    tests.test_frontend_performance_api_client `
    tests.test_frontend_dividend_api_client `
    tests.test_frontend_dividend_quality_api_client `
    tests.test_frontend_api_architecture `
    tests.test_frontend_dividend_ui `
    tests.test_frontend_dividend_quality_ui `
    tests.test_frontend_formatters `
    tests.test_frontend_components `
    tests.test_frontend_states `
    tests.test_streamlit_app `
    -v
```
