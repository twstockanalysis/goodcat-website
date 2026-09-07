"""Conservative review routing, never ACTUAL import or source approval."""

from datetime import date
import re

from backend.app.data_sources.cathay_actual_dividend_discovery import (
    CathayAnnouncementCandidate,
)


def screen_cathay_document(
    candidate: CathayAnnouncementCandidate,
    *,
    etf_code: str,
    evaluated_on: date,
    page_texts: list[str],
) -> dict:
    """Screen all extracted pages; an apparent match still needs human review.

    Callers must retain the original PDF/checksum and inspect its tables. Text
    extraction cannot prove that a scanned or malformed table was understood.
    No component code, amount, or official-zero value is inferred here.
    """

    code = etf_code.strip().upper()
    if not re.fullmatch(r"[0-9]{4,6}[A-Z]?", code):
        raise ValueError("Invalid ETF code")
    normalized_pages = [re.sub(r"\s+", "", text) for text in page_texts]
    text = "\n".join(normalized_pages)
    reasons = []
    if candidate.declared_date > evaluated_on:
        reasons.append("FUTURE_DOCUMENT")
    if not page_texts or any(not page for page in normalized_pages):
        reasons.append("INCOMPLETE_TEXT_EXTRACTION")
    disclosed_codes = set(re.findall(r"證券代號[：:]([0-9]{4,6}[A-Z]?)(?![0-9A-Z])", text))
    if disclosed_codes != {code}:
        reasons.append("ETF_IDENTITY_UNVERIFIED")
    estimated_markers = (
        "預估收益分配組成", "預估配息組成", "估算配息組成",
        "預估每單位受益權", "預估占比", "預估佔比",
        "以收益分配通知書所載", "以實際收益分配通知書所載",
    )
    matched = [marker for marker in estimated_markers if marker in text]
    if matched:
        reasons.append("ESTIMATED_COMPONENTS_NOT_ACTUAL")
    actual_markers = ("實際配發金額組成如下", "實際收益分配組成", "實際配息組成")
    explicit_actual_composition = any(marker in text for marker in actual_markers)
    if not matched and not explicit_actual_composition:
        reasons.append("NO_EXPLICIT_ACTUAL_COMPOSITION")
    return {
        "document_id": candidate.document_id,
        "source_url": candidate.document_url,
        "declared_date": candidate.declared_date.isoformat(),
        "evaluated_on": evaluated_on.isoformat(),
        "etf_code": code,
        "page_count": len(page_texts),
        "routing": "EXCLUDED_FROM_ACTUAL" if reasons else "HUMAN_REVIEW_REQUIRED",
        "reasons": reasons,
        "estimated_markers": matched,
        "actual_import_allowed": False,
    }
