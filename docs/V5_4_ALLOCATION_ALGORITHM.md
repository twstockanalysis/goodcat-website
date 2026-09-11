# V5-4 complete-portfolio allocation algorithm

Status: first implementation stage for Issue #99

## Purpose

V5-4 separates portfolio feasibility from historical quality and risk evidence.
The solver receives candidates only after the existing data and product gates
have classified them as calculable. It then searches ETF combinations and exact
whole-share quantities together. It does not use an ETF quality score, grade,
rank, constituent overlap or risk label to decide whether a cash-flow plan is
feasible.

The result is a bounded historical-data scenario. It is not a buy or sell
instruction, a claim of personal suitability, a future distribution guarantee
or proof of a global minimum unless the response separately says
`PROVED_OPTIMAL`.

## Implemented cash-target order

For each selected month, current modeled cash from every submitted holding is
included first. The solver then:

1. keeps only candidates that already passed the existing internal gates;
2. searches deterministic integer-share batches across the complete gated
   candidate input instead of preselecting by quality score;
3. preserves every submitted existing ETF in every plan, even when that ETF is
   not eligible for additional shares;
4. permits no more than five **added** ETF codes in one plan; existing ETFs do
   not consume this five-code allowance;
5. first minimizes total selected-month shortfall;
6. for complete plans, next minimizes additional capital, avoidable overshoot
   and added-ETF count;
7. uses ETF code only as the final stable tie-breaker; and
8. removes plans dominated on shortfall, capital, overshoot, selected-month
   resulting-cash imbalance, complexity and resulting-position concentration.

### Monthly-balance dominance correction (#135)

Cash-target dominance includes the same balance measure used by the existing
stable/balanced selector: maximum minus minimum resulting cash over selected
months, including existing holdings. It is not the spread of added cash alone
or of overshoot; unequal targets do not redefine the measure. Unselected months
do not participate, and one selected month has zero imbalance.

A cheaper plan cannot dominate a more balanced plan merely because both have
the same total overshoot. For example, modeled cash of 10/20 at capital 10 and
15/15 at capital 20 are distinct trade-offs for targets 10/10. The primary
capital-efficient ordering remains unchanged; the balanced view can select the
second plan. Strict dominance still requires no worse values on every dimension
and improvement on at least one. This adds no grade or new public API field.

The correction does not make bounded search exhaustive. Beam and frontier size
limits can still discard alternatives; `search_truncated` remains evidence of
that limitation, not proof that no better balanced portfolio exists.

## Three post-feasibility plan views

All three views are selected from complete whole-share plans produced from the
same request. They do not pre-rank ETFs by historical quality:

- `資金精簡方案` first minimizes additional capital, then avoidable overshoot
  and the number of added ETFs;
- `穩定均衡方案` first minimizes the cash-flow spread among the requested
  months, then overshoot and additional capital;
- `分散防護方案` first minimizes the largest resulting position after every
  submitted holding and every added share are combined.

Only distinct share combinations are returned. A second or third
card is omitted when its selected combination duplicates an earlier card; the
service records that limitation instead of manufacturing a cosmetic variant.

### Objective-aware search (#137)

The owner rejected a proposed 1% alternative-hiding rule and authorized direct
search for each existing strategy. No minimum improvement threshold applies;
different portfolios remain eligible for display even if their measured gain
is small. Exact duplicate signatures are still omitted. Difference in shares
does not imply significant benefit or personal suitability.

Each strategy now controls both beam retention and bounded feasible-frontier
retention with its existing lexicographic objective. All search orders put
shortfall first. Capital-efficient search retains its prior expansion, stopping
and ordering behavior. Alternate searches can extend complete plans using
positive integer neighbours of selected-month cash-line intersections (balance)
or equal resulting-position values (diversification). Existing holding cash
and value participate in these calculations. Complete refinements continue only
when they improve that strategy's ordering. No holdings are sold or replaced.

