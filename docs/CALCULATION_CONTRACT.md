# Cash-flow and total-return calculation contract

## Purpose

M10-2 establishes a deterministic calculation boundary before user profiles,
recommendation scores, persistence or frontend analysis flows are introduced.

The contract separates three things that must not be treated as equivalent:

- cash distributions received by the investor
- change in the market value of the holding
- total gain or loss after taxes, premiums and costs

The first implementation is stateless. It does not populate the
`etf_performance.TOTAL_RETURN` metric and does not add a database table.

## Analysis modes

Every calculation declares exactly one mode:

| Mode | Meaning |
| --- | --- |
| `HISTORICAL_REPLAY` | Uses observed prices, distributions and costs within a completed period. |
| `SCENARIO_ESTIMATE` | Applies explicit assumptions to a defined future or hypothetical period. |

Historical facts and scenario assumptions cannot be combined without the
caller first labeling the result as a scenario estimate.

## Currency and units

- One calculation uses exactly one ISO 4217 currency.
- The first version performs no foreign-exchange conversion.
- All money, rates and quantities use `Decimal`; binary floating point is not
  accepted inside the calculation service.
- Percentage values use percentage points: `5` means 5%, not `0.05`.
- Intermediate values remain unrounded.
- Public money results are rounded to 2 decimal places with `ROUND_HALF_UP`.
- Public percentage results are rounded to 6 decimal places with
  `ROUND_HALF_UP`.
- A missing value remains `None`; it is never converted to formal zero.

## Date basis

- The analysis period is inclusive of `period_start` and `period_end`.
- Distribution cash is assigned by actual `PAYMENT_DATE`.
- Historical cash-flow, eligibility and allocation projections include only
  events whose `PAYMENT_DATE` is on or before the explicit analysis date.
  A future scheduled payment remains available as announcement evidence but
  cannot become paid history or anchor the historical lookback window.
- Beginning and ending holding values use actual `TRADE_DATE` observations.
- A caller cannot silently substitute announcement, ex-dividend or record date
  for payment date.
- A caller cannot combine values from different date windows without receiving
  a machine-readable unavailable reason.

## Fixed after-tax cash-flow target

The monthly target is a user condition. It remains fixed when available capital
changes.

```text
annual after-tax target
= monthly after-tax target * 12

after-tax usable cash
= gross distribution cash
- distribution tax
- supplementary premium
- other distribution costs

reference after-tax cash rate
= after-tax usable cash / reference capital

target coverage
= projected after-tax usable cash / annual after-tax target

required capital
= annual after-tax target / reference after-tax cash rate

funding shortfall
= max(required capital - available capital, 0)
```

The required-capital result is unavailable when reference capital, gross cash
or any modeled deduction is missing. It is also unavailable when the resulting
after-tax cash rate is zero or negative. A zero monthly target is a valid formal
zero and produces no funding shortfall; it must not be treated as missing.
For that formal-zero target, coverage is reported as `100%` and required
capital and funding shortfall are both `0`, even when no reference rate is
needed. Missing distribution inputs still leave after-tax usable cash
unavailable.

## Total-return ledger

The canonical ledger identity is:

```text
after-tax total gain or loss
= ending holding value
+ net withdrawn cash
- initial capital
- later external contributions
- externally paid costs not already reflected above

after-tax total-return rate
= after-tax total gain or loss / initial capital
```

`net withdrawn cash` contains cash that left the investment and was not
reinvested. Reinvested distributions remain inside ending holding value and are
not added again. Costs already reflected in ending value or net withdrawn cash
are not entered again as externally paid costs.

For a no-reinvestment breakdown, the equivalent identity is:

```text
market-value gain or loss
= ending holding value - initial capital

after-tax total gain or loss
= market-value gain or loss
+ gross distributions
- distribution tax
- supplementary premium
- transaction costs
- other externally paid costs
```

The calculator tests must reconcile these two identities for equivalent input.

## Pure calculator behavior

The first calculator service is deterministic and has no database, network or
clock dependency. It accepts only validated contract models and returns a
result model without mutating its input.

