# Cathay official-source recovery (Issue #103)

This change implements the issue's official-first retry, not the conditional
third-party top-10 fallback. It is not a source-license approval or launch gate.

## Verified request mapping

On 2026-09-06 the public issuer API at
`https://cwapi.cathaysite.com.tw/api/ETF/` returned a 41-entry ETF catalog from
`GetETFDetailPriceList?Keyword=&orderBy=0&orderType=2&status=1`.
Resolve each exact `stockCode` to `fundCode`; the page route `ECN` for 00878 is
not its API fund code `CN`. Verify both fields through `GetETFInfoMain`.

`GetETFAssets` with empty `SearchDate` selects the latest disclosure. An explicit
2026-09-06 weekend query returned code 4005, while the empty query returned
`preDate=2026/09/04`. Use that actual date in `GetETFDetailStockList`, not the
fetch date. Keep source URL and UTC fetch timestamp. HTTP errors, malformed
responses, oversized responses, identity mismatch, stale/future dates and
invalid weights fail closed. No credentials, browser cookies or access-control
bypasses are used. Network availability is not guaranteed.

## Bounded live probe

The current catalog has 28 non-bond/non-currency-suffix entries. This is a
different denominator from the fixed V5-3D 22-target calculation cohort; it is
not a rerun of that candidate database or its 2026-09-02 planner.

The following 18 responses passed direct-stock parsing, with effective dates
2026-09-03 or 2026-09-04: 00922, 00916, 00909, 00898, 00893, 00881, 00878,
00875, 00830, 00770, 00737, 00735, 00702, 00701, 00668, 00657, 00636, 00400A.
00878 returned 29 rows totaling 97.28%, not a normalized 100%.

Seven returned no stock list: 00852L, 00689R, 00688L, 00669R, 00664R, 00663L,
00656R. Two had less than 90% stock coverage: 00736 and 00655L. These remain
unavailable. Leveraged/inverse product gates are unchanged.

009817 exposed one 98.19% position named `DAIWA ETF - TSE REIT INDEX` with code
`1488.JP`. The nominal stock endpoint therefore cannot be assumed to contain
only direct stocks. The adapter rejects explicitly named ETF/ETN/UCITS/futures
positions instead of presenting underlying fund overlap as direct equity
overlap. This conservative name check is not a complete instrument classifier;
unrecognized fund names remain a source-review limitation. No look-through or
borrowed share-class holdings are invented.

## Remaining work

No production database was changed. Candidate import and the fixed-universe
planner replay remain separate validation work. The old 2026-09-02 report is
not silently overwritten with later snapshots. BlackRock, other issuer gaps,
ACTUAL/76W, missing detail fields and grading decisions are not solved here.
Human CODEOWNER review is required before merge or public source use.
