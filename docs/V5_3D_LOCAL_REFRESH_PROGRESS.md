# V5-3D local refresh: interim evidence

Related Issue: #100. The owner requested a new local candidate instead of
waiting for the unavailable earlier candidate, and authorized this progress
report to be pushed. This document records an interim observation, not a
completed refresh, live process status, source approval or launch decision.

## Baseline and boundary

- Code baseline: `9645afa9f357133c646dd90c2b113f6663e95005`, including #107/#108.
- Fixed evaluation date: `2026-09-06`.
- Source SHA-256:
  `4c2cabb98b4df0be79700d99a138d2d11d95da1e153733112945d0f4c513e2fc`.
- Source opened read-only; migration and refresh target a separate candidate.
- This is not the former `2026-09-02` candidate or a like-for-like replay.
- Databases, downloaded payloads, local scripts, logs, process identifiers and
  absolute local paths are intentionally excluded from this change.

## Saved observations

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

## Required before a completion claim

1. Finish and reconcile all 263 performance attempts, with individual reasons.
2. Re-run constituent eligibility and quality checks against refreshed facts.
3. Complete cached-price-first dividend-yield calculation and report failures.
4. Verify candidate integrity, foreign keys, final hash and source preservation.
5. Run the full 18-field detail matrix and eight planner cases at the fixed
   evaluation date, including every candidate eligibility/exclusion record.

Missing fund size, expense, distribution-period, stock-dividend and formal
composition evidence is not invented or converted to zero. Public grading
decisions and SEC-4 remain outside this execution. No database-completeness or
public-readiness claim is made.

## Validation of this change

Documentation only; no calculation, API, data-source code or schema changes.
The numbers above were read from saved local pipeline reports and reconciled
as 837 + 183 + 0 = 255 x 4 periods. This is not a new full-regression result.
