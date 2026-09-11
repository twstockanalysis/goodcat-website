# API Specification

## Overview

### Independent non-distribution notices

`GET /api/v1/etfs/{code}` additionally returns `non_distribution_evidence`,
with `status` (`REVIEWED_NOTICES` or `NO_REVIEWED_NOTICE`) and dated `items`.
The detail-only response preserves period-specific official decisions separately
from paid dividend history. Empty evidence is not zero; present evidence is not
a permanent fund status. List/comparison and planner responses are unchanged.
See [the non-distribution contract](NON_DISTRIBUTION_CONTRACT.md).

### Annual expense provenance

ETF list and detail responses add nullable `annual_expense`, containing the
selected completed reporting year, decimal percentage (JSON string), historical
total-expense basis, issuer/product identity and document provenance. When
present, the existing numeric `expense_ratio` reflects this same percentage.
Selection uses publication date no later than today; old databases and legacy
values remain supported. Consumers must display the year and historical basis,
not describe this value as a current contractual fee. See
[the annual expense contract](ANNUAL_EXPENSE_CONTRACT.md) for all fields and
missing/zero/selection rules. There is no public expense-write endpoint.

Framework:

```text
FastAPI
```

Development base URL:

```text
http://127.0.0.1:8000
```

Interactive OpenAPI documentation:

```text
http://127.0.0.1:8000/docs
```

## System

```http
GET /
GET /health
```

`GET /health` returns:

```json
{
  "status": "healthy"
}
```

### System overview

```http
GET /api/v1/system/overview
```

The homepage uses this single read-only endpoint for:

```text
ETF totals and classifications
latest successful ETF-master import time
PRICE_RETURN coverage for 1M, 3M, 6M and 1Y
latest performance as-of date
dividend-event and ETF counts
ACTUAL, 76W and source-document coverage
latest dividend and ACTUAL source-document dates
five most recent import batches
```

Coverage percentages are `null` when the denominator is zero. Missing dates
remain `null`; the API does not substitute the current date.

## Public cash-flow planning baseline

V5-4 allocation-result plans preserve every submitted existing ETF and may add
at most five ETF codes per plan. Complete, materially distinct results use the
`資金精簡方案`, `穩定均衡方案` and `分散防護方案` labels. The planning grade is a
post-feasibility assessment boundary; no public grade is emitted until its
formula and thresholds are explicitly accepted and replay-tested.

```http
POST /api/v1/allocation-plans/baseline
```

V3-1 accepts a fixed TWD cash target for each selected month, one or more
months, a one-to-ten-year dividend-history window, a generic cash-deduction
percentage and zero to 500 unique existing ETF holdings. Each supplied holding
uses a positive whole-share quantity. The endpoint is public and stateless: it
does not require `X-Owner-Token`, does not update the single-user profile and
does not connect to a broker.

The response always returns January through December in order. It uses the
latest stored official close for current value and actual dividend payment
dates for the historical monthly cash baseline. A known no-event month is
zero; a holding with missing price, unusable payment data or incompatible
currencies keeps the dependent value `null` and returns explicit issues.

This endpoint does not yet select ETFs or recommend additional shares. Its
`AUTO_ALLOCATION_PENDING` next step reserves that boundary for V3-2 and V3-3.
Raw ETF-quality scores and assessment-confidence fields are not part of the
public response.

### Full-market eligibility index

```http
POST /api/v1/allocation-plans/eligibility-index
```

V3-2 applies fixed server-side product, reference-price, completeness,
freshness, payment stability, after-tax cash, total-return, downside,
composition and portfolio-overlap gates to every ETF in the master. Public
requests cannot override these thresholds.

The response includes the complete code-ordered universe, eligible/excluded
counts, source dates, stable payment months, ACTUAL versus estimated component
basis, overlap state, stable reasons and a reproducible `sha256:` snapshot ID.
Allocation-dependent concentration is returned as a mandatory V3-3 constraint.

The server retains a deterministic quality score and twelve Decimal-safe
cash-per-share values only in its internal index for the next solver stage.
V4-1 adds a nested `historical_quality_grade` to each public candidate. It
contains only a versioned `A+` through `F` grade or `UNRATED`, short evidence
and missing-data reasons. The complete market snapshot must pass minimum
sample, coverage and score-saturation gates before any letter is published.
Raw quality scores, components, internal ranks and confidence labels remain
absent. The endpoint remains stateless and requires no owner token.

### Public historical-quality grade lookup

