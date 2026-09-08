# V5-3D: freshness-aware planning composition

Refs #122, parent #100. The owner approved this policy before implementation.
Baseline main: `cca5a66` (merged #121). Human CODEOWNER review remains required.

## Policy boundary

Planning consumers use fresh complete paid ACTUAL first, then fresh complete
paid estimates. The existing 18-calendar-month boundary is unchanged. No
fresh complete source yields unavailable; no mixing of bases, future payments,
inferred zeros or estimated-to-formal tax-code renaming is permitted.

The new planning selector is separate from historical event detail and
capital-gain history. It is consumed consistently by market eligibility,
portfolio projections and the single-ETF tax scenario endpoint. Historical
formal coverage and raw database rows are not changed. A stale historical
ACTUAL date is included in the fallback warning; the single-ETF tax page
renders the additive API warnings with standard `st.warning` (installed
Streamlit 1.60.0 API/docstring verified; no layout or deprecated API changes).

## Local evidence

The preserved Nomura candidate is replayed read-only at 2026-09-06, not
refreshed to today's market. Its SHA-256 is
`aa3940dd72ccde1c5a726309911016e78306300bb1219477ec143695117b321d`.
No new database or source import is needed for this policy change.

For 00878 the old selector uses ACTUAL paid 2023-09-11. The planning selector
uses ESTIMATED_FALLBACK paid 2026-06-12 and warns about the stale ACTUAL date.
The 2026-09-11 payment remains future at evaluation and is not selected.
The historical ACTUAL/76W record remains stored and retrievable.

The completed read-only replay preserved the exact database hash above.
00878 is eligible for addition in the zero-holding case, with
`ESTIMATED_COMPONENTS_ONLY` and `STALE_ACTUAL_COMPONENTS_FALLBACK` tradeoffs;
its historical `actual_76w_available` remains true. This is a dated eligibility
test, not a recommendation or a claim of newly acquired formal composition.

| Case | Result | Added ETFs | Eligible candidates (before -> after) |
| --- | --- | ---: | ---: |
| Zero holdings, quarterly 100 | TARGET_MET | 2 | 67 -> 68 |
| Holding 0050, quarterly 100 | TARGET_MET | 1 | 51 -> 52 |
| Holdings 0050 + 00878, quarterly 100 | TARGET_MET | 1 | 50 -> 51 |
| Zero holdings, all months 3000 | TARGET_MET | 2 | 67 -> 68 |
| Unsupported holding | UNAVAILABLE | 0 | 0 -> 0 |
| Formal zero target | TARGET_MET | 0 | 67 -> 68 |
| Holding 00929, all months 3000 | TARGET_MET | 3 | 66 -> 67 |
| Missing-reference-price holding | UNAVAILABLE | 0 | 0 -> 0 |

Every case retains all 263 candidate decisions. All cases completed without
exceptions; all successful positive-target cases stay within five added ETFs.
The broad existing-holding flag remains false because it includes the two
deliberate negative cases. No other eligibility gate was removed.

## Validation and review

Deterministic tests cover the exact 18-month boundary, calendar month-end,
future/missing payment dates, ACTUAL precedence within freshness, newest
selection independent of row order, incomplete mixes, zero ratios, unchanged
historical 76W selection, and cross-consumer warning propagation. A Streamlit
AppTest runs the real tax-result renderer and checks both freshness and
estimated-versus-formal warnings without errors. No manual browser screenshot
or production acceptance is claimed.

Final validation: 1,165 full regression tests passed in 228.677 seconds;
13 focused selector/portfolio tests, 10 market-index tests, four tax API tests
and the real-renderer AppTest passed. `compileall` and `git diff --check` passed
using the isolated Python 3.12 runtime. Tests use synthetic evidence; the
fixed-date full-market replay is separate local validation.

Local raw audit files and logs are excluded from Git. This does not approve a
source, change tax rates or the V5-4 solver objective, authorize deployment,
complete V5-3 or satisfy SEC-4. Rollback is a reviewed code revert; no database
rollback or deletion of historical evidence is necessary.