- `calculate_cash_flow_target` calculates the fixed after-tax cash target.
- `calculate_total_return` applies the canonical portfolio ledger identity.
- `calculate_no_reinvestment_total_return` applies the equivalent distribution
  breakdown and must reconcile with the canonical ledger for equivalent input.
- A negative after-tax usable cash amount remains visible, while coverage,
  required capital and funding shortfall remain unavailable.
- Zero or negative reference cash rates never enter a division operation.
- Missing values produce field-specific issues; formal zero values remain
  calculable wherever the denominator rules allow them.

## Scenario estimate

The scenario calculator is intentionally separate from historical replay. Its
input context must use `SCENARIO_ESTIMATE`, and every result retains the
`NO_REINVESTMENT` policy. It is an arithmetic projection, not a forecast or a
claim that distributions will continue.

```text
ending holding value
= initial capital * (1 + annual price return rate) ^ projection years

cumulative gross cash
= initial capital * annual gross cash rate * projection years

cumulative cash deductions
= cumulative gross cash * cash deduction rate

cumulative after-tax cash
= cumulative gross cash - cumulative cash deductions

after-tax total gain or loss
= ending holding value + cumulative after-tax cash - initial capital
```

The annual gross cash rate is applied to initial capital each year. Cash is not
reinvested, so it does not compound. Price return compounds only the holding
value. The first version accepts projection periods from 1 through 50 years,
cash deduction rates from 0% through 100%, and price return assumptions no
lower than -100%.

All five numeric assumptions must be explicit. If any one is missing, scenario
outputs remain unavailable with `MISSING_INPUT`; missing assumptions are never
silently replaced by zero. A formal zero assumption remains calculable. Zero
initial capital produces formal zero money results, but its percentage return
is unavailable with `NON_POSITIVE_INITIAL_CAPITAL`.

## Unavailable results

An unavailable numeric result is `None` and includes one or more stable reason
codes. Initial reason codes are:

| Reason | Meaning |
| --- | --- |
| `MISSING_INPUT` | A required source value or assumption is unavailable. |
| `MIXED_CURRENCY` | Inputs use more than one currency. |
| `DATE_BASIS_MISMATCH` | Inputs do not use the required period or date basis. |
| `NON_POSITIVE_INITIAL_CAPITAL` | A return rate has no positive denominator. |
| `NON_POSITIVE_AFTER_TAX_CASH_RATE` | Required capital cannot be inferred from the reference cash rate. |
| `NEGATIVE_AFTER_TAX_USABLE_CASH` | Modeled deductions exceed gross distribution cash. |

Formal zero remains a calculable value when the relevant formula allows zero.
Missing values, invalid denominators and mismatched data never receive a zero
result or a neutral score.

## M10-2 boundaries

M10-2 may add pure models, services, tests and documentation. It does not add:

- database schema or migrations
- user accounts or persisted profiles
- recommendation scores
- automatic trading
- tax advice
- claims that historical distributions will continue

FastAPI and Streamlit integration begin only after the pure calculation
contract passes table-driven tests.

## Tax and reinvestment component fallback

Tax and reinvestment scenarios use one complete historical component event
whose payment date is on or before the analysis date.
Selection follows this fixed order:

1. the latest complete `ACTUAL` event whose ratios total 99% through 101%;
2. otherwise, the latest complete `ESTIMATED` event under the same ratio rule;
3. otherwise, the dependent scenario remains unavailable.

The second path is labeled `ESTIMATED_FALLBACK`. Its `EST_*` component codes
remain unchanged and are never persisted or presented as official `54C` or
`76W`. Each positive estimated category requires an explicit tax assumption,
just like an official category. Therefore the fallback is usable for planning
while its source quality and tax-treatment assumptions remain inspectable.

Missing or incomplete estimated composition is not converted to zero. An
official event always takes precedence even when a newer estimated event is
available.

### Official announcement discovery boundary

The Cathay issuer adapter discovers candidate documents through the issuer's
public JSON announcement API using an explicit ETF-code keyword and bounded
page count. Discovery does not itself create ACTUAL data. It accepts only
official HTTPS PDF paths whose titles describe a final distribution or
component announcement, and rejects pre-announcements and estimated notices.
PDF content must pass the separate issuer-specific ACTUAL parser before import.