```http
GET /api/v1/etfs/historical-quality-grades?codes=0050,0056
```

V4-5 lets public search, ranking, detail and comparison pages request one to
100 ETF grades in input order. The server builds the same full-market V4-1
catalog used by allocation eligibility and applies the same market-wide
publication gate. Each item contains only `etf_code` and the public-safe
`historical_quality_grade`; raw scores, score components, ranks and confidence
fields are never serialized. Unknown codes return `404`, invalid or oversized
requests return `422`, and the endpoint is read-only and stateless.

### Allocation results and long-term scenarios

```http
POST /api/v1/allocation-plans/allocation-results
POST /api/v1/allocation-plans/long-term-scenarios
POST /api/v1/allocation-plans/portfolio-projections
```

The allocation endpoint returns one to three distinct
`RECOMMENDED`, `BALANCED` and `FOCUSED` whole-share configurations. Every plan
includes the required additional capital, selected-month cash and shortfall,
resulting holdings, assumptions and risks. It returns fewer plans rather than
fabricating duplicate alternatives.

For #137, each strategy drives its own feasibility-first bounded search, not
only a final selection from capital-first results. Balanced and diversified
searches may refine an already complete plan toward their respective cash-flow
spread or resulting-position concentration objectives. No 1% or other minimum
improvement filter hides a distinct configuration. Differences may be small;
the quantities, required capital and modeled cash remain the comparison facts,
not proof of material benefit. The public request/response shape is unchanged.

For #139, cash-target allocation requests additionally accept optional
`max_additional_capital_twd` (TWD, finite nonnegative decimal, at most two decimal
places and 16 integer digits). Omitted/null means no ceiling; zero permits no
new investment. Existing holdings and their cash remain included without using
this allowance. Each nested result echoes the value in `assumptions`.

All three strategy searches enforce the ceiling during expansion/refinement,
on both exact cost and the sum of per-ETF costs rounded to cents. No automatic
ceiling or improvement filter is introduced. A capped incomplete search returns
`PARTIAL` and `NO_COMPLETE_PLAN_WITHIN_CAP`, with explicit remaining shortfalls;
it is not a normal TARGET_MET result or proof that no feasible plan exists.
Missing input facts and no eligible candidates retain their existing separate
statuses. The current zero transaction-cost assumption still applies; the cap
is not a promise of actual broker execution cost. Market-evidence snapshot IDs
remain independent of the ceiling. Public form integration is separate V5-5 work.

The nested integer result identifies methodology
`BOUNDED_COMPLETE_PORTFOLIO_V5_4`. Cash-target feasibility is searched before
quality or risk evidence, uses at most five added ETF codes and reports
`BOUNDED_BEST_EFFORT` whenever non-zero shares are required. Its assumptions
retain the historical concentration comparison value while explicitly setting
`concentration_limit_enforced=false`; the solver does not add capital merely to
force every position below that value. Search pruning is disclosed through the
`search_explored_states`, `search_truncated` and `V5_4_BOUNDED_SEARCH` evidence
and is never presented as a global minimum.

Each added ETF carries the same public-safe `historical_quality_grade`. This
grade does not change the integer solution and remains distinct from the
owner-goal allocation result.

The V3-5 endpoint includes the same allocation response and one aligned
long-term-evidence record per returned strategy. Historical portfolio evidence
uses fixed resulting shares, compatible common official close dates, actual
TWD payment-date distributions and the request's generic cash-deduction rate.
It returns the maximum compatible history plus 3Y, 5Y and 10Y windows; a window
without enough data remains `UNAVAILABLE`.

Historical evidence uses raw official closes and a no-reinvestment cash policy.
It is an estimate, not an adjusted official total-return index, because ETF
split and reverse-split adjustments are not yet available. Ten-year scenarios
are produced only with at least two complete one-year observations. Their
conservative, base and optimistic annual assumptions are the 25th, 50th and
75th percentiles of those observations and are shown as a compounded index
starting at 100, not as a cash forecast.

The V3-6 endpoint nests the V3-5 response and adds one aligned portfolio-tax
projection per returned strategy. It accepts a 1-to-20-year horizon, one of two
dividend-tax methods, explicit tax-rate assumptions, remaining dividend-credit
cap, supplementary-premium exemption and custom reinvestment percentage. Each
available plan contains three market bands and four distribution-use results,
with annual points, ending holding value, usable cash, reinvested cash,
estimated individual income tax and estimated supplementary NHI.

