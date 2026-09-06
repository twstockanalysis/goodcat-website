"""TWSE 個股日成交資訊下載及解析工具。"""

import json
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import httpx

from backend.app.config.settings import (
    RAW_DATA_DIR,
)
from backend.app.data_sources.openapi import (
    create_ssl_context,
)
from backend.app.data_sources.registry import (
    get_data_source,
)
from backend.app.models.etf_price import (
    ETFDailyCloseRecord,
)
from backend.app.utils.date_tools import (
    list_month_starts,
)


SOURCE_ID = "twse_stock_day"

TRANSIENT_HTTP_STATUS_CODES = frozenset(
    {
        307,
        308,
        429,
        502,
        503,
        504,
    }
)

NO_DATA_TEXTS = (
    "沒有符合條件",
    "查無資料",
    "無資料",
)


@dataclass(
    frozen=True,
    slots=True,
)
class PriceHistorySnapshot:
    """ETF 歷史價格快照。"""

    etf_code: str
    downloaded_at: datetime
    data_path: Path
    metadata_path: Path
    record_count: int


def parse_twse_trade_date(
    value: object,
) -> date:
    """將 TWSE 民國日期轉為西元日期。

    例如：

    115/07/29 → 2026-07-29
    """

    text = str(value).strip().replace(
        "-",
        "/",
    )

    parts = text.split("/")

    if (
        len(parts) != 3
        or not all(
            part.isdigit()
            for part in parts
        )
    ):
        raise ValueError(
            f"無法辨識 TWSE 交易日期：{text}"
        )

    year_text, month_text, day_text = parts

    year = int(year_text)

    if len(year_text) <= 3:
        year += 1911

    return date(
        year,
        int(month_text),
        int(day_text),
    )


def parse_price(
    value: object,
) -> Decimal | None:
    """解析 TWSE 價格欄位。"""

    text = str(value).strip()

    if text in {
        "",
        "--",
        "---",
        "N/A",
    }:
        return None

    normalized_text = text.replace(
        ",",
        "",
    )

    try:
        price = Decimal(
            normalized_text
        )

    except InvalidOperation as error:
        raise ValueError(
            f"無法辨識收盤價：{text}"
        ) from error

    if price <= 0:
        return None

    return price


def validate_stock_day_payload(
    payload: object,
) -> dict[str, Any]:
    """驗證 TWSE STOCK_DAY 回應格式。"""

    if not isinstance(payload, dict):
        raise ValueError(
            "TWSE 回應最外層必須是 JSON 物件"
        )

    stat = str(
        payload.get("stat", "")
    ).strip()

    if stat != "OK":
        if any(
            text in stat
            for text in NO_DATA_TEXTS
        ):
            return payload

        raise ValueError(
            f"TWSE 回應狀態錯誤：{stat}"
        )

    fields = payload.get("fields")
    data = payload.get("data")

    if not isinstance(fields, list):
        raise ValueError(
            "TWSE 回應缺少 fields"
        )

    if not isinstance(data, list):
        raise ValueError(
            "TWSE 回應缺少 data"
        )

    return payload


def parse_stock_day_records(
    payload: object,
    etf_code: str,
) -> list[ETFDailyCloseRecord]:
    """將 TWSE 月成交資訊轉成每日收盤價。"""

    validated_payload = (
        validate_stock_day_payload(
            payload
        )
    )

    stat = str(
        validated_payload.get(
            "stat",
            "",
        )
    )

    if stat != "OK":
        return []

    raw_fields = validated_payload[
        "fields"
    ]

    fields = [
        str(field).strip()
        for field in raw_fields
    ]

    try:
        date_index = fields.index(
            "日期"
        )

        close_index = fields.index(
            "收盤價"
        )

    except ValueError as error:
        raise ValueError(
            "TWSE 回應缺少日期或收盤價欄位"
        ) from error

    records: list[
        ETFDailyCloseRecord
    ] = []

    for row_number, row in enumerate(
        validated_payload["data"],
        start=1,
    ):
        if not isinstance(row, list):
            raise ValueError(
                f"TWSE 第 {row_number} 筆"
                "成交資料不是陣列"
            )

        required_index = max(
            date_index,
            close_index,
        )

        if len(row) <= required_index:
            raise ValueError(
                f"TWSE 第 {row_number} 筆"
                "成交資料欄位不足"
            )

        close_price = parse_price(
            row[close_index]
        )

        if close_price is None:
            continue

        records.append(
            ETFDailyCloseRecord.model_validate(
                {
                    "etf_code": etf_code,
                    "trade_date": (
                        parse_twse_trade_date(
                            row[date_index]
                        )
                    ),
                    "close_price": (
                        close_price
                    ),
                    "source_id": SOURCE_ID,
                }
            )
        )

    return sorted(
        records,
        key=lambda record: (
            record.trade_date
        ),
    )