The same objective order is shared by search and final plan selection. Each
strategy retains the existing 64-state beam, 20,000-state expansion cap and
round limit. Breakpoints are a heuristic, not exhaustive integer optimization;
different beams may miss different plans. No new capital cap, concentration
mandate, risk score or grade formula is introduced. A lower concentration can
require substantially more capital, which must remain visible as a trade-off.
Already-met/zero targets still return no additions. Data/product gates and
budget-mode behavior are unchanged.

Pareto filtering caches each plan's comparison vector once and maintains an
incremental non-dominated set. It uses the same strict dominance relation,
including removal of earlier members dominated by a later plan. A deterministic
100-vector all-pairs reference test covers equivalence and input-order reversal;
this optimization changes neither dominance tolerances nor search limits.

Direct objective optimization can expose unattractive capital trade-offs. In
the fixed zero-holding quarterly-100 replay, primary capital remains 4,699.48
TWD, while the balanced search produces 122,987.44 TWD with displayed month
spread 0.01, and the diversified search produces 268,706.92 TWD with maximum
position 33.33%. These are not universally better portfolios. No unapproved
capital cap or precision tolerance is added to suppress these results; owner
review of their usefulness remains necessary before accepting the wider V5-4
product behavior. The lexicographic objectives prioritize spread/concentration
before capital, and capital is unbounded by the cash-target request.

#### Validation on 2026-09-11

- 17 focused solver tests passed; final full regression passed all 1,204 tests
  in 187.537 seconds. Compileall and `git diff --check` passed. Timing is not a
  controlled before/after latency benchmark.
- The fixed 2026-09-06 eight-case replay preserves every primary addition and
  required-capital result, all 8 x 263 eligibility/exclusion records, the full
  263 x 18 field ledger, reference evidence and acceptance flags against #135.
  Six TARGET_MET cases (including zero) and two intentional UNAVAILABLE cases
  remain. The broad all-holding-cases eligibility flag remains false by design.
- Strategy output grows from 17 to 18 records: the zero-holding every-month
  3,000 case now has a distinct balanced plan. All positive-case strategy
  searches disclose 20,000 explored states and truncation; no global optimum
  or universal improvement is claimed. Each plan respects five addition codes.
- Candidate SHA-256 remains
  `1c52c0edd0d0ad644f07e427c3e10d6a33e222f9b650f50b7c403845b951250e`,
  integrity `ok`, foreign-key violations zero. No source, database, service,
  public schema or grade formula changed.

Selected-month spread/capital comparisons for the balanced view (TWD):

| Case | Prior capital / spread | New capital / spread |
| --- | ---: | ---: |
| No holdings, quarterly 100 | 5,437.20 / 43.04 | 122,987.44 / 0.01 |
| 0050 holding, quarterly 100 | 5,437.20 / 43.04 | 122,987.44 / 0.01 |
| 0050 + 00878, quarterly 100 | 5,437.20 / 43.04 | 122,987.44 / 0.01 |
| No holdings, every-month 3,000 | No distinct balanced record | 1,561,200.00 / 2,600.04 |
| 00929 holding, every-month 3,000 | 923,702.53 / 3,749.33 | 1,512,906.27 / 2,632.48 |

These are trade-offs, not buying instructions. In particular, the new
zero-holding every-month balanced plan has one ETF and 100% position
concentration. Better cash balance must not be described as lower risk.

The search is a deterministic bounded beam search. It expands exact whole-share
batches around each remaining monthly constraint and records whether state or
frontier pruning occurred. Any non-zero result remains
`BOUNDED_BEST_EFFORT`; pruning evidence is exposed as
`search_explored_states`, `search_truncated` and `V5_4_BOUNDED_SEARCH`. The
system must not call such a result a global minimum.

## Concentration treatment

V3-3 always added shares to low-value positions until every resulting ETF was
at or below 20 percent. That repair could add capital unrelated to the owner's
cash target and could fail an otherwise complete plan when fewer than five
candidates were eligible.