Forward market returns are gross before portfolio tax. Official versus
estimated component provenance is preserved; missing positive-cash component
data makes the plan unavailable. Official `76W` and estimated realized capital
gain are excluded from the modeled personal dividend tax and premium base, and
estimated capital gain is never relabeled as official `76W`. Reinvested cash is
an internal transfer and is not counted twice in after-tax return.

All three endpoints are public and stateless. They do not expose internal ETF-quality
scores or assessment-confidence fields.

### Target-free investable-budget allocation (#141)

```http
POST /api/v1/allocation-plans/budget-allocation
```

This additive, public, stateless endpoint returns one budget-foundation plan.
It does not change cash-target allocation or expose new strategy/grade formulas.
Example request (the amount is illustrative, not a default):

```json
{
  "investable_budget_twd": "5000.00",
  "selected_months": [1, 4, 7, 10],
  "existing_holdings": [{"etf_code": "0050", "held_units": 10}],
  "history_years": 3,
  "cash_deduction_rate_pct": "0",
  "currency": "TWD"
}
```

Budget is required, finite, nonnegative, at most two decimal places and 16
integer digits; null is invalid and zero means no new investment. Months are
required (1-12), deduplicated and sorted. Existing holding inputs and bounds,
history years (1-10, default 3), cash-deduction rate (0-100, default 0) and TWD
currency follow the baseline conventions. Duplicate normalized holding codes
are invalid. Cash-target fields, `target_months`, the optional cash-target cap,
and other extra fields are rejected with sanitized HTTP 422 errors. Clients
must not pass a budget in `target_after_tax_cash_twd`.

The response has methodology `BOUNDED_BUDGET_PORTFOLIO_V5_4` and objective
`MINIMUM_THEN_TOTAL_MONTH_CASH`. It reports selected-month current, added and
resulting historical modeled cash without target, shortfall or TARGET_MET
fields. Search first favors the lowest resulting selected-month cash, then
total selected-month cash, then lower spread, budget use and complexity using
the existing budget-foundation ordering. This is not a yield or risk ranking.

`used_budget_twd` is the sum of per-ETF modeled costs rounded HALF_UP to cents;
`remaining_budget_twd` is submitted budget minus that sum. Both exact investment
and displayed costs are checked during search. Existing holdings consume no new
capital and remain included; at most five codes may receive added whole shares.
The modeled transaction-cost rate remains zero, not a broker-cost guarantee.

| Status | Meaning |
| --- | --- |
| `AVAILABLE` | Search selected positive additions within budget; not a cash-target success or guaranteed distribution. |
| `NO_ADDITIONS` | Zero budget, or no budget-feasible selected-month cash addition was found. Read the issue code for the reason. |
| `NO_ELIGIBLE_ALLOCATION` | Positive budget but no candidate passed the unchanged gates. Existing facts are still returned. |
| `UNAVAILABLE` | Existing selected-month cash or holding value is missing. No additions are calculated, even at zero budget. |

`existing_holdings` always retains submitted holding facts, including nullable
missing facts. For UNAVAILABLE, unknown monthly cash remains null and
`resulting_holdings` is null (no computed portfolio); for the other statuses it
contains the preserved original holdings plus additions. Known cash can remain
visible when price, rather than cash, is missing.

`candidate_evidence` contains all public-safe market eligibility items and
their exclusion/trade-off reasons, source dates, ACTUAL/estimated basis and
historical quality-grade availability. `snapshot_id` identifies that shared
market evidence and is independent of budget; it is not a result hash. Internal
scores are not serialized and do not order the budget search.

Assumptions name the historical same-calendar-month basis, history years,
deduction rate, zero modeled transaction cost, no enforced concentration cap,
five added codes, beam width 64 and a 20,000-state ceiling. Positive-budget
search with eligible candidates reports `BOUNDED_BEST_EFFORT` and
`V5_4_BOUNDED_BUDGET_SEARCH`, even when `search_truncated` is false: batch
quantities are heuristic, not exhaustive. Other states use `NOT_APPLICABLE`.
No global maximum, personal suitability, new planning grade or public launch
claim follows from a result. Frontend and multi-card budget integration remain
separate work.

Existing public middleware still enforces request sizes and rate limits;
unknown holdings return HTTP 404 and unexpected failures use sanitized HTTP 500.
No request persistence, owner credential requirement or broker connection is
introduced. This endpoint does not extend long-term/projection endpoints to
budget requests.

## Public ETF price history

```http
GET /api/v1/etfs/{code}/price-history?limit=260
```

