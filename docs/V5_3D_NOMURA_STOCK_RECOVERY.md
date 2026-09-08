# V5-3D: dated Nomura stock reconciliation

Refs #120; parent #100. Baseline main `7aca5cc` (merged #119). This is not
V5-3E, a source-release approval or a public-launch decision.

## Observed blocker and correction

The prior fixed 2026-09-06 candidate rejected 00985A because its directly
disclosed stocks totaled 88.02%, below the generic source floor of 90%.
The existing calculation-quality floor is 85%. A bounded Nomura path now
requires independently reported same-date stock assets and fund AUM to
reconcile that lower stock percentage. No global threshold is lowered.

The official `GetFundAssets` POST with `FundID=00985A` and ISO
`SearchDate=2026-09-04` returned:

- Stock table effective date: 2026-09-04.
- 50 stock rows, including one reported zero-weight row; total 88.02%.
- Fund AUM: 10,522,630,721; separately reported TWD stock assets: 9,261,892,790.
- A separate futures table, which is not imported into stock overlap.

The reconciliation rule and rounding bound are in
`ETF_CONSTITUENT_CONTRACT.md`. We preserve the original disclosed weights;
neither the difference to 100% nor missing composition is inferred.
The parallel check of 009812 found nested ETF and futures tables, not direct
stocks. It remains unavailable; no ETF look-through or copied class mapping
was introduced.

## Local candidate preservation

A new exclusive-create candidate was copied from the prior fund-size candidate;
no production database or earlier candidate was overwritten. The source was
retrieved through Windows normal verified HTTPS, with no credentials, custom
identity, redirects or TLS weakening. Captured parsed JSON is retained locally.
This execution validates that response through the parser, not unattended
Python transport reliability. The historical Python fetch path is covered by
mocked transport tests.

- Prior candidate SHA-256:
  `1515a5485eab2bbd418095f051849ffd2fe7a0bca20eed3c1f23063816b9a349`.
- New candidate SHA-256:
  `aa3940dd72ccde1c5a726309911016e78306300bb1219477ec143695117b321d`.
- Original source database remains unchanged at
  `4c2cabb98b4df0be79700d99a138d2d11d95da1e153733112945d0f4c513e2fc`.
- Locally serialized parsed source JSON SHA-256 (not HTTP wire bytes):
  `1b2b90359e334ddc19110f602fc05c14c1121b1f48a953f9ce24f9dbb9db9112`.
- Read-only comparison preserved every prior row in all 15 existing tables;
  only one constituent snapshot and its 50 positions were added.
- Integrity check: `ok`; foreign-key violations: 0.
- Constituent quality coverage: 145/157 -> 146/157; issuer coverage stays
  20/21. Eleven ETF gaps remain. This does not establish full data completeness.
- Fund-size coverage remains 29/263; ACTUAL and formal 76W remain 1/263.
  Expense ratio, distribution-period and stock-dividend gaps remain unchanged.

## Full-market replay

All eight cases completed without exceptions at fixed evaluation 2026-09-06.
Each retains all 263 market candidate decisions. The new candidate hash was
unchanged after this read-only replay. Status and eligible-candidate counts
match the prior eight-case audit; this stock recovery does not claim newly
eligible additions. In particular, 00985A remains excluded for other evidence
gaps (stale data, unstable distributions, missing total return, after-tax cash
and complete dividend components).

| Case | Result | Added ETFs | Eligible candidates |
| --- | --- | ---: | ---: |
| Zero holdings, quarterly 100 | TARGET_MET | 2 | 67 |
| Holding 0050, quarterly 100 | TARGET_MET | 1 | 51 |
| Holdings 0050 + 00878, quarterly 100 | TARGET_MET | 1 | 50 |
| Zero holdings, all months 3000 | TARGET_MET | 2 | 67 |
| Unsupported holding | UNAVAILABLE | 0 | 0 |
| Formal zero target | TARGET_MET | 0 | 67 |
| Holding 00929, all months 3000 | TARGET_MET | 3 | 66 |
| Missing-reference-price holding | UNAVAILABLE | 0 | 0 |

The broad existing-holding acceptance flag remains false because it includes
the two deliberate negative cases. No gate was removed to make them pass.

## Review boundaries

Validation on the final implementation: 14 dedicated reconciliation tests,
39 constituent-adapter tests, and 1,149 full regression tests passed
(199.781 seconds for the final full run). `compileall` and `git diff --check`
passed. Tests use synthetic data; live source validation and the eight-case
replay are separate local evidence described above.

Raw responses, databases, audit artifacts and machine-specific handoff remain
local and uncommitted. Human CODEOWNER review is required for the source change.
No UI, allocation objective, tax formula, grading or deployment changed.
Rollback is a reviewed code revert and continued use of the preserved prior
candidate, not deletion of evidence or automatic production mutation.
