"""M11-1 單一使用者條件與手動持有部位 API client。"""

from typing import Any
from urllib.parse import quote

from frontend.api.errors import APIResponseError
from frontend.api.transport import (
    delete_json,
    get_binary,
    get_json,
    post_json,
    put_json,
)


def _owner_headers(owner_token: str) -> dict[str, str]:
    if not owner_token:
        raise ValueError("Owner token 不可為空白")
    return {"X-Owner-Token": owner_token}


def validate_user_conditions(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise APIResponseError("使用者條件回應必須是 JSON 物件")
    required = {
        "monthly_after_tax_target",
        "analysis_years",
        "history_years",
        "cash_deduction_rate_pct",
        "currency",
        "updated_at",
    }
    if required - payload.keys():
        raise APIResponseError("使用者條件回應缺少必要欄位")
    if payload["currency"] != "TWD":
        raise APIResponseError("使用者條件幣別必須為 NTD")
    return payload


def validate_manual_holding(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise APIResponseError("手動持有部位回應必須是 JSON 物件")
    required = {
        "etf_code",
        "name",
        "is_active",
        "is_bond",
        "held_units",
        "unit_price",
        "price_as_of_date",
        "currency",
        "updated_at",
    }
    if required - payload.keys():
        raise APIResponseError("手動持有部位回應缺少必要欄位")
    if payload["currency"] != "TWD":
        raise APIResponseError("手動持有部位幣別必須為 NTD")
    return payload


def validate_decision_profile(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise APIResponseError("決策條件回應必須是 JSON 物件")
    if payload.get("profile_scope") != "SINGLE_USER":
        raise APIResponseError("決策條件 scope 格式不正確")
    if payload.get("broker_connected") is not False:
        raise APIResponseError("M11-1 不可宣稱已連接券商")
    conditions = payload.get("conditions")
    if conditions is not None:
        validate_user_conditions(conditions)
    holdings = payload.get("holdings")
    if not isinstance(holdings, list):
        raise APIResponseError("決策條件 holdings 格式不正確")
    for item in holdings:
        validate_manual_holding(item)
    return payload


def validate_current_holding_analysis(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise APIResponseError("目前持倉分析回應必須是 JSON 物件")
    if payload.get("profile_scope") != "SINGLE_USER":
        raise APIResponseError("目前持倉分析 scope 格式不正確")
    if payload.get("broker_connected") is not False:
        raise APIResponseError("目前持倉分析不可宣稱已連接券商")
    if payload.get("status") not in {"AVAILABLE", "PARTIAL", "UNAVAILABLE"}:
        raise APIResponseError("目前持倉分析 status 格式不正確")
    required = {
        "analysis_date",
        "currency",
        "conditions",
        "total_current_value",
        "holdings",
        "portfolio_analysis",
        "unavailable_fields",
    }
    if required - payload.keys():
        raise APIResponseError("目前持倉分析回應缺少必要欄位")
    if payload["currency"] != "TWD":
        raise APIResponseError("目前持倉分析幣別必須為 NTD")
    if not isinstance(payload["holdings"], list):
        raise APIResponseError("目前持倉分析 holdings 格式不正確")
    if not isinstance(payload["unavailable_fields"], list):
        raise APIResponseError("目前持倉分析 unavailable_fields 格式不正確")
    return payload


def validate_candidate_holding_analysis(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise APIResponseError("候選持倉分析回應必須是 JSON 物件")
    if payload.get("profile_scope") != "SINGLE_USER":
        raise APIResponseError("候選持倉分析 scope 格式不正確")
    if payload.get("broker_connected") is not False:
        raise APIResponseError("候選持倉分析不可宣稱已連接券商")
    if payload.get("status") not in {"AVAILABLE", "PARTIAL", "UNAVAILABLE"}:
        raise APIResponseError("候選持倉分析 status 格式不正確")
    required = {
        "analysis_date",
        "candidate_etf_code",
        "candidate_name",
        "current_portfolio",
        "proposed_portfolio",
        "comparison",
        "eligibility",
        "explainable_assessment",
        "decision_priority",
        "unavailable_fields",
    }
    if required - payload.keys():
        raise APIResponseError("候選持倉分析回應缺少必要欄位")
    if not isinstance(payload["decision_priority"], list):
        raise APIResponseError("候選持倉分析 decision_priority 格式不正確")
    if not isinstance(payload["unavailable_fields"], list):
        raise APIResponseError("候選持倉分析 unavailable_fields 格式不正確")
    eligibility = payload.get("eligibility")
    if eligibility is not None:
        for field in ("selected_candidates", "rejected_candidates"):
            items = eligibility.get(field) if isinstance(eligibility, dict) else None
            if not isinstance(items, list):
                raise APIResponseError("候選持倉分析缺少候選資格結果")
            if any(
                not isinstance(item, dict)
                or not isinstance(item.get("reasons"), list)
                for item in items
            ):
                raise APIResponseError("候選持倉分析缺少納入或排除理由")
    assessment = payload.get("explainable_assessment")
    if assessment is not None:
        if not isinstance(assessment, dict) or assessment.get("outcome") not in {
            "INSUFFICIENT_DATA",
            "BLOCKED_BY_GATE",
            "NEEDS_REVIEW",
            "GATE_ALIGNED",
        }:
            raise APIResponseError("候選持倉分析可解釋評定格式不正確")
        if not isinstance(assessment.get("factors"), list):
            raise APIResponseError("候選持倉分析可解釋評定缺少因素")
        for field in (
            "etf_quality_score",
            "portfolio_fit_score",
            "quality_components",
            "fit_components",
            "unscored_metrics",
        ):
            if field not in assessment:
                raise APIResponseError("候選持倉分析可解釋評定缺少評分欄位")
        if not isinstance(assessment["quality_components"], list) or not isinstance(
            assessment["fit_components"], list
        ):
            raise APIResponseError("候選持倉分析可解釋評定構成格式不正確")
    return payload


def validate_decision_record_summary(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise APIResponseError("決策紀錄摘要必須是 JSON 物件")
    required = {
        "id",
        "record_type",
        "candidate_etf_code",
        "candidate_name",
        "analysis_status",
        "outcome",
        "created_at",
    }
    if required - payload.keys():
        raise APIResponseError("決策紀錄摘要缺少必要欄位")
    if payload["record_type"] != "CANDIDATE_HOLDING_ANALYSIS":
        raise APIResponseError("決策紀錄類型格式不正確")
    if not isinstance(payload["id"], int) or payload["id"] <= 0:
        raise APIResponseError("決策紀錄 id 格式不正確")
    if payload["analysis_status"] not in {
        "AVAILABLE",
        "PARTIAL",
        "UNAVAILABLE",
    }:
        raise APIResponseError("決策紀錄 analysis_status 格式不正確")
    if payload["outcome"] not in {
        "ELIGIBLE",
        "INELIGIBLE",
        "NOT_EVALUATED",
        "UNAVAILABLE",
    }:
        raise APIResponseError("決策紀錄 outcome 格式不正確")
    return payload


def validate_decision_record(payload: object) -> dict[str, Any]:
    result = validate_decision_record_summary(payload)
    if result.get("profile_scope") != "SINGLE_USER":
        raise APIResponseError("決策紀錄 scope 格式不正確")
    if result.get("broker_connected") is not False:
        raise APIResponseError("決策紀錄不可宣稱已連接券商")
    if result.get("immutable") is not True:
        raise APIResponseError("決策紀錄必須標示為不可變快照")
    required = {
        "request",
        "analysis",
        "rationale",
        "exclusions",
        "alternatives",
        "risk_notes",
    }
    if required - result.keys():
        raise APIResponseError("決策紀錄缺少完整快照欄位")
    validate_candidate_holding_analysis(result["analysis"])
    for field in ("rationale", "exclusions", "alternatives", "risk_notes"):
        if not isinstance(result[field], list):
            raise APIResponseError(f"決策紀錄 {field} 格式不正確")
    return result


def fetch_decision_profile(
    api_base_url: str,
    owner_token: str,
    timeout_seconds: float = 10.0,
) -> dict[str, Any]:
    result = get_json(
        api_base_url=api_base_url,
        endpoint_path="/api/v1/decision-profile",
        operation_name="決策條件查詢",
        timeout_seconds=timeout_seconds,
        request_headers=_owner_headers(owner_token),
    )
    return validate_decision_profile(result)


def fetch_current_holding_analysis(
    api_base_url: str,
    owner_token: str,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    result = get_json(
        api_base_url=api_base_url,
        endpoint_path="/api/v1/decision-profile/current-holding-analysis",
        operation_name="目前持倉分析",
        timeout_seconds=timeout_seconds,
        request_headers=_owner_headers(owner_token),
    )
    return validate_current_holding_analysis(result)


def fetch_candidate_holding_analysis(
    api_base_url: str,
    etf_code: str,
    payload: dict[str, Any],
    owner_token: str,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    normalized_code = etf_code.strip().upper()
    if not normalized_code:
        raise ValueError("ETF 代號不可為空白")
    result = post_json(
        api_base_url=api_base_url,
        endpoint_path=(
            "/api/v1/decision-profile/candidate-analysis/"
            f"{quote(normalized_code, safe='')}"
        ),
        operation_name=f"ETF {normalized_code} 候選持倉分析",
        payload=payload,
        timeout_seconds=timeout_seconds,
        request_headers=_owner_headers(owner_token),
    )
    return validate_candidate_holding_analysis(result)


def save_candidate_decision_record(
    api_base_url: str,
    etf_code: str,
    payload: dict[str, Any],
    owner_token: str,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    normalized_code = etf_code.strip().upper()
    if not normalized_code:
        raise ValueError("ETF 代號不可為空白")
    result = post_json(
        api_base_url=api_base_url,
        endpoint_path=(
            "/api/v1/decision-profile/candidate-analysis/"
            f"{quote(normalized_code, safe='')}/decision-records"
        ),
        operation_name=f"ETF {normalized_code} 決策紀錄儲存",
        payload=payload,
        timeout_seconds=timeout_seconds,
        request_headers=_owner_headers(owner_token),
    )
    return validate_decision_record(result)


def fetch_decision_records(
    api_base_url: str,
    owner_token: str,
    timeout_seconds: float = 10.0,
) -> list[dict[str, Any]]:
    result = get_json(
        api_base_url=api_base_url,
        endpoint_path="/api/v1/decision-profile/decision-records",
        operation_name="決策紀錄列表查詢",
        timeout_seconds=timeout_seconds,
        request_headers=_owner_headers(owner_token),
    )
    if not isinstance(result, list):
        raise APIResponseError("決策紀錄列表必須是 JSON 陣列")
    return [validate_decision_record_summary(item) for item in result]


def fetch_decision_record_export(
    api_base_url: str,
    record_id: int,
    owner_token: str,
    timeout_seconds: float = 30.0,
) -> bytes:
    if record_id <= 0:
        raise ValueError("決策紀錄編號必須大於零")
    return get_binary(
        api_base_url=api_base_url,
        endpoint_path=(
            f"/api/v1/decision-profile/decision-records/{record_id}/export.xlsx"
        ),
        operation_name=f"決策紀錄 {record_id} Excel 匯出",
        timeout_seconds=timeout_seconds,
        request_headers=_owner_headers(owner_token),
    )


def save_user_conditions(
    api_base_url: str,
    payload: dict[str, Any],
    owner_token: str,
    timeout_seconds: float = 10.0,
) -> dict[str, Any]:
    result = put_json(
        api_base_url=api_base_url,
        endpoint_path="/api/v1/decision-profile/conditions",
        operation_name="使用者條件儲存",
        payload=payload,
        timeout_seconds=timeout_seconds,
        request_headers=_owner_headers(owner_token),
    )
    return validate_user_conditions(result)


def save_manual_holding(
    api_base_url: str,
    etf_code: str,
    payload: dict[str, Any],
    owner_token: str,
    timeout_seconds: float = 10.0,
) -> dict[str, Any]:
    normalized_code = etf_code.strip().upper()
    if not normalized_code:
        raise ValueError("ETF 代號不可為空白")
    result = put_json(
        api_base_url=api_base_url,
        endpoint_path=(
            "/api/v1/decision-profile/holdings/"
            f"{quote(normalized_code, safe='')}"
        ),
        operation_name=f"ETF {normalized_code} 持有部位儲存",
        payload=payload,
        timeout_seconds=timeout_seconds,
        request_headers=_owner_headers(owner_token),
    )
    return validate_manual_holding(result)


def save_manual_holdings(
    api_base_url: str,
    holdings: list[dict[str, Any]],
    owner_token: str,
    timeout_seconds: float = 10.0,
) -> list[dict[str, Any]]:
    """以兩欄輸入批次取代持股；價格由後端官方資料解析。"""

    result = put_json(
        api_base_url=api_base_url,
        endpoint_path="/api/v1/decision-profile/holdings",
        operation_name="全部持有部位儲存",
        payload={"holdings": holdings},
        timeout_seconds=timeout_seconds,
        request_headers=_owner_headers(owner_token),
    )
    if not isinstance(result, list):
        raise APIResponseError("持有部位批次回應必須是 JSON 陣列")
    return [validate_manual_holding(item) for item in result]


def delete_manual_holding(
    api_base_url: str,
    etf_code: str,
    owner_token: str,
    timeout_seconds: float = 10.0,
) -> None:
    normalized_code = etf_code.strip().upper()
    if not normalized_code:
        raise ValueError("ETF 代號不可為空白")
    delete_json(
        api_base_url=api_base_url,
        endpoint_path=(
            "/api/v1/decision-profile/holdings/"
            f"{quote(normalized_code, safe='')}"
        ),
        operation_name=f"ETF {normalized_code} 持有部位刪除",
        timeout_seconds=timeout_seconds,
        request_headers=_owner_headers(owner_token),
    )