The detail page uses this read-only endpoint for its price trend chart. It
returns the most recent 2 to 1,250 saved official daily closes in ascending
trade-date order. Each item includes only `trade_date`, positive `close_price`
and `source_id`; missing dates are not synthesized and missing prices are never
replaced with zero. An unknown ETF returns `404` and an invalid limit returns
`422`.

## Single-user decision profile

```http
GET /api/v1/decision-profile
GET /api/v1/decision-profile/current-holding-analysis
POST /api/v1/decision-profile/candidate-analysis/{etf_code}
POST /api/v1/decision-profile/candidate-analysis/{etf_code}/decision-records
GET /api/v1/decision-profile/decision-records
GET /api/v1/decision-profile/decision-records/{record_id}
GET /api/v1/decision-profile/decision-records/{record_id}/export.xlsx
PUT /api/v1/decision-profile/conditions
PUT /api/v1/decision-profile/holdings
PUT /api/v1/decision-profile/holdings/{etf_code}
DELETE /api/v1/decision-profile/holdings/{etf_code}
```

M11-1 exposes one `SINGLE_USER` profile and always returns
`broker_connected=false`. It does not create accounts, authenticate brokerage
connections or send orders.

Conditions persist the monthly after-tax cash target, analysis years, history
years and a nullable generic cash-deduction percentage. The batch holdings
`PUT` accepts `0-N` unique `{etf_code, held_units}` rows and atomically replaces
the saved set. It derives price, trade date and source from the latest stored
official close. Missing close data remains `null` and blocks dependent output.
The item `PUT` and `DELETE` remain compatibility operations. Missing deductions
remain `null`, while a formal `0%` deduction remains numerical zero.

Every operation in this section requires `X-Owner-Token`. Private responses,
including errors and Excel exports, return `Cache-Control: no-store, private`,
`Pragma: no-cache` and `Vary: X-Owner-Token`. Missing or wrong credentials
return `401`; a missing or invalid server token configuration returns `503`.
The batch holdings request accepts at most 500 rows.

The M11-2 current-holding endpoint is read-only. It returns per-ETF historical
facts, total saved holding value and one portfolio-level M10 target-analysis
result. The monthly target is applied once to the portfolio. Missing fixed
conditions or holdings return `UNAVAILABLE`; missing market data or assumptions
return `PARTIAL` with `null` results and explicit unavailable fields.

The base `POST /api/v1/etfs/{code}/target-analysis` response includes
source-dated principal-risk warnings. A warning may include `as_of_date`,
`source_id` and a typed `evidence` object containing the exact threshold facts
used by the deterministic rule. Missing facts do not produce a safe warning
result. Multi-year price returns are annualized before scenario projection.

The M11-3 candidate endpoint accepts proposed positive whole units, a positive
TWD reference price, optional holding overlap and the existing M10-5 rules. It
returns current and proposed portfolio snapshots, calculable deltas and the
M10-5 selected/rejected candidate result with stable reasons. The scenario is
read-only and never updates the saved holding.

The same response includes `explainable_assessment` when eligibility can be
evaluated. Its deterministic `DETERMINISTIC_MULTI_SCORE_V2` methodology returns
an ETF quality score, a current-portfolio fit score and ordered evidence
factors. Total return is the largest quality component; dividend cash, official
ACTUAL 76W and overlap cannot independently determine a high score. Missing
official 76W remains unscored. User-entered overlap remains a risk assumption
and is excluded from scoring until automatic constituent data is available.
The UI exposes only the final portfolio-fit score. ETF quality and its
components remain backend data, and no separate confidence label is shown.
The response remains free of buy/sell signals, performance forecasts and gate
overrides.

M11-4 reruns the candidate analysis on the server before saving an immutable
record. Records preserve the original request, full analysis snapshot,
rationale, exclusions, deterministic alternatives and risk notes. The record
API has no update or delete operation. Excel export uses the saved snapshot and
returns a five-sheet `.xlsx`; later profile or market-data changes do not alter
existing records. Unknown record IDs return `404`.

## ETF master data

### List ETFs

```http
GET /api/v1/etfs
```

Query parameters:

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `keyword` | string or null | null | ETF code or name |
| `is_active` | boolean or null | null | Active/passive filter |
| `is_bond` | boolean or null | null | Bond/non-bond filter |
| `limit` | integer | 20 | 1–100 |
| `offset` | integer | 0 | Non-negative |

Response fields:

```text
items
total
limit
offset
```

### ETF detail

