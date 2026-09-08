"""台灣 ETF 稅務與再投資情境的純計算契約。"""

from datetime import date
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TaxReinvestmentBaseModel(BaseModel):
    """M10-4 計算契約共同設定。"""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )


class ReinvestmentPolicy(StrEnum):
    """配息使用方式。"""

    NO_REINVESTMENT = "NO_REINVESTMENT"
    EXCESS_ONLY = "EXCESS_ONLY"
    CUSTOM_PERCENTAGE = "CUSTOM_PERCENTAGE"
    FULL_REINVESTMENT = "FULL_REINVESTMENT"


class TaxScenarioUnavailableReason(StrEnum):
    """稅務情境無法計算的穩定原因。"""

    MISSING_INPUT = "MISSING_INPUT"
    MISSING_ACTUAL_COMPONENTS = "MISSING_ACTUAL_COMPONENTS"
    MISSING_COMPONENT_TAX_ASSUMPTION = (
        "MISSING_COMPONENT_TAX_ASSUMPTION"
    )
    NON_POSITIVE_INITIAL_VALUE = "NON_POSITIVE_INITIAL_VALUE"


class ComponentCalculationBasis(StrEnum):
    """稅務情境所使用的組成資料層級。"""

    ACTUAL = "ACTUAL"
    ESTIMATED_FALLBACK = "ESTIMATED_FALLBACK"


class OfficialComponentAllocation(TaxReinvestmentBaseModel):
    """歷史配息組成；來源層級由外層欄位說明。"""

    component_code: str = Field(
        min_length=1,
        max_length=40,
        pattern=r"^[A-Z0-9_]+$",
    )
    component_name: str | None = None
    ratio_pct: Decimal = Field(
        ge=0,
        le=100,
        max_digits=12,
        decimal_places=6,
    )


class ComponentTaxAssumption(TaxReinvestmentBaseModel):
    """單一正式所得代碼的使用者稅務假設。"""

    component_code: str = Field(
        min_length=1,
        max_length=40,
        pattern=r"^[A-Z0-9_]+$",
    )
    income_tax_rate_pct: Decimal = Field(
        ge=0,
        le=100,
        max_digits=9,
        decimal_places=6,
    )
    tax_credit_rate_pct: Decimal = Field(
        default=Decimal("0"),
        ge=0,
        le=100,
        max_digits=9,
        decimal_places=6,
    )
    supplementary_premium_applicable: bool = False


class TaiwanIndividualTaxRule(TaxReinvestmentBaseModel):
    """可追溯、可由使用者覆寫的台灣個人稅務規則。"""

    rule_version: str = Field(min_length=1, max_length=80)
    effective_date: date
    supplementary_premium_rate_pct: Decimal = Field(
        default=Decimal("2.11"),
        ge=0,
        le=100,
        max_digits=9,
        decimal_places=6,
    )
    supplementary_premium_payment_threshold: Decimal = Field(
        default=Decimal("20000"),
        ge=0,
        max_digits=24,
        decimal_places=6,
    )
    supplementary_premium_payment_cap: Decimal = Field(
        default=Decimal("10000000"),
        ge=0,
        max_digits=24,
        decimal_places=6,
    )
    annual_tax_credit_cap: Decimal = Field(
        default=Decimal("80000"),
        ge=0,
        max_digits=24,
        decimal_places=6,
    )
    allow_credit_offset_other_tax: bool = False
    component_assumptions: list[ComponentTaxAssumption]

    @model_validator(mode="after")
    def validate_component_codes(self):
        """同一所得代碼只能有一組稅務假設。"""

        codes = [
            item.component_code
            for item in self.component_assumptions
        ]
        if len(codes) != len(set(codes)):
            raise ValueError("所得代碼稅務假設不可重複")
        return self


