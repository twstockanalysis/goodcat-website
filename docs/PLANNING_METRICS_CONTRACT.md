# Descriptive post-allocation metrics

Issue #147 implements the owner-approved basis for later MeowMeow planning
assessment. It does not implement a grade, aggregate score, weight, threshold,
risk band or suitability conclusion. Indicators are calculated only after
allocation and exact-signature selection; they cannot feed back into the solver,
alter a candidate gate, reorder plans or hide a distinct portfolio.

## API placement and compatibility

The existing cash-target `allocation-results` and target-free `budget-results`
responses add `plan_metrics`, ordered one-to-one with returned plans. Each entry
contains `plan_key` (existing strategy/objective identifier) and `metrics`.
Omitted budget alternatives have no entry. An unavailable primary still has an
entry explaining missing metrics. Existing response fields and nested single
plans remain unchanged. Single-plan endpoints expose no new fields.

The service computes from already-selected response objects without mutation,
additional database queries or solver calls. No new request input is accepted.
Long-term/projection consumers that embed allocation results inherit this
additive field; their own calculations and schemas are otherwise unchanged.

## Definitions

`methodology=DESCRIPTIVE_PLAN_METRICS_V5_4` and
`amount_basis=DISPLAYED_RESPONSE_AMOUNTS` identify a descriptive projection of
the public response. Cash values use that response's rounding, not the solver's
unrounded objective. Thus displayed differences may disappear at cent precision;
these metrics must not be used to recompute feasibility or rank plans.

| Field | Definition |
| --- | --- |
| `mode`, `source_status`, `selected_months` | Preserve the mode, underlying status and requested months. |
| `target_attainment` | Cash-target TARGET_MET -> MET; PARTIAL/NO_ELIGIBLE_ALLOCATION -> NOT_MET; UNAVAILABLE -> UNAVAILABLE. Budget -> NOT_APPLICABLE, including unavailable budget cases. |
| `minimum_month_cash_twd`, `maximum_month_cash_twd` | Min/max modeled cash over all selected months, including original holdings. |
| `total_selected_month_cash_twd` | Sum of those modeled amounts; not an annual total unless all twelve months were selected. |
| `month_cash_spread_twd` | Maximum minus minimum; one selected month has zero spread, not guaranteed stability. |
| `total_shortfall_twd` | Cash-target sum of existing per-month reported shortfalls. Budget: null. |
| `total_overshoot_twd` | Cash-target sum of max(displayed modeled cash - target, 0), without netting against another month's shortfall. Budget: null. |
| `additional_capital_twd` | Existing required/used new capital, not total portfolio value. |
| `capital_limit_twd` | Submitted optional cash-target cap or required investable budget. |
| `remaining_capital_twd` | Limit minus used new capital, only when a limit exists and the allocation facts are available. |
| `capital_usage_pct` | Used new capital / positive limit x 100, rounded HALF_UP to two decimals. It is not a return, efficiency score or benefit of spending more. |
| `added_etf_count` | Number of returned added ETF codes; additional shares of an original ETF still count. |
| `resulting_etf_count` | Number of complete resulting positions, including all original holdings. |
| `max_resulting_position_pct` | Maximum existing `allocation_pct` across those positions; not recalculated from rounded values and not constituent overlap or a risk grade. |

Target attainment follows the original feasibility status even if a nonzero
shortfall rounds to zero. No achieved-month count or ratio is added to cards.
No transaction-cost, tax or cash-basis assumption is changed.

A usage percentage rounded to 100.00 does not imply an exactly exhausted limit;
the explicit used and remaining capital amounts remain authoritative. For
example, 999,995.53 used from 1,000,000 leaves 4.47 even though usage displays
100.00%. This is not a reason to purchase additional shares.

## Missing, zero and not-applicable rules

- UNAVAILABLE: all calculated amount/count/concentration metrics remain null;
  preserve the submitted limit and source status, and report
  `ALLOCATION_FACTS_UNAVAILABLE`. Known facts remain in the original result.
- Budget has no cash target: attainment NOT_APPLICABLE, shortfall/overshoot null,
  with `NO_CASH_TARGET_IN_BUDGET_MODE`.
- An omitted cash-target cap leaves remaining capital/usage null with
  `NO_CAPITAL_LIMIT`; a formal zero cap/budget leaves usage null with
  `ZERO_CAPITAL_DENOMINATOR`. Known zero used/remaining amounts stay zero.
- If any requested month is missing, duplicated or unknown, cash aggregates
  remain null with `MONTH_CASH_UNAVAILABLE`; do not sum a partial set as complete.
- Resulting positions must cover exactly the union of original and added codes.
  Incomplete/missing positions give null count/concentration with
  `RESULTING_POSITIONS_UNAVAILABLE`. This includes legacy no-eligible cash-target
  responses that omit original positions. Never infer that they were sold.
- A known empty portfolio has count zero but concentration null with
  `NO_RESULTING_POSITIONS`. No position is not a zero-risk portfolio.

Data availability is not a quality score. ACTUAL, estimated fallback, formal
76W, missing, formal zero and announced-versus-paid boundaries remain unchanged.
The interpretation explicitly denies aggregate grades, suitability and trading
instructions. Public grading formulas and UI integration require later decisions.

## Verification

Test the independent projections, missing/zero denominators, existing holdings,
partial versus rounded-zero shortfalls, selected-month completeness, serialized
metrics, non-mutated single results and additive multi-result API output. Replay
the fixed eight cash-target and eight budget cases against the same immutable
candidate/date, comparing all pre-existing fields after removing only
`plan_metrics`. Preserve the candidate hash and integrity before/after.

### Automated validation on 2026-09-12

Focused validation passed 20 tests across planning metrics, budget results and
cash-target results. Full regression passed 1,254 tests in 280.194 seconds.
Compileall and `git diff --check` passed. Tests cover the sub-cent shortfall
status boundary, missing versus empty positions, zero versus omitted limits,
original-only concentration, selected-month aggregation, response non-mutation
and additive API output. No browser acceptance, score calibration, practical
usefulness acceptance or performance benchmark was performed.

The fixed 2026-09-06 immutable-candidate replay passed all eight cash-target and
eight budget cases. Removing only top-level `plan_metrics` leaves every prior
response field identical: cash responses were compared by canonical full-payload
SHA-256 against the clean pre-change worktree (same Git tree as merged main),
and budget responses directly against the #145 stored full replay. This includes
plan order, additions, costs, statuses, original holdings and eligibility evidence.
There are 18 cash-target and 15 budget metric entries, exactly matching returned
schemes, including explicit unavailable/zero states rather than extra normal cards.

The 00929-held monthly budget replay illustrates why indicators stay separate:
primary spread/concentration is 2,985.95 TWD / 48.57%; balanced is 2,861.28 /
48.58%; total-first is 36,757.53 / 97.14%. These are descriptions, not ratings or
owner usefulness acceptance. The candidate SHA-256 remains
`1c52c0edd0d0ad644f07e427c3e10d6a33e222f9b650f50b7c403845b951250e`,
integrity `ok`, FK violations zero. No database, live service or solver changed.
