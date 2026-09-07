"""以 ETF 揭露權重計算可追溯的成分股重疊率。"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from backend.app.models.etf_constituent import (
    ETFConstituentPosition,
    ETFConstituentSnapshot,
    ETFWeightedOverlapResult,
)
from backend.app.repositories.etf_constituent_repository import (
    get_latest_constituent_snapshot,
)
from backend.app.services.constituent_data_quality import (
    evaluate_constituent_data_quality,
)


_PERCENT_QUANTUM = Decimal("0.000001")


@dataclass(frozen=True, slots=True)
class GatedConstituentOverlap:
    """通過正式快照門檻後才提供的自動重疊結果。"""

    decision: str
    overlap_pct: Decimal | None
    reasons: tuple[str, ...]
    snapshot_dates: tuple[date, ...]
    method: str | None = None


def _quality_targets(etf_codes: list[str]) -> list[dict]:
    # 單次計算要求每一檔 ETF 都通過；用 ETF 代號作為獨立資料群組，
    # 避免計算層依賴投信網站來源註冊表。
    return [
        {"etf_code": code, "issuer_key": code}
        for code in dict.fromkeys(item.strip().upper() for item in etf_codes)
    ]


def _quality_reasons(quality: dict) -> tuple[str, ...]:
    return tuple(
        f"{item['etf_code']}:{reason}"
        for item in quality["items"]
        for reason in item["reasons"]
    )


def calculate_gated_pair_overlap(
    left_etf_code: str,
    right_etf_code: str,
    database_path: str | Path,
    *,
    evaluated_on: date | None = None,
) -> GatedConstituentOverlap:
    """只有兩檔 ETF 的最新正式快照都合格時才回傳重疊率。"""

    evaluated_on = evaluated_on or date.today()
    codes = [left_etf_code.strip().upper(), right_etf_code.strip().upper()]
    quality = evaluate_constituent_data_quality(
        _quality_targets(codes),
        database_path,
        evaluated_on=evaluated_on,
    )
    if quality["decision"] != "READY":
        return GatedConstituentOverlap(
            decision="NO_GO",
            overlap_pct=None,
            reasons=_quality_reasons(quality),
            snapshot_dates=(),
        )
    left = get_latest_constituent_snapshot(
        codes[0], database_path, on_or_before=evaluated_on
    )
    right = get_latest_constituent_snapshot(
        codes[1], database_path, on_or_before=evaluated_on
    )
    assert left is not None and right is not None
    result = calculate_weighted_overlap(left, right)
    return GatedConstituentOverlap(
        decision="READY",
        overlap_pct=result.overlap_pct,
        reasons=(),
        snapshot_dates=(left.as_of_date, right.as_of_date),
        method=result.method,
    )


def calculate_gated_portfolio_overlap(
    holdings: list[dict],
    candidate_etf_code: str,
    database_path: str | Path,
    *,
    evaluated_on: date | None = None,
) -> GatedConstituentOverlap:
    """計算候選 ETF 與目前持倉市值加權成分的重疊率。"""

    evaluated_on = evaluated_on or date.today()
    current_values: list[tuple[str, Decimal]] = []
    for holding in holdings:
        unit_price = holding.get("unit_price")
        held_units = holding.get("held_units")
        if unit_price is None or held_units is None:
            return GatedConstituentOverlap(
                decision="NO_GO",
                overlap_pct=None,
                reasons=("CURRENT_PORTFOLIO_VALUE_UNAVAILABLE",),
                snapshot_dates=(),
            )
        value = Decimal(str(unit_price)) * Decimal(str(held_units))
        if value > 0:
            current_values.append((holding["etf_code"].strip().upper(), value))
    total_value = sum((value for _, value in current_values), Decimal("0"))
    if total_value <= 0:
        return GatedConstituentOverlap(
            decision="NO_GO",
            overlap_pct=None,
            reasons=("CURRENT_PORTFOLIO_EMPTY",),
            snapshot_dates=(),
        )

    candidate_code = candidate_etf_code.strip().upper()
    codes = [code for code, _ in current_values] + [candidate_code]
    quality = evaluate_constituent_data_quality(
        _quality_targets(codes),
        database_path,
        evaluated_on=evaluated_on,
    )
    if quality["decision"] != "READY":
        return GatedConstituentOverlap(
            decision="NO_GO",
            overlap_pct=None,
            reasons=_quality_reasons(quality),
            snapshot_dates=(),
        )

    snapshots = {
        code: get_latest_constituent_snapshot(
            code, database_path, on_or_before=evaluated_on
        )
        for code in dict.fromkeys(codes)
    }
    assert all(snapshot is not None for snapshot in snapshots.values())
    aggregate: dict[str, Decimal] = {}
    for code, value in current_values:
        allocation = value / total_value
        snapshot = snapshots[code]
        assert snapshot is not None
        for position in snapshot.positions:
            aggregate[position.constituent_id] = (
                aggregate.get(position.constituent_id, Decimal("0"))
                + allocation * position.weight_pct
            )

    candidate = snapshots[candidate_code]
    assert candidate is not None
    overlap = sum(
        (
            min(
                aggregate.get(position.constituent_id, Decimal("0")),
                position.weight_pct,
            )
            for position in candidate.positions
        ),
        Decimal("0"),
    ).quantize(_PERCENT_QUANTUM, rounding=ROUND_HALF_UP)
    return GatedConstituentOverlap(
        decision="READY",
        overlap_pct=overlap,
        reasons=(),
        snapshot_dates=tuple(
            sorted(
                {
                    snapshot.as_of_date
                    for snapshot in snapshots.values()
                    if snapshot
                }
            )
        ),
        method="PORTFOLIO_VALUE_WEIGHTED_SUM_MIN_DISCLOSED_WEIGHTS_V1",
    )


def calculate_weighted_overlap(
    left: ETFConstituentSnapshot,
    right: ETFConstituentSnapshot,
) -> ETFWeightedOverlapResult:
    """逐一相同識別碼加總兩邊較小的已揭露權重。"""

    left_by_id = {item.constituent_id: item for item in left.positions}
    right_by_id = {item.constituent_id: item for item in right.positions}
    shared: list[ETFConstituentPosition] = []
    for identifier in sorted(left_by_id.keys() & right_by_id.keys()):
        left_item = left_by_id[identifier]
        right_item = right_by_id[identifier]
        shared.append(
            ETFConstituentPosition(
                constituent_id=identifier,
                constituent_name=left_item.constituent_name,
                weight_pct=min(left_item.weight_pct, right_item.weight_pct),
            )
        )
    shared.sort(key=lambda item: (-item.weight_pct, item.constituent_id))
    overlap = sum(
        (item.weight_pct for item in shared),
        Decimal("0"),
    ).quantize(
        _PERCENT_QUANTUM,
        rounding=ROUND_HALF_UP,
    )
    return ETFWeightedOverlapResult(
        left_etf_code=left.etf_code,
        right_etf_code=right.etf_code,
        left_as_of_date=left.as_of_date,
        right_as_of_date=right.as_of_date,
        left_total_weight_pct=left.total_weight_pct,
        right_total_weight_pct=right.total_weight_pct,
        overlap_pct=overlap,
        shared_constituent_count=len(shared),
        shared_constituents=shared,
    )
