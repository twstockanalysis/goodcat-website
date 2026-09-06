"""M11-1 單一使用者條件與手動持有部位頁面。"""

from decimal import Decimal, InvalidOperation
from typing import Any

import pandas as pd
import streamlit as st

from frontend.ui.components import render_page_title

from frontend.api_client import (
    APIClientError,
    fetch_candidate_holding_analysis,
    fetch_current_holding_analysis,
    fetch_decision_profile,
    fetch_decision_record_export,
    fetch_decision_records,
    save_candidate_decision_record,
    save_manual_holdings,
    save_user_conditions,
)
from frontend.config import get_api_base_url
from frontend.owner_access import get_owner_token
from frontend.ui.formatters import (
    asset_type_label,
    format_iso_date,
    format_number,
    management_type_label,
)
from frontend.ui.states import loading_state, render_api_error


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def build_holding_rows(profile: dict[str, Any]) -> list[dict[str, str]]:
    """建立小型持有部位靜態表格，保留價格缺值語意。"""

    rows = []
    for item in profile["holdings"]:
        units = int(item["held_units"])
        unit_price = _decimal(item.get("unit_price"))
        reference_value = (
            unit_price * units if unit_price is not None else None
        )
        rows.append(
            {
                "ETF": f"{item['etf_code']} {item['name']}",
                "管理方式": management_type_label(item["is_active"]),
                "資產類型": asset_type_label(item["is_bond"]),
                "持有單位": f"{units:,}",
                "參考單價": (
                    f"{format_number(unit_price, decimal_places=0)} NTD"
                    if unit_price is not None
                    else "尚未取得"
                ),
                "參考部位價值": (
                    f"{format_number(reference_value, decimal_places=0)} NTD"
                    if reference_value is not None
                    else "無法計算"
                ),
                "價格日期": format_iso_date(
                    item.get("price_as_of_date"),
                    missing_text="未提供",
                ),
                "價格來源": item.get("price_source_id") or "尚未取得",
            }
        )
    return rows


def build_analysis_holding_rows(
    analysis: dict[str, Any],
) -> list[dict[str, str]]:
    """建立目前持倉分析的可閱讀歷史事實表格。"""

    rows = []
    for item in analysis["holdings"]:
        annual_cash = _decimal(item.get("annual_gross_distribution_cash"))
        annual_return = _decimal(item.get("annualized_price_return_pct"))
        current_value = _decimal(item.get("current_value"))
        rows.append(
            {
                "ETF": f"{item['etf_code']} {item['name']}",
                "目前部位價值": (
                    f"{format_number(current_value, decimal_places=0)} NTD"
                    if current_value is not None
                    else "無法計算"
                ),
                "年均稅前配息現金": (
                    f"{format_number(annual_cash, decimal_places=0)} NTD"
                    if annual_cash is not None
                    else "無法計算"
                ),
                "價格報酬期間": item.get("price_return_period_code") or "無資料",
                "年化價格報酬": (
                    f"{format_number(annual_return, decimal_places=2)}%"
                    if annual_return is not None
                    else "無法計算"
                ),
            }
        )
    return rows


def load_decision_profile(api_base_url: str, owner_token: str) -> dict[str, Any]:
    return fetch_decision_profile(api_base_url, owner_token)


def load_current_holding_analysis(api_base_url: str, owner_token: str) -> dict[str, Any]:
    return fetch_current_holding_analysis(api_base_url, owner_token)


def load_decision_records(api_base_url: str, owner_token: str) -> list[dict[str, Any]]:
    return fetch_decision_records(api_base_url, owner_token)


def _clear_candidate_analysis_state() -> None:
    for key in (
        "candidate_holding_analysis_result",
        "candidate_holding_analysis_request",
        "candidate_holding_analysis_code",
    ):
        st.session_state.pop(key, None)


def build_decision_record_rows(
    records: list[dict[str, Any]],
) -> list[dict[str, str]]:
    outcome_labels = {
        "ELIGIBLE": "通過目前門檻",
        "INELIGIBLE": "未通過目前門檻",
        "NOT_EVALUATED": "未進行候選判定",
        "UNAVAILABLE": "資料不足",
    }
    return [
        {
            "紀錄": f"#{item['id']}",
            "建立時間": format_iso_date(item["created_at"]),
            "候選 ETF": (
                f"{item['candidate_etf_code']} {item['candidate_name']}"
            ),
            "分析狀態": item["analysis_status"],
            "資格結果": outcome_labels[item["outcome"]],
        }
        for item in records
    ]


