"""Streamlit 前端共用格式化工具。"""

from __future__ import annotations

from datetime import datetime
import math
import re
from typing import Any


def format_number(
    value: Any,
    *,
    decimal_places: int = 2,
    suffix: str = "",
    missing_text: str = "尚無資料",
    invalid_text: str = "資料格式異常",
    signed: bool = False,
    trim_trailing_zeros: bool = False,
) -> str:
    """格式化一般數值並保留缺值與格式異常語意。"""

    if value is None:
        return missing_text

    try:
        number = float(value)

    except (
        TypeError,
        ValueError,
        OverflowError,
    ):
        return invalid_text

    if not math.isfinite(number):
        return invalid_text

    sign = "+" if signed else ""

    text = (
        f"{number:{sign},.{decimal_places}f}"
    )

    if trim_trailing_zeros and "." in text:
        text = (
            text
            .rstrip("0")
            .rstrip(".")
        )

    return f"{text}{suffix}"


def format_percentage(
    value: Any,
    *,
    missing_text: str = "尚未取得",
    invalid_text: str = "資料格式異常",
    signed: bool = False,
    decimal_places: int = 2,
) -> str:
    """格式化百分比；正式零值不會被視為缺資料。"""

    return format_number(
        value,
        decimal_places=decimal_places,
        suffix="%",
        missing_text=missing_text,
        invalid_text=invalid_text,
        signed=signed,
    )


def format_amount(
    value: Any,
    currency: Any = "TWD",
    *,
    missing_text: str = "尚無資料",
    invalid_text: str = "資料格式異常",
    decimal_places: int = 0,
) -> str:
    """格式化每單位金額與幣別。"""

    amount_text = format_number(
        value,
        decimal_places=decimal_places,
        missing_text=missing_text,
        invalid_text=invalid_text,
        trim_trailing_zeros=True,
    )

    if amount_text in {
        missing_text,
        invalid_text,
    }:
        return amount_text

    currency_text = str(
        currency or "TWD"
    ).strip().upper()
    if currency_text == "TWD":
        currency_text = "NTD"

    return (
        f"{amount_text} "
        f"{currency_text}"
    )


def format_optional_text(
    value: Any,
    *,
    missing_text: str = "—",
) -> str:
    """格式化可能為空值或空白的文字。"""

    if value is None:
        return missing_text

    text = str(value).strip()

    return (
        text
        if text
        else missing_text
    )


def format_iso_date(
    value: Any,
    *,
    missing_text: str = "尚未取得",
) -> str:
    """格式化前端已驗證的 ISO 日期文字。"""

    return format_optional_text(
        value,
        missing_text=missing_text,
    )


def format_iso_datetime(
    value: Any,
    *,
    missing_text: str = "尚未取得",
    timespec: str | None = "minutes",
    utc_label: bool = False,
) -> str:
    """格式化前端已驗證的 ISO 日期時間。"""

    text = format_optional_text(
        value,
        missing_text=missing_text,
    )

    if text == missing_text:
        return missing_text

    if timespec is None:
        formatted = text.replace(
            "T",
            " ",
            1,
        )

    else:
        try:
            parsed = datetime.fromisoformat(
                text.replace(
                    "Z",
                    "+00:00",
                )
            )

        except ValueError:
            formatted = text

        else:
            formatted = parsed.isoformat(
                sep=" ",
                timespec=timespec,
            )

    if utc_label:
        formatted = formatted.replace(
            "+00:00",
            " UTC",
        )

    return formatted


def management_type_label(
    is_active: Any,
) -> str:
    """將主動式布林值轉為顯示標籤。"""

    return (
        "主動式"
        if bool(is_active)
        else "被動式"
    )


def asset_type_label(
    is_bond: Any,
) -> str:
    """將債券布林值轉為顯示標籤。"""

    return (
        "債券"
        if bool(is_bond)
        else "非債券"
    )


FORMER_ETF_NAME_SUFFIX_PATTERN = re.compile(
    (
        r"(?:"
        r"\s*\(\s*原名\s*[:：][^)]*\)"
        r"|"
        r"\s*（\s*原名\s*[:：][^）]*）"
        r")\s*$"
    )
)


def format_etf_display_name(
    value: Any,
    *,
    missing_text: str = "—",
) -> str:
    """移除 ETF 名稱尾端的原名註記。"""

    text = format_optional_text(
        value,
        missing_text=missing_text,
    )

    if text == missing_text:
        return missing_text

    cleaned = (
        FORMER_ETF_NAME_SUFFIX_PATTERN
        .sub(
            "",
            text,
        )
        .strip()
    )

    return cleaned or text


def format_source_references(
    sources: list[dict[str, Any]],
    *,
    missing_text: str = "尚未取得",
) -> str:
    """將來源 ID 與顯示名稱組成穩定文字。"""

    labels: list[str] = []

    for source in sources:
        source_id = str(
            source.get(
                "source_id",
                "",
            )
        ).strip()

        display_name = str(
            source.get(
                "display_name",
                "",
            )
        ).strip()

        if (
            display_name
            and source_id
            and display_name != source_id
        ):
            labels.append(
                f"{display_name} ({source_id})"
            )

        elif display_name or source_id:
            labels.append(
                display_name or source_id
            )

    return (
        "、".join(labels)
        if labels
        else missing_text
    )


def truncate_text(
    value: Any,
    *,
    maximum_length: int,
    missing_text: str = "—",
) -> str:
    """限制顯示文字長度並保留缺值語意。"""

    if maximum_length < 1:
        raise ValueError(
            "maximum_length 必須大於 0"
        )

    text = format_optional_text(
        value,
        missing_text=missing_text,
    )

    if (
        text == missing_text
        or len(text) <= maximum_length
    ):
        return text

    return (
        text[:maximum_length]
        + "…"
    )
