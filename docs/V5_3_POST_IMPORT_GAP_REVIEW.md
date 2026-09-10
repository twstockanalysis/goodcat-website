# V5-3 post-import gap review

Related: #100; follows merged #131. This is an evidence review, not a database
completeness claim, source approval, V5-4 resumption or public-release decision.

## Frozen boundary

- Code: `cfa9c5f5631f5ccd08d7bb574d8aaeb2849b4421`.
- Evaluation: 2026-09-06, not the execution date 2026-09-10.
- Local candidate: `v5-3d-expense-20260906.db`; SHA-256
  `21fef06fdce269a04a1afa205ee7a1f5e734f2ded25d5879e23f29b52ccb320d`.
- No new imports, service switch or database writes in this review.
- Later retrievals reconstruct dated evidence; they do not prove original
  historical online availability. This is not a fresh September 10 market run.

Earlier reports retain their historical findings. The following counts describe
this candidate only and supersede neither source restrictions nor review gates.

## Visible-field ledger

All 263 ETFs retain all 18 field statuses and explicit missing reasons.

| Field | Available / 263 |
| --- | ---: |
| Identity | 263 |
| Classification | 263 |
| Listing date | 263 |
| Fund size | 29 |
| Annual expense ratio | 1 |
| Price history | 245 |
| Dividend history | 121 |
| Dividend yield | 121 |
| Distribution period | 0 |
| Stock dividend | 0 |
| Complete estimated components | 106 |
| Reviewed ACTUAL components | 1 |
| Formal 76W | 1 |
| Published historical quality grade | 0 |
| 1M price return | 230 |
| 3M price return | 224 |
| 6M price return | 210 |
| 1Y price return | 192 |

These are ETF-level availability counts, not event counts or promises that all
observations satisfy the planner's date/freshness requirements. For example,
one stored ACTUAL ETF does not imply one usable current ACTUAL planner candidate.
The zero-holding planner evidence has zero selected ACTUAL component candidates
and 94 estimated-fallback candidates across the universe; the latter is not
the 68 eligible-candidate count. Missing and formal zero remain separate.

The 0056 expense improvement is five annual rows for one ETF. It changes no
planner case. Fund size and expense presentation must not be presented as a
solver improvement or a quality-grade increment.

## Frozen planner matrix

Every case retains 263 market decisions, whole-share additions, monthly cash
flow and shortfalls. Capital below is a model output in TWD, not advice.

| Case | State | Eligible | Added ETFs | Additional capital |
| --- | --- | ---: | ---: | ---: |
| No holdings, quarterly 100 | TARGET_MET | 68 | 2 | 4,699.48 |
| 0050 holding, quarterly 100 | TARGET_MET | 52 | 1 | 4,713.24 |
| 0050 + 00878 holdings, quarterly 100 | TARGET_MET | 51 | 1 | 4,713.24 |
| No holdings, all-month 3000 | TARGET_MET | 68 | 2 | 953,034.38 |
| Unsupported holding | UNAVAILABLE | 0 | 0 | 0 |
| Formal zero target | TARGET_MET | 68 | 0 | 0 |
| 00929 holding, all-month 3000 | TARGET_MET | 67 | 3 | 923,647.39 |
| Holding missing reference price | UNAVAILABLE | 0 | 0 | 0 |

The two unavailable-case capital fields are not feasible zero-cost solutions.
The broad audit flag for all holding cases having eligible candidates remains
false because these intentional negative cases are included. Other audit
acceptance flags pass. Successful positive targets remain within five additions.

The positive-target plans remain `BOUNDED_BEST_EFFORT`, not globally optimal.
Three strategy records are returned for quarterly and 00929 cases; two for the
zero-holding all-month case. Counts alone do not prove materially distinct or
non-dominated portfolios. Comparing complete plans and planning grades remains
V5-4 work; no algorithm acceptance is inferred here.

00929 retains 37 paid events, latest 2026-08-14, and one scheduled 2026-09-14
payment. The scheduled event stays visible but is excluded from paid history.

## Result-critical gaps: avoid double counting

The zero-holding case has 198 supported products, of which 68 are eligible and
130 excluded; the other 65 products are outside the allocation product scope.
Across all 195 excluded products, the most frequent codes are unstable
distributions (120), missing total return (107), missing complete components
(104), stale data (102), missing after-tax cash (89), and incomplete data (50).
These counts overlap. They must not be summed or described as recoverable ETF
counts; product/history/risk restrictions are not automatically data failures.

Intersect each supported, excluded candidate's `reason_codes` with that case's
`exclusion_codes[].code` before grouping. This removes informational warnings
such as `ESTIMATED_COMPONENTS_ONLY` from the blocking-code set. This is diagnostic
grouping, not a counterfactual solver run or permission to remove a gate.

Findings using that method:

- 00736 is the only candidate whose sole blocking code is
  `HOLDING_OVERLAP_UNAVAILABLE` in each normal 0050, 0050+00878 and 00929 holding
  case. Each case has 52 candidates carrying that code, but the other 51 also
  have blockers. A valid stock snapshot is therefore a narrowly targeted next
  investigation, not a promise of 52 recovered candidates or a better plan.
