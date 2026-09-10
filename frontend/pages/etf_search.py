"""ETF 搜尋、篩選及分頁頁面。"""

from dataclasses import replace
from html import escape, unescape
import math
from typing import Any
from unicodedata import east_asian_width
from urllib.parse import urlencode

import streamlit as st

from frontend.api_client import (
    APIClientError,
    fetch_etfs,
)
from frontend.config import (
    get_api_base_url,
)
from frontend.navigation import (
    ETF_DETAIL_ROUTE,
    ETF_SEARCH_ROUTE,
    build_detail_query_params,
)
from frontend.query_state import (
    ETFSearchQueryState,
    PAGE_SIZE_OPTIONS,
    parse_etf_search_query_state,
    sync_query_params,
)
from frontend.ui.components import (
    render_page_title,
    render_pagination_controls,
)
from frontend.ui.formatters import (
    format_etf_display_name,
    format_number,
    management_type_label,
)
from frontend.ui.states import (
    loading_state,
    render_api_error,
    render_empty_state,
)
from frontend.ui.quality_grade import (
    load_historical_quality_grade_lookup,
    quality_grade_short_label,
)


ACTIVE_FILTER_OPTIONS: dict[
    str,
    bool | None,
] = {
    "全部": None,
    "主動式": True,
    "被動式": False,
}

NON_BOND_LABEL = "非債券"

RESULT_ACTION_KEY = "etf_search_detail_action"

SEARCH_QUERY_SIGNATURE_KEY = (
    "_etf_search_query_signature"
)

SEARCH_TABLE_COLUMNS = (
    ("code", "代號"),
    ("name", "名稱"),
    ("historical_quality", "喵喵評等"),
    ("management_type", "管理方式"),
    ("listing_date", "上市日期"),
    ("fund_size", "基金規模"),
    ("expense_ratio", "費用率"),
)


def format_optional_number(
    value: Any,
    suffix: str,
    decimal_places: int = 2,
) -> str:
    """格式化可能為空白的數值。"""

    return format_number(
        value,
        decimal_places=decimal_places,
        suffix=suffix,
        missing_text="—",
        invalid_text="格式異常",
    )


def format_etf_result_row(
    item: dict[str, Any],
    grade_payload: object = None,
) -> dict[str, str]:
    """建立欄位固定的 ETF 搜尋結果。"""

    code = str(
        item["code"]
    ).strip().upper()

    name = format_etf_display_name(
        item["name"]
    )

    management_type = (
        management_type_label(
            item["is_active"]
        )
    )

    listing_date = (
        str(item["listing_date"])
        if item["listing_date"]
        else "—"
    )

    fund_size = format_optional_number(
        item["fund_size"],
        " 億元",
        decimal_places=0,
    )

    expense_ratio = format_optional_number(
        item["expense_ratio"],
        "%",
    )
    if item.get("annual_expense"):
        expense_ratio += f"（{item['annual_expense']['reporting_year']} 年歷史總費用）"

    return {
        "code": code,
        "name": name,
        "historical_quality": quality_grade_short_label(
            grade_payload
        ),
        "management_type": management_type,
        "listing_date": listing_date,
        "fund_size": fund_size,
        "expense_ratio": expense_ratio,
    }


def render_clickable_etf_rows(
    items: list[dict[str, Any]],
    query_state: ETFSearchQueryState | None = None,
    grade_lookup: dict[str, dict[str, Any]] | None = None,
) -> None:
    """以整列可點擊的固定欄位表格顯示 ETF 清單。"""

    source_state = (
        query_state
        if query_state is not None
        else ETFSearchQueryState(
            bond_label=NON_BOND_LABEL
        )
    )

    st.html(
        build_etf_search_table_html(
            items,
            source_state,
            grade_lookup=grade_lookup,
        ),
        width="stretch",
    )


def html_text(value: object) -> str:
    """將外部文字正規化後安全放入 HTML。"""

    return escape(
        unescape(str(value)),
        quote=True,
    )