V5-4 no longer enforces that universal repair while constructing feasibility.
The existing threshold remains in the response only as a backward-compatible
comparison value; `concentration_limit_enforced` is explicitly `false`.
Resulting allocation percentages remain available for later plan-level risk and
trade-off comparison. V5-4 does not convert concentration into a single-ETF
quality score.

## Optional cash-target capital ceiling (#139)

The owner approved an optional user-entered additional-capital ceiling after
reviewing #137's high-capital alternatives. It constrains all three strategies
during search rather than hiding completed over-budget portfolios. Null/omitted
retains the prior unlimited behavior, while formal zero permits no additions.
Existing holdings are preserved and do not consume new capital. This is still
cash-target mode, not the separate target-free investable-budget foundation.

For each candidate expansion, the search derives affordable whole shares from
remaining exact capital, includes boundary quantities, and rejects costs beyond
the ceiling. It additionally checks the sum of per-ETF costs rounded HALF_UP to
TWD cents, matching the response. For example, two costs of 0.335 require 0.68
in the displayed aggregate, so they cannot jointly pass a 0.67 ceiling.

The response echoes the ceiling and rejects an aggregate above it. If the search
finds no complete plan within the cap, explicit PARTIAL/shortfall evidence and
`NO_COMPLETE_PLAN_WITHIN_CAP` distinguish it from a complete plan. Bounded
search is not a proof of infeasibility; no data gate is relaxed to meet a cap.
An already-met target needs no additions even at cap zero. Missing holding
facts and absent eligible candidates retain their existing unavailable states.

The transaction-cost rate remains explicitly zero; this constrains modeled
investment, not real execution costs. No default cap, grade, source, scenario,
or public form change is introduced. Exact-signature deduplication remains.

### Capital-ceiling validation (2026-09-11)

Focused validation passed 23 solver and 12 allocation service/API tests. Final
regression passed 1,212 tests in 169.119 seconds; compileall and diff checks
passed. Additional live TestClient checks confirmed zero-cap propagation through
the inherited long-term-scenarios and portfolio-projections endpoints, using a
temporary test database (not the running services).

The fixed 2026-09-06 unlimited audit matches #137's 263 x 18 field ledger,
eight primary-case summaries including 8 x 263 eligibility decisions, strategy
counts, reference evidence and acceptance flags after excluding only the new
null request field. This is not a byte comparison of every alternative payload.
Six TARGET_MET primary cases (including formal zero) and two intentional
UNAVAILABLE cases remain; the aggregate all-holding eligibility flag remains
false by design. Candidate integrity is `ok`, FK violations zero, and SHA-256
is unchanged: `1c52c0edd0d0ad644f07e427c3e10d6a33e222f9b650f50b7c403845b951250e`.

A separate eight-case capped replay uses test values, not automatic defaults:

| Case | Test cap TWD | Returned capital TWD (capital / balanced / diversified) |
| --- | ---: | --- |
| No holdings, quarterly 100 | 5,000 | 4,699.48 / 4,985.96 / 4,993.88 |
| 0050 holding, quarterly 100 | 5,000 | 4,713.24 / 4,985.96 / 4,993.88 |
| 0050 + 00878, quarterly 100 | 5,000 | 4,713.24 / 4,985.96 / 4,993.88 |
| No holdings, every-month 3,000 | 1,000,000 | 953,034.38 / duplicate omitted / 999,998.20 |
| 00929 holding, every-month 3,000 | 1,000,000 | 923,663.78 / duplicate omitted / 999,999.70 |

The other three cases preserve unsupported/missing-price unavailability and
formal-zero success. All 16 returned strategy/state records stay within the
submitted cap and at most five additions; successful monthly results have zero
shortfall. Synthetic tests separately cover insufficient and exact ceilings,
rounded position sums and already-sufficient holdings at cap zero.