class TaxReinvestmentCalculationInput(TaxReinvestmentBaseModel):
    """稅務與再投資比較的完整明示輸入。"""

    currency: str = Field(
        default="TWD",
        min_length=3,
        max_length=3,
        pattern=r"^[A-Z]{3}$",
    )
    initial_units: Decimal = Field(
        ge=0,
        max_digits=24,
        decimal_places=6,
    )
    initial_unit_price: Decimal = Field(
        gt=0,
        max_digits=24,
        decimal_places=6,
    )
    annual_gross_distribution_rate_pct: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=12,
        decimal_places=6,
    )
    annual_price_return_pct: Decimal | None = Field(
        default=None,
        ge=-100,
        max_digits=12,
        decimal_places=6,
    )
    projection_years: int = Field(ge=1, le=50)
    annual_cash_target: Decimal = Field(
        ge=0,
        max_digits=24,
        decimal_places=6,
    )
    payments_per_year: int = Field(ge=1, le=365)
    actual_component_mix: list[OfficialComponentAllocation] | None = None
    calculation_component_mix: (
        list[OfficialComponentAllocation] | None
    ) = None
    component_calculation_basis: ComponentCalculationBasis | None = None
    tax_rule: TaiwanIndividualTaxRule
    custom_reinvestment_pct: Decimal = Field(
        ge=0,
        le=100,
        max_digits=9,
        decimal_places=6,
    )

    @model_validator(mode="after")
    def validate_actual_mix(self):
        """計算組成須唯一且合計約為 100%。"""

        mix = self.calculation_component_mix or self.actual_component_mix
        if mix is None:
            return self

        codes = [item.component_code for item in mix]
        if len(codes) != len(set(codes)):
            raise ValueError("配息組成代碼不可重複")

        total = sum(
            (item.ratio_pct for item in mix),
            Decimal("0"),
        )
        if total < Decimal("99") or total > Decimal("101"):
            raise ValueError("配息組成比例合計必須介於 99% 與 101%")
        if (
            self.calculation_component_mix is not None
            and self.component_calculation_basis is None
        ):
            raise ValueError("計算組成必須標示資料層級")
        return self


class TaxScenarioIssue(TaxReinvestmentBaseModel):
    """不可計算欄位與原因。"""

    field: str = Field(min_length=1)
    reason: TaxScenarioUnavailableReason
    component_code: str | None = None


class ReinvestmentScenarioResult(TaxReinvestmentBaseModel):
    """單一配息使用政策的估算結果。"""

    policy: ReinvestmentPolicy
    custom_reinvestment_pct: Decimal | None = None
    usable_cash: Decimal | None
    reinvested_cash: Decimal | None
    ending_units: Decimal | None
    ending_value: Decimal | None
    modeled_income_tax: Decimal | None
    modeled_supplementary_premium: Decimal | None
    modeled_tax_cost: Decimal | None
    after_tax_total_gain_loss: Decimal | None
    after_tax_total_return_pct: Decimal | None
    total_return_check_passed: bool | None
    issues: list[TaxScenarioIssue] = Field(default_factory=list)


class TaxReinvestmentCalculationResult(TaxReinvestmentBaseModel):
    """四種稅後現金與期末財富比較。"""

    currency: str
    projection_years: int = Field(ge=1, le=50)
    estimate_label: str = "情境估算，非稅務建議"
    rule_version: str
    rule_effective_date: date
    historical_component_basis: str | None = None
    scenarios: list[ReinvestmentScenarioResult]
    issues: list[TaxScenarioIssue] = Field(default_factory=list)


class TaxReinvestmentAnalysisRequest(TaxReinvestmentBaseModel):
    """ETF 稅務與再投資分析 API 請求。"""

    held_units: Decimal = Field(
        ge=0,
        max_digits=24,
        decimal_places=6,
    )
    unit_price: Decimal = Field(
        gt=0,
        max_digits=24,
        decimal_places=6,
    )
    monthly_cash_target: Decimal = Field(
        ge=0,
        max_digits=24,
        decimal_places=6,
    )
    analysis_years: int = Field(ge=1, le=50)
    history_years: int = Field(default=3, ge=1, le=10)
    payments_per_year: int = Field(ge=1, le=365)
    custom_reinvestment_pct: Decimal = Field(
        ge=0,
        le=100,
        max_digits=9,
        decimal_places=6,
    )
    tax_rule: TaiwanIndividualTaxRule


class TaxReinvestmentHistoricalFacts(TaxReinvestmentBaseModel):
    """與情境假設分離的歷史資料事實。"""

    component_dividend_id: int | None = None
    component_source_event_id: str | None = None
    component_source_date: date | None = None
    actual_component_mix: list[OfficialComponentAllocation] | None
    calculation_component_mix: list[OfficialComponentAllocation] | None = None
    component_calculation_basis: ComponentCalculationBasis | None = None
    annual_gross_distribution_rate_pct: Decimal | None
    price_return_period_code: str | None = None
    annual_price_return_pct: Decimal | None
    history_start_date: date
    history_end_date: date


class TaxReinvestmentAnalysisResult(TaxReinvestmentBaseModel):
    """ETF 稅務與再投資 API 回應。"""

    warnings: list[str] = Field(default_factory=list)
    status: str = Field(pattern=r"^(AVAILABLE|PARTIAL)$")
    historical_facts: TaxReinvestmentHistoricalFacts
    calculation: TaxReinvestmentCalculationResult
