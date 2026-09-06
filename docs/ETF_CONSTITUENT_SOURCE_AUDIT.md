# ETF Constituent Source Audit

## Scope and status meanings

The acceptance baseline is the 23-issuer universe in the TWSE ETF issuer
filter. Representative product codes and product types were cross-checked
against the TWSE `t187ap47_L` official fund master on 2026-08-13.

- `AUTOMATED`: a complete official payload is parsed, validated and persisted.
- `FULL_DISCLOSURE_VERIFIED`: the official issuer page exposes complete
  holdings or a PCF, but this repository does not yet automate it.
- `ENTRYPOINT_VERIFIED`: the official product or PCF application exists, but a
  stable complete response and ETF-code mapping still need verification.
- `NOT_APPLICABLE`: the issuer currently has no equity constituent portfolio.

Finding an official page is not equivalent to automation. Only `AUTOMATED`
sources may be imported without additional issuer-specific work. The current
registry has no entrypoint-only issuer: all applicable issuers returned a
complete official holdings or PCF response during this audit. Twenty-one sources
now have adapters, including the 2026-09-06 Cathay recovery documented in
`V5_3E_CATHAY_OFFICIAL_RECOVERY.md`. BlackRock remains fail-closed because its
tested official automation paths still do not return usable holdings.

## Issuer matrix

| Issuer | Example | Status | Locator | Finding |
|---|---:|---|---|---|
| Yuanta | 0050 | `AUTOMATED` | ETF code in path | Complete official `PCF/Daily` adapter |
| Fubon | 006208 | `AUTOMATED` | ETF-code query | PCF-to-assets adapter |
| SinoPac | 00930 | `AUTOMATED` | ETF code in path | Official PCF adapter |
| Mega | 00932 | `AUTOMATED` | Internal fund ID | Catalog mapping plus holdings adapter |
| Cathay | 00878 | `AUTOMATED` | Catalog-resolved API fund code | Latest dated official stock list with strict coverage gates |
| First | 00408A | `AUTOMATED` | Internal fund ID | ETF catalog plus reconciled asset-weight API |
| Fuh Hwa | 00929 | `AUTOMATED` | Internal fund ID | Catalog mapping plus asset Excel adapter |
| Capital | 00923 | `AUTOMATED` | Internal fund ID | Catalog identity plus complete buyback API |
| Taishin | 00987A | `AUTOMATED` | ETF code in path | Official holdings adapter |
| CTBC | 00891 | `AUTOMATED` | ETF-code query | Official PCF adapter |
| UPAM | 00939 | `AUTOMATED` | Internal fund code | Catalog mapping plus embedded official asset holdings |
| JKO | 00693U | `NOT_APPLICABLE` | Futures ETF only | Current products are commodity futures trusts |
| Franklin Templeton SinoAm | 00905 | `AUTOMATED` | Internal fund ID | Official catalog and holdings API adapter |
| KGI | 00915 | `AUTOMATED` | Internal fund ID | Catalog discovery plus complete holdings table |
| UOB | 00918 | `AUTOMATED` | Internal fund ID | Event mapping plus official PCF adapter |
| Nomura | 00944 | `AUTOMATED` | ETF code in request body | Official `GetFundAssets` adapter |
| E.SUN | 009803 | `AUTOMATED` | Internal fund ID | Overview mapping plus official `GetFundAssets` adapter |
| Union | 009804 | `AUTOMATED` | Form selection | Live fund discovery plus official holdings adapter |
| HN | 009808 | `AUTOMATED` | ETFID query plus short-lived system token | Public system-token login plus official PCF adapter |
| Allianz | 00984A | `AUTOMATED` | Antiforgery plus internal fund ID | Antiforgery session, overview mapping and `GetFundAssets` adapter |
| BlackRock | 009813 | `FULL_DISCLOSURE_VERIFIED` | Internal product ID | Complete holdings verified; official automation is access-protected |
| J.P. Morgan | 00989A | `AUTOMATED` | ISIN slug | Autocomplete mapping plus official product-data PCF adapter |
| AllianceBernstein | 00404A | `AUTOMATED` | Share-class ISIN | ETF catalog mapping plus reconciled holdings adapter |

Canonical URLs and machine-readable notes live in
`backend/app/data_sources/constituent_source_registry.py`.

## Live API validation evidence

The dynamic sources that required request discovery were exercised against
their official production endpoints on 2026-08-13 and 2026-08-14:

- Nomura `Fund/GetFundAssets` returned 50 stock rows for `00944` and a
  `2026/08/13` data date.
- E.SUN `GetETFOverview` mapped `009803` to internal `FundNo=50`, and
  `GetFundAssets` returned 50 stock rows for `2026/08/13`.
- Union's official form exposed both current ETF codes and accepted bounded
  `FundNo` plus `sDate` submissions. It returned 50 stock rows totaling
  `99.4138%` for `009804` and 30 rows totaling `99.5039%` for `009825`.