def fetch_stock_day_month(
    etf_code: str,
    month_start: date,
    timeout_seconds: float = 30.0,
    max_attempts: int = 3,
    retry_backoff_seconds: float = 2.0,
) -> list[ETFDailyCloseRecord]:
    """下載一檔 ETF 的單月成交資訊。"""

    if max_attempts < 1:
        raise ValueError("max_attempts 必須大於 0")

    if retry_backoff_seconds < 0:
        raise ValueError(
            "retry_backoff_seconds 不得小於 0"
        )

    normalized_code = (
        etf_code.strip().upper()
    )

    if not normalized_code:
        raise ValueError(
            "ETF 代號不可為空白"
        )

    source = get_data_source(
        SOURCE_ID
    )

    if not source.base_url:
        raise ValueError(
            "TWSE 日成交來源缺少 Base URL"
        )

    endpoint_url = (
        f"{source.base_url.rstrip('/')}/"
        "STOCK_DAY"
    )

    ssl_context = create_ssl_context(
        allow_legacy_x509=(
            source.allow_legacy_x509
        ),
    )

    response = None

    for attempt in range(max_attempts):
        response = httpx.get(
            endpoint_url,
            params={
                "response": "json",
                "date": (
                    month_start.strftime(
                        "%Y%m01"
                    )
                ),
                "stockNo": normalized_code,
            },
            timeout=timeout_seconds,
            follow_redirects=False,
            verify=ssl_context,
            headers={
                "Accept": "application/json",
                "User-Agent": (
                    "GoodCat/0.1 "
                    "(official-price-downloader)"
                ),
            },
        )

        if (
            response.status_code
            not in TRANSIENT_HTTP_STATUS_CODES
            or attempt == max_attempts - 1
        ):
            break

        retry_after = response.headers.get(
            "Retry-After"
        )
        try:
            delay_seconds = float(retry_after)
        except (TypeError, ValueError):
            delay_seconds = (
                retry_backoff_seconds
                * (2**attempt)
            )

        if delay_seconds > 0:
            time.sleep(delay_seconds)

    if response is None:  # pragma: no cover
        raise RuntimeError("TWSE 請求未執行")

    response.raise_for_status()

    return parse_stock_day_records(
        response.json(),
        normalized_code,
    )


def fetch_price_history(
    etf_code: str,
    end_date: date,
    month_count: int = 8,
    request_interval_seconds: float = 0.4,
) -> list[ETFDailyCloseRecord]:
    """下載指定月份範圍的 ETF 收盤價。"""

    records_by_date: dict[
        date,
        ETFDailyCloseRecord,
    ] = {}

    month_starts = list_month_starts(
        end_date=end_date,
        month_count=month_count,
    )

    for index, month_start in enumerate(
        month_starts
    ):
        month_records = (
            fetch_stock_day_month(
                etf_code=etf_code,
                month_start=month_start,
            )
        )

        for record in month_records:
            records_by_date[
                record.trade_date
            ] = record

        if (
            request_interval_seconds > 0
            and index
            < len(month_starts) - 1
        ):
            time.sleep(
                request_interval_seconds
            )

    return sorted(
        records_by_date.values(),
        key=lambda record: (
            record.trade_date
        ),
    )


def save_price_history_snapshot(
    etf_code: str,
    records: list[ETFDailyCloseRecord],
    output_root: Path | None = None,
    downloaded_at: datetime | None = None,
) -> PriceHistorySnapshot:
    """保存 ETF 歷史價格原始快照。"""

    normalized_code = (
        etf_code.strip().upper()
    )

    if output_root is None:
        output_root = (
            RAW_DATA_DIR
            / "performance"
            / SOURCE_ID
        )

    if downloaded_at is None:
        downloaded_at = datetime.now(
            timezone.utc
        )

    timestamp = downloaded_at.strftime(
        "%Y%m%dT%H%M%SZ"
    )

    output_directory = (
        output_root / normalized_code
    )

    output_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    payload = [
        record.model_dump(
            mode="json"
        )
        for record in records
    ]

    data_path = (
        output_directory
        / (
            f"{normalized_code}_"
            f"{timestamp}.json"
        )
    )

    metadata_path = (
        output_directory
        / (
            f"{normalized_code}_"
            f"{timestamp}.meta.json"
        )
    )

    data_text = json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
    )

    metadata = {
        "source_id": SOURCE_ID,
        "etf_code": normalized_code,
        "downloaded_at": (
            downloaded_at.isoformat()
        ),
        "record_count": len(records),
        "first_trade_date": (
            records[0].trade_date.isoformat()
            if records
            else None
        ),
        "last_trade_date": (
            records[-1].trade_date.isoformat()
            if records
            else None
        ),
        "data_path": str(data_path),
    }

    metadata_text = json.dumps(
        metadata,
        ensure_ascii=False,
        indent=2,
    )

    data_path.write_text(
        data_text,
        encoding="utf-8",
    )

    metadata_path.write_text(
        metadata_text,
        encoding="utf-8",
    )

    (
        output_directory
        / "latest.json"
    ).write_text(
        data_text,
        encoding="utf-8",
    )

    (
        output_directory
        / "latest.meta.json"
    ).write_text(
        metadata_text,
        encoding="utf-8",
    )

    return PriceHistorySnapshot(
        etf_code=normalized_code,
        downloaded_at=downloaded_at,
        data_path=data_path,
        metadata_path=metadata_path,
        record_count=len(records),
    )
