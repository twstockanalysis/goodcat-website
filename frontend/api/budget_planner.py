"""Target-free budget response boundary; no backend imports or scoring."""

from decimal import Decimal, DecimalException, ROUND_HALF_UP, localcontext
from typing import Any

from frontend.api.errors import APIResponseError
from frontend.api.transport import post_json


OBJECTIVES = ("MINIMUM_THEN_TOTAL_MONTH_CASH", "MONTHLY_BALANCED", "TOTAL_MONTH_CASH")


def _require(condition):
    if not condition:
        raise APIResponseError("預算配置回應格式或金額核對不正確")


def _amount(value, *, nullable=False):
    if value is None and nullable:
        return None
    _require(not isinstance(value, bool) and isinstance(value, (str, int, float, Decimal)))
    number = Decimal(str(value))
    _require(number.is_finite() and number >= 0)
    return number


def _public_keys(value):
    # Inspect keys, not explanatory prose mentioning unavailable grades.
    if isinstance(value, dict):
        forbidden = {"quality_score", "etf_quality_score", "confidence", "assessment_confidence"}
        _require(not forbidden.intersection(value))
        for child in value.values():
            _public_keys(child)
    elif isinstance(value, list):
        for child in value:
            _public_keys(child)


def _plan(plan):
    _require(isinstance(plan, dict))
    _require(plan.get("profile_scope") == "PUBLIC_STATELESS"
             and plan.get("request_persisted") is False and plan.get("broker_connected") is False)
    _require(plan.get("methodology") == "BOUNDED_BUDGET_PORTFOLIO_V5_4"
             and plan.get("currency") == "TWD")
    _require(plan.get("status") in ("AVAILABLE", "NO_ADDITIONS", "NO_ELIGIBLE_ALLOCATION", "UNAVAILABLE"))
    _require(not {"target_months", "target_after_tax_cash_twd", "target_attainment"}.intersection(plan))
    months = plan.get("selected_months")
    _require(isinstance(months, list) and 1 <= len(months) <= 12)
    _require(all(type(m) is int and 1 <= m <= 12 for m in months))
    _require(months == sorted(set(months)))
    budget, used, remaining = (_amount(plan.get(k)) for k in
                               ("investable_budget_twd", "used_budget_twd", "remaining_budget_twd"))
    _require(used <= budget and used + remaining == budget)
    additions = plan.get("additions")
    _require(isinstance(additions, list) and len(additions) <= 5)
    codes, costs, exact_costs = [], Decimal(0), Decimal(0)
    for addition in additions:
        _require(isinstance(addition, dict))
        code, shares = addition.get("etf_code"), addition.get("additional_shares")
        _require(isinstance(code, str) and bool(code.strip()) and type(shares) is int and shares > 0)
        _require(code not in codes)
        codes.append(code)
        price, cost = _amount(addition.get("reference_price")), _amount(addition.get("required_capital"))
        _require(price > 0)
        exact = price * shares
        _require(exact.quantize(Decimal(".01"), rounding=ROUND_HALF_UP) == cost)
        costs += cost
        exact_costs += exact
    _require(costs == used and exact_costs <= budget)
    rows = plan.get("monthly_results")
    _require(isinstance(rows, list) and len(rows) == len(months))
    for month, row in zip(months, rows, strict=True):
        _require(isinstance(row, dict) and type(row.get("month")) is int and row["month"] == month)
        _require(not {"shortfall", "target_after_tax_cash", "target_met"}.intersection(row))
        for field in ("current_after_tax_cash", "added_after_tax_cash", "modeled_after_tax_cash"):
            _require(field in row)
            _amount(row[field], nullable=field != "added_after_tax_cash")
    _require(isinstance(plan.get("existing_holdings"), list))
    _require("resulting_holdings" in plan and (plan["resulting_holdings"] is None
                                             or isinstance(plan["resulting_holdings"], list)))
    _require(isinstance(plan.get("candidate_evidence"), list) and isinstance(plan.get("issues"), list))
    return budget, months


def validate_budget_results(payload: object) -> dict[str, Any]:
    """Validate the client consumption boundary and return the original object."""
    try:
        with localcontext() as context:
            context.prec = 64
            _require(isinstance(payload, dict))
            _public_keys(payload)
            primary = payload.get("primary")
            basis = _plan(primary)
            _require(primary.get("objective") == OBJECTIVES[0])
            alternatives = payload.get("alternatives")
            _require(isinstance(alternatives, list) and len(alternatives) <= 2)
            previous = 0
            for alternative in alternatives:
                _require(_plan(alternative) == basis)
                objective = alternative.get("objective")
                _require(objective in OBJECTIVES[1:])
                position = OBJECTIVES.index(objective)
                _require(position > previous)
                previous = position
                for field in ("snapshot_id", "analysis_date", "existing_holdings"):
                    _require(field in primary and alternative.get(field) == primary[field])
                _require(isinstance(alternative.get("tradeoff"), str))
            _require(isinstance(payload.get("issues"), list))
            _require(isinstance(payload.get("alternate_searches"), list))
            if "plan_metrics" in payload:
                _require(isinstance(payload["plan_metrics"], list))
            return payload
    except (DecimalException, ValueError, TypeError, RecursionError) as exc:
        raise APIResponseError("預算配置回應格式或金額核對不正確") from exc


def fetch_budget_results(api_base_url: str, payload: dict[str, Any],
                         timeout_seconds: float = 60.0) -> dict[str, Any]:
    result = post_json(api_base_url=api_base_url,
                       endpoint_path="/api/v1/allocation-plans/budget-results",
                       operation_name="預算配置試算", payload=payload,
                       timeout_seconds=timeout_seconds)
    return validate_budget_results(result)