```http
GET /api/v1/etfs/{code}
```

ETF codes are normalized to uppercase. Missing ETFs return `404`.

### ETF comparison

```http
GET /api/v1/etfs/comparison?codes=0050,0056
```

The endpoint accepts 2–4 unique ETF codes and preserves request order. It returns:

```text
ETF master identity and classifications
latest available 1M, 3M, 6M and 1Y PRICE_RETURN records
dividend-event count and latest event summary
ACTUAL 76W record count and latest/average ratio
per-ETF source and freshness profile
five-section data-completeness explanation
```

One code or more than four codes returns `422`. Missing ETF codes return `404`.
Missing performance or ACTUAL 76W values remain `null` or absent; formal `76W = 0%` remains numerical zero.

### ETF data profile

```http
GET /api/v1/etfs/{code}/data-profile
```

Returns the detail page's traceable data profile:

```text
ETF-master source and latest successful dataset import
PRICE_RETURN source, available periods and latest as-of date
dividend-event sources, count and latest event date
ACTUAL composition sources, 76W count and latest official-document date
```

Missing dates remain `null`. An ETF without performance, dividend or ACTUAL
records returns zero counts and empty source lists rather than fabricated dates
or percentages.

## Performance

### Ranking

```http
GET /api/v1/performance/ranking
```

Query parameters:

| Parameter | Type | Default |
| --- | --- | --- |
| `period` | `1M`, `3M`, `6M`, `1Y` | `6M` |
| `metric` | `PRICE_RETURN`, `TOTAL_RETURN`, `NAV_RETURN` | `PRICE_RETURN` |
| `is_active` | boolean or null | null |
| `is_bond` | boolean or null | false |
| `limit` | integer | 20 |
| `offset` | integer | 0 |

Ranking is calculated within one period and one metric. Global rank numbers
include the pagination offset.

### Multi-period ranking

```http
GET /api/v1/performance/multi-period-ranking
```

Query parameters match the existing ranking filters, with `sort_period`
replacing `period`. The default `sort_period` is `6M`.

The selected period controls ranking order only. Every item also returns the
latest available `1M`, `3M`, `6M` and `1Y` records in `performance_items`.
A missing period is absent and is never represented as `0%`.

The original single-period ranking endpoint remains available for compatible
clients.

### Single ETF performance

```http
GET /api/v1/etfs/{code}/performance
```

Returns the latest available records per supported period for one metric.
Missing periods are absent rather than represented as zero.

## Dividends

### ETF dividend history

```http
GET /api/v1/etfs/{code}/dividends
```

Supports `limit` and `offset`. Missing ETFs return `404`; an ETF without
dividend events returns an empty list.

Each event also returns nullable summary fields:

```text
distribution_period
distribution_period_source_id
yield_pct
yield_basis
yield_source_id
reference_trade_date
reference_close_price
```

`distribution_period` accepts only an official `YYYYQ1`–`YYYYQ4` value.

### Tax and reinvestment scenarios

```text
POST /api/v1/etfs/{code}/tax-reinvestment-scenarios
```

The request supplies holdings, cash target, projection horizon, payment-count
assumption, custom reinvestment percentage and a versioned Taiwan-individual
tax rule. The server supplies historical distribution and price-return inputs
and selects the newest complete, paid, fresh ACTUAL component event, or a
complete paid and fresh estimated fallback when no qualifying ACTUAL event
is available. Freshness uses the existing 18-calendar-month boundary
(anniversary inclusive); neither future payments nor stale mixes qualify.
The additive `warnings: string[]` response field reports when a stale
historical ACTUAL mix was bypassed in favor of a fresh estimate. An empty
list is the default. The detail-page tax renderer displays these warnings.

The response keeps `historical_facts` separate from `calculation`, returns all
four reinvestment policies, echoes `projection_years`, and includes usable cash,
reinvested cash, ending units, ending value, modeled income tax, supplementary
premium and after-tax total return. The explicit horizon lets clients warn when
a 1Y historical return is mechanically applied to a longer scenario. `PARTIAL`
means one or more outputs remain unavailable; missing component data or tax
assumptions are not converted to zero. Estimated components remain labeled as
fallbacks and are not relabeled as official tax codes.
`yield_basis` is `OFFICIAL` or `CALCULATED`. A calculated value includes the
previous trading date and close; an official value never carries a calculated
price reference.

### Monthly-payment combination

```text
POST /api/v1/etfs/{code}/monthly-payment-combination
```

