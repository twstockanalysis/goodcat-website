"""國泰投信正式配息公告自動發現。"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import date
from pathlib import PurePosixPath
from urllib.parse import urlencode, urljoin

import httpx

from backend.app.data_sources.actual_dividend_source_registry import (
    SourceRetrievalPolicy,
    get_actual_dividend_source,
)
from backend.app.data_sources.cathay_actual_dividend_adapter import SOURCE_ID
from backend.app.data_sources.openapi import create_ssl_context
from backend.app.data_sources.official_source_document import (
    validate_official_source_url,
)


API_BASE_URL = "https://cwapi.cathaysite.com.tw/"
ANNOUNCEMENT_LIST_PATH = "api/Fund/GetAnnouncementList"
PUBLIC_DOCUMENT_BASE_URL = "https://cwapi.cathaysite.com.tw/"
MAX_DISCOVERY_PAGES = 20
MAX_PAGE_SIZE = 100

_ACTUAL_TITLE_MARKERS = ("收益分配公告", "收益分配期中公告", "配息組成公告")
_REJECTION_TITLE_MARKERS = ("期前", "預估", "估算")


@dataclass(frozen=True, slots=True)
class CathayAnnouncementCandidate:
    """已通過標題與官方網址邊界的候選公告。"""

    announcement_id: int
    title: str
    declared_date: date
    document_url: str
    document_id: str
    content_type: str


@dataclass(frozen=True, slots=True)
class CathayAnnouncementRejection:
    """公告未進入 ACTUAL 解析的明確原因。"""

    announcement_id: int | None
    title: str
    reason: str


@dataclass(frozen=True, slots=True)
class CathayAnnouncementDiscoveryResult:
    """受控範圍公告搜尋結果。"""

    etf_code: str
    pages_fetched: int
    total_available: int
    candidates: tuple[CathayAnnouncementCandidate, ...]
    rejections: tuple[CathayAnnouncementRejection, ...]


def build_cathay_announcement_list_url(
    *, etf_code: str, page: int, page_size: int
) -> str:
    """建立只包含受控參數的公開 API 網址。"""

    normalized_code = etf_code.strip().upper()
    if not normalized_code:
        raise ValueError("ETF 代號不可為空白")
    if page < 1 or page > MAX_DISCOVERY_PAGES:
        raise ValueError(f"page 必須介於 1 與 {MAX_DISCOVERY_PAGES}")
    if page_size < 1 or page_size > MAX_PAGE_SIZE:
        raise ValueError(f"page_size 必須介於 1 與 {MAX_PAGE_SIZE}")

    query = urlencode(
        {
            "CurrentPage": page,
            "PerPageCount": page_size,
            "AnnouncementType": 1,
            "Keyword": normalized_code,
        }
    )
    return urljoin(API_BASE_URL, f"{ANNOUNCEMENT_LIST_PATH}?{query}")


def fetch_cathay_announcement_page(
    *, etf_code: str, page: int, page_size: int, allow_network: bool = False,
    timeout_seconds: float = 30.0,
) -> dict:
    """明確允許後呼叫國泰官方公開公告 API。"""

    source = get_actual_dividend_source(SOURCE_ID)
    if not allow_network:
        raise ValueError("網路查詢必須明確設定 allow_network=True")
    if source.retrieval_policy != SourceRetrievalPolicy.EXPLICIT_NETWORK:
        raise ValueError("此來源不允許程式查詢")

    url = build_cathay_announcement_list_url(
        etf_code=etf_code, page=page, page_size=page_size
    )
    response = httpx.get(
        url,
        timeout=timeout_seconds,
        follow_redirects=True,
        verify=create_ssl_context(),
        headers={
            "Accept": "application/json",
            "User-Agent": "TW-ETF-AI-Analyzer/0.1 (official-discovery)",
        },
    )
    response.raise_for_status()
    validate_official_source_url(source, str(response.url))
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("國泰公告 API 回應不是 JSON object")
    return payload


def _candidate_from_item(item: dict) -> tuple[
    CathayAnnouncementCandidate | None, CathayAnnouncementRejection | None
]:
    title = str(item.get("title") or "").strip()
    raw_id = item.get("id")
    announcement_id = int(raw_id) if raw_id is not None else None

    rejection_marker = next(
        (marker for marker in _REJECTION_TITLE_MARKERS if marker in title), None
    )
    if rejection_marker is not None:
        return None, CathayAnnouncementRejection(
            announcement_id, title, f"標題包含非最終資料語意：{rejection_marker}"
        )
    if not any(marker in title for marker in _ACTUAL_TITLE_MARKERS):
        return None, CathayAnnouncementRejection(
            announcement_id, title, "標題不是收益分配或配息組成公告"
        )
    if not bool(item.get("isPDF")):
        return None, CathayAnnouncementRejection(
            announcement_id, title, "公告不是可驗證 PDF"
        )

    file_path = str(item.get("filePath") or "").strip()
    if PurePosixPath(file_path).suffix.lower() != ".pdf":
        return None, CathayAnnouncementRejection(
            announcement_id, title, "官方檔案路徑不是 PDF"
        )
    if announcement_id is None:
        return None, CathayAnnouncementRejection(None, title, "公告缺少穩定 ID")

    raw_declared_date = str(item.get("declareTime") or "").strip()
    try:
        declared = date.fromisoformat(raw_declared_date.replace("/", "-"))
    except ValueError:
        return None, CathayAnnouncementRejection(
            announcement_id, title, "公告日期格式錯誤"
        )
    document_url = urljoin(PUBLIC_DOCUMENT_BASE_URL, file_path.lstrip("/"))
    source = get_actual_dividend_source(SOURCE_ID)
    validate_official_source_url(source, document_url)
    return CathayAnnouncementCandidate(
        announcement_id=announcement_id,
        title=title,
        declared_date=declared,
        document_url=document_url,
        document_id=f"cathay-announcement-{announcement_id}",
        content_type="application/pdf",
    ), None


def discover_cathay_actual_dividend_announcements(
    *, etf_code: str, max_pages: int = 3, page_size: int = 50,
    allow_network: bool = False, page_payloads: list[dict] | None = None,
) -> CathayAnnouncementDiscoveryResult:
    """依 ETF 代號找出可進入 PDF ACTUAL 解析的候選。"""

    normalized_code = etf_code.strip().upper()
    if max_pages < 1 or max_pages > MAX_DISCOVERY_PAGES:
        raise ValueError(
            f"max_pages 必須介於 1 與 {MAX_DISCOVERY_PAGES}"
        )

    candidates: list[CathayAnnouncementCandidate] = []
    rejections: list[CathayAnnouncementRejection] = []
    total_available = 0
    pages_fetched = 0

    for page in range(1, max_pages + 1):
        if page_payloads is not None:
            if page > len(page_payloads):
                break
            payload = page_payloads[page - 1]
        else:
            payload = fetch_cathay_announcement_page(
                etf_code=normalized_code,
                page=page,
                page_size=page_size,
                allow_network=allow_network,
            )

        if payload.get("success") is not True:
            raise ValueError(
                "國泰公告 API 回報失敗："
                + str(payload.get("returnMessage") or "未知錯誤")
            )
        items = payload.get("result")
        if not isinstance(items, list):
            raise ValueError("國泰公告 API 缺少 result list")

        pages_fetched += 1
        total_available = int(payload.get("totalCount") or total_available)
        for item in items:
            if not isinstance(item, dict):
                rejections.append(
                    CathayAnnouncementRejection(None, "", "公告項目不是 JSON object")
                )
                continue
            candidate, rejection = _candidate_from_item(item)
            if candidate is not None:
                candidates.append(candidate)
            if rejection is not None:
                rejections.append(rejection)

        total_pages = int(payload.get("totalPage") or 1)
        if page >= total_pages:
            break

    unique_candidates = {
        item.announcement_id: item for item in candidates
    }
    return CathayAnnouncementDiscoveryResult(
        etf_code=normalized_code,
        pages_fetched=pages_fetched,
        total_available=total_available,
        candidates=tuple(unique_candidates.values()),
        rejections=tuple(rejections),
    )


def build_argument_parser() -> argparse.ArgumentParser:
    """建立受控的公告發現 CLI。"""

    parser = argparse.ArgumentParser(
        description="依 ETF 代號自動搜尋國泰投信正式配息 PDF 候選"
    )
    parser.add_argument("--etf-code", required=True, help="ETF 證券代號")
    parser.add_argument(
        "--max-pages", type=int, default=3,
        help=f"最多查詢頁數（1-{MAX_DISCOVERY_PAGES}）",
    )
    parser.add_argument(
        "--page-size", type=int, default=50,
        help=f"每頁筆數（1-{MAX_PAGE_SIZE}）",
    )
    parser.add_argument(
        "--allow-network", action="store_true",
        help="明確允許查詢國泰官方公開 API",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    """輸出可供後續 PDF Pipeline 使用的 JSON。"""

    arguments = build_argument_parser().parse_args(argv)
    if not arguments.allow_network:
        raise ValueError("自動發現必須明確指定 --allow-network")

    result = discover_cathay_actual_dividend_announcements(
        etf_code=arguments.etf_code,
        max_pages=arguments.max_pages,
        page_size=arguments.page_size,
        allow_network=True,
    )
    payload = {
        "etf_code": result.etf_code,
        "pages_fetched": result.pages_fetched,
        "total_available": result.total_available,
        "candidates": [
            {
                "announcement_id": item.announcement_id,
                "title": item.title,
                "declared_date": item.declared_date.isoformat(),
                "document_url": item.document_url,
                "document_id": item.document_id,
                "content_type": item.content_type,
            }
            for item in result.candidates
        ],
        "rejections": [
            {
                "announcement_id": item.announcement_id,
                "title": item.title,
                "reason": item.reason,
            }
            for item in result.rejections
        ],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
