# Reviewed annual expense evidence

Issue #130 implements the owner-confirmed bounded follow-up to
[the source review](V5_3D_EXPENSE_SOURCE_REVIEW.md). Approval covers only the
exact reviewed 0056 document, not a generic issuer feed or future documents.
Human CODEOWNER review of implementation remains required.

## Meaning and provenance

The hash-locked importer transcribes page 3 of the 2026-07-29 Yuanta product
1084 simplified prospectus. SHA-256 is
`b098c8bd46ccc01037fbbf319c10465646475ba69598542941ebd2b3a2b39e50`.
Annual percentages for 2021–2025 are respectively 0.74, 0.86, 0.56, 0.60,
and 0.57. These are historical total fund expenses, including transaction
costs, not current management fees or forecasts. No linked-fund/share-class
substitution is permitted. Other documents fail the hash check.

Each immutable observation retains ETF code, issuer product ID, legal name,
TWD currency, reporting year, decimal percentage, historical basis, publication
date, captured retrieval timestamp, document URL/hash/page, identity URL and
review reference. Retrieval and publication are not the reporting period.
The retrieval timestamp describes the reviewed local capture, not each replay.

Missing remains missing; explicit zero is valid. Non-finite, negative and
over-100 percentages, invalid identity links and incomplete/future reporting
years are rejected. Publication must follow the completed reporting year and
not exceed the import evaluation date. Retrieval cannot precede publication.
The conservative full-year gate requires a known listing date no later than
January 1 of the reporting year. Partial-year/new-fund imports require separate
review; this pipeline does not annualize them.

## Persistence and selection

`etf_annual_expense_evidence` is additive, keyed by ETF and year. Inserts are
atomic. Exact repeats are idempotent (a later retrieval does not rewrite the
original capture). Conflicting evidence rejects the entire batch; corrections
need a separately reviewed migration. No existing master values are overwritten.

ETF list/detail reads select the latest completed annual observation whose
publication date is on or before today's date. Fixed-date coverage audits use
their explicit evaluation date. `expense_ratio` remains a numeric percentage
for compatibility, enriched from selected evidence; `annual_expense` exposes
its full provenance. Old databases without the table remain readable and are
not migrated by reads. Legacy bare values remain legacy, not reviewed evidence.
The detail page labels the historical year, publication date and official source;
legacy values warn that year/source evidence is absent.
Search and comparison rows also label reviewed values with the historical year
and total-expense basis; the official document link is on the detail page.

There is no inferred 18-month expiry rule. A fixed-date audit using a later
retrieval is an ex-post reconstruction from published evidence, not proof that
these exact bytes were accessible online on that historical date.

## Local candidate workflow

```powershell
python -m backend.app.data_sources.reviewed_annual_expense --source-db SOURCE.db --target-db NEW.db --reviewed-pdf REVIEWED.pdf --evaluated-on 2026-09-06
```

The source is opened read-only and backed up into an exclusively created target.
An existing target is never overwritten. Only the new candidate is initialized
and imported. A failure after target creation retains the diagnostic candidate;
it must not be promoted. Verify source hash and every pre-existing table row,
then run the fixed-date full-market audit before considering the candidate usable.

Coverage counts ETFs with selected evidence, not observation rows: five annual
rows for 0056 represent one ETF, not five ETFs. The legacy master column can
remain NULL while API/coverage reads expose reviewed evidence. This is not a
263-ETF bulk import. No service restart, production write, V5-4 change, financial
solver change, deployment or SEC-4 approval is included.

## Measured local acceptance (2026-09-10)

The isolated candidate adds five 0056 observations. All 16 pre-existing tables
and 113,148 rows compare equal as multisets. SQLite integrity returns `ok` and
foreign-key checking finds no violations. The source SHA-256 remains
`aa3940dd72ccde1c5a726309911016e78306300bb1219477ec143695117b321d`.

At evaluation date 2026-09-06, expense coverage changes from 0/263 to 1/263;
262 ETFs remain unavailable. All eight complete planner-case objects compare
identically against a same-code baseline audit, including full-market evidence.
Six cases return TARGET_MET; the unsupported-product and missing-reference-price
negative cases remain UNAVAILABLE. The audit's aggregate
`existing_holding_cases_have_eligible_candidates` flag remains false because it
includes these negative cases; this is not a new regression or a claim that
every audit flag passes.

The candidate API feeds the actual detail-information Streamlit component in
AppTest: 0056 displays 2025 / 0.57%, the historical-cost warning and source link.
This verifies the changed component, not a live browser/service switch. The
original running services and their database were not changed.
