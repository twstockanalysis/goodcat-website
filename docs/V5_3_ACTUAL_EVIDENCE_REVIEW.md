# V5-3: bounded Cathay composition evidence review

Refs #100. This follow-up starts from `64c5a82`, after merged #113 and #115.
It changes discovery/review routing only, not source approval or ACTUAL imports.
The prior candidate and its September 6 evaluation boundary remain unchanged.

## Reproduced gap and correction

One bounded 00878 API request (page 1, 20 entries) reported 54 total available
announcements. The existing title filter returned eight PDF candidates and
rejected the November 2024 `收益分配期中公告` (document 5524).
The corrected filter includes that title variant: nine candidates and eleven
rejections within this page. This is not full-history discovery or nine
verified ACTUAL documents. Preannouncement/estimated titles remain rejected.

The API keyword is a search hint, not verified ETF identity. The review screen
requires the document's own securities code and refuses missing/conflicting
identity. It also records future announcement dates, empty extracted pages,
estimated composition wording and absence of explicit actual composition.

## Observed document semantics

- [Official document 6079](https://cwapi.cathaysite.com.tw/uploads/07cathaynews__online/6079.pdf)
  is dated August 13, 2026. Its first page announces an actual distribution
  amount; its later composition table and warning explicitly describe
  estimates. The presence of a 76W label does not make its values formal ACTUAL.
- [Official document 5524](https://cwapi.cathaysite.com.tw/uploads/07cathaynews__online/5524.pdf)
  is dated November 13, 2024. It likewise distinguishes the distribution amount
  from estimated composition and directs readers to the distribution notice.

The public web reader exposed these documents' text. The normal verified-TLS
direct PDF request returned HTTP 403 on the first candidate, so the local batch
stopped. No completed local batch download, checksum set, complete
visual PDF review, or production PDF parser validation is claimed. The other
seven candidate documents have not been classified from their content.
No alternate identity, authentication bypass, TLS weakening, or retry flood
was used. Raw documents and operational logs are not included in this PR.

## Review-only screening contract

`screen_cathay_document` consumes the discovered metadata and text extracted
from **every** PDF page. Preserve the original PDF, checksum, extraction tool
and retrieval date outside Git; visually compare the identity, tables and
footnotes before relying on extracted text. Empty pages fail closed because
they may contain unextracted scanned evidence.

- Any detected blocker returns `EXCLUDED_FROM_ACTUAL` with explicit reasons.
- Explicit actual-composition wording without a detected blocker returns
  `HUMAN_REVIEW_REQUIRED`, never approval.
- Every return has `actual_import_allowed = false`.
- Actual distribution amount alone does not establish actual composition.
- Estimated composition elsewhere in the document takes priority over actual
  wording, including whitespace-split extraction and estimated tax-code rows.
- The function never parses financial values, infers tax codes, fills zeros,
  connects to SQLite or invokes an importer. Human review and the existing
  accepted source/parser/matching contract remain necessary.

This is conservative triage, not a complete semantic PDF classifier. A missed
wording variant can only lead to human review, not automatic import. A paid
date later than evaluation is still handled by existing paid-history logic;
this screen checks the announcement date, not portfolio cash-flow eligibility.

## Outcome and next safe step

Formal ACTUAL coverage has **not increased** in this execution. Both observed
documents are unsuitable for importing formal composition; the database was
not modified. The unchanged candidate hash remains
`f97dd5f29f488a1bcd66650362a4003d417957a7d40afdcc964c9022b2bcb748`.

For further acquisition, use a permitted reproducible official document path,
or obtain a reviewed public/non-personal official distribution notice through
an authorized channel. Never upload private notices containing account,
identity or holdings data. A new format requires scoped parser fixtures/tests
and human CODEOWNER approval before activation. Estimates remain estimates;
source access failure is not permission to substitute them.

Fund-size, expense, distribution-period, stock-dividend and other constituent
gaps remain separate work. No V5 completion, grading or release decision is made.

## Validation

- 16 focused discovery/review tests passed using synthetic content.
- Full regression on the final change: 1,121 tests passed in 244.009 seconds.
- `compileall` and `git diff --check` passed, using isolated Python 3.12 with
  `requirements.lock` dependencies.
- Live corrected discovery: 9 candidates / 11 rejections, including 5524.
- Complete visual/source-import validation was not performed because the
  official direct-download path refused access. This does not waive review.