def estimate_text_width_rem(value: object) -> float:
    """依字元實際顯示寬度估算固定欄寬。"""

    width = 0.0
    for character in unescape(str(value)):
        if character.isspace():
            width += 0.35
        elif east_asian_width(character) in {"W", "F"}:
            width += 1.0
        elif character in "ilI1.,:;|!'`-":
            width += 0.35
        elif character in "MW@%&":
            width += 0.9
        else:
            width += 0.62

    return width


def build_etf_search_column_layout(
    rows: list[dict[str, str]],
) -> tuple[str, float]:
    """依各欄表頭或內容的最長文字建立固定欄寬。"""

    widths: list[float] = []
    for key, label in SEARCH_TABLE_COLUMNS:
        content_width = max(
            [estimate_text_width_rem(label)]
            + [
                estimate_text_width_rem(row[key])
                for row in rows
            ]
        )
        widths.append(
            max(
                3.5,
                math.ceil(
                    (content_width + 0.9) * 4
                ) / 4,
            )
        )

    template = " ".join(
        f"{width:g}rem"
        for width in widths
    )
    total_width = (
        sum(widths)
        + len(widths) - 1
        + 2
    )
    return template, total_width


def build_etf_search_table_html(
    items: list[dict[str, Any]],
    source_state: ETFSearchQueryState,
    *,
    grade_lookup: dict[str, dict[str, Any]] | None = None,
) -> str:
    """建立無選取欄、整列可開啟詳細資料的搜尋表格。"""

    formatted_rows = [
        (
            item,
            format_etf_result_row(
                item,
                (grade_lookup or {}).get(
                    str(item["code"]).strip().upper()
                ),
            ),
        )
        for item in items
    ]
    column_template, table_width = (
        build_etf_search_column_layout(
            [row for _, row in formatted_rows]
        )
    )

    header_cells = "".join(
        (
            '<span class="performance-ranking-cell" '
            f'role="columnheader">{html_text(label)}</span>'
        )
        for _, label in SEARCH_TABLE_COLUMNS
    )

    row_html: list[str] = []
    for item, row in formatted_rows:
        code = str(item["code"]).strip().upper()
        query = urlencode(
            build_detail_query_params(
                code=code,
                source=str(ETF_SEARCH_ROUTE.url_path),
                source_query_params=source_state.to_query_params(),
            )
        )
        href = f"/{ETF_DETAIL_ROUTE.url_path}?{query}"
        cell_values = (
            row["code"],
            row["name"],
            row["historical_quality"],
            row["management_type"],
            row["listing_date"],
            row["fund_size"],
            row["expense_ratio"],
        )
        cells = "".join(
            (
                '<span class="performance-ranking-cell" '
                f'role="cell">{html_text(value)}</span>'
            )
            for value in cell_values
        )
        row_html.append(
            (
                '<a class="performance-ranking-row" '
                f'href="{html_text(href)}" role="row" '
                f'aria-label="查看 {html_text(code)} '
                f'{html_text(row["name"])} 詳細資料">'
                f"{cells}</a>"
            )
        )

    return (
        '<div class="performance-ranking-scroll">'
        '<div class="performance-ranking-grid etf-search-grid" '
        f'style="--etf-search-columns: {column_template}; '
        f'width: {table_width:g}rem" '
        'role="table" aria-label="ETF 搜尋結果">'
        '<div class="performance-ranking-header" role="row">'
        f"{header_cells}</div>"
        f"{''.join(row_html)}"
        "</div></div>"
    )


def open_etf_detail(
    items: list[dict[str, Any]],
    source_state: ETFSearchQueryState,
    *,
    row_index: int | None = None,
) -> None:
    """由資料表選取列開啟 ETF 詳細資料。"""

    if row_index is None:
        selection = st.session_state.get(
            RESULT_ACTION_KEY,
            {},
        ).get("selection", {})
        selected_rows = selection.get(
            "rows",
            [],
        )
        if not selected_rows:
            return
        row_index = int(selected_rows[0])

    if not 0 <= row_index < len(items):
        return

    item = items[row_index]
    code = str(item["code"]).strip().upper()

    st.switch_page(
        "page_scripts/etf_detail_page.py",
        query_params=build_detail_query_params(
            code=code,
            source=str(
                ETF_SEARCH_ROUTE.url_path
            ),
            source_query_params=(
                source_state.to_query_params()
            ),
        ),
    )


