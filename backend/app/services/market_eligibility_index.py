"""V3-2 全市場候選資格與內部確定性評分索引。"""

from __future__ import annotations

from backend.app.exceptions import ETFNotFoundError

from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
from pathlib import Path

from backend.app.models.decision_profile import (
    ExplainableAssessmentScoreComponent,
)
from backend.app.models.market_eligibility import (
    MarketEligibilityConstraint,
    MarketEligibilityIndexRequest,
    MarketEligibilityIndexResponse,
    MarketEligibilityItem,
    MarketEligibilityReason,
    MarketEligibilityReasonKind,
    MarketEligibilityRules,
)
from backend.app.models.monthly_combination import (
    CandidateReasonKind,
    MonthlyCombinationCandidateAssumption,
    MonthlyCombinationEligibilityRules,
)
from backend.app.repositories.daily_close_repository import get_latest_daily_close
from backend.app.repositories.dividend_repository import (
    build_actual_76w_summary,
    list_etf_component_history,
)
from backend.app.repositories.etf_repository import get_etf_by_code, list_etfs
from backend.app.repositories.monthly_income_repository import (
    build_monthly_income_distribution,
)
from backend.app.repositories.performance_repository import (
    list_latest_etf_performance,
)
from backend.app.services.constituent_overlap import (
    calculate_gated_portfolio_overlap,
)
from backend.app.services.etf_product_scope import (
    unsupported_allocation_product_reason,
)
from backend.app.services.explainable_assessment import (
    calculate_etf_quality_score,
)
from backend.app.services.monthly_combination_calculator import (
    evaluate_candidate_eligibility,
)
from backend.app.services.monthly_combination_data import build_candidate_input
from backend.app.services.quality_grading import (
    build_historical_quality_grade,
    build_unrated_quality_grade,
    evaluate_quality_grade_publication_readiness,
)
from backend.app.services.dividend_component_data import (
    select_composite_component_mix,
)
from backend.app.services.target_analysis_data import is_dividend_data_stale


_MONEY_QUANTUM = Decimal("0.000001")


@dataclass(frozen=True, slots=True)
class InternalMarketCandidate:
    """不得直接序列化到公開 API 的 V3-3 求解輸入。"""

    public_item: MarketEligibilityItem
    quality_score: Decimal | None
    quality_grade_eligible: bool
    quality_components: tuple[ExplainableAssessmentScoreComponent, ...]
    quality_missing: tuple[str, ...]
    monthly_after_tax_cash_per_share: tuple[Decimal, ...]


@dataclass(frozen=True, slots=True)
class BuiltMarketEligibilityIndex:
    response: MarketEligibilityIndexResponse
    ranked_eligible_candidates: tuple[InternalMarketCandidate, ...]
    internal_candidates: tuple[InternalMarketCandidate, ...]


def _date(value: object) -> date | None:
    if isinstance(value, date):
        return value
    if value:
        try:
            return date.fromisoformat(str(value))
        except ValueError:
            return None
    return None


def _reason(
    kind: MarketEligibilityReasonKind,
    code: str,
    message: str,
) -> MarketEligibilityReason:
    return MarketEligibilityReason(kind=kind, code=code, message=message)


def _candidate_rules(
    rules: MarketEligibilityRules,
    *,
    require_holding_overlap: bool,
) -> MonthlyCombinationEligibilityRules:
    return MonthlyCombinationEligibilityRules(
        min_completeness_pct=rules.min_completeness_pct,
        min_distribution_stability_pct=rules.min_distribution_stability_pct,
        min_after_tax_total_return_pct=rules.min_after_tax_total_return_pct,
        min_downside_return_pct=rules.min_downside_return_pct,
        max_holding_overlap_pct=rules.max_holding_overlap_pct,
        max_candidate_allocation_pct=rules.max_candidate_allocation_pct,
        require_holding_overlap=require_holding_overlap,
    )