The path ETF is the visible base anchor. The request supplies one to three
candidate codes, each candidate's explicit unit-price and allocation
assumptions, an optional holding-overlap estimate, lookback years, cash
deduction rate and eligibility rules. A candidate cannot repeat the base ETF.

The server derives payment-month recurrence and cash distributions from actual
`payment_date` records and uses the latest `1M`, `3M`, `6M` and `1Y`
`PRICE_RETURN` records. It applies data completeness, freshness, distribution
stability, after-tax cash, total-return, downside, overlap and concentration
gates before considering payment-month coverage. Active/passive and bond/non-
bond fields are returned as attributes, not quality scores.

Every selected or rejected candidate contains machine-readable and plain-
language reasons. Missing holding overlap remains `null` and produces a
trade-off (or exclusion when explicitly required); formal zero remains zero.
The response keeps historical facts separate from cash-deduction assumptions
and labels the combination as a scenario rather than a guarantee.

### Actual 76W history and composite capital-gain analysis

```http
GET /api/v1/etfs/{code}/dividends/76w
```

The existing `actual_76w_*` fields and `items` still count only
`component_basis=ACTUAL` plus `component_code=76W`. Missing formal data keeps
those ratios `null`, not zero.

The same response also exposes `analysis_*` and `*_realized_gain_*` fields.
For each dividend event, the shared composite selector uses one complete
`ACTUAL` mix first; when it is unavailable, it uses one complete e添富 mix as
`ESTIMATED_FALLBACK`. The analysis reads `76W` from an ACTUAL mix or
`EST_REALIZED_CAPITAL_GAIN` from a fallback mix without renaming either code or
mixing the two bases within one event.

Historical per-event selection and formal coverage above are not subject to
the planning freshness filter. Market eligibility and portfolio projection
use the same freshness-aware planning selector as tax scenarios and expose
`STALE_ACTUAL_COMPONENTS_FALLBACK` as a tradeoff/issue with the historical
ACTUAL date. If no fresh complete paid mix exists, planning remains unavailable;
old ACTUAL and formal `76W` facts remain present in the historical endpoints.

### Dividend event detail

```http
GET /api/v1/dividends/{dividend_id}
```

Returns one dividend event and all raw component records. It also returns
`selected_component_basis` and `selected_components`, produced by the shared
composite-data selector. A complete `ACTUAL` event whose ratios total about
100% is preferred; otherwise one complete e添富 event is returned as
`ESTIMATED_FALLBACK`. Rows from the two bases are never mixed.

### Filter dividend components

```http
GET /api/v1/dividends/{dividend_id}/components
```

Optional query filters:

```text
component_basis
component_code
source_id
```

## Dividend data quality

### Coverage

```http
GET /api/v1/data-quality/dividends/actual-coverage
```

Optional `etf_code` limits the summary to one existing ETF.

### Review queue

```http
GET /api/v1/data-quality/dividends/review-queue
```

Optional query filters:

```text
status
etf_code
issue_type
limit
offset
```

### Review queue item

```http
GET /api/v1/data-quality/dividends/review-queue/{queue_id}
```

The M8 data-quality API is read-only.

## Status behavior

```text
200  successful response
400  malformed request framing such as invalid Content-Length
401  missing or incorrect owner credential on a private endpoint
413  request body exceeds 64 KiB
414  path plus query exceeds 8 KiB
404  ETF, dividend event or queue item not found
422  invalid path, query parameter or JSON body
431  request headers exceed 32 KiB
500  sanitized unexpected server error without exception details
503  owner-only API is not safely configured
```

Validation errors return only stable error types and locations; submitted input
values are not reflected. Frontend API transport does not follow redirects.

All API database access is injected through `get_database_path`, allowing tests
to use isolated temporary SQLite databases.

## ETF lookup error boundary

The allocation-plan endpoints and ETF comparison endpoint return HTTP 404
only when an explicit `ETFNotFoundError` identifies missing ETF records.
The response remains `{"detail": "找不到 ETF：<codes>"}`, with multiple codes
separated by comma and space. Domain failures are translated by a shared
FastAPI exception handler. Unexpected `KeyError`, `IndexError`, and generic
`LookupError` failures use the existing sanitized HTTP 500 response
`{"detail": "Internal server error"}` rather than exposing internal fields
as missing ETF codes. Request validation and successful responses are unchanged.

Database choice: retain SQLite for the current single-host deployment.
This error-boundary change does not migrate storage, alter schemas, enable WAL,
or change financial calculations.
