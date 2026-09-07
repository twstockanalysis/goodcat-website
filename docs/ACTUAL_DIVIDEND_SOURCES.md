# Actual Dividend Source Documents

## Purpose

M8-4B adds traceable official-source documents before an actual dividend
composition enters the M8-4A import path.

The source document layer preserves:

```text
source ID
stable source document ID
official URL
document date
download timestamp
content type
SHA-256 checksum
snapshot path
metadata path
parse status
parse error
linked import batch
```

## Source Modes

Formal dividend sources use one of these modes:

```text
DISCOVERY_ONLY
MANUAL_IMPORT
VERIFIED_ADAPTER
DISABLED
```

A source being listed does not mean that all pages from the source are
acceptable as `ACTUAL`.

TWSE ETF e添富 remains `DISCOVERY_ONLY` for actual composition because its
composition percentages are estimated.

## First Verified Adapter

The first verified adapter is:

```text
cathay_actual_dividend_announcement
```

It accepts only official Cathay SITE announcement URLs under:

```text
cathaysite.com.tw
www.cathaysite.com.tw
```

The adapter requires explicit actual wording such as:

```text
實際配發金額組成如下
```

It rejects pages containing estimated wording such as:

```text
預估收益分配組成
預估配息組成
估算配息組成
以收益分配通知書為準
```

The adapter preserves official component codes and descriptions. It does not
infer a tax code for an uncoded description.

## Document Versioning

A source document version is identified by:

```text
source ID
+ stable source document ID
+ SHA-256 checksum
```

Importing the same content again reuses the existing version.

When the official HTML changes, a new version number and a new content-addressed
snapshot are preserved.

## Pipeline

A reviewed local HTML file can be processed with:

```powershell
python -m backend.app.data_sources.cathay_actual_dividend_pipeline `
    --url "https://www.cathaysite.com.tw/announcement/5141" `
    --etf-code 00878 `
    --input-html .\data\imports\cathay_5141.html
```

Network retrieval is never implicit. To explicitly permit one download:

```powershell
python -m backend.app.data_sources.cathay_actual_dividend_pipeline `
    --url "https://www.cathaysite.com.tw/announcement/5141" `
    --etf-code 00878 `
    --allow-network
```

Before using network retrieval, confirm that the page remains publicly
accessible and that automated retrieval complies with the source's current
terms and operational limits.

When the matching parent event is outside the current TWSE page, request a
bounded official history explicitly:

```powershell
python -m backend.app.data_sources.dividend_pipeline `
    --etf-code 00878 `
    --start-year 2023 `
    --end-year 2023 `
    --preserve-event-on-invalid-estimates
```

The final flag preserves a parent event only when its own dates and amount are
valid. Any incomplete or abnormal estimated composition is still rejected and
reported; it is never imported, repaired, or converted to ACTUAL.

## Processing Flow

```text
official HTML
-> content-addressed source snapshot
-> dividend_source_document record
-> verified issuer adapter
-> M8-4A standard JSON
-> existing dividend-event matcher
-> ACTUAL component upsert
```

The adapter does not create a missing dividend event and does not select among
ambiguous events.

## Parse Status

Source documents use these statuses:

```text
downloaded
parsed
rejected
failed
```

`rejected` means the document was preserved but did not satisfy the verified
ACTUAL parsing policy.

`failed` means the document parsed as ACTUAL but a later pipeline operation
failed.

## Current Boundary

M8-4B verifies one historical Cathay announcement format.

It does not yet provide:

```text
automatic announcement discovery
scheduled issuer-site crawling
OCR or PDF extraction
all-issuer format support
tax-code inference
```

Additional issuers require their own official-source review, fixture and
adapter tests before activation.

## Review-stage discovery follow-up

The Cathay announcement-list discovery now also recognizes the interim-notice
title variant `收益分配期中公告`. A discovered PDF is only a candidate: actual
distribution amounts can coexist with estimated composition, even with tax
codes printed in the appendix. `cathay_actual_evidence.screen_cathay_document`
offers conservative, non-importing review routing; it never grants ACTUAL
approval. See `V5_3_ACTUAL_EVIDENCE_REVIEW.md` for the contract, bounded evidence
and unresolved direct-download access limitation.
