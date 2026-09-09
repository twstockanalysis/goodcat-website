"""V3-1 公開且不儲存資料的現金流配置試算頁。"""

from concurrent.futures import (
    ThreadPoolExecutor,
    TimeoutError as FutureTimeoutError,
)
from decimal import Decimal, InvalidOperation
from typing import Any

import pandas as pd
import streamlit as st

from frontend.ui.components import render_page_title

from frontend.api_client import APIClientError, fetch_portfolio_projections
from frontend.config import get_api_base_url
from frontend.ui.assessment import (
    allocation_fit_presentation,
    historical_quality_presentation,
)
from frontend.ui.formatters import format_number
from frontend.ui.goodcat import GoodCatState, get_goodcat_presentation
from frontend.ui.states import loading_state


MONTH_OPTIONS = list(range(1, 13))
MONTH_PRESETS = {
    "每月": MONTH_OPTIONS,
    "單數月": [1, 3, 5, 7, 9, 11],
    "雙數月": [2, 4, 6, 8, 10, 12],
}
TARGET_MONTHS_STATE_KEY = "public_planner_target_months"
REINVESTMENT_POLICY_STATE_KEY = "public_planner_reinvestment_policy"
HOLDING_ROWS_STATE_KEY = "public_planner_holding_rows"
HOLDING_EDITOR_VERSION_STATE_KEY = "public_planner_holding_editor_version"
RESULT_STATE_KEY = "public_portfolio_projections"
RESULT_INPUT_SIGNATURE_STATE_KEY = "public_planner_result_input_signature"
HOLDING_SELECTION_COLUMN = "選取"
# 配息歷史觀察期與使用者選擇的未來持有年限是不同概念；目前正式資料
# 最長可穩定比較三年，後續資料覆蓋擴充時再同步提高。
DEFAULT_HISTORY_YEARS = 3
DEFAULT_CASH_DEDUCTION_RATE_PCT = 0.0
DEFAULT_CUSTOM_REINVESTMENT_PCT = 50.0
ANNUAL_DIVIDEND_CREDIT_CAP_TWD = 80_000.0
MARGINAL_TAX_RATE_OPTIONS = {
    "5%": 5.0,
    "12%": 12.0,
    "20%": 20.0,
    "30%": 30.0,
    "40%": 40.0,
}
MARGINAL_TAX_RATE_HELP = (
    "115 年度綜合所得稅級距（綜合所得淨額）：\n\n"
    "5%：610,000 元以下\n\n"
    "12%：610,001～1,380,000 元\n\n"
    "20%：1,380,001～2,770,000 元\n\n"
    "30%：2,770,001～5,190,000 元\n\n"
    "40%：5,190,001 元以上"
)
PLANNER_GOODCAT_HERO_FILENAMES = {
    GoodCatState.ATTENTIVE: {
        "light": "goodcat-planner-start-hero.png",
        "dark": "goodcat-planner-start-white-hero.png",
    },
    GoodCatState.WORKING: {
        "light": "goodcat-researching-hero.png",
        "dark": "goodcat-researching-white-hero.png",
    },
    GoodCatState.READY: {
        "light": "goodcat-ready-hero.png",
        "dark": "goodcat-ready-white-hero.png",
    },
    GoodCatState.REWARD: {
        "light": "goodcat-result-reward-hero.png",
        "dark": "goodcat-result-reward-white-hero.png",
    },
    GoodCatState.CAUTION: {
        "light": "goodcat-warning-hero.png",
        "dark": "goodcat-warning-white-hero.png",
    },
}
PLANNER_WORKING_GOODCAT_FRAME_INTERVAL_SECONDS = 1.0
PLANNER_WORKING_GOODCAT_FRAMES = (
    {
        "message": "咪正在努力核對中",
        "light": "goodcat-researching-hero.png",
        "dark": "goodcat-researching-white-hero.png",
    },
    {
        "message": "資料好多，喵覺得累",
        "light": "goodcat-researching-tired-hero.png",
        "dark": "goodcat-researching-tired-white-hero.png",
    },
)


def get_planner_goodcat_hero_filename(
    state: GoodCatState,
    theme_type: str,
) -> str:
    """依規劃狀態與主題挑選一致情境的灰貓或白貓。"""

    theme_key = "dark" if theme_type == "dark" else "light"
    return PLANNER_GOODCAT_HERO_FILENAMES[state][theme_key]


def get_planner_working_goodcat_frame(
    frame_index: int,
    theme_type: str,
) -> tuple[str, str]:
    """依輪替位置與主題取得計算中圖片及訊息。"""

    frame = PLANNER_WORKING_GOODCAT_FRAMES[
        frame_index % len(PLANNER_WORKING_GOODCAT_FRAMES)
    ]
    theme_key = "dark" if theme_type == "dark" else "light"
    return frame[theme_key], frame["message"]


def allocation_goodcat_feedback(
    payload: dict[str, Any],
) -> tuple[GoodCatState, str]:
    """依公開配置狀態選擇簡單、不誇大的角色回饋。"""

    allocation = payload.get("long_term_scenarios", {}).get(
        "allocation_results", {}
    )
    plans = allocation.get("plans", [])
    if not plans:
        return (
            GoodCatState.CAUTION,
            "目前沒有足夠資料完成配置，咪把能確認的原因留在下方。",
        )

    recommended = next(
        (
            plan
            for plan in plans
            if plan.get("strategy") == "RECOMMENDED"
        ),
        plans[0],
    )
    result = recommended.get("result", {})
    status = result.get("status")

    if status == "TARGET_MET":
        if result.get("additions"):
            message = "算好囉！咪已整理要增加的 ETF、股數與所需資金。"
        else:
            message = "算好囉！依目前資料，主人的庫存已能覆蓋設定目標。"
        return GoodCatState.REWARD, message

    if status == "PARTIAL":
        return (
            GoodCatState.REWARD,
            "咪找到目前較接近的配置，但部分月份仍有缺口，請一起看原因。",
        )

    return (
        GoodCatState.CAUTION,
        "目前資料下還找不到合適的新增配置，咪把排除原因整理在下方。",
    )


