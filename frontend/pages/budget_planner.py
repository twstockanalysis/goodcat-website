"""Separate target-free budget form and descriptive result view."""

from decimal import Decimal, InvalidOperation
import json

import streamlit as st

from frontend.api_client import APIClientError, fetch_budget_results
from frontend.config import get_api_base_url
from frontend.ui.formatters import format_number
from frontend.ui.planning_metrics import render_budget_metrics


RESULT = "budget_planner_result"
SIGNATURE = "budget_planner_signature"
LABELS = {
    "MINIMUM_THEN_TOTAL_MONTH_CASH": "最低月份現金流優先",
    "MONTHLY_BALANCED": "月份現金流均衡",
    "TOTAL_MONTH_CASH": "所選月份總現金流優先",
}
STATUSES = {"AVAILABLE": "已有配置情境", "NO_ADDITIONS": "沒有新增配置",
            "NO_ELIGIBLE_ALLOCATION": "沒有通過門檻的新增配置", "UNAVAILABLE": "資料不足"}


def build_budget_request(raw_budget, months, holdings):
    """Use decimal text, not binary floating point or a default investment."""
    try:
        budget = Decimal(raw_budget.strip())
        if (not budget.is_finite() or budget < 0 or budget >= Decimal('1e16')
                or budget != budget.quantize(Decimal('.01'))):
            raise ValueError
    except (InvalidOperation, ValueError, AttributeError):
        raise ValueError("請輸入有效的非負預算，最多兩位小數。") from None
    if not months or any(type(m) is not int or not 1 <= m <= 12 for m in months):
        raise ValueError("請至少選擇一個月份。")
    return {"investable_budget_twd": format(budget, '.2f'),
            "selected_months": sorted(set(months)), "existing_holdings": holdings,
            "history_years": 3, "cash_deduction_rate_pct": 0, "currency": "TWD"}


def _messages(items):
    for item in items:
        message = item.get("message") if isinstance(item, dict) else item
        if isinstance(message, str) and message:
            st.write(message)


def render_budget_results(payload):
    st.subheader("預算配置情境")
    st.caption("依後端原順序呈現，不加總分或評等；方案可能只有一種。金額為估算，不是下單指示。")
    plans = [payload["primary"], *payload["alternatives"]]
    for plan in plans:
        with st.container(border=True):
            st.markdown(f"### {LABELS[plan['objective']]}")
            st.write(STATUSES[plan["status"]])
            st.caption(plan.get("tradeoff", "先比較最低月份現金流，再比較所選月份合計。"))
            if plan["objective"] == "TOTAL_MONTH_CASH":
                st.caption("總額較高仍可能伴隨個別月份下降，不代表風險較低或較適合你。")
            cols = st.columns(3)
            for col, label, field in zip(cols, ("投入預算", "新增資金", "剩餘預算"),
                                        ("investable_budget_twd", "used_budget_twd", "remaining_budget_twd")):
                col.metric(label, format_number(plan[field], suffix=" NTD"))
            st.caption("月份：" + "、".join(map(str, plan["selected_months"])))
            st.dataframe([{"月份": r["month"], "原持股現金流": format_number(r["current_after_tax_cash"]),
                           "新增現金流": format_number(r["added_after_tax_cash"]),
                           "合計現金流（NTD）": format_number(r["modeled_after_tax_cash"])}
                          for r in plan["monthly_results"]], hide_index=True, width="stretch")
            with st.expander("查看股數、持股與限制"):
                if plan["additions"]:
                    st.dataframe([{"ETF": a["etf_code"], "名稱": a["name"],
                                   "新增股數": a["additional_shares"],
                                   "新增資金（NTD）": format_number(a["required_capital"])}
                                  for a in plan["additions"]], hide_index=True, width="stretch")
                    for addition in plan["additions"]:
                        st.write(addition["etf_code"])
                        _messages(addition.get("reasons", []))
                        _messages(addition.get("risks", []))
                else:
                    st.info("此情境沒有新增股數；不代表已滿足某個現金流目標。")
                st.markdown("**原有持股**")
                if plan["existing_holdings"]:
                    st.dataframe([{"ETF": h["etf_code"], "持有股數": h["held_units"]}
                                  for h in plan["existing_holdings"]], hide_index=True)
                else:
                    st.caption("未輸入原有持股。")
                st.markdown("**配置後持股**")
                holdings = plan.get("resulting_holdings")
                if holdings is None:
                    st.caption("配置後持股資料不足，不能推論原持股已售出。")
                elif holdings:
                    st.dataframe([{"ETF": h["etf_code"], "原有股數": h["existing_shares"],
                                   "新增股數": h["additional_shares"], "合計股數": h["resulting_shares"],
                                   "金額占比（%）": format_number(h["allocation_pct"])}
                                  for h in holdings], hide_index=True, width="stretch")
                    st.caption("占比包含原持股與新增部位，不代表底層資產分散程度或風險評等。")
                else:
                    st.caption("目前沒有配置後部位。")
                _messages(plan.get("issues", []))
                st.caption(plan.get("assumptions", {}).get("transaction_cost_note", "交易成本假設未提供。"))
                if plan.get("search_truncated"):
                    st.warning("搜尋受到上限限制，不保證全域最佳配置。")
                st.caption(plan.get("estimate_label", "歷史情境，不保證未來配息。"))
    _messages(payload.get("issues", []))
    render_budget_metrics(payload, LABELS)
    with st.expander("查看候選排除原因與資料基礎"):
        basis = {"ACTUAL": "正式組成", "ESTIMATED_FALLBACK": "估算組成"}
        st.caption("估算組成不是正式 76W；未列出的持股或組成仍屬未知，不補零。")
        evidence = payload["primary"].get("candidate_evidence", [])
        if evidence:
            st.dataframe([{"ETF": item["etf_code"],
                           "可新增": "是" if item["eligible_for_addition"] else "否",
                           "組成基礎": basis.get(item.get("component_basis"), "資料不足"),
                           "原因與取捨": "；".join(r["message"] for r in item.get("reasons", []))}
                          for item in evidence], hide_index=True, width="stretch")
        else:
            st.caption("未提供候選證據。")
    if any(s.get("omission_reason") for s in payload.get("alternate_searches", [])):
        st.caption("部分替代方案因配置重複或沒有新增股數而省略，不補造方案。")


