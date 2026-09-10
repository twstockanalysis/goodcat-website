# Official non-distribution evidence

Issue #133, parent #100. The owner approved a separate historical decision
state for two reviewed issuer announcements. This approval is not permission
to change any allocation, freshness, tax or grading rule, or a source-license
approval for automated collection.

## Separate facts

A decision not to distribute at a particular evaluation date is neither a
missing observation nor a paid dividend of zero. It does not establish a
permanent non-distributing product or forecast any future evaluation.
The notice contains no amount, ex-date, payment date or tax composition.
It never creates dividend/component rows or increases ACTUAL/76W coverage.
Old payments and stale component dates remain unchanged.

`etf_non_distribution_notice` has primary key `(etf_code, evaluation_date)`,
an ETF-master foreign key and validated `evidence_json`. The frozen model
retains legal name, evaluation date, publication date, review date, decision,
source URL, evidence method and review reference. Review/publication/evaluation
dates are distinct. It uses `REVIEWED_TRANSCRIPTION`, not a claimed hash-verified
download; no raw document bytes were captured by this importer.

## Bounded approved evidence

| ETF | Evaluation date | Publication date | Decision |
| --- | --- | --- | --- |
| 00660 | 2025-09-30 | 2025-10-01 | No distribution for that evaluation |
| 00920 | 2025-12-31 | 2026-01-02 | No distribution for that evaluation |

Source links are embedded verbatim in the reviewed manifest:

- [00660 issuer-filed announcement](https://www.twse.com.tw/zh/ETFortune/announcement?company=A00005&date=20251001&fund=00660&seq=1&type=all)
- [00920 issuer-filed announcement](https://wwwc.twse.com.tw/zh/ETFortune/announcement?company=A00010&date=20260102&fund=00920&seq=1&type=all)

These notices were reviewed on 2026-09-10. The first describes the annual
September 30 evaluation. The second explicitly leaves ex/payment dates NA.
Neither supplies formal tax composition. They explain only those evaluations,
not every earlier year. Future notices or corrections require separate review.
No scraper, bulk discovery or automatic approval is introduced.

## Persistence and display

Inserts are atomic and exact repeats idempotent. An existing ETF/evaluation key
cannot be overwritten by different evidence. Unknown ETFs, evaluation before
known listing history, inconsistent dates, URL fund/publication mismatches,
extra payment fields and future publication relative to the import cutoff fail.
A conflicting batch rolls back. Corrections require a reviewed migration.

Only `GET /api/v1/etfs/{code}` adds `non_distribution_evidence`:

```json
{"status": "NO_REVIEWED_NOTICE", "items": []}
```

When stored notices published on or before today's date exist, status is
`REVIEWED_NOTICES` and items contain the complete dated records, newest evaluation
first. This means reviewed history is present, not that the latest distribution
decision of the ETF is necessarily non-distribution. A later paid event may
coexist with these historical notices. Empty means no reviewed notice in this
database at the cutoff, not evidence of a payment or of zero.

The detail-information component renders the evaluation date, publication date,
official link and explicit historical-only warning. Old APIs with no field stay
usable. Old databases without this additive table read as no reviewed notice;
reads do not migrate them. List, comparison and internal ETF/solver readers
are intentionally unchanged. The existing 18-field coverage ledger is unchanged;
these two notices are not counted as recovered dividend/component observations.

## Local candidate and validation

```powershell
python -m backend.app.data_sources.reviewed_non_distribution --source-db SOURCE.db --target-db NEW.db --evaluated-on 2026-09-06
```

This replays only the two approved transcriptions, without fetching a website.
It opens the source read-only, creates the target exclusively, backs up SQLite,
initializes only the candidate and inserts the notices. Existing targets, even
the source path, fail rather than overwrite. Failures after creation retain a
diagnostic target which must not be promoted. A later review used in a fixed-date
audit is ex-post reconstruction, not proof of historical online availability.

Verify every prior table row, integrity, foreign keys and original source hash;
replay all eight frozen cases and compare the complete prior audit objects.
Test model/date/conflict/missing/legacy behavior, API and actual Streamlit detail
component rendering. No running service or production database is switched.

## Local acceptance evidence (2026-09-10)

- Focused regression: 23 tests passed; full regression: 1,195 passed in
  263.072 seconds. Compileall and diff checks passed.
- The candidate adds exactly two notices. All 17 pre-existing tables and
  113,153 rows compare equal as multisets; source SHA-256 remains
  `21fef06fdce269a04a1afa205ee7a1f5e734f2ded25d5879e23f29b52ccb320d`.
- Candidate SHA-256:
  `1c52c0edd0d0ad644f07e427c3e10d6a33e222f9b650f50b7c403845b951250e`.
  SQLite integrity is `ok`; foreign-key violations are zero.
- Actual candidate API responses were rendered through the real detail-information
  Streamlit component for 00660, 00920 and no-notice 0050. Dates, source links,
  historical-only/no-zero warnings and the no-reviewed-notice state passed.
  This is component acceptance, not a live browser/service switch.
- Fixed-date 2026-09-06 audit matches the prior candidate's complete field
  coverage/items, eight planner-case objects, reference evidence and acceptance
  flags. Six TARGET_MET and two intentional UNAVAILABLE cases remain unchanged;
  the aggregate all-holding-cases eligibility flag remains false because it
  includes the intentional negative cases. No all-flags-pass claim is made.
  Candidate and source hashes remain unchanged after the read-only audit.