def planner_input_signature(
    *,
    target_cash: int,
    selected_months: list[int],
    projection_years: int,
    holdings: list[dict[str, Any]],
    reinvestment_policy: str,
    tax_method: str,
    marginal_tax_rate: float,
    other_income_tax_rate: float,
    remaining_credit_cap: float,
    premium_exempt: bool,
) -> tuple[Any, ...]:
    """辨識本頁輸入，避免條件改變後仍顯示舊配置。"""

    return (
        int(target_cash),
        tuple(sorted(int(month) for month in selected_months)),
        int(projection_years),
        tuple(
            (str(item["etf_code"]), int(item["held_units"]))
            for item in holdings
        ),
        reinvestment_policy,
        tax_method,
        float(marginal_tax_rate),
        float(other_income_tax_rate),
        float(remaining_credit_cap),
        bool(premium_exempt),
    )


def render_planner_goodcat(
    slot: Any,
    state: GoodCatState,
    message: str,
    *,
    asset_filename: str | None = None,
) -> None:
    """在固定位置替換規劃流程的角色狀態。"""

    presentation = get_goodcat_presentation(state)
    hero_asset_path = presentation.asset_path.with_name(
        asset_filename
        or get_planner_goodcat_hero_filename(
            state, st.context.theme.type
        )
    )

    slot.empty()
    with slot.container():
        with st.container(border=True):
            image_column, copy_column = st.columns(
                [2, 3],
                vertical_alignment="center",
                gap="medium",
            )
            with image_column:
                st.image(
                    hero_asset_path,
                    caption=None,
                    width=260,
                    output_format="PNG",
                )
            with copy_column:
                st.caption(presentation.label)
                st.markdown(f"**{message.strip()}**")


def fetch_portfolio_projections_with_working_animation(
    api_base_url: str,
    payload: dict[str, Any],
    goodcat_slot: Any,
) -> dict[str, Any]:
    """等待試算時每秒輪替符合目前主題的 GoodCat 畫面。"""

    theme_type = st.context.theme.type
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(
            fetch_portfolio_projections,
            api_base_url,
            payload,
        )
        frame_index = 0
        while True:
            asset_filename, message = get_planner_working_goodcat_frame(
                frame_index,
                theme_type,
            )
            render_planner_goodcat(
                goodcat_slot,
                GoodCatState.WORKING,
                message,
                asset_filename=asset_filename,
            )
            try:
                return future.result(
                    timeout=PLANNER_WORKING_GOODCAT_FRAME_INTERVAL_SECONDS
                )
            except FutureTimeoutError:
                frame_index += 1


def apply_month_preset(months: list[int]) -> None:
    """將月份快速選取同步到逐月選擇元件。"""

    st.session_state[TARGET_MONTHS_STATE_KEY] = list(months)


def toggle_target_month(month: int) -> None:
    """切換單一目標月份並維持月份順序。"""

    selected_months = {
        int(value) for value in st.session_state[TARGET_MONTHS_STATE_KEY]
    }
    if month in selected_months:
        selected_months.remove(month)
    else:
        selected_months.add(month)
    st.session_state[TARGET_MONTHS_STATE_KEY] = sorted(selected_months)


def empty_holding_editor_rows() -> pd.DataFrame:
    """建立可接受 0 檔持股的明確型別空表。"""

    return pd.DataFrame(
        {
            HOLDING_SELECTION_COLUMN: pd.Series(dtype="bool"),
            "ETF 代號": pd.Series(dtype="string"),
            "持有股數": pd.Series(dtype="Int64"),
        }
    )


def normalize_holding_editor_rows(rows: pd.DataFrame) -> pd.DataFrame:
    """維持庫存持股表欄位順序與明確型別。"""

    normalized = rows.reindex(
        columns=[HOLDING_SELECTION_COLUMN, "ETF 代號", "持有股數"]
    ).copy()
    normalized[HOLDING_SELECTION_COLUMN] = (
        normalized[HOLDING_SELECTION_COLUMN].fillna(False).astype("bool")
    )
    normalized["ETF 代號"] = normalized["ETF 代號"].astype("string")
    normalized["持有股數"] = pd.to_numeric(
        normalized["持有股數"], errors="coerce"
    ).astype("Int64")
    return normalized.reset_index(drop=True)


def sort_holding_editor_rows(rows: pd.DataFrame) -> pd.DataFrame:
    """依 ETF 代號排序，尚未輸入代號的空白列固定放在最後。"""

    normalized = normalize_holding_editor_rows(rows)
    codes = normalized["ETF 代號"].fillna("").str.strip().str.upper()
    normalized["ETF 代號"] = codes.mask(codes.eq(""), pd.NA).astype("string")
    return (
        normalized.assign(_is_blank=codes.eq(""), _code_sort=codes)
        .sort_values(["_is_blank", "_code_sort"], kind="stable")
        .drop(columns=["_is_blank", "_code_sort"])
        .reset_index(drop=True)
    )


def add_empty_holding_row(rows: pd.DataFrame) -> pd.DataFrame:
    """在庫存持股表加入一列空白輸入。"""

    new_row = pd.DataFrame(
        {
            HOLDING_SELECTION_COLUMN: pd.Series([False], dtype="bool"),
            "ETF 代號": pd.Series([pd.NA], dtype="string"),
            "持有股數": pd.Series([pd.NA], dtype="Int64"),
        }
    )
    return normalize_holding_editor_rows(
        pd.concat([normalize_holding_editor_rows(rows), new_row], ignore_index=True)
    )


def remove_selected_holding_rows(rows: pd.DataFrame) -> pd.DataFrame:
    """只刪除已明確勾選的庫存持股列。"""

    normalized = normalize_holding_editor_rows(rows)
    return normalize_holding_editor_rows(
        normalized.loc[~normalized[HOLDING_SELECTION_COLUMN]]
    )


def replace_holding_rows(rows: pd.DataFrame) -> None:
    """更新庫存持股資料並重建編輯器，避免殘留舊列狀態。"""

    st.session_state[HOLDING_ROWS_STATE_KEY] = sort_holding_editor_rows(rows)
    st.session_state[HOLDING_EDITOR_VERSION_STATE_KEY] += 1


def merge_holding_editor_changes(
    rows: pd.DataFrame, edited_rows: dict[int | str, dict[str, Any]]
) -> pd.DataFrame:
    """將 Streamlit 編輯器的列級異動合併回明確型別資料。"""

    merged = normalize_holding_editor_rows(rows)
    for row_index, changes in edited_rows.items():
        index = int(row_index)
        if not 0 <= index < len(merged):
            continue
        for column, value in changes.items():
            if column in merged.columns:
                merged.at[index, column] = value
    return sort_holding_editor_rows(merged)