The affordability boundary changes explored batches when a cap is supplied.
Consequently a bounded search may return a different or slightly higher-capital
primary even when the prior unlimited plan fits (00929: 923,647.39 unlimited
versus 923,663.78 capped). No monotonic-improvement or global-minimum guarantee
is made. Omitted/null preserves the old search path. No database was modified.

## Budget-mode foundation

`solve_budget_frontier()` establishes the separate investable-budget boundary:

- used budget never exceeds the submitted amount;
- current modeled cash from every submitted holding participates in monthly
  balance without consuming the new-investment budget;
- quantities remain non-negative whole shares;
- each plan contains at most five added ETFs;
- deterministic ordering first favors the minimum cash among selected months,
  then total selected-month cash, lower imbalance, budget use and complexity;
- Pareto filtering removes a plan only when another uses no more budget, is no
  more complex and provides at least as much cash in every selected month.

The current public request remains cash-target only. Adding budget mode to the
public Pydantic and FastAPI contracts is a later additive V5-4 step and must not
be simulated by overloading the cash-target field.

## Missing data and evidence boundaries

The solver accepts twelve explicit monthly cash values for each gated
candidate. A missing monthly vector is invalid input and cannot be converted to
formal zero. Upstream calculation remains responsible for preserving formal
ACTUAL composition, eFortune estimated fallback, official `76W`, estimated
realized capital gain, formal zero and unavailable evidence as distinct states.

Historical quality and risk evidence may compare already feasible frontier
plans later. The planning-grade boundary is fixed: it evaluates the completed
plan against this request only after feasibility, and must not change the
capital-efficient solution. The shared decision record intentionally did not
define a formula, weights, thresholds or public A/B/C labels. Those values are
therefore not invented in this change and require representative replay plus an
explicit owner decision before they become a public contract.

## Reproducibility and limits

Equivalent ordered facts, request values and search bounds produce the same
frontier regardless of incoming candidate order. Default cash-target bounds are
five added ETFs, a 64-state beam and 20,000 explored states. Stable ETF code
order resolves exact ties.

The pure solver is covered independently from repositories so deterministic
cash-target, existing-holding, dominance, maximum-five, missing-input and
budget-boundary behavior can be replayed without a mutable database.

## Balance correction validation (#135)

The three added regressions fail on the prior solver and pass with the balance
dimension: equal targets, existing-holding cash, and unequal targets with an
unselected-month payment. They exercise the real monthly-balanced selector;
the first also verifies candidate-order invariance and unchanged capital-first
selection. Existing strict-dominance and single-month cases remain covered.

Focused solver suite: 12 passed. Full regression: 1,198 passed in 261.432 seconds
on 2026-09-10. Compileall and `git diff --check` passed. No public request/response
schema, source selector, tax calculation, data gate or live service changed.

The immutable candidate recorded for #133 was replayed at 2026-09-06. Its full
263-by-18 field ledger, all eight primary-case summaries and 263-candidate
eligibility records per case, reference evidence and acceptance flags match the
pre-change audit exactly. Six cases remain TARGET_MET (including formal zero);
two intentional negative cases remain UNAVAILABLE. The broad all-holding-cases
eligibility flag remains false by design; this is not an all-flags-pass claim.
Integrity is `ok`, foreign-key violations zero, and SHA-256 remains
`1c52c0edd0d0ad644f07e427c3e10d6a33e222f9b650f50b7c403845b951250e`.

A separate eight-case strategy replay confirms the existing card counts and
maximum-five constraint. This is not a before/after comparison of every alternate
plan. For the zero-holding quarterly case, the capital-efficient plan uses
4,699.48 TWD with a selected-month spread of 66.12; the balanced plan uses
5,437.20 TWD with a spread of 43.04. For the 00929 holding case, the balanced
plan costs 55.14 TWD more and reduces spread by only 0.73 TWD: distinct share
combinations alone do not establish a material user benefit. Materiality
tolerances, public grading and budget API integration remain separate work.

Reproduce using `deployment.v5_full_database_audit` with the recorded immutable
candidate and fixed date; do not switch running services or import data.
