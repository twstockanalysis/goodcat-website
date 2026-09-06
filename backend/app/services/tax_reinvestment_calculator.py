"""M10-4 台灣 ETF 稅務與再投資純計算服務。"""

from decimal import Decimal

from backend.app.models.tax_reinvestment import (
    ReinvestmentPolicy,
    ReinvestmentScenarioResult,
    TaxReinvestmentCalculationInput,
    TaxReinvestmentCalculationResult,
    TaxScenarioIssue,
    TaxScenarioUnavailableReason,
)
from backend.app.services.calculation_precision import (
    round_money as _money,
    round_percentage as _percentage,
    round_units as _units,
)

HUNDRED = Decimal("100")


def _issue(
    field: str,
    reason: TaxScenarioUnavailableReason,
    component_code: str | None = None,
) -> TaxScenarioIssue:
    return TaxScenarioIssue(
        field=field,
        reason=reason,
        component_code=component_code,
    )


def _unavailable_scenarios(
    value: TaxReinvestmentCalculationInput,
    issues: list[TaxScenarioIssue],
) -> list[ReinvestmentScenarioResult]:
    return [
        ReinvestmentScenarioResult(
            policy=policy,
            custom_reinvestment_pct=(
                value.custom_reinvestment_pct
                if policy == ReinvestmentPolicy.CUSTOM_PERCENTAGE
                else None
            ),
            usable_cash=None,
            reinvested_cash=None,
            ending_units=None,
            ending_value=None,
            modeled_income_tax=None,
            modeled_supplementary_premium=None,
            modeled_tax_cost=None,
            after_tax_total_gain_loss=None,
            after_tax_total_return_pct=None,
            total_return_check_passed=None,
            issues=list(issues),
        )
        for policy in ReinvestmentPolicy
    ]


def _reinvestment_amount(
    policy: ReinvestmentPolicy,
    after_tax_cash: Decimal,
    annual_cash_target: Decimal,
    custom_pct: Decimal,
) -> Decimal:
    if policy == ReinvestmentPolicy.NO_REINVESTMENT:
        return Decimal("0")
    if policy == ReinvestmentPolicy.EXCESS_ONLY:
        return max(after_tax_cash - annual_cash_target, Decimal("0"))
    if policy == ReinvestmentPolicy.FULL_REINVESTMENT:
        return after_tax_cash
    return after_tax_cash * custom_pct / HUNDRED


