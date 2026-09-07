# V5-3D: dated fund-size evidence

Refs #118, parent #100. High-risk source/additive-schema change; human
CODEOWNER review remains required. This does not approve a source for release.

## Meaning and source boundary

The existing `ETFResponse.fund_size` unit remains TWD 100 million. For this
bounded Cathay adapter it means reported total fund net assets (`fundNav` in
`GetETFAssets`) divided by 100,000,000. It is not `fundPerNav`, market price,
market capitalization or NAV multiplied by a guessed share count. No expense
ratio, FX conversion, component, tax or suitability conclusion is derived.

Resolve exact securities code and fund code through the existing official
`GetETFDetailPriceList` catalog and verify both in `GetETFInfoMain`. Only the
explicit currency label `新台幣` is accepted. Missing/other currencies and
unverified share-class mappings fail closed rather than copy another class.

`GetETFAssets.preDate` is the effective date. The requested historical date
must be returned exactly; it must be on/before evaluation and no more than
seven days old. No implicit latest-date or weekend fallback is performed.
Use an explicit business-date `snapshot_on` when appropriate. Retrieval is
opt-in, with the existing bounded JSON reader, TLS verification, timeout and
no redirect following. This is not an unattended scheduler.

Blank, malformed, negative and non-finite totals are rejected. A reported
numeric zero is preserved as zero. Exact reported Decimal text is stored;
the existing scalar API/SQLite REAL projection retains its float behavior.

## Additive provenance and projection

Initialization adds `etf_fund_size_evidence` with `CREATE TABLE IF NOT EXISTS`;
existing tables and data are not rebuilt or deleted. Each row stores code,
fund code, currency, effective date, timezone-aware fetch timestamp, reported
TWD total, source ID/URL, canonical parsed source JSON and its SHA-256. The
hash identifies the canonical evidence JSON, not the original HTTP wire bytes.
The evidence JSON contains the catalog row, identity and asset response.
Unrelated current fields in an identity response do not change the historical
asset date or become historical price facts.

`(etf_code, as_of_date, source_id)` is immutable through this repository.
An identical value/fund/currency reuses the first evidence row without changing
its timestamp/hash. A conflicting same-key financial value fails; source
corrections need a separately reviewed versioning decision. Evidence insertion
and updating `etf_master.fund_size` occur in one transaction. Any failure rolls
back both. Older evidence may be retained but cannot replace newer projection.
A legacy non-null size with no managed evidence is not silently overwritten.

The legacy API exposes the scalar latest-imported projection, not an as-of
query or freshness guarantee. The dated evidence table is the audit source.
This field is not currently consumed by allocation/assessment services; no
new grading, risk score, eligibility gate or public date-display contract is
introduced. Provenance-aware UI/API expansion is separate work.

## Local 2026-09-06 candidate evidence

- Code baseline: `b0b6d7d` (merged #117).
- Fixed evaluation: September 6, 2026; requested assets: September 4, 2026.
- Official catalog: 41 entries. 29 exact matches in the fixed 263-ETF candidate
  imported; 12 were outside that candidate. No universe expansion was made.
- Fund-size detail availability increased from 0/263 to 29/263; 234 remain
  unavailable. This includes funds whose constituent overlap remains missing;
  knowing total assets does not establish equity constituent completeness.
- Example 00878: reported TWD 645,680,113,181 -> 6,456.80113181 TWD 100 million.
- The Python transport returned 403; the same public API succeeded through
  Windows default HTTPS, without credentials, custom identity, redirects or
  disabled verification. Local operations used the unchanged parser on those
  responses. The Python fetcher is not claimed reliably live-validated.
- New candidate SHA-256:
  `1515a5485eab2bbd418095f051849ffd2fe7a0bca20eed3c1f23063816b9a349`.
  Integrity `ok`, zero foreign-key violations.
- Prior candidate remains unchanged at
  `f97dd5f29f488a1bcd66650362a4003d417957a7d40afdcc964c9022b2bcb748`.
  Original source remains unchanged at
  `4c2cabb98b4df0be79700d99a138d2d11d95da1e153733112945d0f4c513e2fc`.
- Read-only comparison confirmed every pre-existing table's facts unchanged,
  excluding only `etf_master.fund_size`. New evidence has 29 rows. The 18-field
  coverage audit changed only the fund-size count. ACTUAL/76W remain 1/263;
  expense ratio, distribution period and stock dividend remain unavailable.

## Validation and limitations

14 focused tests and 1,135 full regression tests passed (186.191 seconds), with
`compileall` and `git diff --check`. Tests cover units, zero/missing, identity,
currency, dates, duplicate imports, conflicts, older/newer projection, legacy
protection, additive initialization and transactional rollback. Runtime:
isolated Python 3.12 from `requirements.lock`.

The eight-case full-market planner replay was not rerun for this scalar-only
addition. All planner regression tests ran, existing calculation facts were
compared unchanged, and no service consumes `fund_size`. No new full-market
allocation outcome is claimed. Raw responses, databases, logs and local
operational scripts stay outside Git. Revert code to stop further ingestion;
do not delete provenance or overwrite prior databases as an automatic rollback.

Remaining V5-3 sources/fields, V5-4 acceptance, grading and release gates are
unchanged. This is neither full database completion nor a launch decision.
