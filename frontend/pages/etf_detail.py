"""ETF 詳細資料頁面。"""

import math
import unicodedata
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

import streamlit as st

from frontend.owner_access import get_owner_token
from frontend.ui.components import render_page_title

from frontend.api_client import (
    APIClientError,
    APIResourceNotFoundError,
    SUPPORTED_PERFORMANCE_PERIODS,
    fetch_dividend_detail,
    fetch_etf_actual_76w,
    fetch_etf_by_code,
    fetch_etf_data_profile,
    fetch_etf_dividends,
    fetch_etf_performance,
    fetch_etf_latest_close,
    fetch_etf_price_history,
    fetch_etf_target_analysis,
    fetch_tax_reinvestment_scenarios,
)
from frontend.config import (
    get_api_base_url,
)
from frontend.navigation import (
    ETF_COMPARISON_ROUTE,
    ETF_DETAIL_ROUTE,
    build_comparison_query_params,
    build_detail_query_params,
    create_streamlit_page,
    resolve_detail_return,
)
from frontend.query_state import (
    get_query_value,
    query_params_to_dict,
    sync_query_params,
)
from frontend.ui.formatters import (
    asset_type_label,
    format_amount as format_shared_amount,
    format_iso_date,
    format_iso_datetime,
    format_number,
    format_percentage as format_shared_percentage,
    format_source_references as format_shared_source_references,
    management_type_label,
)
from frontend.ui.states import (
    loading_state,
    render_api_error,
    render_not_found_state,
    render_warning_state,
)
from frontend.ui.quality_grade import (
    load_historical_quality_grade_lookup,
    render_historical_quality_evidence,
)


DIVIDEND_CASH_COLOR = "#D9A15B"
DIVIDEND_STOCK_COLOR = "#2878D0"


@st.cache_data(
    ttl=60,
    show_spinner=False,
)
def load_etf_detail(
    api_base_url: str,
    code: str,
) -> dict[str, Any]:
    """取得並短暫快取 ETF 詳細資料。"""

    return fetch_etf_by_code(
        api_base_url=api_base_url,
        code=code,
    )


@st.cache_data(
    ttl=60,
    show_spinner=False,
)
def load_etf_data_profile(
    api_base_url: str,
    code: str,
) -> dict[str, Any]:
    """取得並短暫快取 ETF 資料來源概況。"""

    return fetch_etf_data_profile(
        api_base_url=api_base_url,
        code=code,
    )



@st.cache_data(
    ttl=60,
    show_spinner=False,
)
def load_etf_performance(
    api_base_url: str,
    code: str,
) -> dict[str, Any]:
    """取得並短暫快取 ETF 多期間績效。"""

    return fetch_etf_performance(
        api_base_url=api_base_url,
        code=code,
        metric="PRICE_RETURN",
    )


@st.cache_data(
    ttl=60,
    show_spinner=False,
)
def load_etf_price_history(
    api_base_url: str,
    code: str,
) -> dict[str, Any]:
    """取得並短暫快取最近 260 筆官方收盤價。"""

    return fetch_etf_price_history(
        api_base_url=api_base_url,
        code=code,
        limit=260,
    )


@st.cache_data(
    ttl=60,
    show_spinner=False,
)
def load_etf_dividends(
    api_base_url: str,
    code: str,
) -> dict[str, Any]:
    """取得並短暫快取 ETF 配息歷史。"""

    return fetch_etf_dividends(
        api_base_url=api_base_url,
        code=code,
        limit=20,
        offset=0,
    )


@st.cache_data(
    ttl=60,
    show_spinner=False,
)
def load_etf_actual_76w(
    api_base_url: str,
    code: str,
) -> dict[str, Any]:
    """取得並短暫快取 ETF 正式 76W 與綜合資本利得摘要。"""

    return fetch_etf_actual_76w(
        api_base_url=api_base_url,
        code=code,
    )


@st.cache_data(ttl=60, show_spinner=False)
def load_etf_latest_close(
    api_base_url: str,
    code: str,
) -> dict[str, Any]:
    """取得並短暫快取官方最新收盤價。"""

    return fetch_etf_latest_close(api_base_url=api_base_url, code=code)


@st.cache_data(
    ttl=60,
    show_spinner=False,
)
def load_dividend_detail(
    api_base_url: str,
    dividend_id: int,
) -> dict[str, Any]:
    """取得並短暫快取單次配息及其組成。"""

    return fetch_dividend_detail(
        api_base_url=api_base_url,
        dividend_id=dividend_id,
    )


def get_requested_code() -> str:
    """從網址取得 ETF 代號。"""

    return get_query_value(
        st.query_params,
        "code",
    ).upper()


def format_fund_size(
    value: Any,
) -> str:
    """格式化基金規模。"""

    return format_number(
        value,
        suffix=" 億元",
        missing_text="資料抓取中",
        invalid_text="資料格式異常",
        decimal_places=0,
    )


def format_expense_ratio(
    value: Any,
) -> str:
    """格式化費用率。"""

    return format_shared_percentage(
        value,
        missing_text="資料抓取中",
        invalid_text="資料格式異常",
    )


def format_performance_return(
    value: Any,
) -> str:
    """格式化績效報酬率。"""

    return format_shared_percentage(
        value,
        signed=True,
        missing_text="資料格式異常",
        invalid_text="資料格式異常",
    )


