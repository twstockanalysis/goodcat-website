"""官方 ETF 成分股快照匯入流程。"""

from dataclasses import dataclass
from pathlib import Path
from backend.app.data_sources.cathay_constituent_adapter import fetch_cathay_constituent_snapshot

from backend.app.data_sources.direct_constituent_adapters import (
    DIRECT_CONSTITUENT_FETCHERS,
)
from backend.app.data_sources.form_constituent_adapters import (
    FORM_CONSTITUENT_FETCHERS,
)
from backend.app.data_sources.mapped_constituent_adapters import (
    MAPPED_CONSTITUENT_FETCHERS,
)
from backend.app.data_sources.session_constituent_adapters import (
    SESSION_CONSTITUENT_FETCHERS,
)
from backend.app.data_sources.yuanta_constituent_adapter import (
    fetch_yuanta_constituent_snapshot,
)
from backend.app.models.etf_constituent import ETFConstituentSnapshot
from backend.app.repositories.etf_constituent_repository import (
    get_constituent_snapshot_by_identity,
    save_constituent_snapshot,
)
from backend.app.repositories.etf_repository import get_etf_by_code


@dataclass(frozen=True, slots=True)
class OfficialConstituentImportResult:
    """單一官方快照的可重跑保存結果。"""

    snapshot: ETFConstituentSnapshot
    outcome: str


def _position_signature(snapshot) -> tuple[tuple[str, str, str, int | None], ...]:
    return tuple(
        sorted(
            (
                item.constituent_id,
                item.constituent_name,
                str(item.weight_pct.normalize()),
                item.rank,
            )
            for item in snapshot.positions
        )
    )


def _save_idempotently(
    value,
    database_path: str | Path,
) -> OfficialConstituentImportResult:
    existing = get_constituent_snapshot_by_identity(
        value.etf_code,
        value.as_of_date.isoformat(),
        value.source_id,
        database_path,
    )
    if existing is not None:
        if _position_signature(existing) != _position_signature(value):
            raise ValueError(
                "同一 ETF、資料日與來源已有不同的成分股內容，拒絕覆寫"
            )
        return OfficialConstituentImportResult(existing, "UNCHANGED")
    return OfficialConstituentImportResult(
        save_constituent_snapshot(value, database_path),
        "IMPORTED",
    )


def import_yuanta_constituents(
    etf_code: str,
    database_path: str | Path,
) -> ETFConstituentSnapshot:
    """驗證 ETF 已存在後，下載並原子保存元大官方持股。"""

    normalized_code = etf_code.strip().upper()
    if get_etf_by_code(normalized_code, database_path) is None:
        raise ValueError(f"找不到 ETF：{normalized_code}")
    value = fetch_yuanta_constituent_snapshot(normalized_code)
    return _save_idempotently(value, database_path).snapshot


def import_official_constituents(
    issuer_key: str,
    etf_code: str,
    database_path: str | Path,
) -> ETFConstituentSnapshot:
    """以統一介面匯入已自動化投信的官方成分股。"""

    return import_official_constituents_with_status(
        issuer_key,
        etf_code,
        database_path,
    ).snapshot


def import_official_constituents_with_status(
    issuer_key: str,
    etf_code: str,
    database_path: str | Path,
) -> OfficialConstituentImportResult:
    """匯入官方快照並回報新增或內容未變。"""

    normalized_issuer = issuer_key.strip().lower()
    normalized_code = etf_code.strip().upper()
    if get_etf_by_code(normalized_code, database_path) is None:
        raise ValueError(f"找不到 ETF：{normalized_code}")
    if normalized_issuer == "yuanta":
        value = fetch_yuanta_constituent_snapshot(normalized_code)
    elif normalized_issuer == "cathay":
        value = fetch_cathay_constituent_snapshot(normalized_code)
    else:
        fetcher = (
            DIRECT_CONSTITUENT_FETCHERS.get(normalized_issuer)
            or MAPPED_CONSTITUENT_FETCHERS.get(normalized_issuer)
            or SESSION_CONSTITUENT_FETCHERS.get(normalized_issuer)
            or FORM_CONSTITUENT_FETCHERS.get(normalized_issuer)
        )
        if fetcher is None:
            raise ValueError(f"尚未支援投信成分股自動匯入：{normalized_issuer}")
        value = fetcher(normalized_code)
    return _save_idempotently(value, database_path)