def apply_search_state(
    state: ETFSearchQueryState,
) -> None:
    """將 URL 狀態套用至 Session State。"""

    st.session_state[
        "etf_search_keyword"
    ] = state.keyword

    st.session_state[
        "etf_search_active_label"
    ] = state.active_label

    st.session_state[
        "etf_search_bond_label"
    ] = state.bond_label

    st.session_state[
        "etf_search_page_size"
    ] = state.page_size

    st.session_state[
        "etf_search_page_number"
    ] = state.page

    st.session_state[
        SEARCH_QUERY_SIGNATURE_KEY
    ] = tuple(
        sorted(
            state.to_query_params().items()
        )
    )


def get_search_state() -> ETFSearchQueryState:
    """由 Session State 建立目前 ETF 查詢狀態。"""

    return ETFSearchQueryState(
        keyword=str(
            st.session_state[
                "etf_search_keyword"
            ]
        ),
        active_label=str(
            st.session_state[
                "etf_search_active_label"
            ]
        ),
        bond_label=str(
            st.session_state[
                "etf_search_bond_label"
            ]
        ),
        page=int(
            st.session_state[
                "etf_search_page_number"
            ]
        ),
        page_size=int(
            st.session_state[
                "etf_search_page_size"
            ]
        ),
    )


def initialize_search_state() -> None:
    """由 URL 初始化或更新 ETF 搜尋狀態。"""

    state = replace(
        parse_etf_search_query_state(
            st.query_params
        ),
        bond_label=NON_BOND_LABEL,
    )

    canonical = state.to_query_params()

    sync_query_params(
        st.query_params,
        canonical,
    )

    signature = tuple(
        sorted(canonical.items())
    )

    if (
        st.session_state.get(
            SEARCH_QUERY_SIGNATURE_KEY
        )
        != signature
    ):
        apply_search_state(state)


def update_search_state(
    state: ETFSearchQueryState,
) -> None:
    """同步 ETF 查詢 Session State 與網址。"""

    apply_search_state(state)

    sync_query_params(
        st.query_params,
        state.to_query_params(),
    )


def reset_search_state() -> None:
    """清除所有 ETF 搜尋條件。"""

    update_search_state(
        ETFSearchQueryState(
            bond_label=NON_BOND_LABEL
        )
    )


