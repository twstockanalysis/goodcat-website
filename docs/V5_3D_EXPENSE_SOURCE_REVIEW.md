# V5-3D expense-ratio source review

Related: #124 and #100. Review date: 2026-09-08.
Code baseline: `58d4d79e0b9c1c8867a7bdddc14668c85164e26a`.

## Outcome and scope

A reproducible issuer-hosted annual expense table is available for a bounded
0056 sample. This is an evidence and contract proposal, **not source approval
or an import implementation**. The existing candidate remains at 0/263 expense
ratio coverage. No database, source registry, API, UI, allocation or grade was
changed. Human CODEOWNER review remains required before source promotion.

## SITCA discovery limitation

The [SITCA directory](https://www.sitca.org.tw/ROC/Industry/IN2002.aspx?PGMID=IN)
links to the [monthly/quarterly/annual expense query](https://www.sitca.org.tw/ROC/Industry/IN2211.aspx?pid=IN2222_01).
Web retrieval exposed the form but not selected annual rows. Direct Windows
HTTPS, Python verified-TLS requests and an in-app browser navigation failed
with connection closure or timeout. This proves a limitation of these attempts,
not that the public source has no data. No TLS weakening or authentication
bypass was attempted.

The form notes active ETF reporting starts in December 2025. Do not infer that
all active ETFs have full-year 2025 expense observations. An explicit annual
report and its period rules are still needed. SITCA fund-identifier/share-class
mapping has not been verified for bulk acquisition.

## Reproducible alternative sample

- [Issuer product page](https://www.yuantafunds.com/myfund/information/1084)
  explicitly identifies securities code `0056`; `1084` is the issuer product
  identifier, not an exchange code. Do not infer mappings from filenames alone.
- [Issuer simplified prospectus](https://www.yuantafunds.com/fund/download/1084%E5%8F%B0%E7%81%A3%E9%AB%98%E8%82%A1%E6%81%AF-%E7%B0%A1%E5%BC%8F%E5%85%AC%E9%96%8B%E8%AA%AA%E6%98%8E%E6%9B%B8.pdf):
  four pages, retrieved over ordinary HTTPS on 2026-09-08.
- Retrieved PDF SHA-256:
  `b098c8bd46ccc01037fbbf319c10465646475ba69598542941ebd2b3a2b39e50`.
- Printed page 1: fund identity, TWD denomination, establishment on
  2007-12-13, and publication date 2026-07-29.
- Printed page 3: five annual expense observations and the definition directly
  below the table. Local text extraction was checked against rendered pages
  1 and 3; year/value column alignment and the footnote were visually verified.

| Reporting year | Published expense ratio (%) |
| --- | ---: |
| 2021 | 0.74 |
| 2022 | 0.86 |
| 2023 | 0.56 |
| 2024 | 0.60 |
| 2025 | 0.57 |

The footnote describes fund-borne costs relative to average net assets,
including transaction costs and accounting expenses. Thus these observations
are not merely the contractual management and custody rates listed separately
on that page. They are historical annual facts, not guaranteed future costs.
The 2026-06-30 date above the performance table must not become the expense
reporting year. Retrieval time, document publication and measurement period
are separate facts. Publication date alone does not prove the original online
availability date of these exact bytes.

The separate Yuanta B7 share-class table appeared in discovery, but it is not
accepted as an ETF bulk source here: related names such as ETF-linked funds do
not establish identity with the exchange-traded fund. No rows from that table
were imported or visually accepted as ETF evidence.

## Proposed import contract for human review

The current `expense_ratio` API field specifies a percentage but carries no
reporting year. The detail page renders the numeric value without an expense
year. A bare master-field write would therefore lose material context.

Before implementation, approve an additive dated-evidence design that retains:

- exact ETF code, issuer product ID, legal fund identity and currency/class;
- explicit reporting year, published decimal percentage and total-cost basis;
- document URL, publication date, retrieval timestamp, content hash, page and
  table location, and identity-mapping evidence;
- human review reference, without assigning approval automatically.

Display/API behavior must expose the expense year and historical basis before
the master value is made visible. Proposed selection is the latest reviewed
completed annual observation compatible with the evaluation date, with a
separate publication-date cutoff. This is not yet an approved freshness policy
or a strict historical-online-availability reconstruction. Do not reuse the
dividend-component 18-month policy without a separate decision.

For subsequent implementation, fail closed on missing years, malformed or
non-finite numbers, ambiguous identity, conflicting values, partial periods,
future publication/periods and changed table layouts. Preserve explicit zero
only when actually reported; `NA`, blank and absent rows remain missing.
New-fund partial-year values need a separately reviewed period policy, not
automatic annualization. Exact repeats should be idempotent and conflicting
evidence must not overwrite prior facts. Use a new no-overwrite local candidate.

## Required next acceptance

1. Human review of the issuer alternative, annual-cost definition and proposed
   provenance/display contract; this document alone grants no source approval.
2. A separately scoped implementation with schema/API/UI ownership coordination,
   deterministic parser/identity/date/zero/conflict tests and full regression.
3. Reconcile accepted and rejected ETF rows, preserve every prior database row,
   and report actual coverage after import. One reviewed sample does not prove
   a 263-ETF pipeline or close #124's SITCA-specific acceptance criteria.
4. Replay the fixed 2026-09-06 audit separately; do not claim planner improvement
   from source discovery. V5-4 and SEC-4 remain outside this work.

The untouched prior candidate has SHA-256
`aa3940dd72ccde1c5a726309911016e78306300bb1219477ec143695117b321d`.
No new candidate was created during this review.