- HN's official OpenAPI defines `GET /Stk/PcfData` with the `ETFID` query.
  Its public short-lived system-token flow returned 60 stock rows plus one
  futures row for `009808`, dated `2026-08-13`; the active adapter converts
  fractional weights to percentages and persists only the stock table.
- Allianz's official OpenAPI defines the antiforgery flow and
  `POST /api/Fund/GetFundAssets`. The overview mapped `00984A` to `E0001`;
  the holdings response returned 122 stock rows plus one futures row for
  `2026/08/13`. The same flow returned complete tables for `00993A` and
  `00402A`; `00412A` currently has no fund-asset table and remains fail-closed.
- AllianceBernstein's ETF catalog mapped `00404A` to `TW00000404A5`; its
  holdings API returned 54 equities totaling `89.487277%`. This exactly matched
  the official equity asset total, while the same response separately reported
  futures and options exposure.
- J.P. Morgan's official autocomplete response mapped both current Taiwan ETFs
  to their ISINs. Its product-data response returned 64 equity rows each for
  `00401A` (`92.4829%`) and `00989A` (`98.3042%`), dated `2026-08-13`.
- Capital's official catalog and basic-data API mapped `00923` to `fundNo=365`;
  its buyback API returned 50 stocks totaling `99.1425%`, dated `2026-08-14`.
- First's official ETF API mapped `00408A` to `FundID=183`. Its asset endpoint
  returned 46 stocks totaling `87.75%`, exactly matching the separately declared
  stock-asset total; the remaining allocation was disclosed as cash/other assets.
- UPAM's official catalog mapped `00939` to `46YTW`. The product page embedded
  40 stock rows totaling `96.93%`, dated `2026-08-13`, alongside separate futures
  and cash asset groups.
- KGI's official catalog and detail-page identity mapped `00915` to `J015`.
  The complete server-rendered stock table returned 30 rows totaling `97.04%`,
  dated `2026-08-14`.
- Cathay's public `GetETFDetailStockList` endpoint still returned `4005` / no
  data for the verified `00878` product path and identifiers on `2026-08-14`.
  No adapter is enabled until the official request can be reproduced reliably.
- BlackRock's previously verified complete product holdings remain visible to
  interactive users, but the product page and tested official CSV variants
  returned HTTP 403 on `2026-08-14`. No adapter is enabled while automated
  access remains protected.
- The V5-3C replay on `2026-09-02` recovered eight of thirteen measured
  automated-source failures. Four were transient source-connectivity failures;
  three Fubon products had complete official stock plus futures tables with
  87.8471% to 89.8784% stock weight; and First `00728` reconciled to its 97.19%
  official stock-asset total after one formally zero row was excluded from
  positions.
- `0061` and `009812` expose ETF/futures rather than direct-stock portfolios,
  `00924` exposes only 54.789% unreconciled direct stock weight, and currency
  share classes `00625K` and `00643K` do not resolve to verified official
  holdings. They remain unavailable instead of borrowing another share class.
- Cathay's official product page returned an edge-service HTTP 500 on the
  `2026-09-02` recheck. It remained `FULL_DISCLOSURE_VERIFIED` at that time.
  The 2026-09-06 official catalog/code/date recovery supersedes that limitation;
  the new adapter does not imply all Cathay products pass direct-stock gates.

These observations prove source availability and request mapping. They are not
runtime guarantees: production adapters must still enforce schema, identity,
date, coverage and failure-mode checks before persisting snapshots.

## External market-data APIs

The published Fugle Market Data endpoints provide instruments, quotes,
snapshots, historical prices and technical indicators. Shioaji provides
contracts, quotes, scanners, trading and account data. Neither published API
currently exposes an ETF-to-constituent list with portfolio weights. They may
still be useful later for price history or read-only account synchronization,
but they are not substitutes for issuer portfolio disclosure.

## Next implementation order

1. Direct ETF-code sources: completed for SinoPac, Taishin, CTBC, Fubon and
   Nomura, including identity, date and minimum-coverage validation.
2. Stable internal-ID discovery: completed for Mega, Fuh Hwa, UOB, E.SUN,
   First, Capital, UPAM and KGI. Franklin Templeton SinoAm is also complete.
   Cathay catalog/code/date recovery was verified on 2026-09-06; candidate
   import and fixed-universe replay remain follow-up validation.
3. Stable product-ID or ISIN discovery: completed for J.P. Morgan and
   AllianceBernstein. Revisit BlackRock only when an officially accessible
   catalog and complete holdings response can be verified without bypassing
   access protection.
4. Session-aware sources: completed for HN's short-lived public system token
   and Allianz's antiforgery cookie/header pair.
5. Form-backed sources: completed for Union with live form discovery, identity
   checks and complete stock-table validation.
6. Add freshness and multi-issuer coverage gates before calculated overlap is
   allowed to affect assessment scoring: completed in V2-10. Assessment
   integration remains separate.