def _public_candidate_reasons(reasons) -> list[MarketEligibilityReason]:
    return [
        _reason(
            (
                MarketEligibilityReasonKind.EXCLUDE
                if item.kind == CandidateReasonKind.EXCLUDE
                else MarketEligibilityReasonKind.TRADEOFF
            ),
            item.code.value,
            item.message,
        )
        for item in reasons
    ]


def _monthly_after_tax_per_share(
    monthly_income: dict | None,
    *,
    history_years: int,
    deduction_rate_pct: Decimal,
) -> tuple[Decimal, ...]:
    available = bool(
        monthly_income
        and monthly_income.get("analysis_event_count", 0) > 0
        and monthly_income.get("analysis_currency") == "TWD"
        and not monthly_income.get("has_mixed_currencies", False)
        and monthly_income.get("missing_payment_date_count", 0) == 0
    )
    if not available:
        return ()
    factor = Decimal("1") - deduction_rate_pct / Decimal("100")
    return tuple(
        (
            Decimal(str(item.get("total_amount_per_unit") or 0))
            / Decimal(history_years)
            * factor
        ).quantize(_MONEY_QUANTUM, rounding=ROUND_HALF_UP)
        for item in monthly_income["months"]
    )


def _snapshot_id(
    request: MarketEligibilityIndexRequest,
    rules: MarketEligibilityRules,
    analysis_date: date,
    items: list[MarketEligibilityItem],
) -> str:
    canonical = json.dumps(
        {
            "analysis_date": analysis_date.isoformat(),
            "target_months": request.target_months,
            "history_years": request.history_years,
            "cash_deduction_rate_pct": str(request.cash_deduction_rate_pct),
            "existing_holdings": [
                holding.model_dump(mode="json")
                for holding in request.existing_holdings
            ],
            "rules": rules.model_dump(mode="json"),
            "items": [item.model_dump(mode="json") for item in items],
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def build_market_eligibility_index(
    request: MarketEligibilityIndexRequest,
    database_path: str | Path,
    *,
    as_of_date: date | None = None,
) -> BuiltMarketEligibilityIndex:
    """建立全 ETF 主檔索引；公開投影不含內部品質分數。"""

    analysis_date = as_of_date or date.today()
    existing_codes = {holding.etf_code for holding in request.existing_holdings}
    current_holdings = []
    for holding in request.existing_holdings:
        if get_etf_by_code(holding.etf_code, database_path) is None:
            raise ETFNotFoundError(holding.etf_code)
        close = get_latest_daily_close(holding.etf_code, database_path)
        current_holdings.append(
            {
                "etf_code": holding.etf_code,
                "held_units": holding.held_units,
                "unit_price": close["close_price"] if close else None,
            }
        )

    public_rules = MarketEligibilityRules()
    rules = _candidate_rules(
        public_rules,
        require_holding_overlap=bool(request.existing_holdings),
    )
    public_items: list[MarketEligibilityItem] = []
    internal_items: list[InternalMarketCandidate] = []
    for etf in list_etfs(database_path, limit=10000):
        code = str(etf["code"])
        name = str(etf["name"])
        product_reason = unsupported_allocation_product_reason(
            code,
            name,
            bool(etf["is_bond"]),
        )
        if product_reason is not None:
            public_items.append(
                MarketEligibilityItem(
                    etf_code=code,
                    name=name,
                    is_active=bool(etf["is_active"]),
                    is_bond=bool(etf["is_bond"]),
                    existing_holding=code in existing_codes,
                    supported_product=False,
                    eligible_for_addition=False,
                    historical_quality_grade=build_unrated_quality_grade(
                        history_years=request.history_years,
                        reason="此產品類型尚未納入一般股票型 ETF 評等範圍。",
                    ),
                    holding_overlap_status=(
                        "UNAVAILABLE" if current_holdings else "NOT_APPLICABLE"
                    ),
                    reasons=[
                        _reason(
                            MarketEligibilityReasonKind.EXCLUDE,
                            product_reason,
                            "此產品類型尚未納入一般股票型 ETF 配置規則。",
                        )
                    ],
                )
            )
            continue

        close = get_latest_daily_close(code, database_path)
        close_date = _date(close.get("trade_date")) if close else None
        reference_price = close["close_price"] if close else None
        extra_reasons: list[MarketEligibilityReason] = []
        if reference_price is None or close_date is None:
            extra_reasons.append(
                _reason(
                    MarketEligibilityReasonKind.EXCLUDE,
                    "MISSING_REFERENCE_PRICE",
                    "缺少可用的官方參考收盤價。",
                )
            )
        elif close_date > analysis_date:
            extra_reasons.append(
                _reason(
                    MarketEligibilityReasonKind.EXCLUDE,
                    "FUTURE_REFERENCE_PRICE",
                    "官方參考收盤價日期晚於分析日期。",
                )
            )
        elif (
            analysis_date - close_date
        ).days > public_rules.max_reference_price_age_days:
            extra_reasons.append(
                _reason(
                    MarketEligibilityReasonKind.EXCLUDE,
                    "STALE_REFERENCE_PRICE",
                    "官方參考收盤價已超過新鮮度門檻。",
                )
            )

        monthly = build_monthly_income_distribution(
            code,
            database_path,
            request.history_years,
            analysis_date=analysis_date,
        )
        performance = list_latest_etf_performance(code, database_path)
        performance_dates = [
            parsed
            for row in performance
            if row.get("metric_code") == "PRICE_RETURN"
            and (parsed := _date(row.get("as_of_date"))) is not None
        ]
        latest_payment_date = _date(monthly.get("as_of_date")) if monthly else None
        has_future_market_fact = False
        if any(item > analysis_date for item in performance_dates):
            has_future_market_fact = True
            extra_reasons.append(
                _reason(
                    MarketEligibilityReasonKind.EXCLUDE,
                    "FUTURE_PERFORMANCE_DATA",
                    "價格報酬資料日期晚於分析日期。",
                )
            )
        if latest_payment_date is not None and latest_payment_date > analysis_date:
            has_future_market_fact = True
            extra_reasons.append(
                _reason(
                    MarketEligibilityReasonKind.EXCLUDE,
                    "FUTURE_DIVIDEND_DATA",
                    "配息付款日期晚於分析日期。",
                )
            )
        if current_holdings:
            overlap = calculate_gated_portfolio_overlap(
                current_holdings,
                code,
                database_path,
                evaluated_on=analysis_date,
            )
            overlap_pct = overlap.overlap_pct
            overlap_status = "AVAILABLE" if overlap_pct is not None else "UNAVAILABLE"
            snapshot_dates = list(overlap.snapshot_dates)
        else:
            overlap_pct = Decimal("0")
            overlap_status = "NOT_APPLICABLE"
            snapshot_dates = []

        assumption = MonthlyCombinationCandidateAssumption(
            etf_code=code,
            unit_price=reference_price or Decimal("1"),
            proposed_allocation_pct=Decimal("1"),
        )
        candidate = build_candidate_input(
            etf=etf,
            assumption=assumption,
            monthly_income=monthly,
            performance_rows=performance,
            lookback_years=request.history_years,
            cash_deduction_rate_pct=request.cash_deduction_rate_pct,
            rules=rules,
            as_of_date=analysis_date,
            automatic_holding_overlap_pct=overlap_pct,
        )
        if reference_price is None:
            candidate = candidate.model_copy(
                update={
                    "annual_after_tax_cash_rate_pct": None,
                    "estimated_after_tax_total_return_pct": None,
                }
            )
        if has_future_market_fact:
            candidate = candidate.model_copy(update={"data_is_fresh": False})
        eligibility_reasons = evaluate_candidate_eligibility(
            candidate,
            rules,
            evaluate_allocation_concentration=False,
        )
        public_reasons = _public_candidate_reasons(eligibility_reasons)
        if code in existing_codes:
            # Adding an existing position is not introducing a redundant ETF.
            # Keep measured overlap (or missing evidence) visible, but do not
            # let self-overlap prohibit topping up an otherwise eligible ETF.
            public_reasons = [
                reason.model_copy(update={
                    "kind": MarketEligibilityReasonKind.TRADEOFF,
                    "message": reason.message + " 此標的是既有持股，重疊僅作風險提示，不單獨禁止增持。",
                })
                if reason.code in {
                    "EXCESSIVE_HOLDING_OVERLAP", "HOLDING_OVERLAP_UNAVAILABLE"
                }
                else reason
                for reason in public_reasons
            ]

        component_selection = select_composite_component_mix(
            list_etf_component_history(code, database_path),
            analysis_date=analysis_date,
        )
        component_basis = component_selection.basis if component_selection else None
        if component_selection is None:
            extra_reasons.append(
                _reason(
                    MarketEligibilityReasonKind.EXCLUDE,
                    "MISSING_COMPLETE_DIVIDEND_COMPONENTS",
                    "缺少比例完整的正式或估算配息組成。",
                )
            )
        elif component_basis == "ESTIMATED_FALLBACK":
            extra_reasons.append(
                _reason(
                    MarketEligibilityReasonKind.TRADEOFF,
                    "ESTIMATED_COMPONENTS_ONLY",
                    "目前僅有比例完整的估算配息組成，尚無完整正式組成。",
                )
            )
        if component_selection is not None:
            component_date = component_selection.source_date
            if component_date is None:
                extra_reasons.append(
                    _reason(
                        MarketEligibilityReasonKind.EXCLUDE,
                        "MISSING_DIVIDEND_COMPONENT_DATE",
                        "配息組成缺少可追溯的事件日期。",
                    )
                )
            elif component_date > analysis_date:
                extra_reasons.append(
                    _reason(
                        MarketEligibilityReasonKind.EXCLUDE,
                        "FUTURE_DIVIDEND_COMPONENTS",
                        "配息組成事件日期晚於分析日期。",
                    )
                )
            elif is_dividend_data_stale(component_date, analysis_date):
                extra_reasons.append(
                    _reason(
                        MarketEligibilityReasonKind.EXCLUDE,
                        "STALE_DIVIDEND_COMPONENTS",
                        "最新完整配息組成已超過新鮮度門檻。",
                    )
                )

        all_reasons = [*public_reasons, *extra_reasons]
        all_reasons = list(
            {(item.kind, item.code, item.message): item for item in all_reasons}.values()
        )
        eligible = not any(
            item.kind == MarketEligibilityReasonKind.EXCLUDE for item in all_reasons
        )
        actual_76w = build_actual_76w_summary(
            code,
            database_path,
            analysis_date=analysis_date,
        )
        performance_as_of = {
            str(row["period_code"]): _date(row.get("as_of_date"))
            for row in performance
            if row.get("metric_code") == "PRICE_RETURN"
        }
        actual_76w_date = None
        if actual_76w["items"]:
            latest_76w = actual_76w["items"][0]
            actual_76w_date = next(
                (
                    parsed
                    for field in (
                        "payment_date",
                        "ex_dividend_date",
                        "record_date",
                        "announcement_date",
                    )
                    if (parsed := _date(latest_76w.get(field))) is not None
                ),
                None,
            )
        scored_actual_76w = (
            actual_76w
            if actual_76w_date is not None
            and actual_76w_date <= analysis_date
            and not is_dividend_data_stale(actual_76w_date, analysis_date)
            else None
        )
        quality_score, quality_components, quality_missing = (
            calculate_etf_quality_score(
                candidate,
                scored_actual_76w,
            )
        )
        quality_grade = build_historical_quality_grade(
            score=quality_score,
            components=quality_components,
            missing_metrics=quality_missing,
            history_years=request.history_years,
            blocking_reason_codes=(reason.code for reason in all_reasons),
        )
        item = MarketEligibilityItem(
            etf_code=code,
            name=name,
            is_active=bool(etf["is_active"]),
            is_bond=bool(etf["is_bond"]),
            existing_holding=code in existing_codes,
            supported_product=True,
            eligible_for_addition=eligible,
            historical_quality_grade=quality_grade,
            reference_price=reference_price,
            reference_price_as_of=close_date,
            reference_price_source_id=(str(close["source_id"]) if close else None),
            performance_as_of=performance_as_of,
            latest_payment_date=latest_payment_date,
            stable_payment_months=candidate.stable_payment_months,
            completeness_pct=candidate.completeness_pct,
            data_is_fresh=candidate.data_is_fresh,
            distribution_stability_pct=candidate.distribution_stability_pct,
            annual_after_tax_cash_rate_pct=candidate.annual_after_tax_cash_rate_pct,
            estimated_after_tax_total_return_pct=(
                candidate.estimated_after_tax_total_return_pct
            ),
            downside_return_pct=candidate.downside_return_pct,
            component_basis=component_basis,
            component_source_date=(
                component_selection.source_date if component_selection else None
            ),
            actual_76w_available=(actual_76w["actual_76w_record_count"] > 0),
            holding_overlap_status=overlap_status,
            holding_overlap_pct=overlap_pct,
            constituent_snapshot_dates=snapshot_dates,
            reasons=all_reasons,
        )
        public_items.append(item)
        internal_items.append(
            InternalMarketCandidate(
                public_item=item,
                quality_score=quality_score,
                quality_grade_eligible=(quality_grade.status == "RATED"),
                quality_components=tuple(quality_components),
                quality_missing=tuple(quality_missing),
                monthly_after_tax_cash_per_share=_monthly_after_tax_per_share(
                    monthly,
                    history_years=request.history_years,
                    deduction_rate_pct=request.cash_deduction_rate_pct,
                ),
            )
        )

    supported_product_count = sum(item.supported_product for item in public_items)
    grade_readiness = evaluate_quality_grade_publication_readiness(
        scores=(
            item.quality_score if item.quality_grade_eligible else None
            for item in internal_items
        ),
        supported_product_count=supported_product_count,
        total_return_component_scores=(
            component.score
            for item in internal_items
            for component in item.quality_components
            if component.code == "AFTER_TAX_TOTAL_RETURN"
        ),
    )
    if not grade_readiness.ready:
        public_items = [
            item.model_copy(
                update={
                    "historical_quality_grade": build_unrated_quality_grade(
                        history_years=request.history_years,
                        reason="；".join(grade_readiness.reasons),
                    )
                }
            )
            if item.historical_quality_grade.status == "RATED"
            else item
            for item in public_items
        ]
        items_by_code = {item.etf_code: item for item in public_items}
        internal_items = [
            replace(item, public_item=items_by_code[item.public_item.etf_code])
            for item in internal_items
        ]

    public_items.sort(key=lambda item: item.etf_code)
    ranked = tuple(
        sorted(
            (
                item
                for item in internal_items
                if item.public_item.eligible_for_addition
            ),
            key=lambda item: (
                -(item.quality_score or Decimal("0")),
                item.public_item.etf_code,
            ),
        )
    )
    response = MarketEligibilityIndexResponse(
        analysis_date=analysis_date,
        snapshot_id=_snapshot_id(request, public_rules, analysis_date, public_items),
        target_months=request.target_months,
        history_years=request.history_years,
        cash_deduction_rate_pct=request.cash_deduction_rate_pct,
        rules=public_rules,
        universe_count=len(public_items),
        supported_product_count=supported_product_count,
        eligible_count=sum(item.eligible_for_addition for item in public_items),
        excluded_count=sum(not item.eligible_for_addition for item in public_items),
        actual_component_count=sum(
            item.component_basis == "ACTUAL" for item in public_items
        ),
        estimated_component_fallback_count=sum(
            item.component_basis == "ESTIMATED_FALLBACK" for item in public_items
        ),
        allocation_constraints=[
            MarketEligibilityConstraint(
                value=public_rules.max_candidate_allocation_pct
            )
        ],
        candidates=public_items,
    )
    return BuiltMarketEligibilityIndex(
        response=response,
        ranked_eligible_candidates=ranked,
        internal_candidates=tuple(internal_items),
    )
