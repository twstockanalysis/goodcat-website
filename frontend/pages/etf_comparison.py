"""ETF 多檔比較頁面。"""

from __future__ import annotations

import re
from typing import Any

import streamlit as st

from frontend.ui.components import render_page_title

from frontend.api_client import (
    APIClientError,
    fetch_etf_comparison,
    fetch_etfs,
    fetch_monthly_payment_combination,
)
from frontend.config import (
    get_api_base_url,
)
from frontend.query_state import (
    ETFComparisonQueryState,
    normalize_comparison_codes,
    parse_etf_comparison_query_state,
    query_params_to_dict,
    sync_query_params,
)
from frontend.ui.formatters import (
    asset_type_label,
    format_amount,
    format_iso_date,
    format_number,
    format_percentage as format_shared_percentage,
    management_type_label,
)
from frontend.ui.states import (
    loading_state,
    render_api_error,
)
from frontend.ui.quality_grade import (
    load_historical_quality_grade_lookup,
    render_historical_quality_evidence,
)


COMPARISON_PERIODS = (
    "1M",
    "3M",
    "6M",
    "1Y",
)


def build_monthly_coverage_rows(
    calculation: dict[str, Any],
) -> list[dict[str, str]]:
    """建立基準與組合付款月份覆蓋表。"""

    base_months = calculation.get("base_payment_months")
    combined_months = calculation.get("combined_payment_months")
    target_months = set(
        calculation.get("target_payment_months") or range(1, 13)
    )
    return [
        {
            "月份": f"{month} 月",
            "目標": "是" if month in target_months else "否",
            "基準 ETF": (
                "有歷史付款" if base_months is not None and month in base_months
                else "未覆蓋" if base_months is not None else "資料不足"
            ),
            "組合情境": (
                "不列入目標"
                if month not in target_months
                else "有歷史付款"
                if combined_months is not None and month in combined_months
                else "未覆蓋"
                if combined_months is not None
                else "無法估算"
            ),
        }
        for month in range(1, 13)
    ]


def build_target_payment_months(
    mode: str,
    *,
    anchor_month: int = 1,
    custom_months: list[int] | None = None,
) -> list[int]:
    """將 UI 目標模式轉成排序且不重複的月份集合。"""

    if anchor_month < 1 or anchor_month > 12:
        raise ValueError("起始月份必須介於 1 到 12")
    if mode == "全年每月":
        return list(range(1, 13))
    if mode in {"單月", "每年固定月"}:
        return [anchor_month]
    if mode == "隔月":
        return list(range(1 if anchor_month % 2 else 2, 13, 2))
    if mode == "每季":
        return list(range((anchor_month - 1) % 3 + 1, 13, 3))
    if mode == "任意月份":
        normalized = sorted(set(custom_months or []))
        if not normalized or any(month < 1 or month > 12 for month in normalized):
            raise ValueError("任意月份至少選擇一個 1 到 12 月的月份")
        return normalized
    raise ValueError("不支援的付款月份模式")