def _calculate_scenario(
    value: TaxReinvestmentCalculationInput,
    policy: ReinvestmentPolicy,
) -> ReinvestmentScenarioResult:
    assert value.annual_gross_distribution_rate_pct is not None
    assert value.annual_price_return_pct is not None
    component_mix = (
        value.calculation_component_mix or value.actual_component_mix
    )
    assert component_mix is not None

    assumptions = {
        item.component_code: item
        for item in value.tax_rule.component_assumptions
    }
    units = value.initial_units
    price = value.initial_unit_price
    initial_value = units * price
    cumulative_usable = Decimal("0")
    cumulative_reinvested = Decimal("0")
    cumulative_income_tax = Decimal("0")
    cumulative_premium = Decimal("0")

    for _ in range(value.projection_years):
        start_value = units * price
        gross_cash = (
            start_value
            * value.annual_gross_distribution_rate_pct
            / HUNDRED
        )
        income_tax = Decimal("0")
        tax_credit = Decimal("0")
        premium_base = Decimal("0")

        for component in component_mix:
            assumption = assumptions[component.component_code]
            component_cash = gross_cash * component.ratio_pct / HUNDRED
            income_tax += (
                component_cash
                * assumption.income_tax_rate_pct
                / HUNDRED
            )
            tax_credit += (
                component_cash
                * assumption.tax_credit_rate_pct
                / HUNDRED
            )
            if assumption.supplementary_premium_applicable:
                premium_base += component_cash

        allowed_credit = min(
            tax_credit,
            value.tax_rule.annual_tax_credit_cap,
        )
        income_tax -= allowed_credit
        if not value.tax_rule.allow_credit_offset_other_tax:
            income_tax = max(income_tax, Decimal("0"))

        payment_base = premium_base / Decimal(value.payments_per_year)
        premium = Decimal("0")
        if (
            payment_base
            >= value.tax_rule.supplementary_premium_payment_threshold
        ):
            capped_payment_base = min(
                payment_base,
                value.tax_rule.supplementary_premium_payment_cap,
            )
            premium = (
                capped_payment_base
                * value.tax_rule.supplementary_premium_rate_pct
                / HUNDRED
                * Decimal(value.payments_per_year)
            )

        after_tax_cash = gross_cash - income_tax - premium
        reinvested = _reinvestment_amount(
            policy,
            after_tax_cash,
            value.annual_cash_target,
            value.custom_reinvestment_pct,
        )
        usable = after_tax_cash - reinvested

        price *= Decimal("1") + value.annual_price_return_pct / HUNDRED
        if price > 0 and reinvested > 0:
            units += reinvested / price

        cumulative_usable += usable
        cumulative_reinvested += reinvested
        cumulative_income_tax += income_tax
        cumulative_premium += premium

    ending_value = units * price
    gain_loss = ending_value + cumulative_usable - initial_value
    return_pct = gain_loss / initial_value * HUNDRED

    return ReinvestmentScenarioResult(
        policy=policy,
        custom_reinvestment_pct=(
            value.custom_reinvestment_pct
            if policy == ReinvestmentPolicy.CUSTOM_PERCENTAGE
            else None
        ),
        usable_cash=_money(cumulative_usable),
        reinvested_cash=_money(cumulative_reinvested),
        ending_units=_units(units),
        ending_value=_money(ending_value),
        modeled_income_tax=_money(cumulative_income_tax),
        modeled_supplementary_premium=_money(cumulative_premium),
        modeled_tax_cost=_money(
            cumulative_income_tax + cumulative_premium
        ),
        after_tax_total_gain_loss=_money(gain_loss),
        after_tax_total_return_pct=_percentage(return_pct),
        total_return_check_passed=gain_loss >= 0,
    )


def calculate_tax_reinvestment_scenarios(
    value: TaxReinvestmentCalculationInput,
) -> TaxReinvestmentCalculationResult:
    """比較四種配息使用方式，不產生推薦或稅務結論。"""

    issues: list[TaxScenarioIssue] = []
    if value.annual_gross_distribution_rate_pct is None:
        issues.append(
            _issue(
                "annual_gross_distribution_rate_pct",
                TaxScenarioUnavailableReason.MISSING_INPUT,
            )
        )
    if value.annual_price_return_pct is None:
        issues.append(
            _issue(
                "annual_price_return_pct",
                TaxScenarioUnavailableReason.MISSING_INPUT,
            )
        )
    component_mix = (
        value.calculation_component_mix or value.actual_component_mix
    )
    if component_mix is None:
        issues.append(
            _issue(
                "actual_component_mix",
                TaxScenarioUnavailableReason.MISSING_ACTUAL_COMPONENTS,
            )
        )

    if component_mix is not None:
        assumption_codes = {
            item.component_code
            for item in value.tax_rule.component_assumptions
        }
        for component in component_mix:
            if (
                component.ratio_pct > 0
                and component.component_code not in assumption_codes
            ):
                issues.append(
                    _issue(
                        "tax_rule.component_assumptions",
                        TaxScenarioUnavailableReason
                        .MISSING_COMPONENT_TAX_ASSUMPTION,
                        component.component_code,
                    )
                )

    initial_value = value.initial_units * value.initial_unit_price
    if initial_value <= 0:
        issues.append(
            _issue(
                "initial_units",
                TaxScenarioUnavailableReason.NON_POSITIVE_INITIAL_VALUE,
            )
        )

    scenarios = (
        _unavailable_scenarios(value, issues)
        if issues
        else [
            _calculate_scenario(value, policy)
            for policy in ReinvestmentPolicy
        ]
    )

    return TaxReinvestmentCalculationResult(
        currency=value.currency,
        projection_years=value.projection_years,
        rule_version=value.tax_rule.rule_version,
        rule_effective_date=value.tax_rule.effective_date,
        historical_component_basis=(
            value.component_calculation_basis.value
            if value.component_calculation_basis is not None
            else ("ACTUAL" if value.actual_component_mix is not None else None)
        ),
        scenarios=scenarios,
        issues=issues,
    )