def apply_holding_editor_changes(editor_key: str) -> None:
    """套用本次儲存格異動，並在完成輸入後重排 ETF 代號。"""

    editor_state = st.session_state.get(editor_key, {})
    replace_holding_rows(
        merge_holding_editor_changes(
            st.session_state[HOLDING_ROWS_STATE_KEY],
            editor_state.get("edited_rows", {}),
        )
    )


def build_holding_payload(
    rows: pd.DataFrame,
) -> tuple[list[dict[str, Any]], list[str]]:
    """將公開表格輸入正規化，並回傳可讀的列級錯誤。"""

    holdings: list[dict[str, Any]] = []
    errors: list[str] = []
    for row_number, row in enumerate(rows.to_dict(orient="records"), start=1):
        raw_code = row.get("ETF 代號")
        raw_units = row.get("持有股數")
        code = "" if pd.isna(raw_code) else str(raw_code).strip().upper()

        if not code and pd.isna(raw_units):
            continue
        if not code:
            errors.append(f"第 {row_number} 列缺少 ETF 代號。")
            continue
        try:
            units = Decimal(str(raw_units))
            units_is_valid = units.is_finite() and units > 0
        except (InvalidOperation, ValueError):
            units_is_valid = False
            units = Decimal("0")
        if not units_is_valid or units != units.to_integral_value():
            errors.append(f"第 {row_number} 列持有股數必須是正整數。")
            continue
        holdings.append({"etf_code": code, "held_units": int(units)})

    codes = [item["etf_code"] for item in holdings]
    duplicates = sorted({code for code in codes if codes.count(code) > 1})
    if duplicates:
        errors.append("ETF 代號不可重複：" + "、".join(duplicates))
    return holdings, errors


def build_monthly_rows(result: dict[str, Any]) -> list[dict[str, str]]:
    """建立 12 個月份的透明現金流與缺口表格。"""

    rows = []
    for item in result["monthly_cash_flow"]:
        rows.append(
            {
                "月份": f"{int(item['month'])} 月",
                "目標月份": "是" if item["selected"] else "—",
                "歷史年均稅前現金": format_number(
                    item.get("gross_cash"),
                    decimal_places=0,
                    suffix=" NTD",
                    missing_text="無法計算",
                ),
                "扣除後可用現金": format_number(
                    item.get("after_tax_cash"),
                    decimal_places=0,
                    suffix=" NTD",
                    missing_text="無法計算",
                ),
                "現金流目標": format_number(
                    item.get("target_after_tax_cash"),
                    decimal_places=0,
                    suffix=" NTD",
                ),
                "尚缺金額": format_number(
                    item.get("shortfall"),
                    decimal_places=0,
                    suffix=" NTD",
                    missing_text="無法計算",
                ),
            }
        )
    return rows


def build_holding_rows(result: dict[str, Any]) -> list[dict[str, str]]:
    """建立現有持股事實表，不將缺值誤顯示為零。"""

    return [
        {
            "ETF": f"{item['etf_code']} {item['name']}",
            "持有股數": f"{int(item['held_units']):,}",
            "官方收盤價": format_number(
                item.get("unit_price"),
                decimal_places=0,
                suffix=" NTD",
                missing_text="尚未取得",
            ),
            "目前部位價值": format_number(
                item.get("current_value"),
                decimal_places=0,
                suffix=" NTD",
                missing_text="無法計算",
            ),
            "價格日期": item.get("price_as_of_date") or "尚未取得",
            "歷史付款月份": (
                "、".join(f"{month} 月" for month in item["historical_payment_months"])
                or "尚無可用資料"
            ),
        }
        for item in result["holdings"]
    ]


def render_public_planner_result(result: dict[str, Any]) -> None:
    """呈現現有持股基線，並清楚標示尚未涵蓋的自動配置。"""

    st.subheader("現有持股現金流基線")
    status_text = "資料可計算" if result["status"] == "AVAILABLE" else "部分資料不足"
    with st.container(horizontal=True):
        st.metric(
            "目前持股總值",
            format_number(
                result.get("total_current_value"),
                decimal_places=0,
                suffix=" NTD",
                missing_text="無法計算",
            ),
            border=True,
        )
        st.metric("選定領息月份", f"{len(result['target_months'])} 個月", border=True)
        st.metric("基線狀態", status_text, border=True)

    if result["holdings"]:
        st.table(build_holding_rows(result))
    else:
        st.info("目前以 0 檔持股起算，因此所有目標月份的缺口等於現金流目標。")

    st.dataframe(build_monthly_rows(result), hide_index=True)
    st.caption(
        f"分析日期 {result['analysis_date']}；使用最近 {result['history_years']} 年、"
        "依付款日歸月的歷史配息年均值。無配息事件的正式月份視為 0；"
        "整檔缺少可用資料時顯示為無法計算。"
    )

    issue_messages = []
    for item in result.get("issues", []):
        prefix = f"{item['etf_code']}：" if item.get("etf_code") else ""
        issue_messages.append(prefix + item["message"])
    if issue_messages:
        st.warning("資料提醒：" + "、".join(dict.fromkeys(issue_messages)))

    st.info(
        "此階段先建立現有持股與月份缺口基線。全市場自動挑選 ETF、"
        "各買多少整股及所需資金，將由 V3-2 與 V3-3 接續完成。"
    )


def build_addition_rows(result: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {
            "ETF": f"{item['etf_code']} {item['name']}",
            "增加股數": f"{int(item['additional_shares']):,}",
            "參考價格": format_number(
                item.get("reference_price"),
                decimal_places=0,
                suffix=" NTD",
            ),
            "價格日期": item.get("reference_price_as_of") or "未提供",
            "預估所需資金": format_number(
                item.get("required_capital"),
                decimal_places=0,
                suffix=" NTD",
            ),
            "支援月份": "、".join(
                f"{month} 月" for month in item.get("supported_target_months", [])
            ) or "未直接支援目標月份",
        }
        for item in result.get("additions", [])
    ]


