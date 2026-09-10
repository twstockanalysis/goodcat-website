"""Reviewed historical annual total expense observations, in percentage units."""

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class AnnualExpenseEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    etf_code: str = Field(pattern=r"^[0-9A-Z]{4,10}$")
    issuer_product_id: str = Field(pattern=r"^[0-9]{4}$")
    legal_name: str = Field(min_length=1)
    currency: Literal["TWD"] = "TWD"
    reporting_year: int = Field(ge=2000, le=9998, strict=True)
    expense_ratio_pct: Decimal = Field(ge=0, le=100, allow_inf_nan=False)
    basis: Literal["HISTORICAL_ANNUAL_TOTAL_EXPENSE"] = "HISTORICAL_ANNUAL_TOTAL_EXPENSE"
    publication_date: date
    retrieved_at: AwareDatetime
    source_url: str = Field(pattern=r"^https://www\.yuantafunds\.com/fund/download/[^?#]+\.pdf$")
    identity_url: str = Field(pattern=r"^https://www\.yuantafunds\.com/myfund/information/[0-9]{4}$")
    document_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    document_page: int = Field(ge=1)
    review_reference: str = Field(pattern=r"^https://github\.com/twstockanalysis/goodcat-website/issues/[0-9]+$")

    @model_validator(mode="after")
    def validate_dates_and_identity(self):
        if self.publication_date <= date(self.reporting_year, 12, 31):
            raise ValueError("Completed reporting year must precede publication")
        if self.retrieved_at.date() < self.publication_date:
            raise ValueError("Retrieval precedes publication")
        if not self.identity_url.endswith("/" + self.issuer_product_id):
            raise ValueError("Product identity mismatch")
        return self