def render_budget_planner():
    # Local import reuses the established holdings parser without changing its contract.
    from frontend.pages.public_planner import build_holding_payload, empty_holding_editor_rows

    st.caption("預算是本次新增資金，原有持股不扣除此預算。保留原持股，最多新增五個 ETF 代號。")
    st.caption("採近三年同曆月歷史現金流，固定現金扣減率 0%；不是個人稅後所得，也不包含長期預測或再投入試算。")
    raw = st.text_input("新增投入預算（NTD）", key="budget_amount", placeholder="請自行輸入，可為 0")
    months = st.multiselect("比較月份", list(range(1, 13)), default=list(range(1, 13)), key="budget_months")
    st.markdown("#### 原有持股（可留白）")
    rows = st.data_editor(empty_holding_editor_rows()[["ETF 代號", "持有股數"]],
                          num_rows="dynamic", hide_index=True, key="budget_holdings", width="stretch",
                          column_config={"ETF 代號": st.column_config.TextColumn("ETF 代號"),
                                         "持有股數": st.column_config.NumberColumn("持有股數", min_value=1, step=1)})
    holdings, errors = build_holding_payload(rows)
    request = None
    try:
        request = build_budget_request(raw, months, holdings)
    except ValueError as error:
        errors.append(str(error))
    signature = json.dumps(request, sort_keys=True) if not errors else None
    if signature is None or st.session_state.get(SIGNATURE) != signature:
        st.session_state.pop(RESULT, None)
        st.session_state.pop(SIGNATURE, None)
    if st.button("計算預算配置", key="budget_submit", type="primary"):
        st.session_state.pop(RESULT, None)
        st.session_state.pop(SIGNATURE, None)
        if errors:
            for message in errors:
                st.warning(message)
        else:
            try:
                with st.spinner("正在計算預算配置…"):
                    response = fetch_budget_results(get_api_base_url(), request)
            except APIClientError:
                st.error("暫時無法完成預算試算，請稍後重試；輸入仍保留。")
            else:
                st.session_state[RESULT] = response
                st.session_state[SIGNATURE] = signature
    if RESULT in st.session_state:
        render_budget_results(st.session_state[RESULT])
    st.caption("不需登入，輸入僅用於本次試算；非投資建議或買賣指示，過往結果不保證未來表現。")
