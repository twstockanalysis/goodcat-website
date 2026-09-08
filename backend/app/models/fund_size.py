"""Dated total fund net assets, distinct from per-unit NAV and market price."""

from datetime import date
from decimal import Decimal
import hashlib
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class FundSizeEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    etf_code: str = Field(pattern=r"^[0-9A-Z]{4,10}$")
    fund_code: str = Field(pattern=r"^[A-Z0-9]{1,10}$")
    as_of_date: date
    fetched_at: AwareDatetime
    currency: Literal["TWD"] = "TWD"
    source_id: Literal["cathay_official_fund_assets"] = "cathay_official_fund_assets"
    source_url: str = Field(pattern=r"^https://cwapi\.cathaysite\.com\.tw/api/ETF/GetETFAssets\?")
    total_net_assets_twd: Decimal = Field(ge=0, le=Decimal("1e18"), allow_inf_nan=False)
    evidence_json: str = Field(min_length=2)

    @property
    def fund_size(self) -> Decimal:
        return self.total_net_assets_twd / Decimal("100000000")

    @property
    def evidence_sha256(self) -> str:
        return hashlib.sha256(self.evidence_json.encode("utf-8")).hexdigest()