def _metric_value(value: Any, *, suffix: str = "") -> str:
    parsed = _decimal(value)
    if parsed is None:
        return "無法計算"
    precision = 0 if suffix == " NTD" else 2
    return f"{format_number(parsed, decimal_places=precision)}{suffix}"


def build_short_history_projection_warning(
    analysis: dict[str, Any] | None,
) -> str | None:
    """提醒使用者短期歷史報酬被機械式外推到多年情境。"""

    if not analysis:
        return None
    portfolio = analysis.get("portfolio_analysis") or {}
    scenario = portfolio.get("scenario_estimate") or {}
    projection_years = scenario.get("projection_years")
    if projection_years is None or int(projection_years) <= 1:
        return None
    short_history_codes = sorted(
        {
            str(item["etf_code"])
            for item in analysis.get("holdings", [])
            if item.get("price_return_period_code") == "1Y"
        }
    )
    if not short_history_codes:
        return None
    return (
        "情境外推提醒："
        + "、".join(short_history_codes)
        + f" 目前使用最近 1 年價格報酬，並以相同報酬率機械式複利 "
        f"{int(projection_years)} 年；數值可能被大幅放大，並非績效預測。"
    )


def render_current_holding_analysis_result(
    analysis: dict[str, Any],
) -> None:
    """以原生 Streamlit 元件呈現整體持倉情境結果。"""

    if analysis["status"] == "UNAVAILABLE":
        reasons = "、".join(
            item["reason"] for item in analysis["unavailable_fields"]
        )
        st.info(f"目前無法分析：{reasons}")
        return

    portfolio = analysis["portfolio_analysis"]
    cash_flow = portfolio["cash_flow"]
    scenario = portfolio["scenario_estimate"]
    with st.container(horizontal=True):
        st.metric(
            "目前部位總值",
            _metric_value(analysis.get("total_current_value"), suffix=" NTD"),
            border=True,
        )
        st.metric(
            "年均稅前配息現金",
            _metric_value(cash_flow.get("gross_distribution_cash"), suffix=" NTD"),
            border=True,
        )
        st.metric(
            "年均稅後可用現金",
            _metric_value(cash_flow.get("after_tax_usable_cash"), suffix=" NTD"),
            border=True,
        )
        st.metric(
            "年度目標覆蓋率",
            _metric_value(cash_flow.get("target_coverage_pct"), suffix="%"),
            border=True,
        )

    st.table(build_analysis_holding_rows(analysis))
    st.caption(
        f"分析日期 {analysis['analysis_date']}；情境期間 "
        f"{scenario.get('projection_years') or '無法計算'} 年。"
        "價格報酬會先年化後依目前部位價值加權；配息不再投入。"
    )
    projection_warning = build_short_history_projection_warning(analysis)
    if projection_warning is not None:
        st.warning(projection_warning)
    data_warnings = [
        f"{item['etf_code']}：{warning['message']}"
        for item in analysis["holdings"]
        for warning in item.get("warnings", [])
    ]
    if data_warnings:
        st.warning("資料提醒：" + "、".join(data_warnings))
    if analysis["status"] == "PARTIAL":
        reasons = "、".join(
            f"{item['field']}：{item['reason']}"
            for item in analysis["unavailable_fields"]
        )
        st.warning(f"部分結果無法計算：{reasons}")


def build_candidate_comparison_rows(
    comparison: dict[str, Any],
) -> list[dict[str, str]]:
    """建立候選加入前後的小型靜態比較表。"""

    fields = [
        ("目前部位總值", "total_value_before", "total_value_after", " NTD"),
        (
            "年均稅後可用現金",
            "annual_after_tax_cash_before",
            "annual_after_tax_cash_after",
            " NTD",
        ),
        (
            "年度目標覆蓋率",
            "target_coverage_pct_before",
            "target_coverage_pct_after",
            "%",
        ),
        (
            "資金缺口",
            "funding_shortfall_before",
            "funding_shortfall_after",
            " NTD",
        ),
        (
            "情境稅後總報酬率",
            "after_tax_total_return_pct_before",
            "after_tax_total_return_pct_after",
            "%",
        ),
    ]
    return [
        {
            "比較項目": label,
            "目前持倉": _metric_value(comparison.get(before), suffix=suffix),
            "加入候選後": _metric_value(comparison.get(after), suffix=suffix),
        }
        for label, before, after, suffix in fields
    ]