Discovery can be inspected without writing snapshots:

```powershell
python -m backend.app.data_sources.cathay_actual_dividend_discovery `
  --etf-code 00878 `
  --max-pages 3 `
  --allow-network
```

The issuer-source registry also records discovery capabilities separately from
parser verification:

| Issuer | Discovery | Current acceptance |
| --- | --- | --- |
| Cathay | Public JSON announcement API | Verified HTML ACTUAL adapter; PDF parser pending |
| CTBC | Deterministic latest-dividend PDF by ETF code | Discovery only; content basis remains `UNKNOWN` |
| KGI | Official ETF announcement HTML/PDF list | Discovery route registered; pagination parser pending |
| UPAM | Official document host | Stable ETF-code discovery route pending verification |

CTBC discovery performs an HTTPS `HEAD` request only. It verifies the final
domain and `application/pdf` content type, but does not download the document
or treat it as ACTUAL:

```powershell
python -m backend.app.data_sources.ctbc_actual_dividend_discovery `
  --etf-code 00891 `
  --allow-network
```

The multi-issuer design deliberately separates three states: an official host,
a discoverable official document, and a verified ACTUAL parser. Reaching an
earlier state never implies the later one.

KGI discovery submits the official page's bounded form fields (`ETF`, the
validated ETF code and function ID `1708`) to `/Home/ArticleVC`. It accepts only
same-domain PDF links whose title says `收益分配期後公告`. `期前`, estimated,
no-distribution and unrelated announcements remain explicit rejections. The
returned PDF basis remains `UNKNOWN` until its content is parsed and verified:

```powershell
python -m backend.app.data_sources.kgi_actual_dividend_discovery `
  --etf-code 00938 `
  --allow-network
```

## M11-2 current-holding aggregation

The saved current-holding scenario reuses the M10 target calculator with one
synthetic portfolio input: one unit priced at the sum of every saved holding's
`held_units * unit_price`. This representation changes no M10 formula and
ensures the fixed monthly target is evaluated once.

For each holding:

```text
annual gross distribution cash
= historical distribution cash per unit / history years * held units

annualized price return
= (1 + period PRICE_RETURN) ^ (1 / period years) - 1
```

Portfolio annual gross cash is the sum only when every holding has compatible
TWD cash data. No foreign-exchange conversion is assumed. Portfolio annual
price return is the current-value-weighted mean
only when every holding has a usable annualized return. Any missing component
keeps the dependent portfolio input `None`; partial known totals are not passed
off as complete portfolio totals.
# M11-5B principal-risk warning rules

Base-ETF target analysis emits deterministic warnings only when the required
facts exist. Missing facts never become a safe result or a formal zero.

- `NEGATIVE_TOTAL_RETURN`: the modeled after-tax total-return rate is below 0%.
- `PERSISTENT_PRICE_DECLINE`: the latest four available calendar-month-end
  official closes contain three consecutive declines and the cumulative change
  is at most -10%.
- `WEAK_PRICE_RECOVERY`: for the latest ex-dividend event with a complete
  60-calendar-day observation window, no stored official close in that window
  reaches the last official close before the ex-dividend date.
- `MATERIAL_PEER_UNDERPERFORMANCE`: the ETF's latest 1Y price return trails the
  median of at least five other ETFs with the same bond/non-bond classification
  by at least 10 percentage points.

Every emitted warning includes an observation date, source identifier and the
numeric/date evidence used by the rule. These are historical risk flags, not
predictions or recommendations.

## Shared output precision

The cash-flow and tax-reinvestment calculators use
`backend/app/services/calculation_precision.py` for Decimal output rounding:
amounts retain two decimal places; percentages and fractional units retain
six; all use explicit `ROUND_HALF_UP`, including negative values. The shared
functions are called at the existing result boundaries. Intermediate
distributions, taxes and reinvestment balances are not rounded earlier.
Frontend integer display does not change this API calculation precision.
Missing-input handling and ACTUAL/estimated/76W selection remain in their
existing models and services.