- The recorded Cathay probe rejected 00736 for less than 90% direct-stock
  coverage. A retry alone is not evidence of completeness. Investigate exact
  dated asset/stock reconciliation first; do not normalize to 100%, copy another
  class, lower the global floor or transfer Nomura-specific approval.
- 00660 has only missing complete components plus stale-data blockers in the
  zero-holding case. 00920 additionally has stale-dividend-components. These
  are focused component-history investigations, not guaranteed recoveries.
  Confirm actual source history and a permitted reviewed import before writing.
- 18 supported products have only `UNSTABLE_DISTRIBUTIONS` as a blocking code:
  00851, 00938, 00951, 00952, 00961, 00962, 00963, 00964, 00971, 00972,
  009802, 009803, 009805, 009808, 00980A, 00981A, 00982A and 00984A.
  More downloads cannot be assumed to create a stable paid history at the fixed
  date. Distinguish genuinely absent source records from short/unstable history;
  changing the acceptance rule would be a separate product/algorithm decision.
- Large combined-missing cohorts have multiple simultaneous blockers: 50 lack
  after-tax cash/components/total return and are stale/unstable; another 22 also
  have incomplete-data flags. Do not prioritize them merely by one raw count.

## Constituent issuer/source cohorts

The existing dated quality evaluator covers 146/157 target ETFs and 20/21
issuers. This denominator requires the existing six-month performance baseline;
it is neither the 263-master universe nor the 198 supported allocation products.
All 11 remaining targets report `MISSING_SNAPSHOT` at the evaluation date.
That storage reason alone does not establish why acquisition failed.

| Issuer | Covered / targeted | Missing target codes |
| --- | ---: | --- |
| Cathay | 17/22 | 00636K, 00657K, 00668K, 00736, 009817 |
| Yuanta | 20/21 | 0061 |
| Fubon | 25/26 | 00625K |
| Capital | 9/10 | 00643K |
| Fuh Hwa | 6/7 | 00924 |
| Nomura | 7/8 | 009812 |
| BlackRock | 0/1 | 009813 |

The other 14 issuers cover all 62 of their targets. Source reviews distinguish
currency-class identity gaps, incomplete direct-stock disclosures, nested
ETF/futures portfolios and access restrictions. In particular, 009812 and
009817 have documented underlying-fund evidence rather than valid direct-stock
look-through. BlackRock access remains a separate permitted-source-route issue.
None can be completed by borrowing another ETF's holdings or bypassing access.

## Prioritized next boundary

1. Investigate 00736's same-date official stock/asset reconciliation; require
   independent evidence and a bounded contract before any new import rule.
2. Inspect permitted component-history routes for 00660 and 00920, preserving
   ACTUAL versus estimated and publication/paid-history cutoffs. Measure an
   actual replay after any separately approved recovery; no uplift is promised.
3. Keep formal ACTUAL/76W expansion as source-review work. One event cannot be
   relabeled as market coverage, and estimated realized gains are not 76W.
4. Treat fund-size/expense expansion, distribution period and stock dividend
   as explanatory-field work requiring exact source/period/schema evidence,
   not prerequisites invented for otherwise working planner cases.
5. Owner acceptance is still required to freeze the explicit residual-data
   boundary before V5-4 resumes. Do not close #100 as database-complete or
   silently declare that the current coverage percentages are sufficient.

This ordering is an evidence-based recommendation, not approval of new sources.
No financial, tax, grading, deployment or SEC-4 decision is made by this report.

## Reproduction and references

Merged-main verification on 2026-09-10: 1,184 tests passed (233.877 seconds),
compileall and diff checks passed. The read-only replay preserved the candidate
hash, returned SQLite integrity `ok` and zero foreign-key violations. Its full
field coverage/items, eight planner-case objects, reference evidence and audit
acceptance flags match the prior #131 candidate audit exactly. Matrix checks
confirmed 263 x 18 fields and 8 x 263 unique ETF decisions. No earlier test run
is substituted for this merged-main validation.

```powershell
python -m deployment.v5_full_database_audit --database <immutable-candidate.db> --evaluated-on 2026-09-06 --output <new-audit.json>
python -m compileall -q backend frontend tests deployment
python -m unittest discover -s tests -p "test_*.py"
git diff --check
```

For issuer counts, call `build_constituent_batch_plan`, select only
`ELIGIBLE_AUTOMATED` / `SOURCE_NOT_AUTOMATED` rows with an issuer, and pass their
ETF/issuer keys to `evaluate_constituent_data_quality` at 2026-09-06 with default
thresholds. This is read-only; do not call the batch import runner.

Local candidate location is recorded in `AI_HANDOFF.md`. Full audit artifacts
remain ignored; no database, downloaded document or raw logs are committed.
Related contracts and source evidence:

- [Annual expense contract](ANNUAL_EXPENSE_CONTRACT.md)
- [Cathay source recovery](V5_3E_CATHAY_OFFICIAL_RECOVERY.md)
- [Nomura stock reconciliation](V5_3D_NOMURA_STOCK_RECOVERY.md)
- [Constituent source audit](ETF_CONSTITUENT_SOURCE_AUDIT.md)
- [V5 data/result iteration](V5_DATA_RESULT_ITERATION.md)
