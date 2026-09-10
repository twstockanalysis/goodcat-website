"""ETF API 資料模型。"""

from datetime import date

from pydantic import BaseModel, Field
from backend.app.models.annual_expense import AnnualExpenseEvidence
from backend.app.models.non_distribution import NonDistributionEvidence


class ETFResponse(BaseModel):
    """ETF 主資料 API 回應模型。"""

    annual_expense: AnnualExpenseEvidence | None = Field(
        default=None, description="已審查的歷史年度總費用率與文件來源；非目前契約費率"
    )

    code: str = Field(
        description="ETF 證券代號",
        examples=["00918"],
    )

    name: str = Field(
        description="ETF 中文名稱",
    )

    is_active: bool = Field(
        description="是否為主動式 ETF",
    )

    is_bond: bool = Field(
        description="是否為債券 ETF",
    )

    listing_date: date | None = Field(
        default=None,
        description="上市日期",
    )

    fund_size: float | None = Field(
        default=None,
        description="基金規模，單位為新台幣億元",
    )

    expense_ratio: float | None = Field(
        default=None,
        description="總費用率，單位為百分比",
    )


class ETFDetailResponse(ETFResponse):
    non_distribution_evidence: NonDistributionEvidence


class ETFListResponse(BaseModel):
    """ETF 分頁列表 API 回應模型。"""

    items: list[ETFResponse] = Field(
        description="本頁 ETF 資料",
    )

    total: int = Field(
        ge=0,
        description="符合條件的 ETF 總筆數",
    )

    limit: int = Field(
        ge=1,
        description="單次回傳筆數上限",
    )

    offset: int = Field(
        ge=0,
        description="略過的資料筆數",
    )
