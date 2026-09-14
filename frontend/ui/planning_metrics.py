"""Display existing cash-target facts without scoring or recalculating plans."""

from decimal import Decimal, InvalidOperation

import streamlit as st


FIELDS = (
    ("minimum_month_cash_twd", "最低月現金流（NTD）"),
    ("maximum_month_cash_twd", "最高月現金流（NTD）"),
    ("total_selected_month_cash_twd", "所選月份現金流合計（NTD）"),
    ("month_cash_spread_twd", "月份差距：最高減最低（NTD）"),
    ("additional_capital_twd", "新增資金（NTD）"),
    ("capital_limit_twd", "新增資金上限（NTD）"),
    ("remaining_capital_twd", "剩餘新增資金（NTD）"),
    ("capital_usage_pct", "新增資金使用率（%）"),
    ("max_resulting_position_pct", "配置後最大單檔金額占比（%）"),
)
NOTE = (
    "同一次需求的方案採用相同欄位與單位，不加權、不評分、不重新排序。"
    "現金流為估算，金額彙總依後端已顯示精度；未提供不等於零。"
    "月份差距不是波動風險，最大單檔占比包含原有持股與新增部位，"
    "不代表底層資產分散程度、ETF 品質或個人適合度；使用率也不是越高越好。"
)
MISSING = "未提供"


def _number(value, *, percentage=False):
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        return MISSING
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        return MISSING
    if not number.is_finite() or number < 0 or (percentage and number > 100):
        return MISSING
    return f"{number:,.2f}"


def build_planning_metric_rows(payload):
    """Fail closed per plan; absent optional metadata never breaks old results."""
    entries = payload.get("plan_metrics")
    entries = entries if isinstance(entries, list) else []
    rows = [{"指標": "目標月份"}, {"指標": "目標狀態"}]
    rows.extend({"指標": label} for _, label in FIELDS)
    rows.append({"指標": "資料說明"})
    for index, plan in enumerate(payload["plans"], 1):
        column = f"{index}. {plan['label']}"
        result = plan["result"]
        matches = [entry for entry in entries if isinstance(entry, dict)
                   and entry.get("plan_key") == plan["strategy"]]
        metric = matches[0].get("metrics") if len(matches) == 1 else None
        months = result.get("target_months")
        valid_months = (isinstance(months, list) and 1 <= len(months) <= 12
                        and all(type(m) is int and 1 <= m <= 12 for m in months)
                        and len(set(months)) == len(months))
        expected_status = {"TARGET_MET": "MET", "PARTIAL": "NOT_MET",
                           "NO_ELIGIBLE_ALLOCATION": "NOT_MET", "UNAVAILABLE": "UNAVAILABLE"}
        valid = (isinstance(metric, dict) and valid_months
                 and metric.get("methodology") == "DESCRIPTIVE_PLAN_METRICS_V5_4"
                 and metric.get("amount_basis") == "DISPLAYED_RESPONSE_AMOUNTS"
                 and metric.get("mode") == "CASH_TARGET"
                 and isinstance(metric.get("source_status"), str)
                 and metric.get("source_status") in expected_status
                 and metric.get("source_status") == result.get("status")
                 and metric.get("target_attainment") == expected_status.get(result.get("status"))
                 and metric.get("selected_months") == months)
        rows[0][column] = "、".join(map(str, months)) if valid_months else MISSING
        rows[1][column] = ({"MET": "已達標", "NOT_MET": "未達標", "UNAVAILABLE": "資料不足"}
                           [metric["target_attainment"]] if valid else MISSING)
        for row, (field, _) in zip(rows[2:-1], FIELDS, strict=True):
            row[column] = (_number(metric.get(field), percentage=field.endswith("_pct"))
                           if valid and (result["status"] != "UNAVAILABLE"
                                         or field == "capital_limit_twd") else MISSING)
        messages = []
        if valid:
            issues = metric.get("issues", [])
            if isinstance(issues, list):
                messages = [i["message"] for i in issues if isinstance(i, dict)
                            and isinstance(i.get("message"), str) and i["message"]]
            if any(row[column] == MISSING for row in rows[2:-1]):
                messages.append("部分指標未提供或不適用，請參考原方案資料與提醒。")
        else:
            messages.append("指標未提供或與此方案不一致；原方案仍可查看。")
        rows[-1][column] = "；".join(dict.fromkeys(messages)) or "無額外指標提醒"
    return rows


def render_planning_metrics(payload):
    st.markdown("#### 方案客觀指標比較")
    st.caption(NOTE)
    st.dataframe(build_planning_metric_rows(payload), hide_index=True,
                 width="stretch", height="content", key="planning-metric-comparison")
