# V5-3D local refresh evidence

Related Issue: #100. The owner requested a new local candidate instead of
waiting for the unavailable earlier candidate, and authorized this progress
report to be pushed. The final recovery section supersedes the interim
checkpoints below. This is not source approval or a launch decision.

## Final local recovery, fixed evaluation date 2026-09-06

- All 263 performance attempts completed: 856 successful period records,
  196 insufficient-history periods and zero failed periods (263 x 4).
- Dividend events: 1,525. Yield is available for 1,518 events; the seven
  remaining events are 00940 (ex-date September 8), 00400A (September 7),
  three 00774C events and two 0081 events without an official prior close.
  Future events and unavailable closes remain missing, never zero.
- The 461 initial HTTP 308 failures were recovered through bounded retries
  and independently saved per-ETF continuation. The interrupted global retry
  is not represented as a completed run.
- Constituent calculation-quality coverage: 145/157 ETFs (92.356688%) and
  20/21 issuers (95.238095%). This meets these two numeric coverage thresholds,
  not database completeness or permission for public launch.
- Three Taishin snapshots recovered through normal retries. UOB 00918 used
  standard Windows TLS verification and the unchanged official parser.
- Nine Capital historical snapshots for September 4 were imported without
  overwriting the retained September 7 snapshots: 00643, 00678, 00714, 00919,
  00923, 00927, 00946, 00982A and 00992A. Each request verified the official
  catalog/basic ETF identity, exact response date and unchanged stock parser.
  Historical disclosed stock totals range from 96.9883% to 99.4231%.
- Quality and overlap now consistently select the latest effective snapshot
  on or before evaluation. Future-only, stale and incomplete data still fail
  closed. Later-fetched history is not evidence of historical availability.
- Candidate SHA-256:
  `f97dd5f29f488a1bcd66650362a4003d417957a7d40afdcc964c9022b2bcb748`.
  Integrity: `ok`; foreign-key violations: zero; source SHA unchanged.

Remaining constituent gaps are 0061, 00625K, 00636K, 00643K, 00657K,
00668K, 00736, 00924, 009812, 009813, 009817 and 00985A. Their causes
include unverified currency/share-class mappings, insufficient direct-stock
coverage, nested ETF/derivative-only evidence and unavailable official access.
Do not copy another share class, normalize incomplete weights or bypass access.

Detail availability counts out of 263 ETFs remain explicit:

| Detail fields | Available |
| --- | ---: |
| Identity, classification, listing date (each) | 263 |
| Price history | 245 |
| Dividend history, dividend yield (each) | 121 |
| Estimated components | 106 |
| Reviewed ACTUAL components, formal 76W (each) | 1 |
| 1M / 3M / 6M / 1Y price return | 230 / 224 / 210 / 192 |
| Fund size, expense ratio, distribution period, stock dividend (each) | 0 |
| Published historical quality grade | 0 |

Missing formal components and unverified detail fields need reviewed source
evidence or a separately accepted source/schema contract; they cannot be
completed by substituting estimates. V5-4 algorithm/grade changes and SEC-4
remain out of scope. Issue #100 must not be closed as fully data-complete.

### Eight-case replay

All eight cases completed without exceptions and retained 263 market-candidate
evidence records each. All 263 x 18 fields have explicit availability reasons.
The candidate hash was identical before and after this read-only audit.

| Case | Result | Added ETFs |
| --- | --- | ---: |
| No holdings, quarterly target 100 | TARGET_MET | 2 |
| Holding 0050, quarterly target 100 | TARGET_MET | 1 |
| Holding 0050 + 00878, quarterly target 100 | TARGET_MET | 1 |
| No holdings, all-month target 3000 | TARGET_MET | 2 |
| Unsupported holding product | UNAVAILABLE | 0 |
| Formal zero target | TARGET_MET | 0 |
| Holding 00929, all-month target 3000 | TARGET_MET | 3 |
| Holding without reference price | UNAVAILABLE | 0 |