def build_allocation_month_rows(result: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {
            "月份": f"{int(item['month'])} 月",
            "目前可用現金": format_number(
                item.get("current_after_tax_cash"),
                decimal_places=0,
                suffix=" NTD",
            ),
            "新增現金": format_number(
                item.get("added_after_tax_cash"),
                decimal_places=0,
                suffix=" NTD",
            ),
            "配置後現金": format_number(
                item.get("modeled_after_tax_cash"),
                decimal_places=0,
                suffix=" NTD",
            ),
            "目標": format_number(
                item.get("target_after_tax_cash"),
                decimal_places=0,
                suffix=" NTD",
            ),
            "尚缺": format_number(
                item.get("shortfall"),
                decimal_places=0,
                suffix=" NTD",
            ),
        }
        for item in result.get("monthly_results", [])
    ]


def build_resulting_holding_rows(result: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {
            "ETF 代號": item["etf_code"],
            "原有股數": f"{int(item['existing_shares']):,}",
            "增加股數": f"{int(item['additional_shares']):,}",
            "配置後股數": f"{int(item['resulting_shares']):,}",
            "配置後市值": format_number(
                item.get("resulting_value"),
                decimal_places=0,
                suffix=" NTD",
            ),
            "市值占比": format_number(
                item.get("allocation_pct"),
                decimal_places=2,
                suffix="%",
            ),
        }
        for item in result.get("resulting_holdings", [])
    ]


def summarize_allocation_result(result: dict[str, Any]) -> dict[str, Any]:
    """彙整主人最先需要知道的達標月份與剩餘缺口。"""

    months = result.get("monthly_results", [])
    met_months = 0
    total_shortfall = Decimal("0")
    for item in months:
        shortfall = Decimal(str(item.get("shortfall", "0")))
        total_shortfall += shortfall
        if shortfall == 0:
            met_months += 1
    return {
        "target_month_count": len(months),
        "met_month_count": met_months,
        "total_shortfall": total_shortfall,
    }


def render_plan_preview(plan: dict[str, Any]) -> None:
    """顯示一張可快速比較但不取代詳細結果的方案摘要卡。"""

    result = plan["result"]
    fit = allocation_fit_presentation(result)
    summary = summarize_allocation_result(result)
    with st.container(
        border=True,
        height="stretch",
        key=f"allocation-plan-summary-card-{plan['strategy'].lower()}",
    ):
        st.markdown(f"#### {plan['label']}")
        st.badge(fit.label, color=fit.color)
        st.caption(plan["simple_explanation"])
        st.write(
            "新增資金：**"
            + format_number(
                result.get("total_required_additional_capital"),
                decimal_places=0,
                suffix=" NTD",
            )
            + "**"
        )
        st.caption(
            f"新增 {len(result.get('additions', []))} 檔 ETF；"
            f"{summary['met_month_count']}／{summary['target_month_count']} 個目標月達標。"
        )


def render_addition_card(addition: dict[str, Any], *, strategy: str) -> None:
    """以整數股數、資金、理由、評等與主要風險呈現單一新增 ETF。"""

    code = str(addition["etf_code"])
    grade = historical_quality_presentation(
        addition.get("historical_quality_grade")
    )
    reasons = list(dict.fromkeys(addition.get("reasons", [])))
    risks = list(dict.fromkeys(addition.get("risks", [])))
    months = addition.get("supported_target_months", [])

    with st.container(
        border=True,
        key=f"allocation-addition-card-{strategy.lower()}-{code.lower()}",
    ):
        st.markdown(f"#### {code} {addition['name']}")
        st.badge(grade.label, color=grade.color)
        st.caption("這是 ETF 喵喵評等，不代表一定適合每位主人。")
        columns = st.columns(3)
        columns[0].metric(
            "增加股數",
            f"{int(addition['additional_shares']):,} 股",
            border=True,
        )
        columns[1].metric(
            "預估所需資金",
            format_number(
                addition.get("required_capital"),
                decimal_places=0,
                suffix=" NTD",
            ),
            border=True,
        )
        columns[2].metric(
            "支援目標月份",
            "、".join(f"{month} 月" for month in months) or "未直接支援",
            border=True,
        )

        st.markdown("**為什麼放進這個配置**")
        if reasons:
            for reason in reasons:
                st.write(f"- {reason}")
        else:
            st.caption("通過資料與風險門檻，並用來縮小本次現金流缺口。")

        if risks:
            st.warning(f"主要風險：{risks[0]}", icon=":material/warning:")
        else:
            st.caption("目前公開資料沒有額外的單檔風險提醒；仍須留意市場波動。")

        with st.expander(
            "查看喵喵評等依據與其他風險",
            icon=":material/fact_check:",
        ):
            st.write(grade.explanation)
            grade_payload = addition.get("historical_quality_grade")
            if isinstance(grade_payload, dict):
                strengths = list(dict.fromkeys(grade_payload.get("strengths", [])))
                grade_risks = list(
                    dict.fromkeys(grade_payload.get("risks", []))
                )
                unavailable = list(
                    dict.fromkeys(grade_payload.get("unavailable_evidence", []))
                )
                if strengths:
                    st.markdown("**目前支持證據**")
                    for strength in strengths:
                        st.write(f"- {strength}")
                if grade_risks:
                    st.markdown("**喵喵評等風險**")
                    for item in grade_risks:
                        st.write(f"- {item}")
                if unavailable:
                    st.markdown("**尚缺證據**")
                    for item in unavailable:
                        st.write(f"- {item}")
            for risk in risks[1:]:
                st.write(f"- {risk}")


