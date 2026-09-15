"""Streamlit 前端使用的 FastAPI Client。"""

import httpx

from frontend.api.budget_planner import fetch_budget_results, validate_budget_results

from frontend.api.errors import (
    APIClientError,
    APIConnectionError,
    APIResourceNotFoundError,
    APIResponseError,
)
from frontend.api.comparison import (
    fetch_etf_comparison,
    validate_etf_comparison,
)
from frontend.api.etfs import (
    fetch_etf_by_code,
    fetch_etfs,
    validate_etf_item,
)
from frontend.api.health import fetch_api_health
from frontend.api.monthly_combination import (
    fetch_monthly_payment_combination,
    validate_monthly_combination_result,
)
from frontend.api.normalizers import (
    COMPARISON_PERIODS,
    SUPPORTED_DIVIDEND_COMPONENT_BASES,
    SUPPORTED_DIVIDEND_REVIEW_ISSUE_TYPES,
    SUPPORTED_DIVIDEND_REVIEW_STATUSES,
    SUPPORTED_PERFORMANCE_METRICS,
    SUPPORTED_PERFORMANCE_PERIODS,
    normalize_component_basis,
    normalize_dividend_review_issue_type,
    normalize_dividend_review_status,
    normalize_etf_comparison_codes,
    normalize_performance_metric,
    normalize_performance_period,
)
from frontend.api.data_profile import (
    fetch_etf_data_profile,
    validate_etf_data_profile,
    validate_etf_data_profile_sources,
)
from frontend.api.decision_profile import (
    delete_manual_holding,
    fetch_candidate_holding_analysis,
    fetch_current_holding_analysis,
    fetch_decision_profile,
    fetch_decision_record_export,
    fetch_decision_records,
    save_candidate_decision_record,
    save_manual_holding,
    save_manual_holdings,
    save_user_conditions,
    validate_decision_profile,
    validate_current_holding_analysis,
    validate_candidate_holding_analysis,
    validate_decision_record,
    validate_decision_record_summary,
    validate_manual_holding,
    validate_user_conditions,
)
from frontend.api.dividend_quality import (
    fetch_actual_dividend_coverage,
    fetch_dividend_review_queue,
    fetch_dividend_review_queue_item,
    fetch_etf_actual_76w,
    validate_actual_76w_item,
    validate_actual_dividend_coverage,
    validate_dividend_review_queue_item,
)
from frontend.api.dividends import (
    SUPPORTED_DIVIDEND_YIELD_BASES,
    fetch_dividend_components,
    fetch_dividend_detail,
    fetch_etf_dividends,
    fetch_etf_monthly_income,
    validate_dividend_component_item,
    validate_dividend_event_item,
    validate_monthly_income_distribution,
    validate_monthly_income_month_item,
)
from frontend.api.performance import (
    fetch_etf_performance,
    fetch_multi_period_performance_ranking,
    fetch_performance_ranking,
    validate_etf_performance_item,
    validate_multi_period_ranking_item,
    validate_performance_ranking_item,
    validate_return_pct,
)
from frontend.api.public_planner import (
    fetch_allocation_results,
    fetch_long_term_scenarios,
    fetch_portfolio_projections,
    fetch_public_planner_baseline,
    validate_allocation_results,
    validate_long_term_scenarios,
    validate_portfolio_projections,
    validate_public_planner_result,
)
from frontend.api.quality_grades import (
    fetch_historical_quality_grades,
    quality_grade_lookup,
    validate_historical_quality_grade,
    validate_quality_grade_response,
)
from frontend.api.system_overview import (
    SYSTEM_OVERVIEW_BATCH_STATUSES,
    SYSTEM_OVERVIEW_PERIODS,
    fetch_system_overview,
    validate_overview_coverage_pct,
    validate_system_overview,
    validate_system_overview_batch,
    validate_system_overview_dividends,
    validate_system_overview_etfs,
    validate_system_overview_performance,
)
from frontend.api.transport import (
    delete_json,
    extract_response_detail,
    get_binary,
    get_json,
    post_json,
    put_json,
)
from frontend.api.tax_reinvestment import (
    fetch_tax_reinvestment_scenarios,
    validate_tax_reinvestment_result,
)
from frontend.api.target_analysis import (
    fetch_etf_latest_close,
    fetch_etf_price_history,
    fetch_etf_target_analysis,
    validate_latest_close,
    validate_price_history,
    validate_target_analysis_result,
)

from frontend.api.validators import (
    validate_non_negative_integer,
    validate_optional_dividend_period,
    validate_optional_iso_date,
    validate_optional_iso_datetime,
    validate_optional_number,
    validate_performance_date,
    validate_positive_integer,
    validate_required_iso_datetime,
    validate_required_text,
)