def build_candidate_result_rows(
    candidates: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """建立含理由、月份與透明分類的候選結果列。"""

    return [
        {
            "ETF": f"{item['etf_code']} {item['name']}",
            "管理方式": management_type_label(item["is_active"]),
            "資產類型": asset_type_label(item["is_bond"]),
            "補足月份": (
                "、".join(f"{month}月" for month in item["supported_gap_months"])
                or "無"
            ),
            "資料完整度": format_percentage(item.get("completeness_pct")),
            "付款穩定度": format_percentage(
                item.get("distribution_stability_pct")
            ),
            "資料新鮮": (
                "是" if item.get("data_is_fresh") is True else "否／不足"
            ),
            "估算稅後現金率": format_percentage(
                item.get("annual_after_tax_cash_rate_pct")
            ),
            "估算稅後總報酬": format_return(
                item.get("estimated_after_tax_total_return_pct")
            ),
            "下行觀察值": format_return(item.get("downside_return_pct")),
            "自動持股重疊": format_percentage(
                item.get("holding_overlap_pct")
            ),
            "理由": "；".join(
                reason["message"] for reason in item.get("reasons", [])
            ),
        }
        for item in candidates
    ]


def render_monthly_combination_result(result: dict[str, Any]) -> None:
    """顯示基準錨點、覆蓋、納入與排除理由。"""

    facts = result["historical_facts"]
    calculation = result["calculation"]
    with st.container(border=True, key="monthly-combination-card"):
        st.markdown(
            f"**基準 ETF：{calculation['base_etf_code']} "
            f"{calculation['base_etf_name']}**"
        )
        st.caption(
            f"付款日基礎；回看 {facts['lookback_years']} 年；"
            f"分析日 {facts['as_of_date']}。基準 ETF 始終保留為錨點。"
        )
    if calculation["status"] == "UNAVAILABLE":
        st.error("基準 ETF 的付款月份資料不足，無法建立組合情境。")
    elif calculation["status"] == "PARTIAL":
        st.warning("結果含資料限制；請閱讀每檔候選的取捨理由。")

    st.markdown("**付款月份覆蓋**")
    st.table(build_monthly_coverage_rows(calculation))
    selected = calculation["selected_candidates"]
    rejected = calculation["rejected_candidates"]
    st.markdown("**納入候選**")
    if selected:
        st.table(build_candidate_result_rows(selected))
    else:
        st.info("沒有候選通過全部門檻並補足付款缺口。")
    st.markdown("**排除候選**")
    if rejected:
        st.table(build_candidate_result_rows(rejected))
    else:
        st.caption("沒有被排除的候選。")
    st.caption(
        f"稅後現金扣除率假設：{format_percentage(result.get('cash_deduction_rate_pct'))}。"
        "主動／被動與債券／非債券只作透明屬性，不是品質評分。"
        f"{calculation['estimate_label']}。"
    )


def render_monthly_combination_analysis(
    *,
    api_base_url: str,
    comparison: dict[str, Any],
) -> None:
    """以比較清單建立 M10-5 月配缺口情境。"""

    items = comparison["items"]
    labels = {
        item["etf"]["code"]: (
            f"{item['etf']['code']} {item['etf']['name']}"
        )
        for item in items
    }
    st.divider()
    st.subheader("月配缺口組合")
    st.caption(
        "先檢查資料完整度、新鮮度、付款穩定性、總報酬與下行風險，"
        "再從比較清單選擇最多 1 至 3 檔互補 ETF。"
    )
    base_code = st.selectbox(
        "基準 ETF",
        options=list(labels),
        format_func=labels.__getitem__,
        help="基準 ETF 是分析錨點，不會被候選取代。",
    )
    candidate_items = [
        item for item in items if item["etf"]["code"] != base_code
    ]
    with st.form(
        f"monthly_combination_{'_'.join(labels)}",
        enter_to_submit=False,
    ):
        goal = st.segmented_control(
            "分析目標",
            options=["補足月配缺口", "只檢查候選資格"],
            default="補足月配缺口",
        )
        month_mode = st.selectbox(
            "希望收到現金流的月份模式",
            ["全年每月", "單月", "隔月", "每季", "每年固定月", "任意月份"],
            help="只補足指定的目標月份；未選月份不會被視為缺口。",
        )
        anchor_month = 1
        custom_months: list[int] | None = None
        if month_mode in {"單月", "每年固定月"}:
            anchor_month = st.selectbox(
                "目標月份", list(range(1, 13)),
                format_func=lambda month: f"{month} 月",
            )
        elif month_mode == "隔月":
            anchor_month = st.segmented_control(
                "隔月起始", [1, 2], default=1,
                format_func=lambda month: f"{month} 月起",
            )
        elif month_mode == "每季":
            anchor_month = st.segmented_control(
                "季度月份組", [1, 2, 3], default=1,
                format_func=lambda month: "、".join(
                    f"{value}月" for value in range(month, 13, 3)
                ),
            )
        elif month_mode == "任意月份":
            custom_months = st.pills(
                "選擇目標月份", list(range(1, 13)),
                default=list(range(1, 13)), selection_mode="multi",
                format_func=lambda month: f"{month} 月",
            )
        settings = st.columns(4)
        with settings[0]:
            lookback_years = st.number_input(
                "歷史資料年數", min_value=1, max_value=10, value=3
            )
        with settings[1]:
            max_additions = st.number_input(
                "最多互補檔數",
                min_value=1,
                max_value=len(candidate_items),
                value=min(3, len(candidate_items)),
            )
        with settings[2]:
            deduction_rate = st.number_input(
                "現金扣除率（%）",
                min_value=0.0,
                max_value=100.0,
                value=0.0,
            )
        with settings[3]:
            allocation = st.number_input(
                "每檔情境配置（%）",
                min_value=0.1,
                max_value=20.0,
                value=10.0,
            )

        assumptions = []
        candidate_columns = st.columns(len(candidate_items))
        for column, item in zip(candidate_columns, candidate_items, strict=True):
            code = item["etf"]["code"]
            with column:
                st.markdown(f"**{labels[code]}**")
                unit_price = st.number_input(
                    "每單位價格（NTD）",
                    format="%.0f",
                    min_value=0.01,
                    value=30.0,
                    step=0.1,
                    key=f"monthly_price_{base_code}_{code}",
                )
                st.caption(
                    "重疊率由正式成分股快照自動計算；資料未通過門檻時顯示未知。"
                )
                assumptions.append(
                    {
                        "etf_code": code,
                        "unit_price": unit_price,
                        "proposed_allocation_pct": allocation,
                    }
                )
        submitted = st.form_submit_button(
            "分析候選與付款缺口",
            type="primary",
            icon=":material/account_tree:",
        )

    state_key = (
        f"monthly_combination_result_{base_code}_{'_'.join(labels)}"
    )
    if submitted:
        try:
            target_payment_months = build_target_payment_months(
                month_mode,
                anchor_month=int(anchor_month),
                custom_months=custom_months,
            )
        except ValueError as error:
            st.error(str(error))
            return
        payload = {
            "candidates": assumptions,
            "lookback_years": int(lookback_years),
            "cash_deduction_rate_pct": deduction_rate,
            "max_complementary_etfs": int(max_additions),
            "monthly_coverage_enabled": goal == "補足月配缺口",
            "target_payment_months": target_payment_months,
        }
        try:
            with loading_state("正在分析候選 ETF 與付款缺口..."):
                st.session_state[state_key] = fetch_monthly_payment_combination(
                    api_base_url=api_base_url,
                    code=base_code,
                    payload=payload,
                )
        except APIClientError as error:
            render_api_error("無法完成月配組合分析。", error)
    if state_key in st.session_state:
        render_monthly_combination_result(st.session_state[state_key])


def format_optional_date(
    value: Any,
) -> str:
    """格式化可缺少日期。"""

    return format_iso_date(
        value,
        missing_text="尚無資料",
    )


def format_optional_number(
    value: Any,
    *,
    suffix: str = "",
    decimal_places: int = 2,
) -> str:
    """格式化可缺少數值。"""

    return format_number(
        value,
        decimal_places=decimal_places,
        suffix=suffix,
        missing_text="尚無資料",
        invalid_text="資料格式異常",
    )


def format_return(
    value: Any,
) -> str:
    """格式化市價報酬率。"""

    return format_shared_percentage(
        value,
        signed=True,
        missing_text="歷史資料不足",
        invalid_text="資料格式異常",
    )


def format_percentage(
    value: Any,
) -> str:
    """格式化正式百分比並區分缺資料與零。"""

    return format_shared_percentage(
        value,
        missing_text="尚未取得",
        invalid_text="資料格式異常",
    )


def build_identity_rows(
    comparison: dict[str, Any],
) -> list[dict[str, str]]:
    """建立基本資料並列表。"""

    rows: list[dict[str, str]] = []

    for item in comparison["items"]:
        etf = item["etf"]

        rows.append(
            {
                "代號": str(etf["code"]),
                "名稱": str(etf["name"]),
                "管理方式": (
                    management_type_label(
                        etf["is_active"]
                    )
                ),
                "資產類型": (
                    asset_type_label(
                        etf["is_bond"]
                    )
                ),
                "上市日期": (
                    format_optional_date(
                        etf["listing_date"]
                    )
                ),
                "基金規模": (
                    format_optional_number(
                        etf["fund_size"],
                        suffix=" 億元",
                        decimal_places=0,
                    )
                ),
                "費用率": (
                    format_optional_number(
                        etf["expense_ratio"],
                        suffix="%",
                    )
                ),
            }
        )

    return rows


def render_comparison_summary_cards(
    comparison: dict[str, Any],
    grade_lookup: dict[str, dict[str, Any]],
) -> None:
    """以一致卡片呈現各 ETF 身分與公開歷史評等。"""

    items = comparison["items"]
    columns = st.columns(len(items))
    for column, item in zip(columns, items, strict=True):
        etf = item["etf"]
        code = str(etf["code"]).strip().upper()
        with column:
            with st.container(
                border=True,
                key=f"etf-comparison-card-{code.lower()}",
            ):
                st.subheader(code)
                st.write(str(etf["name"]))
                render_historical_quality_evidence(
                    grade_lookup.get(code),
                    compact=True,
                )
                st.caption(
                    management_type_label(etf["is_active"])
                    + "　｜　上市 "
                    + format_optional_date(etf["listing_date"])
                )


def build_performance_rows(
    comparison: dict[str, Any],
) -> list[dict[str, str]]:
    """建立 1M、3M、6M、1Y 績效比較列。"""

    lookup_by_code: dict[
        str,
        dict[str, dict[str, Any]],
    ] = {}

    for item in comparison["items"]:
        code = item["etf"]["code"]

        lookup_by_code[code] = {
            performance_item[
                "period_code"
            ]: performance_item
            for performance_item in (
                item["performance_items"]
            )
        }

    rows: list[dict[str, str]] = []

    for period in comparison["periods"]:
        row: dict[str, str] = {
            "期間": period,
        }

        for item in comparison["items"]:
            code = item["etf"]["code"]
            performance_item = (
                lookup_by_code[code].get(
                    period
                )
            )

            if performance_item is None:
                row[code] = "歷史資料不足"

            else:
                row[code] = (
                    format_return(
                        performance_item[
                            "return_pct"
                        ]
                    )
                    + "\n截至 "
                    + performance_item[
                        "as_of_date"
                    ]
                )

        rows.append(row)

    return rows


def build_dividend_rows(
    comparison: dict[str, Any],
) -> list[dict[str, str]]:
    """建立配息與正式 76W 比較列。"""

    rows: list[dict[str, str]] = []

    for item in comparison["items"]:
        etf = item["etf"]
        dividend = item["dividend"]
        actual = item["actual_76w"]

        latest_amount = (
            "尚無資料"
            if dividend[
                "latest_amount_per_unit"
            ] is None
            else (
                format_amount(
                    dividend["latest_amount_per_unit"],
                    dividend["currency"],
                )
            )
        )

        rows.append(
            {
                "ETF": (
                    f"{etf['code']} {etf['name']}"
                ),
                "配息事件": (
                    f"{dividend['event_count']:,} 次"
                ),
                "最新事件日": (
                    format_optional_date(
                        dividend[
                            "latest_event_date"
                        ]
                    )
                ),
                "最新每單位配息": (
                    latest_amount
                ),
                "正式 76W 紀錄": (
                    f"{actual['record_count']:,} 次"
                ),
                "最新 76W 比例": (
                    format_percentage(
                        actual[
                            "latest_ratio_pct"
                        ]
                    )
                ),
                "平均 76W 比例": (
                    format_percentage(
                        actual[
                            "average_ratio_pct"
                        ]
                    )
                ),
            }
        )

    return rows


def build_completeness_rows(
    comparison: dict[str, Any],
) -> list[dict[str, str]]:
    """建立資料完整度比較列。"""

    rows: list[dict[str, str]] = []

    for item in comparison["items"]:
        etf = item["etf"]
        completeness = item[
            "completeness"
        ]

        missing_sections = (
            completeness[
                "missing_sections"
            ]
        )

        rows.append(
            {
                "ETF": (
                    f"{etf['code']} {etf['name']}"
                ),
                "完整度": (
                    format_percentage(
                        completeness[
                            "score_pct"
                        ]
                    )
                ),
                "可用區塊": (
                    f"{completeness['available_section_count']}"
                    f"/{completeness['total_section_count']}"
                ),
                "缺少區塊": (
                    "、".join(
                        missing_sections
                    )
                    if missing_sections
                    else "無"
                ),
            }
        )

    return rows


@st.cache_data(
    ttl=60,
    show_spinner=False,
)
def load_etf_comparison(
    api_base_url: str,
    codes: tuple[str, ...],
) -> dict[str, Any]:
    """取得並短暫快取 ETF 比較資料。"""

    return fetch_etf_comparison(
        api_base_url=api_base_url,
        codes=codes,
    )


def _return_state_params() -> dict[str, str]:
    """保留比較頁來源參數。"""

    current = query_params_to_dict(
        st.query_params
    )

    return {
        key: value
        for key, value in current.items()
        if (
            key == "from"
            or key.startswith("return_")
        )
    }


def update_comparison_codes(
    codes: tuple[str, ...],
) -> None:
    """更新網址中的比較清單並保留返回狀態。"""

    comparison_params = (
        ETFComparisonQueryState(
            codes=codes
        ).to_query_params()
    )

    sync_query_params(
        st.query_params,
        {
            **comparison_params,
            **_return_state_params(),
        },
    )


def parse_comparison_terms(
    value: str,
) -> list[str]:
    """解析以半形／全形逗號或換行分隔的比較關鍵字。"""

    return [
        term.strip()
        for term in re.split(r"[,，\n]+", value)
        if term.strip()
    ]


def resolve_comparison_terms(
    api_base_url: str,
    terms: list[str],
) -> tuple[tuple[str, ...], list[str], list[str]]:
    """將 ETF 代號、完整名稱或唯一關鍵字結果解析為代號。"""

    resolved_codes: list[str] = []
    unresolved_terms: list[str] = []
    ambiguous_terms: list[str] = []

    for term in terms:
        result = fetch_etfs(
            api_base_url=api_base_url,
            keyword=term,
            limit=100,
            offset=0,
        )
        items = result["items"]
        normalized_term = term.strip().casefold()
        exact_matches = [
            item
            for item in items
            if (
                str(item["code"]).strip().casefold()
                == normalized_term
                or str(item["name"]).strip().casefold()
                == normalized_term
            )
        ]

        if len(exact_matches) == 1:
            selected = exact_matches[0]
        elif len(exact_matches) > 1:
            ambiguous_terms.append(term)
            continue
        elif result["total"] == 1 and len(items) == 1:
            selected = items[0]
        elif not items:
            unresolved_terms.append(term)
            continue
        else:
            ambiguous_terms.append(term)
            continue

        code = str(selected["code"]).strip().upper()
        if code not in resolved_codes:
            resolved_codes.append(code)

    return (
        normalize_comparison_codes(resolved_codes),
        unresolved_terms,
        ambiguous_terms,
    )


def render_code_form(
    codes: tuple[str, ...],
) -> None:
    """顯示比較代號輸入與清單操作。"""

    with st.form(
        "etf_comparison_form",
        enter_to_submit=False,
    ):
        code_text = st.text_input(
            "ETF 代號或名稱",
            value=",".join(codes),
            placeholder="輸入ETF代號或名稱",
            help=(
                "使用逗號分隔；可輸入完整代號、"
                "完整名稱或能唯一辨識的名稱關鍵字。"
            ),
            label_visibility="collapsed",
        )

        submitted = (
            st.form_submit_button(
                "開始比較",
                type="primary",
            )
        )

        if len(codes) < 2:
            st.caption(
                "請輸入至少2檔才能比較，最多同時比較4檔"
            )

    if submitted:
        terms = parse_comparison_terms(code_text)

        if len(terms) > 4:
            st.warning(
                "ETF 比較最多支援 4 檔。"
            )
            return

        if not terms:
            st.warning(
                "請輸入至少一個 ETF 代號或名稱。"
            )
            return

        try:
            api_base_url = get_api_base_url()
            (
                normalized,
                unresolved_terms,
                ambiguous_terms,
            ) = resolve_comparison_terms(
                api_base_url,
                terms,
            )
        except (APIClientError, ValueError) as error:
            render_api_error(
                "無法查找 ETF 代號或名稱。",
                error,
            )
            return

        if unresolved_terms:
            st.warning(
                "找不到 ETF："
                + "、".join(unresolved_terms)
            )
            return

        if ambiguous_terms:
            st.warning(
                "請輸入更完整的 ETF 代號或名稱："
                + "、".join(ambiguous_terms)
            )
            return

        if len(normalized) < 2:
            st.warning(
                "請輸入至少2檔不同的 ETF 才能比較。"
            )
            return

        update_comparison_codes(
            normalized
        )
        load_etf_comparison.clear()
        st.rerun()

    if not codes:
        return

    columns = st.columns(
        len(codes) + 1
    )

    for column, code in zip(
        columns,
        codes,
        strict=False,
    ):
        with column:
            if st.button(
                f"移除 {code}",
                key=f"remove_compare_{code}",
                width="stretch",
            ):
                update_comparison_codes(
                    tuple(
                        current_code
                        for current_code in codes
                        if current_code != code
                    )
                )
                load_etf_comparison.clear()
                st.rerun()

    with columns[-1]:
        if st.button(
            "清空比較",
            key="clear_comparison",
            width="stretch",
        ):
            update_comparison_codes(())
            load_etf_comparison.clear()
            st.rerun()


def render_etf_comparison() -> None:
    """顯示 ETF 比較頁。"""

    render_page_title("比較")

    state = parse_etf_comparison_query_state(
        st.query_params
    )

    sync_query_params(
        st.query_params,
        {
            **state.to_query_params(),
            **_return_state_params(),
        },
    )

    render_code_form(
        state.codes
    )

    if len(state.codes) < 2:
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
            "正在整理 ETF 比較資料..."
        ):
            comparison = (
                load_etf_comparison(
                    api_base_url,
                    state.codes,
                )
            )

    except APIClientError as error:
        render_api_error(
            "無法取得 ETF 比較資料。",
            error,
            hint=(
                "請確認代號存在且 FastAPI "
                "已正常啟動。"
            ),
        )
        return

    grade_lookup: dict[str, dict[str, Any]] = {}
    grade_error = False
    try:
        grade_lookup = load_historical_quality_grade_lookup(
            api_base_url,
            tuple(
                str(item["etf"]["code"])
                for item in comparison["items"]
            ),
        )
    except (APIClientError, ValueError):
        grade_error = True

    refresh_column, _ = st.columns(
        [1, 4]
    )

    with refresh_column:
        if st.button(
            "重新載入比較",
            key="refresh_etf_comparison",
        ):
            load_etf_comparison.clear()
            load_historical_quality_grade_lookup.clear()
            st.rerun()

    render_comparison_summary_cards(
        comparison,
        grade_lookup,
    )

    if grade_error:
        st.caption(
            "喵喵評等暫時無法取得；"
            "其他比較資料仍可正常查看。"
        )

    st.subheader("基本資料")
    st.table(
        build_identity_rows(
            comparison
        )
    )

    st.divider()
    st.subheader("市價績效")
    st.caption(
        "每個期間獨立比較；"
        "缺少歷史資料不轉換為 0%。"
    )
    st.table(
        build_performance_rows(
            comparison
        )
    )

    st.divider()
    st.subheader("配息與正式 76W")
    st.caption(
        "只有 ACTUAL + 76W 才列為正式 76W；"
        "預估已實現資本利得不列入。"
    )
    st.table(
        build_dividend_rows(
            comparison
        )
    )

    render_monthly_combination_analysis(
        api_base_url=api_base_url,
        comparison=comparison,
    )