def render_allocation_results(payload: dict[str, Any]) -> str:
    st.subheader("咪算出的配置")
    plans = payload["plans"]
    st.caption(
        "資金精簡方案先降低新增資金；穩定均衡與分散防護方案只有在完整達標且配置確實不同時才會出現。"
    )

    preview_columns = st.columns(len(plans))
    for column, preview_plan in zip(preview_columns, plans, strict=True):
        with column:
            render_plan_preview(preview_plan)

    labels = [plan["label"] for plan in plans]
    selected_label = labels[0]
    if len(labels) > 1:
        selected_label = st.segmented_control(
            "查看方案細節",
            labels,
            default=labels[0],
            key="public_planner_strategy",
        ) or labels[0]
    plan = next(item for item in plans if item["label"] == selected_label)
    result = plan["result"]
    fit = allocation_fit_presentation(result)
    summary = summarize_allocation_result(result)

    with st.container(
        border=True,
        key=f"allocation-plan-detail-card-{plan['strategy'].lower()}",
    ):
        st.markdown(f"### {plan['label']}細節")
        st.badge(f"主人目標適配｜{fit.label}", color=fit.color)
        st.write(fit.explanation)
        st.caption("主人目標適配只針對本次輸入；不等同 ETF 喵喵評等。")
        columns = st.columns(4)
        columns[0].metric(
            "新增所需資金",
            format_number(
                result.get("total_required_additional_capital"),
                decimal_places=0,
                suffix=" NTD",
            ),
            border=True,
        )
        columns[1].metric(
            "新增 ETF",
            f"{len(result.get('additions', []))} 檔",
            border=True,
        )
        columns[2].metric(
            "達標月份",
            f"{summary['met_month_count']}／{summary['target_month_count']} 月",
            border=True,
        )
        columns[3].metric(
            "尚缺總額",
            format_number(
                summary["total_shortfall"],
                decimal_places=0,
                suffix=" NTD",
            ),
            border=True,
        )

    if result.get("additions"):
        st.markdown("#### 咪建議增加的 ETF 與整數股數")
        for addition in result["additions"]:
            render_addition_card(addition, strategy=plan["strategy"])
    else:
        st.info(
            "此配置目前沒有可新增的 ETF；可能是庫存已達標，或目前沒有標的通過資料與風險門檻。",
            icon=":material/info:",
        )

    st.markdown("#### 每個目標月有沒有達標")
    st.dataframe(
        build_allocation_month_rows(result),
        hide_index=True,
        key=f"allocation-months-{plan['strategy'].lower()}",
    )

    issues = [item["message"] for item in result.get("issues", [])]
    if issues:
        st.warning(
            "配置提醒：" + "、".join(dict.fromkeys(issues)),
            icon=":material/warning:",
        )

    holdings = build_resulting_holding_rows(result)
    assumptions = result.get("assumptions", {})
    with st.expander(
        "查看配置後持股與計算假設",
        icon=":material/tune:",
    ):
        if holdings:
            st.markdown("**配置後持股**")
            st.dataframe(holdings, hide_index=True)
        else:
            st.caption("目前沒有可顯示的配置後持股。")
        if result.get("optimality") == "BOUNDED_BEST_EFFORT":
            st.warning("這是有界配置結果，不代表唯一或已證明的最低資金方案。")
        st.caption(
            f"參考資料快照：{result.get('snapshot_id', '未提供')}。"
            f"{assumptions.get('transaction_cost_note', '交易成本假設未提供')}"
        )
        st.caption(payload["estimate_label"])

    strategy_messages = [
        item["message"] for item in payload.get("strategy_issues", [])
    ]
    if strategy_messages:
        with st.expander(
            "為什麼沒有更多不同方案",
            icon=":material/compare_arrows:",
        ):
            for message in dict.fromkeys(strategy_messages):
                st.write(f"- {message}")

    excluded = payload.get("excluded_candidates", [])
    if excluded:
        with st.expander(
            f"查看未納入的 ETF（{len(excluded)} 檔）",
            icon=":material/filter_alt_off:",
        ):
            st.caption("只顯示資料或風險門檻的排除理由，不代表買賣建議。")
            st.dataframe(
                [
                    {
                        "ETF": f"{item['etf_code']} {item['name']}",
                        "未納入原因": "、".join(
                            reason["message"] for reason in item.get("reasons", [])
                        ) or "未提供原因",
                    }
                    for item in excluded
                ],
                hide_index=True,
            )

    return plan["strategy"]


def build_historical_evidence_rows(evidence: dict[str, Any]) -> list[dict[str, str]]:
    labels = {
        "AVAILABLE_HISTORY": "最長可用歷史",
        "3Y": "近 3 年",
        "5Y": "近 5 年",
        "10Y": "近 10 年",
    }
    rows = []
    for item in evidence.get("historical_periods", []):
        available = item.get("status") == "AVAILABLE"
        period_start = item.get("period_start")
        period_end = item.get("period_end")
        issue_messages = [
            issue["message"] for issue in item.get("issues", [])
        ]
        rows.append(
            {
                "期間": labels.get(item.get("period"), item.get("period", "")),
                "實際資料範圍": (
                    f"{period_start} 至 {period_end}"
                    if available and period_start and period_end
                    else "歷史資料不足"
                ),
                "含息總報酬估算": format_number(
                    item.get("total_return_pct") if available else None,
                    decimal_places=2,
                    suffix="%",
                    missing_text="無法計算",
                ),
                "年化含息報酬估算": format_number(
                    item.get("annualized_total_return_pct") if available else None,
                    decimal_places=2,
                    suffix="%",
                    missing_text="無法計算",
                ),
                "說明": "、".join(issue_messages) if issue_messages else "可用",
            }
        )
    return rows