@st.cache_data(
    ttl=30,
    show_spinner=False,
)
def load_etf_page(
    api_base_url: str,
    keyword: str | None,
    is_active: bool | None,
    is_bond: bool | None,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    """取得並短暫快取 ETF 列表。"""

    return fetch_etfs(
        api_base_url=api_base_url,
        keyword=keyword,
        is_active=is_active,
        is_bond=is_bond,
        limit=limit,
        offset=offset,
    )


def render_search_form() -> None:
    """顯示 ETF 搜尋條件表單。"""

    active_labels = list(
        ACTIVE_FILTER_OPTIONS
    )

    with st.form(
        "etf_search_form",
        enter_to_submit=False,
    ):
        (
            keyword_column,
            active_column,
            size_column,
        ) = st.columns([2, 1, 1])

        with keyword_column:
            keyword = st.text_input(
                "關鍵字",
                value=str(
                    st.session_state[
                        "etf_search_keyword"
                    ]
                ),
                placeholder=(
                    "輸入 ETF 代號或名稱，"
                    "例如 00918"
                ),
            )

        with active_column:
            current_active_label = str(
                st.session_state[
                    "etf_search_active_label"
                ]
            )

            active_label = st.selectbox(
                "管理方式",
                options=active_labels,
                index=active_labels.index(
                    current_active_label
                ),
            )

        with size_column:
            current_page_size = int(
                st.session_state[
                    "etf_search_page_size"
                ]
            )

            page_size = st.selectbox(
                "每頁筆數",
                options=PAGE_SIZE_OPTIONS,
                index=(
                    PAGE_SIZE_OPTIONS.index(
                        current_page_size
                    )
                ),
            )

        submitted = st.form_submit_button(
            "搜尋",
            type="primary",
        )

        with st.container(
            key="etf-search-secondary-actions",
            horizontal=True,
            gap="small",
        ):
            clear_clicked = st.form_submit_button(
                "清除條件"
            )
            refresh_clicked = st.form_submit_button(
                "重新載入"
            )

    if clear_clicked:
        reset_search_state()
        load_etf_page.clear()
        st.rerun()

    if refresh_clicked:
        load_etf_page.clear()
        load_historical_quality_grade_lookup.clear()
        st.rerun()

    if submitted:
        update_search_state(
            ETFSearchQueryState(
                keyword=keyword.strip(),
                active_label=active_label,
                bond_label=NON_BOND_LABEL,
                page=1,
                page_size=page_size,
            )
        )

        load_etf_page.clear()
        st.rerun()
def render_pagination(
    state: ETFSearchQueryState,
    total_pages: int,
) -> None:
    """顯示上一頁與下一頁控制項。"""

    action = render_pagination_controls(
        current_page=state.page,
        total_pages=total_pages,
        previous_key="previous_etf_page",
        next_key="next_etf_page",
    )

    if action == "previous":
        update_search_state(
            replace(
                state,
                page=state.page - 1,
            )
        )
        st.rerun()

    if action == "next":
        update_search_state(
            replace(
                state,
                page=state.page + 1,
            )
        )
        st.rerun()


def render_etf_search() -> None:
    """顯示 ETF 搜尋頁面。"""

    initialize_search_state()

    render_page_title("搜尋")

    render_search_form()

    try:
        api_base_url = get_api_base_url()

    except ValueError as error:
        render_api_error(
            "前端 API 網址設定不正確。",
            error,
        )
        return

    state = get_search_state()

    is_active = ACTIVE_FILTER_OPTIONS[
        state.active_label
    ]

    is_bond = False

    offset = (
        state.page - 1
    ) * state.page_size

    try:
        with loading_state(
            "正在讀取 ETF 資料..."
        ):
            result = load_etf_page(
                api_base_url=api_base_url,
                keyword=(
                    state.keyword
                    if state.keyword
                    else None
                ),
                is_active=is_active,
                is_bond=is_bond,
                limit=state.page_size,
                offset=offset,
            )

    except APIClientError as error:
        render_api_error(
            "無法取得 ETF 資料。",
            error,
            hint=(
                "請確認 FastAPI 已在 "
                "127.0.0.1:8000 啟動。"
            ),
        )
        return

    total = int(result["total"])
    items = result["items"]

    total_pages = max(
        1,
        math.ceil(
            total / state.page_size
        ),
    )

    if state.page > total_pages:
        update_search_state(
            replace(
                state,
                page=total_pages,
            )
        )
        st.rerun()

    with st.container(
        key="etf-search-summary",
        gap=None,
    ):
        total_column, page_column, count_column = (
            st.columns(3)
        )

        with total_column:
            st.metric(
                "符合條件",
                f"{total:,} 檔",
            )

        with page_column:
            st.metric(
                "目前頁次",
                (
                    f"{state.page}"
                    f" / {total_pages}"
                ),
            )

        with count_column:
            st.metric(
                "本頁筆數",
                f"{len(items)}",
            )

        st.divider()

    if not items:
        render_empty_state(
            "目前沒有符合條件的 ETF。",
            hint=(
                "可清除條件或調整關鍵字與"
                "管理方式。"
            ),
        )
        return

    grade_lookup: dict[str, dict[str, Any]] = {}
    grade_error = False
    try:
        grade_lookup = load_historical_quality_grade_lookup(
            api_base_url,
            tuple(str(item["code"]) for item in items),
        )
    except (APIClientError, ValueError):
        grade_error = True

    render_clickable_etf_rows(
        items,
        query_state=state,
        grade_lookup=grade_lookup,
    )

    if grade_error:
        st.caption(
            "喵喵評等暫時無法取得；"
            "其他 ETF 資料仍可正常查看。"
        )

    st.caption(
        f"目前顯示第 "
        f"{offset + 1:,} 至 "
        f"{offset + len(items):,} 筆，"
        f"共 {total:,} 筆"
    )

    st.caption(
        "點選即可查看詳細資料。"
    )

    render_pagination(
        state=state,
        total_pages=total_pages,
    )