Every positive-target success stayed within five additions. Nonzero plans
retain `V5_4_BOUNDED_SEARCH`; this is not a global-optimality claim. The audit's
broad `existing_holding_cases_have_eligible_candidates` flag remains false
because it includes the two deliberate unavailable-data/product cases above,
not because 0050+00878 or 00929 failed. Missing data stays explicit.

## Bounded HTTP 308 recovery

The first complete yield pass calculated 638 of 1,106 outstanding events and
retained 468 failures: 461 HTTP 308 responses, two future ex-dividend dates and
five events without a prior trading close. The observed 308 responses pointed
back to the original TWSE STOCK_DAY request.

The downloader now includes HTTP 308 in its existing bounded retry set alongside
307. It still retries the configured official URL, never follows `Location`,
keeps TLS/hostname verification, and raises the response error after exhausting
the attempt limit. Tests cover 308 recovery plus 307/308 exhaustion and refusal
to follow an unrelated redirect destination. No dividend, tax or price formula
changes are introduced. A live retry of 00916 for June 2025 returned 21 daily
closes. The final recovery above supersedes this first-pass checkpoint.

## Baseline and boundary

- Code baseline: `9645afa9f357133c646dd90c2b113f6663e95005`, including #107/#108.
- Fixed evaluation date: `2026-09-06`.
- Source SHA-256:
  `4c2cabb98b4df0be79700d99a138d2d11d95da1e153733112945d0f4c513e2fc`.
- Source opened read-only; migration and refresh target a separate candidate.
- This is not the former `2026-09-02` candidate or a like-for-like replay.
- Databases, downloaded payloads, local scripts, logs, process identifiers and
  absolute local paths are intentionally excluded from this change.

## Earlier saved observations (superseded checkpoints)

The master refresh accepted 263 ETFs from 271 source entries, inserting seven
and updating 256; eight non-ETF entries were rejected.

Dividend refresh inserted eight events and updated 329. The resulting database
contained 1,525 dividend events. Formal ACTUAL composition and ACTUAL 76W each
remained at one event; 1,524 events still lacked formal ACTUAL composition.
Estimated components are not relabeled as ACTUAL or formal 76W.

The first constituent pass recorded 132 imports and 21 failures. These are
attempt outcomes, not final freshness/coverage acceptance. A final pass must
re-evaluate eligibility after the performance refresh; unresolved share-class,
nested-holding, coverage and network failures retain their actual reasons.

At the captured performance checkpoint, 255 of 263 ETF attempts were saved:
837 successful period records, 183 insufficient-history periods and zero failed
periods among those saved attempts. Each attempt covers 1M/3M/6M/1Y. This does
not mean 255 ETFs satisfy all four periods. The eight remaining attempts were
not included in this observation. Checkpoints preserve completed attempts so
an interrupted execution need not discard all earlier downloads.

## Local execution checklist

1. Completed all 263 performance attempts, with individual reasons.
2. Re-evaluated constituent eligibility and quality against refreshed facts.
3. Completed outstanding yield attempts and retained seven explicit gaps.
4. Verified candidate integrity, foreign keys, hash and source preservation.
5. Saved the full 18-field matrix and eight planner cases at the fixed date,
   including every candidate eligibility/exclusion record.

Missing fund size, expense, distribution-period, stock-dividend and formal
composition evidence is not invented or converted to zero. Public grading
decisions and SEC-4 remain outside this execution. No database-completeness or
public-readiness claim is made.

## Validation

- 21 focused constituent foundation/batch tests passed, including six new
  effective-date regressions. Existing bounded TWSE downloader tests: 8 passed.
- Full regression: 1,101 tests passed in 219.530 seconds on this branch,
  using isolated Python 3.12 installed from `requirements.lock`.
- `compileall` and `git diff --check` passed.
- No frontend, schema, tax formula, TLS-policy or public grading changes.
- The branch baseline is recorded above; these test results must not be
  represented as validation of later default-branch changes.