def build_scenario_chart_rows(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    rows_by_year: dict[int, dict[str, Any]] = {}
    for scenario in evidence.get("scenarios", []):
        label = scenario["label"]
        for point in scenario.get("index_points", []):
            year = int(point["year"])
            rows_by_year.setdefault(year, {"年數": year})[label] = float(
                point["total_value_index"]
            )
    return [rows_by_year[year] for year in sorted(rows_by_year)]


def render_long_term_evidence(payload: dict[str, Any], strategy: str) -> None:
    evidence = next(
        item for item in payload["plan_evidence"] if item["strategy"] == strategy
    )
    st.subheader("長期歷史與十年情境")
    st.caption(
        "以上方配置後的整數股數回算；歷史配息不再投入。"
    )
    st.dataframe(build_historical_evidence_rows(evidence), hide_index=True)
    has_available_history = any(
        item.get("status") == "AVAILABLE"
        for item in evidence.get("historical_periods", [])
    )
    if has_available_history:
        st.warning(
            "歷史價格目前是官方原始收盤價，尚未調整 ETF 分割或反分割；"
            "如果期間發生股數變動，報酬估算可能失真。"
        )

    scenarios = evidence.get("scenarios", [])
    if not scenarios:
        st.info("完整一年期觀察少於 2 筆，因此不產生十年情境。")
    else:
        with st.container(horizontal=True):
            for scenario in scenarios:
                st.metric(
                    scenario["label"],
                    format_number(
                        scenario["annual_total_return_assumption_pct"],
                        decimal_places=2,
                        suffix="% / 年",
                    ),
                    border=True,
                )
        chart_rows = build_scenario_chart_rows(evidence)
        st.line_chart(
            pd.DataFrame(chart_rows),
            x="年數",
            y=[scenario["label"] for scenario in scenarios],
            x_label="配置後年數",
            y_label="含息總價值指數",
        )
        st.caption(
            f"指數從 100 起算，不是實際金額。三種情境來自 "
            f"{int(evidence.get('annual_observation_count', 0))} 筆完整一年期歷史觀察的"
            "25／50／75 百分位，再以每年複利延伸。"
        )

    issue_messages = [item["message"] for item in evidence.get("issues", [])]
    extra_messages = [
        message
        for message in dict.fromkeys(issue_messages)
        if "分割或反分割" not in message
        and "少於兩個完整一年期" not in message
    ]
    if extra_messages:
        st.info("長期資料提醒：" + "、".join(extra_messages))
    st.caption(payload["estimate_label"])


def _portfolio_projection_chart_rows(
    market: dict[str, Any],
    selected_policy: str | None = None,
) -> list[dict[str, Any]]:
    policy_labels = {
        "NO_REINVESTMENT": "領出使用",
        "EXCESS_ONLY": "只投入超過目標部分",
        "CUSTOM_PERCENTAGE": "按比例投入",
        "FULL_REINVESTMENT": "全部投入",
    }
    rows_by_year: dict[int, dict[str, Any]] = {}
    for result in market.get("reinvestment_results", []):
        if selected_policy is not None and result["policy"] != selected_policy:
            continue
        label = policy_labels[result["policy"]]
        for point in result.get("year_points", []):
            year = int(point["year"])
            rows_by_year.setdefault(year, {"年數": year})[label] = float(
                point["ending_value"]
            ) + float(point["usable_cash"])
    return [rows_by_year[year] for year in sorted(rows_by_year)]


def render_portfolio_projection(
    payload: dict[str, Any],
    strategy: str,
    selected_reinvestment_policy: str,
) -> None:
    projection = next(
        item for item in payload["plan_projections"] if item["strategy"] == strategy
    )
    st.subheader(f"整體組合 {payload['projection_years']} 年試算")
    st.caption(
        "以配置後全部持股一起估算，只顯示可能產生的個人所得稅與二代健保金額；"
        "不同人的實際結果可能不同。"
    )
    with st.container(horizontal=True):
        st.metric(
            "組合起始價值",
            format_number(
                projection.get("initial_value"), decimal_places=0, suffix=" NTD"
            ),
            border=True,
        )
        st.metric(
            "年現金目標",
            format_number(
                projection.get("annual_cash_target"), decimal_places=0, suffix=" NTD"
            ),
            border=True,
        )
        st.metric(
            "歷史年均配息率",
            format_number(
                projection.get("weighted_annual_gross_distribution_rate_pct"),
                decimal_places=2,
                suffix="%",
                missing_text="無法計算",
            ),
            border=True,
        )

    if projection.get("status") != "AVAILABLE":
        messages = [item["message"] for item in projection.get("issues", [])]
        st.info(
            "目前無法建立整體組合試算。"
            + ((" " + "、".join(dict.fromkeys(messages))) if messages else "")
        )
        return

    markets = projection["market_projections"]
    labels = [item["label"] for item in markets]
    selected = st.segmented_control(
        "市場情境",
        labels,
        default=labels[1] if len(labels) > 1 else labels[0],
        key=f"portfolio_market_{strategy}",
    ) or labels[0]
    market = next(item for item in markets if item["label"] == selected)
    st.caption(
        "這個市場情境假設每年含息報酬約 "
        + format_number(
            market["gross_annual_total_return_assumption_pct"],
            decimal_places=2,
            suffix="%",
        )
        + "；不是未來預測。"
    )

    policy_labels = {
        "NO_REINVESTMENT": "領出使用",
        "EXCESS_ONLY": "只投入超過目標部分",
        "CUSTOM_PERCENTAGE": "按比例投入",
        "FULL_REINVESTMENT": "全部投入",
    }
    selected_policy_label = policy_labels[selected_reinvestment_policy]
    st.caption(f"本次選擇的股息使用方式：{selected_policy_label}。")
    rows = []
    for result in market["reinvestment_results"]:
        if result["policy"] != selected_reinvestment_policy:
            continue
        rows.append(
            {
                "配息使用方式": policy_labels[result["policy"]],
                "期末持股價值": format_number(
                    result["ending_value"], decimal_places=0, suffix=" NTD"
                ),
                "期間可用現金": format_number(
                    result["usable_cash"], decimal_places=0, suffix=" NTD"
                ),
                "投入金額": format_number(
                    result["reinvested_cash"], decimal_places=0, suffix=" NTD"
                ),
                "可能的所得稅": format_number(
                    result["modeled_income_tax"], decimal_places=0, suffix=" NTD"
                ),
                "可能的二代健保": format_number(
                    result["modeled_supplementary_premium"],
                    decimal_places=0,
                    suffix=" NTD",
                ),
                "稅後總報酬": format_number(
                    result["after_tax_total_return_pct"],
                    decimal_places=2,
                    suffix="%",
                ),
            }
        )
    st.dataframe(rows, hide_index=True)
    st.vega_lite_chart(
        pd.DataFrame(
            _portfolio_projection_chart_rows(market, selected_reinvestment_policy)
        ),
        {
            "mark": {"type": "line", "tooltip": True},
            "encoding": {
                "x": {"field": "年數", "type": "quantitative", "title": "配置後年數"},
                "y": {
                    "field": selected_policy_label,
                    "type": "quantitative",
                    "title": "持股價值加已領可用現金（NTD）",
                    "axis": {"format": ",.0f"},
                },
                "tooltip": [
                    {"field": "年數", "type": "quantitative", "format": "d"},
                    {"field": selected_policy_label, "type": "quantitative", "format": ",.0f"},
                ],
            },
        },
        width="stretch",
    )

    actual_count = int(projection.get("actual_component_holding_count", 0))
    estimated_count = int(projection.get("estimated_component_holding_count", 0))
    unavailable_count = int(projection.get("unavailable_component_holding_count", 0))
    st.caption(
        f"配息組成來源：正式資料 {actual_count} 檔、估算資料 {estimated_count} 檔、"
        f"缺少資料 {unavailable_count} 檔。估算資本利得不會標示為正式 76W。"
    )
    st.caption(payload["estimate_label"])


def render_public_planner() -> None:
    """顯示公開、不儲存資料的 GoodCat 引導式規劃流程。"""

    render_page_title("股利試算")

    st.session_state.setdefault(TARGET_MONTHS_STATE_KEY, MONTH_OPTIONS)
    st.session_state.setdefault(
        HOLDING_ROWS_STATE_KEY,
        add_empty_holding_row(empty_holding_editor_rows()),
    )
    st.session_state.setdefault(HOLDING_EDITOR_VERSION_STATE_KEY, 0)

    with st.container(key="public-planner-guided-form"):
        with st.container(border=True, key="public-planner-month-card"):
            month_intro_column, month_grid_column = st.columns([2, 3])
            with month_intro_column:
                st.subheader(":material/calendar_month: 1. 數錢月份")
                st.caption("可以點選每月、單數月或雙數月")
                with st.container(horizontal=True):
                    for preset_label, preset_months in MONTH_PRESETS.items():
                        preset_is_active = set(
                            st.session_state[TARGET_MONTHS_STATE_KEY]
                        ) == set(preset_months)
                        st.button(
                            preset_label,
                            type="primary" if preset_is_active else "secondary",
                            on_click=apply_month_preset,
                            args=(preset_months,),
                            key=f"public_planner_month_preset_{preset_label}",
                        )

            with month_grid_column:
                for row_start in range(0, len(MONTH_OPTIONS), 3):
                    with st.container(
                        key=f"public-planner-month-row-{row_start}",
                        gap=None,
                    ):
                        with st.container(
                            horizontal=True,
                            horizontal_alignment="distribute",
                            gap="small",
                        ):
                            for month in MONTH_OPTIONS[row_start : row_start + 3]:
                                st.button(
                                    f"{month}月",
                                    type=(
                                        "primary"
                                        if month
                                        in st.session_state[TARGET_MONTHS_STATE_KEY]
                                        else "secondary"
                                    ),
                                    on_click=toggle_target_month,
                                    args=(month,),
                                    key=f"public_planner_month_{month}",
                                    width="stretch",
                                )

            selected_months = list(st.session_state[TARGET_MONTHS_STATE_KEY])

        with st.container(border=True, key="public-planner-target-card"):
            st.subheader(":material/payments: 2. 罐頭錢目標")
            st.caption("咪會用主人的目標去計算")
            target_cash = st.number_input(
                "每個目標月想領多少股利 (NTD)",
                format="%d",
                min_value=0,
                value=3000,
                step=500,
                label_visibility="collapsed",
            )

        with st.container(border=True, key="public-planner-years-card"):
            st.subheader(":material/timeline: 3. 想持有年限")
            st.caption("使用AI預測長期表現")
            projection_years = st.number_input(
                "想持有年限",
                min_value=1,
                max_value=20,
                value=10,
                step=1,
                label_visibility="collapsed",
            )

        with st.container(border=True, key="public-planner-holding-card"):
            st.subheader(":material/account_balance_wallet: 4. 主人的庫存")
            st.caption("將持有的ETF輸入，咪可以更精準規劃，也可留白")
            editor_version = st.session_state[HOLDING_EDITOR_VERSION_STATE_KEY]
            holding_editor_key = f"public_planner_holding_editor_{editor_version}"
            with st.container(key="public-planner-holdings"):
                edited_holdings = st.data_editor(
                    st.session_state[HOLDING_ROWS_STATE_KEY],
                    num_rows="fixed",
                    hide_index=True,
                    key=holding_editor_key,
                    on_change=apply_holding_editor_changes,
                    args=(holding_editor_key,),
                    width="content",
                    column_order=[HOLDING_SELECTION_COLUMN, "ETF 代號", "持有股數"],
                    column_config={
                        HOLDING_SELECTION_COLUMN: st.column_config.CheckboxColumn(
                            "選取",
                            help="先勾選要刪除的持股",
                            default=False,
                            width=75,
                            pinned=True,
                        ),
                        "ETF 代號": st.column_config.TextColumn(
                            "ETF 代號",
                            help="限本網站收錄的台灣 ETF 代號",
                            max_chars=10,
                            width=160,
                        ),
                        "持有股數": st.column_config.NumberColumn(
                            "持有股數",
                            min_value=1,
                            step=1,
                            format="%d",
                            width=140,
                            alignment="left",
                        ),
                    },
                )

            selected_holding_count = int(
                edited_holdings[HOLDING_SELECTION_COLUMN].fillna(False).sum()
            )
            with st.container(horizontal=True):
                add_holding_clicked = st.button(
                    "持股",
                    icon=":material/add:",
                    key="public_planner_add_holding",
                )
                delete_holdings_clicked = False
                if selected_holding_count:
                    delete_holdings_clicked = st.button(
                        f"刪除已選取（{selected_holding_count}）",
                        icon=":material/delete:",
                        type="secondary",
                        key="public_planner_delete_holdings",
                    )

            st.caption(
                "價格自動擷取收盤價；若盤中，則為前一日收盤價。"
            )

            if add_holding_clicked:
                replace_holding_rows(add_empty_holding_row(edited_holdings))
                st.rerun()
            if delete_holdings_clicked:
                replace_holding_rows(remove_selected_holding_rows(edited_holdings))
                st.rerun()

        with st.container(border=True, key="public-planner-reinvestment-card"):
            st.subheader("5. 股息再投入與否")
            reinvestment_policy_label = st.segmented_control(
                "股息再投入與否",
                ["不再投入", "全部再投入"],
                default="不再投入",
                selection_mode="single",
                label_visibility="collapsed",
                key="public_planner_reinvestment_choice",
            ) or "不再投入"

        with st.expander("稅務試算選項"):
            st.caption(
                "可調整或依照預設值，咪會算出預計產生的所得稅與二代健保費"
            )
            tax_method_label = st.segmented_control(
                "股利計稅方式",
                ["合併計稅並試算抵減", "股利 28% 分開計稅"],
                default="合併計稅並試算抵減",
            ) or "合併計稅並試算抵減"
            st.caption(
                "合併計稅時，抵減額會依可適用的股利 × 8.5% "
                "自動計算，每戶/年上限 80,000 元。"
            )
            advanced_columns = st.columns(2)
            with advanced_columns[0]:
                marginal_tax_rate_label = st.selectbox(
                    "個人所得稅率（115年度級距）",
                    options=list(MARGINAL_TAX_RATE_OPTIONS),
                    index=0,
                    disabled=tax_method_label == "股利 28% 分開計稅",
                    help=MARGINAL_TAX_RATE_HELP,
                )
                marginal_tax_rate = MARGINAL_TAX_RATE_OPTIONS[
                    marginal_tax_rate_label
                ]
            with advanced_columns[1]:
                premium_exempt = st.checkbox("不估算二代健保", value=False)

            st.caption(
                "僅預估收入來源為股利，喵之後會再增加手動輸入 "
                "薪資所得欄，讓計算更準確"
            )

            other_income_tax_rate = 0.0
            remaining_credit_cap = ANNUAL_DIVIDEND_CREDIT_CAP_TWD

        goodcat_slot = st.empty()
        render_planner_goodcat(
            goodcat_slot,
            GoodCatState.ATTENTIVE,
            "如果都選完了，就「讓咪開始工作」吧！",
        )

        submitted = st.button(
            "讓咪開始工作",
            type="primary",
            icon=":material/calculate:",
            key="public_planner_submit",
            width="stretch",
        )

    selected_reinvestment_policy = (
        "FULL_REINVESTMENT"
        if reinvestment_policy_label == "全部再投入"
        else "NO_REINVESTMENT"
    )
    tax_method = (
        "SEPARATE_28"
        if tax_method_label == "股利 28% 分開計稅"
        else "COMBINED_WITH_CREDIT"
    )
    holdings, errors = build_holding_payload(edited_holdings)
    current_input_signature = planner_input_signature(
        target_cash=target_cash,
        selected_months=selected_months,
        projection_years=projection_years,
        holdings=holdings,
        reinvestment_policy=selected_reinvestment_policy,
        tax_method=tax_method,
        marginal_tax_rate=marginal_tax_rate,
        other_income_tax_rate=other_income_tax_rate,
        remaining_credit_cap=remaining_credit_cap,
        premium_exempt=premium_exempt,
    )
    saved_result = st.session_state.get(RESULT_STATE_KEY)
    saved_signature = st.session_state.get(RESULT_INPUT_SIGNATURE_STATE_KEY)
    if isinstance(saved_result, dict) and saved_signature != current_input_signature:
        st.session_state.pop(RESULT_STATE_KEY, None)
        st.session_state.pop(RESULT_INPUT_SIGNATURE_STATE_KEY, None)
        saved_result = None

    if isinstance(saved_result, dict):
        state, message = allocation_goodcat_feedback(saved_result)
        render_planner_goodcat(goodcat_slot, state, message)

    if submitted:
        st.session_state[REINVESTMENT_POLICY_STATE_KEY] = (
            selected_reinvestment_policy
        )
        if not selected_months:
            errors.append("請至少選擇一個領息月份。")
        if errors:
            render_planner_goodcat(
                goodcat_slot,
                GoodCatState.CAUTION,
                "有幾個欄位需要主人再確認，修好後咪就能開始計算。",
            )
            for message in errors:
                st.warning(message)
        else:
            try:
                api_base_url = get_api_base_url()
                with loading_state("正在檢查全市場資料並計算整數股數..."):
                    result = fetch_portfolio_projections_with_working_animation(
                        api_base_url,
                        {
                            "target_after_tax_cash_twd": target_cash,
                            "target_months": selected_months,
                            "existing_holdings": holdings,
                            "history_years": DEFAULT_HISTORY_YEARS,
                            "cash_deduction_rate_pct": (
                                DEFAULT_CASH_DEDUCTION_RATE_PCT
                            ),
                            "currency": "TWD",
                            "projection_years": int(projection_years),
                            "custom_reinvestment_pct": (
                                DEFAULT_CUSTOM_REINVESTMENT_PCT
                            ),
                            "dividend_tax_method": (
                                tax_method
                            ),
                            "marginal_income_tax_rate_pct": marginal_tax_rate,
                            "other_income_tax_rate_pct": other_income_tax_rate,
                            "remaining_annual_dividend_credit_cap_twd": (
                                remaining_credit_cap
                            ),
                            "supplementary_premium_exempt": premium_exempt,
                        },
                        goodcat_slot,
                    )
            except (APIClientError, ValueError) as error:
                render_planner_goodcat(
                    goodcat_slot,
                    GoodCatState.CAUTION,
                    "咪暫時無法完成計算，請稍後再試；主人剛才的輸入仍留在畫面上。",
                )
                st.error("暫時無法完成股利試算，請確認服務已啟動後再試一次。")
                st.caption(f"錯誤類型：{type(error).__name__}")
            else:
                st.session_state[RESULT_STATE_KEY] = result
                st.session_state[RESULT_INPUT_SIGNATURE_STATE_KEY] = (
                    current_input_signature
                )
                saved_result = result
                state, message = allocation_goodcat_feedback(result)
                render_planner_goodcat(goodcat_slot, state, message)

    if isinstance(saved_result, dict):
        long_term = saved_result["long_term_scenarios"]
        selected_strategy = render_allocation_results(long_term["allocation_results"])
        with st.expander(
            "查看歷史績效與長期情境",
            icon=":material/query_stats:",
        ):
            render_long_term_evidence(long_term, selected_strategy)
        with st.expander(
            f"查看整體組合 {saved_result['projection_years']} 年稅務與再投入試算",
            icon=":material/timeline:",
        ):
            render_portfolio_projection(
                saved_result,
                selected_strategy,
                st.session_state.get(
                    REINVESTMENT_POLICY_STATE_KEY,
                    "NO_REINVESTMENT",
                ),
            )
        with st.container(key="public-planner-disclaimer"):
            st.caption(
                "不需登入，輸入只用於本次試算；本網站提供之數據僅供個人參考，"
                "不構成任何形式之投資建議、下單指示或金融商品推薦。"
                "過往績效不代表未來表現，需評估風險並自負盈虧。"
            )