def render_explainable_assessment(assessment: dict[str, Any]) -> None:
    """呈現雙分數與原始證據，不顯示可信度或買賣訊號。"""

    outcome = assessment["outcome"]
    headline = assessment["headline"]
    if outcome == "GATE_ALIGNED":
        st.success(f"可解釋評定：{headline}")
    elif outcome == "BLOCKED_BY_GATE":
        st.error(f"可解釋評定：{headline}")
    elif outcome == "INSUFFICIENT_DATA":
        st.warning(f"可解釋評定：{headline}")
    else:
        st.info(f"可解釋評定：{headline}")

    st.metric(
        "與目前持股適配分數",
        _metric_value(assessment.get("portfolio_fit_score"), suffix=" / 100"),
        border=True,
    )
    st.caption(
        "後端以 ETF 品質作為主要計算基礎；頁面只顯示最終適配分數。"
        "高股息、高 76W 或低重複性都不能單獨形成高分。"
    )

    component_rows = [
        {
            "適配項目": item["label"],
            "項目分數": f"{Decimal(str(item['score'])):.2f}",
            "原始權重": f"{Decimal(str(item['weight_pct'])):.2f}%",
            "說明": item["explanation"],
        }
        for item in assessment.get("fit_components", [])
        if item.get("code") != "ETF_QUALITY"
    ]
    if component_rows:
        st.table(component_rows)

    status_labels = {
        "PASS": "通過",
        "FAIL": "未通過",
        "REVIEW": "需確認",
        "UNAVAILABLE": "資料不足",
        "NOT_EVALUATED": "未評估",
    }
    st.table(
        [
            {
                "評定面向": factor["title"],
                "狀態": status_labels[factor["status"]],
                "判定原則": factor["summary"],
            }
            for factor in assessment["factors"]
        ]
    )
    with st.expander("查看評定證據與限制"):
        for factor in assessment["factors"]:
            st.markdown(f"**{factor['title']}**")
            for item in factor.get("evidence", []):
                st.write(f"- {item}")
        if "AUTOMATED_CONSTITUENT_OVERLAP" in assessment.get(
            "unscored_metrics", []
        ):
            st.info(
                "成分股重複尚未計分：目前持倉或候選 ETF 的正式成分股快照"
                "缺少、過期，或揭露權重未達門檻；系統不會把未知值當成 0%。"
            )
        st.caption(assessment["disclaimer"])


def render_candidate_holding_analysis_result(
    analysis: dict[str, Any],
) -> None:
    """呈現候選 ETF 前後差異與 M10-5 納入／排除理由。"""

    if analysis["status"] == "UNAVAILABLE":
        reasons = "、".join(
            item["reason"] for item in analysis["unavailable_fields"]
        )
        st.info(f"目前無法比較候選 ETF：{reasons}")
        return

    comparison = analysis["comparison"]
    with st.container(horizontal=True):
        st.metric(
            "候選投入金額",
            _metric_value(comparison.get("additional_capital"), suffix=" NTD"),
            border=True,
        )
        st.metric(
            "目標覆蓋率變化",
            _metric_value(
                comparison.get("target_coverage_pct_delta"), suffix="%"
            ),
            border=True,
        )
        st.metric(
            "稅後現金變化",
            _metric_value(
                comparison.get("annual_after_tax_cash_delta"), suffix=" NTD"
            ),
            border=True,
        )
        st.metric(
            "資金缺口減少",
            _metric_value(
                comparison.get("funding_shortfall_reduction"), suffix=" NTD"
            ),
            border=True,
        )
    st.table(build_candidate_comparison_rows(comparison))

    projection_warning = build_short_history_projection_warning(
        analysis.get("proposed_portfolio")
        or analysis.get("current_portfolio")
    )
    if projection_warning is not None:
        st.warning(projection_warning)

    assessment = analysis.get("explainable_assessment")
    if assessment is not None:
        render_explainable_assessment(assessment)

    eligibility = analysis["eligibility"]
    selected = eligibility["selected_candidates"]
    rejected = eligibility["rejected_candidates"]
    candidate = selected[0] if selected else rejected[0]
    reason_text = "；".join(
        item["message"] for item in candidate.get("reasons", [])
    )
    reason_codes = {
        item["code"] for item in candidate.get("reasons", [])
    }
    if "MONTHLY_COVERAGE_DISABLED" in reason_codes:
        st.info(f"本次未進行月配候選判定：{reason_text}")
    elif selected:
        st.success(f"候選通過目前門檻：{reason_text}")
    else:
        st.warning(f"候選未通過目前門檻：{reason_text}")
    st.caption(
        "判定順序固定為：總報酬與本金風險 → 稅後現金流可行性 → "
        "稅務效率 → 選配月月領息。持股重疊缺值不等於零。"
    )
    st.caption(analysis["estimate_label"] + "；分析不會寫入手動持倉。")


