"""ETF 多檔比較 Read Model Repository。"""

from __future__ import annotations

from backend.app.exceptions import ETFNotFoundError

from pathlib import Path
from typing import Any, Iterable

from backend.app.models.etf_analysis import (
    PerformanceMetric,
)
from backend.app.repositories.dividend_repository import (
    build_actual_76w_summary,
    count_etf_dividends,
    list_etf_dividends,
)
from backend.app.repositories.etf_data_profile_repository import (
    build_etf_data_profile,
)
from backend.app.repositories.etf_repository import (
    get_etf_by_code,
)
from backend.app.repositories.performance_repository import (
    list_latest_etf_performance,
)


COMPARISON_PERIODS = (
    "1M",
    "3M",
    "6M",
    "1Y",
)

COMPARISON_METRIC = (
    PerformanceMetric.PRICE_RETURN
)

COMPLETENESS_SECTIONS = (
    "ETF 主資料",
    "市價績效",
    "配息歷史",
    "正式 76W",
    "正式來源文件",
)


def normalize_comparison_codes(
    codes: Iterable[str],
) -> tuple[str, ...]:
    """正規化、去重並驗證 2 至 4 檔 ETF 代號。"""

    normalized: list[str] = []
    seen: set[str] = set()

    for value in codes:
        code = str(value).strip().upper()

        if not code or code in seen:
            continue

        if (
            len(code) < 4
            or len(code) > 10
            or not code.isalnum()
        ):
            raise ValueError(
                f"ETF 代號格式不正確：{code}"
            )

        normalized.append(code)
        seen.add(code)

    if len(normalized) < 2:
        raise ValueError(
            "ETF 比較至少需要 2 個不同代號"
        )

    if len(normalized) > 4:
        raise ValueError(
            "ETF 比較最多支援 4 個不同代號"
        )

    return tuple(normalized)


def parse_comparison_codes(
    value: str,
) -> tuple[str, ...]:
    """解析逗號分隔的 ETF 代號。"""

    return normalize_comparison_codes(
        value.split(",")
    )


def _latest_dividend_summary(
    *,
    etf_code: str,
    database_path: str | Path | None,
) -> dict[str, Any]:
    """建立單一 ETF 最新配息摘要。"""

    total = count_etf_dividends(
        etf_code=etf_code,
        database_path=database_path,
    )

    latest_items = list_etf_dividends(
        etf_code=etf_code,
        database_path=database_path,
        limit=1,
        offset=0,
    )

    if not latest_items:
        return {
            "event_count": total,
            "latest_event_date": None,
            "latest_amount_per_unit": None,
            "currency": None,
        }

    latest = latest_items[0]

    event_dates = [
        latest[field_name]
        for field_name in (
            "announcement_date",
            "ex_dividend_date",
            "record_date",
            "payment_date",
        )
        if latest[field_name] is not None
    ]

    latest_event_date = (
        max(event_dates)
        if event_dates
        else None
    )

    return {
        "event_count": total,
        "latest_event_date": latest_event_date,
        "latest_amount_per_unit": (
            latest["amount_per_unit"]
        ),
        "currency": latest["currency"],
    }


def _build_completeness(
    *,
    performance_items: list[dict[str, Any]],
    dividend: dict[str, Any],
    actual_76w: dict[str, Any],
    data_profile: dict[str, Any],
) -> dict[str, Any]:
    """依五個比較資料區塊建立可解釋完整度。"""

    availability = {
        "ETF 主資料": True,
        "市價績效": bool(
            performance_items
        ),
        "配息歷史": (
            int(dividend["event_count"]) > 0
        ),
        "正式 76W": (
            int(
                actual_76w[
                    "actual_76w_record_count"
                ]
            )
            > 0
        ),
        "正式來源文件": (
            int(
                data_profile[
                    "actual_dividend"
                ][
                    "source_document_event_count"
                ]
            )
            > 0
        ),
    }

    available_sections = [
        section
        for section in COMPLETENESS_SECTIONS
        if availability[section]
    ]

    missing_sections = [
        section
        for section in COMPLETENESS_SECTIONS
        if not availability[section]
    ]

    available_count = len(
        available_sections
    )
    total_count = len(
        COMPLETENESS_SECTIONS
    )

    return {
        "available_section_count": (
            available_count
        ),
        "total_section_count": total_count,
        "score_pct": round(
            available_count
            / total_count
            * 100,
            6,
        ),
        "available_sections": (
            available_sections
        ),
        "missing_sections": missing_sections,
    }


def build_etf_comparison(
    codes: Iterable[str],
    database_path: str | Path | None = None,
) -> dict[str, Any]:
    """建立 2 至 4 檔 ETF 的比較 Read Model。"""

    normalized_codes = (
        normalize_comparison_codes(codes)
    )

    etf_rows: list[dict[str, Any]] = []
    missing_codes: list[str] = []

    for code in normalized_codes:
        etf = get_etf_by_code(
            code,
            database_path,
        )

        if etf is None:
            missing_codes.append(code)
            continue

        etf_rows.append(etf)

    if missing_codes:
        raise ETFNotFoundError(*missing_codes)

    items: list[dict[str, Any]] = []

    for etf in etf_rows:
        code = str(etf["code"])

        performance_items = (
            list_latest_etf_performance(
                etf_code=code,
                database_path=database_path,
                metric_code=COMPARISON_METRIC,
            )
        )

        dividend = _latest_dividend_summary(
            etf_code=code,
            database_path=database_path,
        )

        actual_summary = (
            build_actual_76w_summary(
                etf_code=code,
                database_path=database_path,
            )
        )

        profile = build_etf_data_profile(
            etf_code=code,
            database_path=database_path,
        )

        if profile is None:
            raise RuntimeError(
                f"無法建立 ETF 資料概況：{code}"
            )

        actual_76w = {
            "record_count": (
                actual_summary[
                    "actual_76w_record_count"
                ]
            ),
            "full_76w_count": (
                actual_summary[
                    "full_76w_count"
                ]
            ),
            "latest_ratio_pct": (
                actual_summary[
                    "latest_76w_ratio_pct"
                ]
            ),
            "average_ratio_pct": (
                actual_summary[
                    "average_76w_ratio_pct"
                ]
            ),
        }

        items.append(
            {
                "etf": etf,
                "performance_items": (
                    performance_items
                ),
                "dividend": dividend,
                "actual_76w": actual_76w,
                "data_profile": profile,
                "completeness": (
                    _build_completeness(
                        performance_items=(
                            performance_items
                        ),
                        dividend=dividend,
                        actual_76w=(
                            actual_summary
                        ),
                        data_profile=profile,
                    )
                ),
            }
        )

    return {
        "codes": list(normalized_codes),
        "metric_code": (
            COMPARISON_METRIC.value
        ),
        "periods": list(
            COMPARISON_PERIODS
        ),
        "items": items,
    }
