"""成分股重複性計算前的資料完整性與新鮮度門檻。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

from backend.app.repositories.etf_constituent_repository import (
    get_latest_constituent_snapshot,
)


@dataclass(frozen=True, slots=True)
class ConstituentQualityThreshold:
    max_age_days: int = 7
    minimum_disclosed_weight_pct: Decimal = Decimal("85")
    minimum_etf_coverage_pct: Decimal = Decimal("90")
    minimum_issuer_coverage_pct: Decimal = Decimal("90")

    def __post_init__(self) -> None:
        if self.max_age_days < 0:
            raise ValueError("max_age_days must be non-negative")
        if not (
            Decimal("0")
            <= self.minimum_disclosed_weight_pct
            <= Decimal("100.5")
        ):
            raise ValueError(
                "minimum_disclosed_weight_pct must be between 0 and 100.5"
            )
        for field_name in (
            "minimum_etf_coverage_pct",
            "minimum_issuer_coverage_pct",
        ):
            value = getattr(self, field_name)
            if not Decimal("0") <= value <= Decimal("100"):
                raise ValueError(f"{field_name} must be between 0 and 100")


def _percentage(numerator: int, denominator: int) -> Decimal:
    if denominator == 0:
        return Decimal("0")
    return (Decimal(numerator) * Decimal("100") / Decimal(denominator)).quantize(
        Decimal("0.000001")
    )


def evaluate_constituent_data_quality(
    targets: list[dict],
    database_path: str | Path,
    *,
    evaluated_on: date | None = None,
    threshold: ConstituentQualityThreshold | None = None,
) -> dict:
    """評估指定股票型 ETF 清單能否安全供重複性計算使用。"""

    evaluated_on = evaluated_on or date.today()
    threshold = threshold or ConstituentQualityThreshold()
    items: list[dict] = []
    covered_issuers: set[str] = set()
    target_issuers = {item["issuer_key"] for item in targets}

    for target in targets:
        snapshot = get_latest_constituent_snapshot(
            target["etf_code"], database_path, on_or_before=evaluated_on
        )
        if snapshot is None:
            # Retain the future-only diagnostic without using future evidence.
            snapshot = get_latest_constituent_snapshot(
                target["etf_code"], database_path
            )
        reasons: list[str] = []
        age_days: int | None = None
        if snapshot is None:
            reasons.append("MISSING_SNAPSHOT")
        else:
            age_days = (evaluated_on - snapshot.as_of_date).days
            if age_days < 0:
                reasons.append("FUTURE_DATED_SNAPSHOT")
            elif age_days > threshold.max_age_days:
                reasons.append("STALE_SNAPSHOT")
            if snapshot.total_weight_pct < threshold.minimum_disclosed_weight_pct:
                reasons.append("INSUFFICIENT_DISCLOSED_WEIGHT")

        passed = not reasons
        if passed:
            covered_issuers.add(target["issuer_key"])
        items.append(
            {
                "etf_code": target["etf_code"],
                "issuer_key": target["issuer_key"],
                "passed": passed,
                "reasons": reasons,
                "as_of_date": (
                    snapshot.as_of_date.isoformat() if snapshot is not None else None
                ),
                "age_days": age_days,
                "disclosed_weight_pct": (
                    str(snapshot.total_weight_pct) if snapshot is not None else None
                ),
            }
        )

    covered_etfs = sum(1 for item in items if item["passed"])
    etf_coverage = _percentage(covered_etfs, len(targets))
    issuer_coverage = _percentage(len(covered_issuers), len(target_issuers))
    checks = [
        {
            "name": "eligible_etf_coverage",
            "actual_pct": str(etf_coverage),
            "minimum_pct": str(threshold.minimum_etf_coverage_pct),
            "passed": etf_coverage >= threshold.minimum_etf_coverage_pct,
        },
        {
            "name": "issuer_coverage",
            "actual_pct": str(issuer_coverage),
            "minimum_pct": str(threshold.minimum_issuer_coverage_pct),
            "passed": issuer_coverage >= threshold.minimum_issuer_coverage_pct,
        },
    ]
    ready = bool(targets) and all(check["passed"] for check in checks)
    return {
        "schema_version": 1,
        "evaluated_on": evaluated_on.isoformat(),
        "decision": "READY" if ready else "NO_GO",
        "threshold": {
            **asdict(threshold),
            "minimum_disclosed_weight_pct": str(
                threshold.minimum_disclosed_weight_pct
            ),
            "minimum_etf_coverage_pct": str(threshold.minimum_etf_coverage_pct),
            "minimum_issuer_coverage_pct": str(
                threshold.minimum_issuer_coverage_pct
            ),
        },
        "target_etf_count": len(targets),
        "covered_etf_count": covered_etfs,
        "target_issuer_count": len(target_issuers),
        "covered_issuer_count": len(covered_issuers),
        "checks": checks,
        "items": items,
    }
