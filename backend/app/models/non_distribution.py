"""A reviewed decision for one evaluation date, never a paid dividend."""

from datetime import date
from typing import Literal
from urllib.parse import parse_qs, urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator


class NonDistributionNotice(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    etf_code: str = Field(pattern=r"^[0-9A-Z]{4,10}$")
    legal_name: str = Field(min_length=1)
    evaluation_date: date
    publication_date: date
    reviewed_on: date
    decision: Literal["NO_DISTRIBUTION"] = "NO_DISTRIBUTION"
    source_url: str
    evidence_method: Literal["REVIEWED_TRANSCRIPTION"] = "REVIEWED_TRANSCRIPTION"
    review_reference: str = Field(
        pattern=r"^https://github\.com/twstockanalysis/goodcat-website/issues/[0-9]+$"
    )

    @model_validator(mode="after")
    def validate_notice(self):
        if not self.evaluation_date <= self.publication_date <= self.reviewed_on:
            raise ValueError("Evaluation, publication and review dates are inconsistent")
        url = urlsplit(self.source_url)
        params = parse_qs(url.query)
        if (url.scheme != "https" or url.netloc not in {"www.twse.com.tw", "wwwc.twse.com.tw"}
                or url.path != "/zh/ETFortune/announcement" or url.fragment
                or params.get("fund") != [self.etf_code]
                or params.get("date") != [self.publication_date.strftime("%Y%m%d")]):
            raise ValueError("Announcement URL identity/date mismatch")
        return self


class NonDistributionEvidence(BaseModel):
    """Presence of reviewed history, not the ETF's current distribution status."""

    status: Literal["REVIEWED_NOTICES", "NO_REVIEWED_NOTICE"]
    items: list[NonDistributionNotice]

    @model_validator(mode="after")
    def validate_status(self):
        if bool(self.items) != (self.status == "REVIEWED_NOTICES"):
            raise ValueError("Evidence status and notices disagree")
        return self