def render_decision_profile() -> None:
    """顯示單一使用者條件與無券商連線的手動持有部位。"""

    render_page_title("我的條件與持有部位")
    st.caption(
        "M11-1 為單一使用者、手動輸入模式；"
        "不連接券商、不讀取帳戶，也不會送出交易。"
    )
    owner_token = get_owner_token()
    if owner_token is None:
        st.error("此頁僅限 owner；請回到側邊欄重新解鎖。")
        st.stop()
    st.info("此頁的讀取、寫入、分析、紀錄與匯出均由後端 owner gate 保護。")
    try:
        api_base_url = get_api_base_url()
        with loading_state("正在讀取已儲存的條件與持有部位..."):
            profile = load_decision_profile(api_base_url, owner_token)
    except (APIClientError, ValueError) as error:
        render_api_error("無法取得決策條件。", error)
        return

    conditions = profile.get("conditions") or {}
    st.subheader("固定分析條件")
    st.caption("這些條件會在後續切片重用 M10 計算；儲存本身不會產生推薦。")
    with st.form("decision_profile_conditions", enter_to_submit=False):
        condition_columns = st.columns(3)
        with condition_columns[0]:
            monthly_target = st.number_input(
                "每月稅後現金目標（NTD）",
                format="%.0f",
                min_value=0.0,
                value=float(conditions.get("monthly_after_tax_target", 3000)),
                step=500.0,
            )
        with condition_columns[1]:
            analysis_years = st.number_input(
                "分析年數",
                min_value=1,
                max_value=50,
                value=int(conditions.get("analysis_years", 10)),
            )
            history_years = st.number_input(
                "歷史資料年數",
                min_value=1,
                max_value=10,
                value=int(conditions.get("history_years", 3)),
            )
        with condition_columns[2]:
            saved_deduction = conditions.get("cash_deduction_rate_pct")
            has_deduction = st.checkbox(
                "提供現金扣除率假設",
                value=saved_deduction is not None,
            )
            deduction_rate = st.number_input(
                "現金扣除率（%）",
                min_value=0.0,
                max_value=100.0,
                value=float(saved_deduction or 0),
            )
        condition_submitted = st.form_submit_button(
            "儲存固定條件",
            type="primary",
            icon=":material/save:",
        )

    if condition_submitted:
        try:
            save_user_conditions(
                api_base_url,
                {
                    "monthly_after_tax_target": monthly_target,
                    "analysis_years": int(analysis_years),
                    "history_years": int(history_years),
                    "cash_deduction_rate_pct": (
                        deduction_rate if has_deduction else None
                    ),
                    "currency": "TWD",
                },
                owner_token,
            )
        except APIClientError as error:
            render_api_error("無法儲存固定分析條件。", error)
        else:
            _clear_candidate_analysis_state()
            st.rerun()

    st.divider()
    st.subheader("手動持有部位")
    st.caption(
        "初始可為 0 檔；使用表格下方的新增／刪除列控制管理任意檔數。"
        "只需輸入 ETF 代號與股數，參考價格、日期及來源由系統使用最新"
        "已保存的官方收盤價提供，不是即時報價。"
    )
    editor_rows = pd.DataFrame(
        {
            "股票代號": pd.Series(
                [item["etf_code"] for item in profile["holdings"]],
                dtype="string",
            ),
            "股數": pd.Series(
                [item["held_units"] for item in profile["holdings"]],
                dtype="Int64",
            ),
        }
    )
    with st.form("manual_holding_batch", enter_to_submit=False):
        edited_holdings = st.data_editor(
            editor_rows,
            num_rows="dynamic",
            hide_index=True,
            key="manual_holding_editor",
            column_config={
                "股票代號": st.column_config.TextColumn(
                    "股票代號",
                    help="限本網站收錄的台灣 ETF 代號",
                    max_chars=10,
                ),
                "股數": st.column_config.NumberColumn(
                    "股數",
                    min_value=1,
                    step=1,
                    format="%d",
                ),
            },
        )
        holding_submitted = st.form_submit_button(
            "儲存全部持股",
            type="primary",
            icon=":material/save:",
        )

    if holding_submitted:
        holding_payload = []
        row_errors = []
        for row_number, row in enumerate(
            edited_holdings.to_dict(orient="records"),
            start=1,
        ):
            code = str(row.get("股票代號") or "").strip().upper()
            units = row.get("股數")
            if not code:
                row_errors.append(f"第 {row_number} 列缺少 ETF 代號。")
                continue
            if pd.isna(units) or int(units) <= 0 or float(units) != int(units):
                row_errors.append(f"第 {row_number} 列股數必須是正整數。")
                continue
            holding_payload.append({"etf_code": code, "held_units": int(units)})
        codes = [item["etf_code"] for item in holding_payload]
        duplicates = sorted({code for code in codes if codes.count(code) > 1})
        if duplicates:
            row_errors.append("ETF 代號不可重複：" + "、".join(duplicates))

        if row_errors:
            for message in row_errors:
                st.warning(message)
        else:
            try:
                save_manual_holdings(
                    api_base_url,
                    holding_payload,
                    owner_token,
                )
            except APIClientError as error:
                render_api_error("無法儲存全部持有部位。", error)
            else:
                _clear_candidate_analysis_state()
                st.rerun()

    if not profile["holdings"]:
        st.info("目前尚未建立手動持有部位。")
    else:
        st.table(build_holding_rows(profile))
        if any(item.get("unit_price") is None for item in profile["holdings"]):
            st.warning(
                "部分 ETF 尚無可信的已保存官方收盤價；部位價值與依賴估值的"
                "現金流結果會標示為無法計算，不會以 0 代替。"
            )

    st.divider()
    st.subheader("目前持倉分析")
    st.caption(
        "使用上方已儲存條件與所有手動持倉，重用 M10 公式進行整體情境估算；"
        "結果不是個別 ETF 推薦，也不保證未來收益。"
    )
    if st.button(
        "分析目前持倉",
        type="primary",
        icon=":material/analytics:",
    ):
        st.session_state["show_current_holding_analysis"] = True
    if st.session_state.get("show_current_holding_analysis", False):
        try:
            with loading_state("正在彙總目前持倉分析..."):
                analysis = load_current_holding_analysis(api_base_url, owner_token)
        except APIClientError as error:
            render_api_error("無法取得目前持倉分析。", error)
        else:
            render_current_holding_analysis_result(analysis)

    st.divider()
    st.subheader("候選 ETF 加碼比較")
    st.caption(
        "輸入一個候選加碼情境，比較加入前後的整體持倉；"
        "此分析不會新增或更新手動持倉。"
    )
    with st.form("candidate_holding_analysis", enter_to_submit=False):
        candidate_columns = st.columns(3)
        with candidate_columns[0]:
            candidate_code = st.text_input(
                "候選 ETF 代號",
                placeholder="例如 00878",
                max_chars=10,
            )
            proposed_units = st.number_input(
                "預計增加單位數",
                min_value=1,
                value=1000,
                step=1,
            )
        with candidate_columns[1]:
            candidate_price = st.number_input(
                "候選參考單價（NTD）",
                format="%.0f",
                min_value=0.01,
                value=20.0,
                step=0.1,
            )
            analysis_goal = st.segmented_control(
                "候選分析目標",
                options=["補足月配缺口", "不進行月配候選判定"],
                default="補足月配缺口",
            )
        with candidate_columns[2]:
            st.info(
                "持股重疊率會使用通過新鮮度與揭露權重門檻的正式成分股快照"
                "自動計算。資料不足時維持未知。"
            )
        candidate_submitted = st.form_submit_button(
            "比較候選加入前後",
            type="primary",
            icon=":material/compare_arrows:",
        )

    if candidate_submitted:
        normalized_candidate = candidate_code.strip().upper()
        if not normalized_candidate:
            st.warning("請輸入候選 ETF 代號。")
        else:
            _clear_candidate_analysis_state()
            try:
                with loading_state("正在比較候選 ETF 加入前後..."):
                    candidate_request = {
                        "proposed_units": int(proposed_units),
                        "unit_price": candidate_price,
                        "monthly_coverage_enabled": (
                            analysis_goal == "補足月配缺口"
                        ),
                    }
                    st.session_state[
                        "candidate_holding_analysis_result"
                    ] = fetch_candidate_holding_analysis(
                        api_base_url,
                        normalized_candidate,
                        candidate_request,
                        owner_token,
                    )
                    st.session_state[
                        "candidate_holding_analysis_request"
                    ] = candidate_request
                    st.session_state[
                        "candidate_holding_analysis_code"
                    ] = normalized_candidate
            except APIClientError as error:
                render_api_error("無法完成候選持倉分析。", error)
    if "candidate_holding_analysis_result" in st.session_state:
        render_candidate_holding_analysis_result(
            st.session_state["candidate_holding_analysis_result"]
        )
        st.caption(
            "保存時後端會重新執行同一份輸入，再建立不可變快照；"
            "後續條件或資料更新不會改寫舊紀錄。"
        )
        if st.button(
            "保存為決策紀錄",
            icon=":material/save:",
            key="save_candidate_decision_record",
        ):
            try:
                with loading_state("正在重新分析並保存不可變快照..."):
                    saved_record = save_candidate_decision_record(
                        api_base_url,
                        st.session_state["candidate_holding_analysis_code"],
                        st.session_state["candidate_holding_analysis_request"],
                        owner_token,
                    )
            except APIClientError as error:
                render_api_error("無法保存決策紀錄。", error)
            else:
                st.success(f"已保存決策紀錄 #{saved_record['id']}。")

    st.divider()
    st.subheader("決策紀錄與 Excel 匯出")
    st.caption(
        "每筆紀錄都是保存當下的不可變快照；不提供覆寫或刪除，"
        "重新分析會建立新紀錄。"
    )
    try:
        records = load_decision_records(api_base_url, owner_token)
    except APIClientError as error:
        render_api_error("無法取得決策紀錄。", error)
        return
    if not records:
        st.info("尚未保存候選分析決策紀錄。")
        return
    st.table(build_decision_record_rows(records))
    selected_record_id = st.selectbox(
        "選擇要匯出的紀錄",
        options=[item["id"] for item in records],
        format_func=lambda record_id: next(
            (
                f"#{item['id']} · {item['candidate_etf_code']} "
                f"{item['candidate_name']}"
                for item in records
                if item["id"] == record_id
            ),
            f"#{record_id}",
        ),
        key="decision_record_export_selection",
    )
    prepared_key = f"decision_record_export_{selected_record_id}"
    if st.button(
        "準備 Excel",
        icon=":material/table_view:",
        key=f"prepare_{prepared_key}",
    ):
        try:
            with loading_state("正在建立 Excel..."):
                st.session_state[prepared_key] = fetch_decision_record_export(
                    api_base_url,
                    selected_record_id,
                    owner_token,
                )
        except APIClientError as error:
            render_api_error("無法準備決策紀錄 Excel。", error)
    if prepared_key in st.session_state:
        selected_record = next(
            item for item in records if item["id"] == selected_record_id
        )
        st.download_button(
            "下載 Excel",
            data=st.session_state[prepared_key],
            file_name=(
                f"decision-record-{selected_record_id}-"
                f"{selected_record['candidate_etf_code']}.xlsx"
            ),
            mime=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
            on_click="ignore",
            icon=":material/download:",
            key=f"download_{prepared_key}",
        )