def build_performance_lookup(
    items: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """依績效期間建立快速查詢表。"""

    lookup: dict[
        str,
        dict[str, Any],
    ] = {}

    for item in items:
        period_code = str(
            item["period_code"]
        ).strip().upper()

        if (
            period_code
            not in SUPPORTED_PERFORMANCE_PERIODS
        ):
            continue

        lookup[period_code] = item

    return lookup


def render_back_button() -> None:
    """依來源頁顯示返回按鈕並保留 URL 狀態。"""

    route, return_query_params = (
        resolve_detail_return(
            st.query_params
        )
    )

    return_page = create_streamlit_page(
        route
    )

    if st.button(
        f"← 返回 {route.title}",
        type="secondary",
    ):
        st.switch_page(
            return_page,
            query_params=(
                return_query_params
            ),
        )


def clear_etf_detail_caches() -> None:
    """清除詳細資料頁使用的快取。"""

    load_etf_detail.clear()
    load_etf_data_profile.clear()
    load_etf_performance.clear()
    load_etf_price_history.clear()
    load_etf_dividends.clear()
    load_etf_actual_76w.clear()
    load_etf_latest_close.clear()
    load_dividend_detail.clear()
    load_historical_quality_grade_lookup.clear()


def render_detail_actions(
    *,
    can_refresh: bool,
) -> None:
    """並列顯示返回與更新操作。"""

    with st.container(
        horizontal=True,
        gap="small",
        key="etf-detail-actions",
    ):
        render_back_button()

        if can_refresh and st.button(
            "更新",
            key="refresh_etf_detail",
        ):
            clear_etf_detail_caches()
            st.rerun()


def render_code_form(
    default_code: str = "",
) -> None:
    """顯示 ETF 代號查詢表單。"""

    with st.form(
        "etf_detail_code_form",
        enter_to_submit=False,
    ):
        code = st.text_input(
            "ETF 代號",
            value=default_code,
            placeholder="例如 0050 或 00980A",
        )

        submitted = (
            st.form_submit_button(
                "查詢 ETF",
                type="primary",
            )
        )

    if not submitted:
        return

    normalized_code = (
        code.strip().upper()
    )

    if not normalized_code:
        st.warning(
            "請輸入 ETF 代號。"
        )
        return

    route, return_query_params = (
        resolve_detail_return(
            st.query_params
        )
    )

    sync_query_params(
        st.query_params,
        build_detail_query_params(
            code=normalized_code,
            source=str(
                route.url_path
            ),
            source_query_params=(
                return_query_params
            ),
        ),
    )

    load_etf_detail.clear()
    load_etf_data_profile.clear()
    load_etf_performance.clear()
    load_etf_price_history.clear()
    load_etf_dividends.clear()
    load_etf_actual_76w.clear()
    load_dividend_detail.clear()

    st.rerun()


def render_etf_information(
    etf: dict[str, Any],
    grade_payload: object = None,
    *,
    show_owner_details: bool = False,
) -> None:
    """顯示 ETF 身分、分類與核心資料。"""

    code = str(etf["code"])
    name = str(etf["name"])

    management_type = (
        management_type_label(
            etf["is_active"]
        )
    )

    asset_type = asset_type_label(
        etf["is_bond"]
    )

    listing_date = (
        etf["listing_date"]
        or "資料抓取中"
    )

    with st.container(
        border=True,
        key="etf-detail-summary",
        gap="small",
    ):
        with st.container(
            horizontal=True,
            horizontal_alignment="distribute",
            vertical_alignment="center",
            gap="small",
        ):
            with st.container(
                horizontal=True,
                vertical_alignment="center",
                gap="small",
            ):
                st.header(
                    f"{code} {name}",
                    width="content",
                )
                st.caption(
                    f"{management_type}｜{asset_type}",
                    width="content",
                )

            render_comparison_action(code)

        render_historical_quality_evidence(
            grade_payload,
            show_owner_details=show_owner_details,
        )

        date_column, size_column, fee_column = (
            st.columns(3)
        )

        with date_column:
            st.metric(
                "上市日期",
                listing_date,
            )

        with size_column:
            st.metric(
                "基金規模",
                format_fund_size(
                    etf["fund_size"]
                ),
            )

        with fee_column:
            render_annual_expense(etf)

        if show_owner_details and (
            etf["fund_size"] is None
            or etf["expense_ratio"] is None
        ):
            st.info(
                "目前 ETF 主資料來源尚未提供或"
                "尚未匯入該項指標。"
            )



def render_annual_expense(etf: dict[str, Any]) -> None:
    """Keep the historical year adjacent to the percentage and its source."""
    evidence = etf.get("annual_expense")
    if evidence:
        st.metric(f"{evidence['reporting_year']} 年總費用率",
                  format_expense_ratio(float(evidence["expense_ratio_pct"])))
        st.caption("歷史年度實際費用，含交易成本；不代表目前契約費率或未來費用。")
        st.caption(f"文件日期：{evidence['publication_date']}｜第 {evidence['document_page']} 頁")
        st.link_button("官方費用率來源", evidence["source_url"])
    else:
        st.metric("費用率", format_expense_ratio(etf.get("expense_ratio")))
        if etf.get("expense_ratio") is not None:
            st.caption("此舊資料未附年度與來源，尚未完成年度費用率驗證。")


def build_price_history_chart_rows(
    price_history: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """建立不補值、不推估的官方收盤價走勢資料。"""

    if price_history is None:
        return []

    return [
        {
            "交易日": item["trade_date"],
            "收盤價": item["close_price"],
        }
        for item in price_history.get("items", [])
    ]


def get_performance_data_date(
    items: list[dict[str, Any]],
    price_history: dict[str, Any] | None,
) -> str | None:
    """取得績效卡片共用的最新官方資料日期。"""

    performance_dates = [
        str(item["as_of_date"]).strip()
        for item in items
        if item.get("as_of_date")
    ]
    if performance_dates:
        return max(performance_dates)

    price_rows = build_price_history_chart_rows(
        price_history
    )
    if price_rows:
        return str(price_rows[-1]["交易日"])

    return None


def render_price_history_chart(
    price_history: dict[str, Any] | None,
) -> None:
    """以券商常見的折線面積圖顯示官方收盤價走勢。"""

    rows = build_price_history_chart_rows(
        price_history
    )
    if len(rows) < 2:
        st.info("股價走勢資料抓取中")
        return

    st.vega_lite_chart(
        rows,
        {
            "height": 240,
            "mark": {
                "type": "area",
                "line": {
                    "color": "#2878D0",
                    "strokeWidth": 2,
                },
                "color": "#2878D0",
                "opacity": 0.16,
            },
            "encoding": {
                "x": {
                    "field": "交易日",
                    "type": "temporal",
                    "axis": {
                        "title": None,
                        "format": "%Y-%m",
                        "labelAngle": 0,
                    },
                },
                "y": {
                    "field": "收盤價",
                    "type": "quantitative",
                    "scale": {"zero": False},
                    "axis": {
                        "format": ",.0f",
                        "title": None,
                    },
                },
                "tooltip": [
                    {
                        "field": "交易日",
                        "type": "temporal",
                        "format": "%Y-%m-%d",
                    },
                    {
                        "field": "收盤價",
                        "type": "quantitative",
                        "format": ",.0f",
                    },
                ],
            },
        },
        width="stretch",
    )


def render_etf_performance(
    performance: dict[str, Any],
    price_history: dict[str, Any] | None = None,
) -> None:
    """顯示 ETF 的 1M、3M、6M、1Y 績效。"""

    with st.container(
        border=True,
        key="etf-detail-performance",
    ):
        st.subheader("績效")

        items = performance.get(
            "items",
            [],
        )

        lookup = build_performance_lookup(
            items
        )

        columns = st.columns(
            len(SUPPORTED_PERFORMANCE_PERIODS)
        )

        for column, period_code in zip(
            columns,
            SUPPORTED_PERFORMANCE_PERIODS,
            strict=True,
        ):
            item = lookup.get(
                period_code
            )

            with column:
                if item is None:
                    st.metric(
                        period_code,
                        "資料抓取中",
                    )

                    st.caption(
                        "尚無足夠價格歷史"
                    )

                    continue

                st.metric(
                    period_code,
                    format_performance_return(
                        item["return_pct"]
                    ),
                )

        if not items:
            st.info(
                "目前尚無可顯示的績效資料。"
            )

        render_price_history_chart(
            price_history
        )

        data_date = get_performance_data_date(
            items,
            price_history,
        )
        source_caption = "資料來源於證交所"
        if data_date is not None:
            source_caption += (
                f"　資料日期：{data_date}"
            )

        st.caption(source_caption)



DIVIDEND_COMPONENT_LABELS = {
    "EST_DIVIDEND": "股利所得",
    "EST_INTEREST": "利息所得",
    "EST_EQUALIZATION": "收益平準金",
    "EST_REALIZED_CAPITAL_GAIN": (
        "已實現資本利得"
    ),
    "EST_OTHER": "其他所得",
    "76W": "實際所得類別 76W",
}


def format_dividend_amount(
    value: Any,
    currency: Any = "TWD",
) -> str:
    """格式化每單位配息金額。"""

    return format_shared_amount(
        value,
        currency,
        missing_text="資料抓取中",
        invalid_text="資料格式異常",
    )


def format_dividend_percentage(
    value: Any,
) -> str:
    """格式化配息組成比例並保留缺資料語意。"""

    return format_shared_percentage(
        value,
        missing_text="尚未取得",
        invalid_text="資料格式異常",
    )


def format_optional_date(
    value: Any,
) -> str:
    """格式化可能缺少的日期。"""

    return format_iso_date(
        value,
        missing_text="資料抓取中",
    )


def format_dividend_summary_date(
    value: Any,
) -> str:
    """格式化配息摘要日期，缺少時顯示破折號。"""

    return format_iso_date(
        value,
        missing_text="—",
    )


def format_dividend_yield(
    value: Any,
) -> str:
    """格式化單次殖利率並保留缺資料語意。"""

    return format_shared_percentage(
        value,
        missing_text="—",
        invalid_text="資料格式異常",
    )


def format_cash_stock_dividend(
    cash_value: Any,
    stock_value: Any,
) -> str:
    """以現金／股票順序顯示每單位股利，保留缺值。"""

    def format_value(value: Any, decimal_places: int) -> str:
        return format_number(
            value,
            decimal_places=decimal_places,
            trim_trailing_zeros=True,
            missing_text="—",
            invalid_text="資料格式異常",
        )

    return (
        f"{format_value(cash_value, 0)}/"
        f"{format_value(stock_value, 4)}"
    )


def format_dividend_period(
    item: dict[str, Any],
) -> str:
    """優先顯示官方年季，缺少時依除息日補出日曆年季。"""

    period = item.get("distribution_period")
    if period is not None:
        normalized = str(period).strip().upper()
        if (
            len(normalized) == 6
            and normalized[:4].isdigit()
            and normalized[4] == "Q"
            and normalized[5] in "1234"
        ):
            return f"{normalized[:4]}/{normalized[4:]}"
        return normalized or "—"

    ex_dividend_date = item.get("ex_dividend_date")
    try:
        parsed_date = date.fromisoformat(
            str(ex_dividend_date)
        )
    except (TypeError, ValueError):
        return "—"

    quarter = (parsed_date.month - 1) // 3 + 1
    return f"{parsed_date.year}/Q{quarter}"


def chart_axis_upper_bound(
    values: list[float | int | None],
    *,
    target_steps: int = 5,
) -> float:
    """以整齊刻度建立嚴格高於資料最大值的 Y 軸上限。"""

    maximum = max(
        (
            float(value)
            for value in values
            if value is not None and float(value) > 0
        ),
        default=0.0,
    )
    if maximum <= 0:
        return 1.0

    rough_step = maximum / max(target_steps, 1)
    magnitude = 10 ** math.floor(math.log10(rough_step))
    normalized_step = rough_step / magnitude
    nice_multiplier = next(
        multiplier
        for multiplier in (1.0, 2.0, 2.5, 5.0, 10.0)
        if normalized_step <= multiplier
    )
    step = nice_multiplier * magnitude
    upper_bound = math.ceil(maximum / step) * step
    if math.isclose(upper_bound, maximum, rel_tol=1e-12, abs_tol=1e-12):
        upper_bound += step

    precision = max(0, -math.floor(math.log10(step)) + 2)
    return round(upper_bound, precision)


def build_annual_dividend_chart_rows(
    items: list[dict[str, Any]],
    *,
    current_year: int | None = None,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    bool,
]:
    """建立近五年逐次股利堆疊與年度殖利率資料。"""

    anchor_year = (
        current_year
        if current_year is not None
        else date.today().year
    )
    years = [
        str(year)
        for year in range(
            anchor_year - 4,
            anchor_year + 1,
        )
    ]
    annual: dict[str, dict[str, Any]] = {
        year: {
            "殖利率": 0.0,
            "殖利率筆數": 0,
            "配息筆數": 0,
            "現金股利": [],
            "股票股利": [],
        }
        for year in years
    }
    stock_dividend_available = False

    for item in items:
        ex_dividend_date = str(
            item.get("ex_dividend_date")
            or ""
        )

        if (
            len(ex_dividend_date) < 4
            or not ex_dividend_date[:4].isdigit()
        ):
            continue

        year = ex_dividend_date[:4]
        if year not in annual:
            continue

        summary = annual[year]
        summary["配息筆數"] += 1

        cash_dividend = item.get(
            "amount_per_unit"
        )
        if cash_dividend is not None:
            summary["現金股利"].append(
                {
                    "金額": float(cash_dividend),
                    "除息日": ex_dividend_date,
                }
            )

        stock_dividend = item.get(
            "stock_dividend_per_unit"
        )
        if stock_dividend is not None:
            stock_dividend_available = True
            summary["股票股利"].append(
                {
                    "金額": float(stock_dividend),
                    "除息日": ex_dividend_date,
                }
            )

        yield_pct = item.get("yield_pct")
        if yield_pct is not None:
            summary["殖利率"] += float(
                yield_pct
            )
            summary["殖利率筆數"] += 1

    dividend_rows: list[dict[str, Any]] = []
    yield_rows: list[dict[str, Any]] = []

    for year in years:
        summary = annual[year]
        for dividend_type in (
            "現金股利",
            "股票股利",
        ):
            distributions = sorted(
                summary[dividend_type],
                key=lambda item: str(
                    item["除息日"]
                ),
            )

            if not distributions:
                dividend_rows.append(
                    {
                        "年份": year,
                        "股利類型": dividend_type,
                        "每單位股利": None,
                        "配息次序": None,
                        "除息日": None,
                        "堆疊順序": None,
                        "累計股利": None,
                        "顯示分隔線": False,
                        "年度股利合計": None,
                        "顯示年度合計": False,
                    }
                )
                continue

            for index, distribution in enumerate(
                distributions,
                start=1,
            ):
                dividend_rows.append(
                    {
                        "年份": year,
                        "股利類型": dividend_type,
                        "每單位股利": distribution[
                            "金額"
                        ],
                        "配息次序": index,
                        "除息日": distribution[
                            "除息日"
                        ],
                        "堆疊順序": None,
                        "累計股利": None,
                        "顯示分隔線": False,
                        "年度股利合計": None,
                        "顯示年度合計": False,
                    }
                )

        year_dividend_rows = [
            row
            for row in dividend_rows
            if row["年份"] == year
            and row["每單位股利"] is not None
        ]
        cumulative_dividend = 0.0
        for index, row in enumerate(
            year_dividend_rows
        ):
            row["堆疊順序"] = index + 1
            cumulative_dividend += float(
                row["每單位股利"]
            )
            row["累計股利"] = cumulative_dividend
            row["顯示分隔線"] = (
                index < len(year_dividend_rows) - 1
            )
            row["年度股利合計"] = cumulative_dividend
            row["顯示年度合計"] = (
                index == len(year_dividend_rows) - 1
            )

        yield_rows.append(
            {
                "年份": year,
                "殖利率": (
                    summary["殖利率"]
                    if summary["殖利率筆數"]
                    else None
                ),
                "已取得筆數": summary[
                    "殖利率筆數"
                ],
                "配息筆數": summary[
                    "配息筆數"
                ],
            }
        )

    return (
        dividend_rows,
        yield_rows,
        stock_dividend_available,
    )


def build_dividend_summary_rows(
    items: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """建立較完整的歷次配息摘要明細。"""

    return [
        {
            "年/季": format_dividend_period(item),
            "現金/股票": format_cash_stock_dividend(
                item.get("amount_per_unit"),
                item.get("stock_dividend_per_unit"),
            ),
            "殖利率": format_dividend_yield(
                item.get("yield_pct")
            ),
            "除息日": (
                format_dividend_summary_date(
                    item.get(
                        "ex_dividend_date"
                    )
                )
            ),
            "發放日": (
                format_dividend_summary_date(
                    item.get(
                        "payment_date"
                    )
                )
            ),
        }
        for item in items
    ]


DIVIDEND_EVENT_COLUMN_SEPARATOR = " ｜ "
DIVIDEND_EVENT_COLUMN_WIDTHS = (8, 11, 8, 12)


def get_display_width(value: str) -> int:
    """計算中英文混排文字在等寬字型中的顯示格數。"""

    return sum(
        2
        if unicodedata.east_asian_width(character) in {"W", "F"}
        else 1
        for character in value
    )


def pad_to_display_width(value: str, width: int) -> str:
    """補足欄位顯示寬度，讓表頭與資料分隔線一致。"""

    return value + " " * max(0, width - get_display_width(value))


def format_dividend_event_row_label(
    values: tuple[str, str, str, str, str],
) -> str:
    """以一致的顯示寬度建立可展開配息列。"""

    fixed_columns = tuple(
        pad_to_display_width(value, width)
        for value, width in zip(
            values[:-1],
            DIVIDEND_EVENT_COLUMN_WIDTHS,
            strict=True,
        )
    )
    return DIVIDEND_EVENT_COLUMN_SEPARATOR.join(
        (*fixed_columns, values[-1])
    )


def get_component_display_name(
    component: dict[str, Any],
) -> str:
    """取得不混淆預估與實際所得的顯示名稱。"""

    code = str(
        component.get(
            "component_code",
            "",
        )
    ).strip().upper()

    configured_label = (
        DIVIDEND_COMPONENT_LABELS.get(
            code
        )
    )

    if configured_label is not None:
        return configured_label

    component_name = component.get(
        "component_name"
    )

    if component_name is not None:
        normalized_name = str(
            component_name
        ).strip()

        if normalized_name:
            return normalized_name.replace(
                "預估",
                "",
            )

    return code or "未命名組成"


def build_component_display_rows(
    components: list[dict[str, Any]],
    component_basis: str,
    dividend_amount_per_unit: Any = None,
    currency: Any = "TWD",
) -> list[dict[str, str]]:
    """建立指定資訊基礎的配息組成顯示資料。"""

    # 保留參數以相容既有呼叫端；組成表的欄名已明確為「金額」，
    # 因此畫面不再於每個儲存格重複顯示幣別。
    del currency

    normalized_basis = (
        component_basis.strip().upper()
    )

    rows: list[
        dict[str, str]
    ] = []

    for component in components:
        current_basis = str(
            component.get(
                "component_basis",
                "",
            )
        ).strip().upper()

        if current_basis != normalized_basis:
            continue

        component_amount = component.get(
            "amount_per_unit"
        )
        if component_amount is None:
            ratio_pct = component.get(
                "ratio_pct"
            )

            if (
                dividend_amount_per_unit is not None
                and ratio_pct is not None
            ):
                try:
                    component_amount = (
                        Decimal(str(dividend_amount_per_unit))
                        * Decimal(str(ratio_pct))
                        / Decimal("100")
                    )

                except (InvalidOperation, ValueError):
                    component_amount = None

        rows.append(
            {
                "組成": (
                    get_component_display_name(
                        component
                    )
                ),
                "比例": (
                    format_dividend_percentage(
                        component.get(
                            "ratio_pct"
                        )
                    )
                ),
                "金額": (
                    format_number(
                        component_amount,
                        decimal_places=0,
                        trim_trailing_zeros=True,
                    )
                    if component_amount is not None
                    else "尚未取得"
                ),
            }
        )

    return rows


def render_component_group(
    title: str,
    components: list[dict[str, Any]],
    component_basis: str,
    dividend_amount_per_unit: Any = None,
    currency: Any = "TWD",
) -> None:
    """顯示指定資料基礎的配息組成。"""

    st.markdown(
        f"**{title}**"
    )

    rows = build_component_display_rows(
        components=components,
        component_basis=component_basis,
        dividend_amount_per_unit=(
            dividend_amount_per_unit
        ),
        currency=currency,
    )

    if not rows:
        st.caption(
            "目前沒有此類組成資料。"
        )
        return

    st.table(rows)


def render_dividend_summary(
    api_base_url: str,
    history: dict[str, Any],
    *,
    show_owner_details: bool = False,
) -> None:
    """以卡片顯示 ETF 配息摘要。"""

    with st.container(
        border=True,
        key="etf-detail-dividend-summary",
    ):
        _render_dividend_summary_card(
            api_base_url,
            history,
            show_owner_details=show_owner_details,
        )


def _render_dividend_summary_card(
    api_base_url: str,
    history: dict[str, Any],
    *,
    show_owner_details: bool,
) -> None:
    """顯示配息摘要卡片內容。"""

    st.subheader("配息資料")

    items = history.get(
        "items",
        [],
    )

    if not items:
        st.info(
            "目前沒有配息歷史資料。"
        )
        return

    latest = items[0]

    date_column, amount_column, payment_column = (
        st.columns(3)
    )

    with date_column:
        st.metric(
            "最新除息日",
            format_optional_date(
                latest.get(
                    "ex_dividend_date"
                )
            ),
        )

    with amount_column:
        st.metric(
            "現金/股票",
            format_cash_stock_dividend(
                latest.get(
                    "amount_per_unit"
                ),
                latest.get(
                    "stock_dividend_per_unit"
                ),
            ),
        )

    with payment_column:
        st.metric(
            "最新發放日",
            format_optional_date(
                latest.get(
                    "payment_date"
                )
            ),
        )

    (
        annual_dividend_rows,
        annual_yield_rows,
        stock_dividend_available,
    ) = build_annual_dividend_chart_rows(
        items
    )
    chart_years = [
        str(row["年份"])
        for row in annual_yield_rows
    ]
    dividend_y_upper = chart_axis_upper_bound(
        [
            row.get("年度股利合計")
            for row in annual_dividend_rows
            if row.get("顯示年度合計")
        ]
    )
    yield_y_upper = chart_axis_upper_bound(
        [row.get("殖利率") for row in annual_yield_rows]
    )
    chart_value_text_color = (
        "#FFFFFF"
        if st.context.theme.type == "dark"
        else "#000000"
    )

    if annual_dividend_rows:
        dividend_chart_column, yield_chart_column = (
            st.columns(2, gap="medium")
        )

        with dividend_chart_column:
            st.markdown(
                "**股利**　"
                f'<span style="color:{DIVIDEND_CASH_COLOR}">■</span> '
                "現金股利　"
                f'<span style="color:{DIVIDEND_STOCK_COLOR}">■</span> '
                "股票股利",
                unsafe_allow_html=True,
            )
            st.vega_lite_chart(
                annual_dividend_rows,
                {
                    "height": 280,
                    "transform": [{
                        "calculate": "format(datum['每單位股利'], datum['股利類型'] === '現金股利' ? ',.0f' : '.4f')",
                        "as": "股利顯示",
                    }],
                    "layer": [
                        {
                            "mark": {
                                "type": "bar",
                            },
                            "encoding": {
                                "x": {
                                    "field": "年份",
                                    "type": "ordinal",
                                    "sort": "ascending",
                                    "scale": {
                                        "domain": chart_years,
                                    },
                                    "axis": {
                                        "title": None,
                                        "labelAngle": 0,
                                    },
                                },
                                "y": {
                                    "field": "每單位股利",
                                    "type": "quantitative",
                                    "stack": "zero",
                                    "scale": {
                                        "domain": [0, dividend_y_upper],
                                        "nice": False,
                                    },
                                    "axis": {
                                        "title": None,
                                        "tickCount": 6,
                                        "format": ",.0f",
                                    },
                                },
                                "color": {
                                    "field": "股利類型",
                                    "type": "nominal",
                                    "scale": {
                                        "domain": [
                                            "現金股利",
                                            "股票股利",
                                        ],
                                        "range": [
                                            DIVIDEND_CASH_COLOR,
                                            DIVIDEND_STOCK_COLOR,
                                        ],
                                    },
                                    "legend": None,
                                },
                                "order": {
                                    "field": "堆疊順序",
                                    "type": "quantitative",
                                    "sort": "ascending",
                                },
                                "tooltip": [
                                    {
                                        "field": "年份",
                                        "type": "ordinal",
                                    },
                                    {
                                        "field": "股利類型",
                                        "type": "nominal",
                                    },
                                    {
                                        "field": "股利顯示",
                                        "type": "nominal",
                                        "title": "現金／股票股利",
                                    },
                                    {
                                        "field": "配息次序",
                                        "type": "quantitative",
                                    },
                                    {
                                        "field": "除息日",
                                        "type": "nominal",
                                    },
                                ],
                            },
                        },
                        {
                            "transform": [
                                {
                                    "filter": (
                                        "datum['顯示分隔線'] === true"
                                    ),
                                }
                            ],
                            "mark": {
                                "type": "rule",
                                "stroke": "#FFFFFF",
                                "strokeWidth": 1.5,
                                "strokeDash": [4, 2],
                            },
                            "encoding": {
                                "x": {
                                    "field": "年份",
                                    "type": "ordinal",
                                    "bandPosition": 0.1,
                                    "scale": {
                                        "domain": chart_years,
                                    },
                                },
                                "x2": {
                                    "field": "年份",
                                    "bandPosition": 0.9,
                                },
                                "y": {
                                    "field": "累計股利",
                                    "type": "quantitative",
                                    "scale": {
                                        "domain": [0, dividend_y_upper],
                                        "nice": False,
                                    },
                                },
                            },
                        },
                        {
                            "transform": [
                                {
                                    "filter": (
                                        "datum['顯示年度合計'] === true"
                                    ),
                                }
                            ],
                            "mark": {
                                "type": "text",
                                "dy": -9,
                                "fontWeight": "bold",
                                "color": chart_value_text_color,
                            },
                            "encoding": {
                                "x": {
                                    "field": "年份",
                                    "type": "ordinal",
                                    "sort": "ascending",
                                    "scale": {
                                        "domain": chart_years,
                                    },
                                },
                                "y": {
                                    "field": "年度股利合計",
                                    "type": "quantitative",
                                    "scale": {
                                        "domain": [0, dividend_y_upper],
                                        "nice": False,
                                    },
                                },
                                "text": {
                                    "field": "年度股利合計",
                                    "type": "quantitative",
                                    "format": ".2f",
                                },
                            },
                        },
                    ],
                },
                width="stretch",
                key="dividend-cash-stock-chart",
            )

            if (
                show_owner_details
                and not stock_dividend_available
            ):
                st.caption(
                    "股票股利資料尚未匯入，"
                    "不以 0 代替。"
                )

        with yield_chart_column:
            st.markdown("**殖利率(%)**")
            st.vega_lite_chart(
                annual_yield_rows,
                {
                    "height": 280,
                    "layer": [
                        {
                            "mark": {
                                "type": "line",
                                "point": True,
                                "color": "#D9822B",
                            },
                            "encoding": {
                                "x": {
                                    "field": "年份",
                                    "type": "ordinal",
                                    "sort": "ascending",
                                    "scale": {
                                        "domain": chart_years,
                                    },
                                    "axis": {
                                        "title": None,
                                        "labelAngle": 0,
                                    },
                                },
                                "y": {
                                    "field": "殖利率",
                                    "type": "quantitative",
                                    "scale": {
                                        "domain": [0, yield_y_upper],
                                        "nice": False,
                                    },
                                    "axis": {
                                        "title": None,
                                        "tickCount": 6,
                                    },
                                },
                                "tooltip": [
                                    {
                                        "field": "年份",
                                        "type": "ordinal",
                                    },
                                    {
                                        "field": "殖利率",
                                        "type": "quantitative",
                                        "format": ".2f",
                                    },
                                    {
                                        "field": "已取得筆數",
                                        "type": "quantitative",
                                    },
                                    {
                                        "field": "配息筆數",
                                        "type": "quantitative",
                                    },
                                ],
                            },
                        },
                        {
                            "transform": [
                                {
                                    "filter": "isValid(datum['殖利率'])",
                                }
                            ],
                            "mark": {
                                "type": "text",
                                "dy": -10,
                                "fontWeight": "bold",
                                "color": chart_value_text_color,
                            },
                            "encoding": {
                                "x": {
                                    "field": "年份",
                                    "type": "ordinal",
                                    "sort": "ascending",
                                    "scale": {
                                        "domain": chart_years,
                                    },
                                },
                                "y": {
                                    "field": "殖利率",
                                    "type": "quantitative",
                                    "scale": {
                                        "domain": [0, yield_y_upper],
                                        "nice": False,
                                    },
                                },
                                "text": {
                                    "field": "殖利率",
                                    "type": "quantitative",
                                    "format": ".2f",
                                },
                            },
                        },
                    ],
                },
                width="stretch",
                key="dividend-yield-chart",
            )

    else:
        st.info(
            "目前沒有可繪製趨勢的除息資料。"
        )

    st.caption(
        "資料皆來源於證交所；若有缺少時才以"
        "每單位現金股利 ÷ 除息前一交易日收盤價 × 100 計算。"
    )

    render_dividend_event_rows(
        api_base_url=api_base_url,
        items=items,
    )


def render_actual_76w_summary(
    summary: dict[str, Any],
    *,
    show_owner_details: bool = False,
) -> None:
    """顯示正式優先、e添富完整組成替代的資本利得分析。"""

    st.divider()
    st.subheader("資本利得組成 (76W) 統計")

    if show_owner_details:
        st.caption(
            "每次配息優先採完整正式 ACTUAL 組成；"
            "缺少時才採完整 e添富組成。"
            "e添富已實現資本利得僅供替代分析，"
            "不視為正式 76W。"
        )

    record_count = int(
        summary.get(
            "analysis_record_count",
            summary.get("actual_76w_record_count", 0),
        )
    )

    if record_count == 0:
        st.info(
            "尚未取得可用的正式 76W 或替代資本利得組成資料。"
        )
        return

    record_column, full_column, latest_column, average_column = (
        st.columns(4)
    )
    full_count = int(
        summary.get(
            "full_realized_gain_count",
            summary.get("full_76w_count", 0),
        )
    )
    latest_ratio = summary.get(
        "latest_realized_gain_ratio_pct",
        summary.get("latest_76w_ratio_pct"),
    )
    average_ratio = summary.get(
        "average_realized_gain_ratio_pct",
        summary.get("average_76w_ratio_pct"),
    )
    analysis_actual_count = int(
        summary.get(
            "analysis_actual_count",
            summary.get("actual_76w_record_count", 0),
        )
    )
    analysis_estimated_count = int(
        summary.get(
            "analysis_estimated_fallback_count",
            0,
        )
    )

    with record_column:
        st.metric(
            "分析配息",
            f"{record_count:,} 次",
        )

    with full_column:
        st.metric(
            "100% 資本利得",
            (
                f"{full_count:,} "
                "次"
            ),
        )

    with latest_column:
        st.metric(
            "最新資本利得比例",
            format_dividend_percentage(
                latest_ratio
            ),
        )

    with average_column:
        st.metric(
            "平均資本利得比例",
            format_dividend_percentage(
                average_ratio
            ),
        )

    if show_owner_details:
        st.caption(
            "分析基礎：正式 ACTUAL "
            f"{analysis_actual_count:,} 次；"
            "e添富替代 "
            f"{analysis_estimated_count:,} 次。"
        )


def render_dividend_event_rows(
    api_base_url: str,
    items: list[dict[str, Any]],
) -> None:
    """以可展開列顯示配息摘要與組成明細。"""

    with st.container(
        key="dividend-event-header",
    ):
        st.markdown(
            (
                '<span class="dividend-event-grid-header">'
                "<span>年/季</span><span> ｜ </span>"
                "<span>現金/股票</span><span> ｜ </span>"
                "<span>殖利率</span><span> ｜ </span>"
                "<span>除息日</span><span> ｜ </span>"
                "<span>發放日</span></span>"
            ),
            unsafe_allow_html=True,
        )

    for item in items:
        dividend_id = int(
            item["dividend_id"]
        )

        ex_date = format_optional_date(
            item.get(
                "ex_dividend_date"
            )
        )

        amount = format_cash_stock_dividend(
            item.get(
                "amount_per_unit"
            ),
            item.get(
                "stock_dividend_per_unit"
            ),
        )

        period = format_dividend_period(item)
        yield_text = format_dividend_yield(
            item.get("yield_pct")
        )
        payment_date = format_optional_date(
            item.get("payment_date")
        )

        label = format_dividend_event_row_label(
            (
                period,
                amount,
                yield_text,
                ex_date,
                payment_date,
            )
        )

        with st.expander(
            label,
            expanded=False,
        ):
            try:
                detail = load_dividend_detail(
                    api_base_url=api_base_url,
                    dividend_id=dividend_id,
                )

            except APIClientError as error:
                st.warning(
                    "無法取得此配息事件的組成資料。"
                )

                st.code(
                    str(error),
                    language=None,
                )

                continue

            selected_components = detail.get(
                "selected_components",
                [],
            )
            selected_basis = detail.get(
                "selected_component_basis"
            )
            source_basis = (
                "ACTUAL"
                if selected_basis == "ACTUAL"
                else "ESTIMATED"
            )

            render_component_group(
                title="現金股利組成",
                components=selected_components,
                component_basis=source_basis,
                dividend_amount_per_unit=(
                    detail.get("amount_per_unit")
                ),
                currency=detail.get("currency"),
            )





def format_optional_datetime(
    value: Any,
) -> str:
    """格式化可能缺少的 ISO 日期時間。"""

    return format_iso_datetime(
        value,
        missing_text="尚未取得",
        timespec=None,
        utc_label=True,
    )


def format_freshness_date(
    value: Any,
) -> str:
    """格式化新鮮度日期並保留缺資料語意。"""

    return format_iso_date(
        value,
        missing_text="尚未取得",
    )


def format_source_references(
    sources: list[dict[str, Any]],
) -> str:
    """將資料來源清單格式化為可讀文字。"""

    return format_shared_source_references(
        sources,
        missing_text="尚未取得",
    )


def build_data_profile_rows(
    profile: dict[str, Any],
) -> list[dict[str, str]]:
    """建立資料來源與新鮮度顯示列。"""

    master = profile["master"]
    performance = profile[
        "performance"
    ]
    dividends = profile["dividends"]
    actual = profile[
        "actual_dividend"
    ]

    available_periods = (
        performance[
            "available_periods"
        ]
    )

    period_text = (
        "、".join(
            available_periods
        )
        if available_periods
        else "尚無期間"
    )

    return [
        {
            "資料區塊": "ETF 主資料",
            "官方來源": (
                format_source_references(
                    master["sources"]
                )
            ),
            "最新資料日期": "—",
            "最近匯入": (
                format_optional_datetime(
                    master[
                        "latest_import_at"
                    ]
                )
            ),
            "資料量": "1 檔 ETF",
            "說明": (
                "最近匯入時間為 ETF "
                "主資料集層級"
            ),
        },
        {
            "資料區塊": "市價績效",
            "官方來源": (
                format_source_references(
                    performance["sources"]
                )
            ),
            "最新資料日期": (
                format_freshness_date(
                    performance[
                        "latest_as_of_date"
                    ]
                )
            ),
            "最近匯入": (
                format_optional_datetime(
                    performance[
                        "latest_import_at"
                    ]
                )
            ),
            "資料量": (
                f"{performance['record_count']:,} 筆"
            ),
            "說明": (
                "可用期間："
                f"{period_text}；"
                "目前為 PRICE_RETURN"
            ),
        },
        {
            "資料區塊": "配息事件",
            "官方來源": (
                format_source_references(
                    dividends["sources"]
                )
            ),
            "最新資料日期": (
                format_freshness_date(
                    dividends[
                        "latest_event_date"
                    ]
                )
            ),
            "最近匯入": (
                format_optional_datetime(
                    dividends[
                        "latest_import_at"
                    ]
                )
            ),
            "資料量": (
                f"{dividends['event_count']:,} 次"
            ),
            "說明": (
                "事件日期依除息、"
                "基準、發放或公告日判定"
            ),
        },
        {
            "資料區塊": "正式配息組成",
            "官方來源": (
                format_source_references(
                    actual["sources"]
                )
            ),
            "最新資料日期": (
                format_freshness_date(
                    actual[
                        "latest_source_document_date"
                    ]
                )
            ),
            "最近匯入": (
                format_optional_datetime(
                    actual[
                        "latest_import_at"
                    ]
                )
            ),
            "資料量": (
                "ACTUAL "
                f"{actual['actual_component_event_count']:,} 次；"
                "76W "
                f"{actual['actual_76w_event_count']:,} 次；"
                "來源文件 "
                f"{actual['source_document_event_count']:,} 次"
            ),
            "說明": (
                "僅統計正式 ACTUAL；"
                "預估資本利得不算 76W"
            ),
        },
    ]


def render_data_profile(
    profile: dict[str, Any],
) -> None:
    """顯示 ETF 資料來源與新鮮度。"""

    st.divider()
    st.subheader("資料來源與新鮮度")

    st.caption(
        "所有資訊均由 FastAPI 提供；"
        "日期缺少時顯示尚未取得，"
        "不以今天日期代替。"
    )

    st.table(
        build_data_profile_rows(
            profile
        )
    )


def render_comparison_action(
    code: str,
) -> None:
    """以資訊卡連結將目前 ETF 帶入公開比較頁。"""

    st.page_link(
        create_streamlit_page(
            ETF_COMPARISON_ROUTE
        ),
        label="加入比較",
        icon=":material/compare_arrows:",
        width="content",
        query_params=(
            build_comparison_query_params(
                codes=(
                    str(code),
                ),
                source=str(
                    ETF_DETAIL_ROUTE.url_path
                ),
                source_query_params=(
                    query_params_to_dict(
                        st.query_params
                    )
                ),
            )
        ),
    )


def render_detail_section_error(
    title: str,
    message: str,
    error: APIClientError,
) -> None:
    """顯示不影響其他區塊的載入錯誤。"""

    st.divider()
    st.subheader(title)

    render_warning_state(
        message,
        detail=error,
    )


_REINVESTMENT_POLICY_LABELS = {
    "NO_REINVESTMENT": "不再投入",
    "EXCESS_ONLY": "僅投入超過目標的現金",
    "CUSTOM_PERCENTAGE": "自訂比例再投入",
    "FULL_REINVESTMENT": "全部再投入",
}


def _build_tax_rule_payload(
    *,
    income_tax_rate_54c: float,
    tax_credit_rate_54c: float,
    other_income_tax_rate: float,
    allow_credit_offset: bool,
) -> dict[str, Any]:
    """建立畫面明示的版本化稅務假設。"""

    common_other_codes = (
        "5A",
        "5B",
        "61D",
        "71",
        "76",
        "OTHER",
    )
    assumptions = [
        {
            "component_code": "54C",
            "income_tax_rate_pct": income_tax_rate_54c,
            "tax_credit_rate_pct": tax_credit_rate_54c,
            "supplementary_premium_applicable": True,
        },
        {
            "component_code": "76W",
            "income_tax_rate_pct": 0,
            "tax_credit_rate_pct": 0,
            "supplementary_premium_applicable": False,
        },
        {
            "component_code": "EST_DIVIDEND",
            "income_tax_rate_pct": income_tax_rate_54c,
            "tax_credit_rate_pct": tax_credit_rate_54c,
            "supplementary_premium_applicable": True,
        },
        {
            "component_code": "EST_INTEREST",
            "income_tax_rate_pct": other_income_tax_rate,
            "tax_credit_rate_pct": 0,
            "supplementary_premium_applicable": True,
        },
        {
            "component_code": "EST_REALIZED_CAPITAL_GAIN",
            "income_tax_rate_pct": 0,
            "tax_credit_rate_pct": 0,
            "supplementary_premium_applicable": False,
        },
        {
            "component_code": "EST_EQUALIZATION",
            "income_tax_rate_pct": other_income_tax_rate,
            "tax_credit_rate_pct": 0,
            "supplementary_premium_applicable": False,
        },
        {
            "component_code": "EST_OTHER",
            "income_tax_rate_pct": other_income_tax_rate,
            "tax_credit_rate_pct": 0,
            "supplementary_premium_applicable": False,
        },
    ]
    assumptions.extend(
        {
            "component_code": code,
            "income_tax_rate_pct": other_income_tax_rate,
            "tax_credit_rate_pct": 0,
            "supplementary_premium_applicable": code in {"5A", "5B"},
        }
        for code in common_other_codes
    )
    return {
        "rule_version": "TW-INDIVIDUAL-2026.1",
        "effective_date": "2021-01-01",
        "supplementary_premium_rate_pct": 2.11,
        "supplementary_premium_payment_threshold": 20000,
        "supplementary_premium_payment_cap": 10000000,
        "annual_tax_credit_cap": 80000,
        "allow_credit_offset_other_tax": allow_credit_offset,
        "component_assumptions": assumptions,
    }


def _render_tax_reinvestment_result(result: dict[str, Any]) -> None:
    """顯示歷史事實與四種前瞻假設，不產生推薦。"""

    for warning in result.get("warnings", []):
        st.warning(warning)
    facts = result["historical_facts"]
    calculation = result["calculation"]
    component_basis = facts.get("component_calculation_basis")
    is_estimated_fallback = component_basis == "ESTIMATED_FALLBACK"
    if result["status"] == "PARTIAL":
        issue_text = "、".join(
            (
                f"{item['field']} ({item['reason']})"
                + (
                    f"：{item['component_code']}"
                    if item.get("component_code")
                    else ""
                )
            )
            for item in calculation.get("issues", [])
        )
        st.warning(
            "部分結果無法計算；缺少的資料不會被當成 0。"
            + (f" {issue_text}" if issue_text else "")
        )

    with st.container(
        border=True,
        key="etf-detail-historical-facts-card",
    ):
        st.markdown("**歷史資料事實**")
        st.caption(
            "配息組成與歷史報酬只用來建立情境起點，"
            "不代表未來仍會持續。"
        )
        if is_estimated_fallback:
            st.warning(
                "本次查無可用的完整正式所得組成，"
                "已自動以 e添富預估占比作為計算替代。"
                "這些類別不等同投信正式揭露的 54C 或 76W。"
            )
        st.table(
            [
                {
                    "組成資料層級": (
                        "預估替代"
                        if is_estimated_fallback
                        else "正式 ACTUAL"
                        if component_basis == "ACTUAL"
                        else "尚未取得"
                    ),
                    "組成事件": facts.get("component_source_event_id")
                    or "尚未取得",
                    "組成日期": facts.get("component_source_date")
                    or "尚未取得",
                    "歷史年化配息率": format_shared_percentage(
                        facts.get("annual_gross_distribution_rate_pct")
                    ),
                    "價格報酬期間": facts.get("price_return_period_code")
                    or "尚未取得",
                    "年化價格報酬假設": format_shared_percentage(
                        facts.get("annual_price_return_pct")
                    ),
                }
            ]
        )
        component_mix = facts.get("calculation_component_mix")
        if component_mix:
            st.table(
                [
                    {
                        "組成代碼": item["component_code"],
                        "名稱": item.get("component_name") or "—",
                        "計算比例": format_shared_percentage(
                            item.get("ratio_pct")
                        ),
                    }
                    for item in component_mix
                ]
            )

    st.markdown("**情境估算結果**")
    st.caption(
        f"規則版本 {calculation['rule_version']}；"
        f"生效日 {calculation['rule_effective_date']}；"
        f"情境期間 {calculation['projection_years']} 年。"
        "以下為估算，不是稅務建議，也不標示最佳方案。"
    )
    if (
        facts.get("price_return_period_code") == "1Y"
        and int(calculation["projection_years"]) > 1
    ):
        st.warning(
            "情境外推提醒：目前使用最近 1 年價格報酬，並以相同報酬率"
            f"機械式複利 {int(calculation['projection_years'])} 年；"
            "數值可能被大幅放大，並非績效預測。"
        )
    rows = []
    failed_total_return = False
    for item in calculation["scenarios"]:
        failed_total_return = failed_total_return or (
            item.get("total_return_check_passed") is False
        )
        rows.append(
            {
                "配息使用方式": _REINVESTMENT_POLICY_LABELS.get(
                    item["policy"], item["policy"]
                ),
                "可使用現金": format_shared_amount(
                    item.get("usable_cash"), calculation["currency"],
                    decimal_places=0,
                ),
                "再投入現金": format_shared_amount(
                    item.get("reinvested_cash"), calculation["currency"],
                    decimal_places=0,
                ),
                "期末單位數": format_number(
                    item.get("ending_units"), decimal_places=4
                ),
                "期末價值": format_shared_amount(
                    item.get("ending_value"), calculation["currency"],
                    decimal_places=0,
                ),
                "估算稅與補充保費": format_shared_amount(
                    item.get("modeled_tax_cost"), calculation["currency"],
                    decimal_places=0,
                ),
                "稅後總報酬": format_shared_percentage(
                    item.get("after_tax_total_return_pct"), signed=True
                ),
            }
        )
    st.table(rows)
    if failed_total_return:
        st.error(
            "至少一個情境未通過總報酬檢查；"
            "稅務差異不能覆蓋資產價值惡化。"
        )


def build_target_monthly_cash_rows(
    monthly_cash_flow: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """建立 1 至 12 月現金流表格並清楚區分缺值與零。"""

    rows: list[dict[str, Any]] = []
    for item in monthly_cash_flow:
        rows.append(
            {
                "月份": f"{item['month']} 月",
                "歷史入帳次數": item["event_count"],
                "涵蓋年數": item["observed_year_count"],
                "年化稅前現金": format_shared_amount(
                    item.get("annualized_gross_cash"),
                    missing_text="無法計算",
                    decimal_places=0,
                ),
                "年化稅後現金": format_shared_amount(
                    item.get("annualized_after_tax_cash"),
                    missing_text="無法計算",
                    decimal_places=0,
                ),
                "最近入帳日": format_iso_date(
                    item.get("latest_payment_date")
                ),
            }
        )
    return rows


def _render_target_analysis_result(result: dict[str, Any]) -> None:
    """呈現固定現金流目標與歷史逐月估算。"""

    cash_flow = result["cash_flow"]
    scenario = result["scenario_estimate"]
    with st.container(horizontal=True, border=True):
        st.metric(
            "所需本金",
            format_shared_amount(
                cash_flow.get("required_capital"), decimal_places=0
            ),
        )
        st.metric(
            "資金缺口",
            format_shared_amount(
                cash_flow.get("funding_shortfall"), decimal_places=0
            ),
        )
        st.metric(
            "年度稅後目標",
            format_shared_amount(
                cash_flow.get("annual_after_tax_target"), decimal_places=0
            ),
        )
        st.metric(
            "目前目標覆蓋率",
            format_shared_percentage(cash_flow.get("target_coverage_pct")),
        )

    st.caption(
        "下表以歷史付款月份按涵蓋年數年化；無入帳資料顯示為無法計算，"
        "不代表該月現金流為 0。"
    )
    st.table(build_target_monthly_cash_rows(result["monthly_cash_flow"]))
    st.caption(
        "不再投入配息情境的估算稅後總報酬："
        + format_shared_percentage(
            scenario.get("after_tax_total_return_pct"), signed=True
        )
    )
    for warning in result.get("warnings", []):
        st.warning(warning.get("message", "歷史結果不保證未來表現。"))
        if warning.get("as_of_date") or warning.get("source_id"):
            basis = "；".join(
                item
                for item in (
                    (
                        f"資料基準日 {warning['as_of_date']}"
                        if warning.get("as_of_date")
                        else ""
                    ),
                    (
                        f"來源 {warning['source_id']}"
                        if warning.get("source_id")
                        else ""
                    ),
                )
                if item
            )
            st.caption(basis)
        if warning.get("evidence"):
            evidence_text = "、".join(
                f"{key}={value}"
                for key, value in warning["evidence"].items()
                if value is not None and value != ""
            )
            st.caption(f"判定證據：{evidence_text}")
    if result.get("unavailable_fields"):
        fields = "、".join(
            str(item.get("field", "未知欄位"))
            for item in result["unavailable_fields"]
        )
        st.info(f"目前無法計算：{fields}")


def render_base_target_analysis(
    *,
    api_base_url: str,
    etf: dict[str, Any],
    latest_close: dict[str, Any] | None,
    latest_close_error: APIClientError | None = None,
) -> None:
    """呈現基準 ETF 的固定現金流目標分析。"""

    st.divider()
    st.subheader("目標現金流分析")
    st.caption("依歷史配息與市價績效估算；不是報酬承諾或投資建議。")
    if latest_close_error is not None:
        render_warning_state("無法取得官方最新收盤價。", detail=latest_close_error)
        return
    if latest_close is None or latest_close.get("close_price") is None:
        st.warning("目前沒有可追溯的官方收盤價，因此暫不提供本金需求估算。")
        return

    st.info(
        "計算採用官方收盤價 "
        f"{latest_close['close_price']:,.0f} NTD（{latest_close['trade_date']}；"
        f"來源 {latest_close['source_id']}），價格不可手動覆寫。"
    )
    with st.form(
        f"target_analysis_{etf['code']}",
        enter_to_submit=False,
    ):
        columns = st.columns(3)
        with columns[0]:
            held_units = st.number_input(
                "目前持有單位數", min_value=0, value=0, step=100
            )
            monthly_target = st.number_input(
                "每月稅後現金目標（NTD）",
                format="%.0f",
                min_value=0.0,
                value=3000.0,
                step=500.0,
            )
        with columns[1]:
            analysis_years = st.number_input(
                "估算年數", min_value=1, max_value=50, value=10
            )
            history_years = st.number_input(
                "歷史資料年數", min_value=1, max_value=10, value=3
            )
        with columns[2]:
            has_deduction = st.checkbox("提供現金扣除率假設", value=False)
            deduction_rate = st.number_input(
                "現金扣除率（%）",
                min_value=0.0,
                max_value=100.0,
                value=5.0,
                disabled=not has_deduction,
            )
        submitted = st.form_submit_button(
            "計算現金流目標", type="primary", icon=":material/calculate:"
        )

    state_key = f"target_analysis_result_{etf['code']}"
    if submitted:
        payload = {
            "held_units": int(held_units),
            "unit_price": latest_close["close_price"],
            "monthly_after_tax_target": monthly_target,
            "analysis_years": int(analysis_years),
            "history_years": int(history_years),
            "cash_deduction_rate_pct": (
                deduction_rate if has_deduction else None
            ),
        }
        try:
            with loading_state("正在計算目標現金流..."):
                st.session_state[state_key] = fetch_etf_target_analysis(
                    api_base_url=api_base_url,
                    code=str(etf["code"]),
                    payload=payload,
                )
        except APIClientError as error:
            render_warning_state("無法完成目標現金流分析。", detail=error)
    if state_key in st.session_state:
        _render_target_analysis_result(st.session_state[state_key])


def render_tax_reinvestment_analysis(
    *,
    api_base_url: str,
    etf: dict[str, Any],
) -> None:
    """顯示 M10-4 稅務與再投資估算表單。"""

    st.divider()
    st.subheader("稅務與再投入情境")
    st.caption(
        "適用範圍：持有台灣上市 ETF 的台灣稅務居民個人。"
        "請依自身申報情況調整有效稅率；結果僅供估算。"
    )

    with st.form(
        f"tax_reinvestment_{etf['code']}",
        enter_to_submit=False,
    ):
        input_columns = st.columns(3)
        with input_columns[0]:
            held_units = st.number_input(
                "持有單位數", min_value=0.0, value=1000.0, step=100.0
            )
            unit_price = st.number_input(
                "目前每單位價格（NTD）",
                format="%.0f",
                min_value=0.01,
                value=30.0,
                step=0.1,
            )
            monthly_target = st.number_input(
                "每月希望保留的現金（NTD）",
                format="%.0f",
                min_value=0.0,
                value=3000.0,
                step=500.0,
            )
        with input_columns[1]:
            analysis_years = st.number_input(
                "估算年數", min_value=1, max_value=50, value=10
            )
            history_years = st.number_input(
                "歷史資料年數", min_value=1, max_value=10, value=3
            )
            payments_per_year = st.number_input(
                "假設每年配息次數", min_value=1, max_value=365, value=4
            )
            custom_pct = st.number_input(
                "自訂再投入比例（%）",
                min_value=0.0,
                max_value=100.0,
                value=50.0,
            )
        with input_columns[2]:
            rate_54c = st.number_input(
                "54C 有效所得稅率（%）",
                min_value=0.0,
                max_value=100.0,
                value=12.0,
            )
            credit_54c = st.number_input(
                "54C 可用抵減率（%）",
                min_value=0.0,
                max_value=100.0,
                value=8.5,
            )
            other_rate = st.number_input(
                "其他所得有效稅率（%）",
                min_value=0.0,
                max_value=100.0,
                value=12.0,
            )
            allow_credit_offset = st.checkbox(
                "允許股利抵減影響其他所得稅額",
                value=False,
            )
        submitted = st.form_submit_button(
            "比較四種情境",
            type="primary",
            icon=":material/calculate:",
        )

    state_key = f"tax_reinvestment_result_{etf['code']}"
    if submitted:
        request_payload = {
            "held_units": held_units,
            "unit_price": unit_price,
            "monthly_cash_target": monthly_target,
            "analysis_years": int(analysis_years),
            "history_years": int(history_years),
            "payments_per_year": int(payments_per_year),
            "custom_reinvestment_pct": custom_pct,
            "tax_rule": _build_tax_rule_payload(
                income_tax_rate_54c=rate_54c,
                tax_credit_rate_54c=credit_54c,
                other_income_tax_rate=other_rate,
                allow_credit_offset=allow_credit_offset,
            ),
        }
        try:
            with loading_state("正在計算稅務與再投入情境..."):
                st.session_state[state_key] = (
                    fetch_tax_reinvestment_scenarios(
                        api_base_url=api_base_url,
                        code=str(etf["code"]),
                        payload=request_payload,
                    )
                )
        except APIClientError as error:
            render_warning_state("無法完成稅務情境估算。", detail=error)

    if state_key in st.session_state:
        _render_tax_reinvestment_result(st.session_state[state_key])


def render_etf_detail() -> None:
    """顯示 ETF 詳細資料頁。"""

    render_page_title("詳細資料")

    requested_code = (
        get_requested_code()
    )

    render_detail_actions(
        can_refresh=bool(requested_code),
    )

    if not requested_code:
        st.warning(
            "目前網址沒有指定 ETF 代號。"
        )

        render_code_form()
        return

    try:
        api_base_url = get_api_base_url()

    except ValueError as error:
        render_api_error(
            "前端 API 網址設定不正確。",
            error,
        )
        return

    try:
        with loading_state(
            f"正在讀取 {requested_code}..."
        ):
            etf = load_etf_detail(
                api_base_url=api_base_url,
                code=requested_code,
            )

    except APIResourceNotFoundError as error:
        render_not_found_state(
            f"找不到 ETF：{requested_code}",
            hint=str(error),
        )

        render_code_form(
            default_code=requested_code
        )

        return

    except APIClientError as error:
        render_api_error(
            "無法取得 ETF 詳細資料。",
            error,
            hint=(
                "請確認 FastAPI 已在 "
                "127.0.0.1:8000 啟動。"
            ),
        )
        return

    grade_payload: object = None
    grade_error = False
    try:
        grade_lookup = load_historical_quality_grade_lookup(
            api_base_url,
            (requested_code,),
        )
        grade_payload = grade_lookup.get(requested_code)
    except (APIClientError, ValueError):
        grade_error = True

    performance: dict[str, Any] | None = None
    performance_error: APIClientError | None = None

    try:
        performance = load_etf_performance(
            api_base_url=api_base_url,
            code=requested_code,
        )

    except APIClientError as error:
        performance_error = error

    price_history: dict[str, Any] | None = None
    try:
        price_history = load_etf_price_history(
            api_base_url=api_base_url,
            code=requested_code,
        )
    except APIClientError:
        price_history = None

    dividend_history: dict[
        str,
        Any,
    ] | None = None

    dividend_history_error: (
        APIClientError | None
    ) = None

    try:
        dividend_history = (
            load_etf_dividends(
                api_base_url=api_base_url,
                code=requested_code,
            )
        )

    except APIClientError as error:
        dividend_history_error = error

    actual_76w: dict[
        str,
        Any,
    ] | None = None

    actual_76w_error: (
        APIClientError | None
    ) = None

    try:
        actual_76w = (
            load_etf_actual_76w(
                api_base_url=api_base_url,
                code=requested_code,
            )
        )

    except APIClientError as error:
        actual_76w_error = error

    owner_unlocked = get_owner_token() is not None

    render_etf_information(
        etf,
        grade_payload,
        show_owner_details=owner_unlocked,
    )

    if grade_error:
        st.caption(
            "喵喵評等服務暫時無法取得；"
            "本頁其他資料仍可正常查看。"
        )

    if performance_error is not None:
        render_detail_section_error(
            "績效",
            "無法取得 ETF 績效資料。",
            performance_error,
        )

    elif performance is not None:
        render_etf_performance(
            performance,
            price_history,
        )

    if dividend_history_error is not None:
        render_detail_section_error(
            "配息摘要",
            "無法取得 ETF 配息歷史。",
            dividend_history_error,
        )

    elif dividend_history is not None:
        render_dividend_summary(
            api_base_url,
            dividend_history,
            show_owner_details=owner_unlocked,
        )

    if actual_76w_error is not None:
        render_detail_section_error(
            "資本利得組成 (76W) 統計",
            "無法取得 76W 與資本利得資料。",
            actual_76w_error,
        )

    elif actual_76w is not None:
        render_actual_76w_summary(
            actual_76w,
            show_owner_details=owner_unlocked,
        )

    if owner_unlocked:
        render_tax_reinvestment_analysis(
            api_base_url=api_base_url,
            etf=etf,
        )
