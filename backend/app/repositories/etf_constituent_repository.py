"""ETF 成分股不可變快照 Repository。"""

from datetime import date
from decimal import Decimal
from pathlib import Path

from backend.app.database.connection import get_connection
from backend.app.models.etf_constituent import (
    ETFConstituentPosition,
    ETFConstituentSnapshot,
    ETFConstituentSnapshotCreate,
)


def _snapshot_from_rows(row, positions) -> ETFConstituentSnapshot:
    return ETFConstituentSnapshot(
        id=row["id"],
        etf_code=row["etf_code"],
        as_of_date=row["as_of_date"],
        source_id=row["source_id"],
        source_url=row["source_url"],
        fetched_at=row["fetched_at"],
        total_weight_pct=Decimal(str(row["total_weight_pct"])),
        constituent_count=row["constituent_count"],
        positions=[ETFConstituentPosition(**dict(item)) for item in positions],
    )


def get_constituent_snapshot(
    snapshot_id: int,
    database_path: str | Path | None = None,
) -> ETFConstituentSnapshot | None:
    connection = get_connection(database_path)
    try:
        row = connection.execute(
            "SELECT * FROM etf_constituent_snapshot WHERE id = ?;",
            (snapshot_id,),
        ).fetchone()
        if row is None:
            return None
        positions = connection.execute(
            """
            SELECT constituent_id, constituent_name, weight_pct, rank
            FROM etf_constituent_position
            WHERE snapshot_id = ?
            ORDER BY COALESCE(rank, 2147483647), weight_pct DESC,
                     constituent_id;
            """,
            (snapshot_id,),
        ).fetchall()
        return _snapshot_from_rows(row, positions)
    finally:
        connection.close()


def get_latest_constituent_snapshot(
    etf_code: str,
    database_path: str | Path | None = None,
    *,
    on_or_before: date | None = None,
) -> ETFConstituentSnapshot | None:
    """Return the latest effective snapshot within an optional inclusive cutoff."""

    connection = get_connection(database_path)
    try:
        row = connection.execute(
            """
            SELECT * FROM etf_constituent_snapshot
            WHERE etf_code = ? AND (? IS NULL OR as_of_date <= ?)
            ORDER BY as_of_date DESC, id DESC
            LIMIT 1;
            """,
            (
                etf_code.strip().upper(),
                on_or_before.isoformat() if on_or_before else None,
                on_or_before.isoformat() if on_or_before else None,
            ),
        ).fetchone()
        if row is None:
            return None
        positions = connection.execute(
            """
            SELECT constituent_id, constituent_name, weight_pct, rank
            FROM etf_constituent_position
            WHERE snapshot_id = ?
            ORDER BY COALESCE(rank, 2147483647), weight_pct DESC,
                     constituent_id;
            """,
            (row["id"],),
        ).fetchall()
        return _snapshot_from_rows(row, positions)
    finally:
        connection.close()


def get_constituent_snapshot_by_identity(
    etf_code: str,
    as_of_date: str,
    source_id: str,
    database_path: str | Path | None = None,
) -> ETFConstituentSnapshot | None:
    """依不可變來源識別鍵取得既有快照。"""

    connection = get_connection(database_path)
    try:
        row = connection.execute(
            """
            SELECT * FROM etf_constituent_snapshot
            WHERE etf_code = ? AND as_of_date = ? AND source_id = ?
            LIMIT 1;
            """,
            (etf_code.strip().upper(), as_of_date, source_id.strip()),
        ).fetchone()
        if row is None:
            return None
        positions = connection.execute(
            """
            SELECT constituent_id, constituent_name, weight_pct, rank
            FROM etf_constituent_position
            WHERE snapshot_id = ?
            ORDER BY COALESCE(rank, 2147483647), weight_pct DESC,
                     constituent_id;
            """,
            (row["id"],),
        ).fetchall()
        return _snapshot_from_rows(row, positions)
    finally:
        connection.close()


def save_constituent_snapshot(
    value: ETFConstituentSnapshotCreate,
    database_path: str | Path | None = None,
) -> ETFConstituentSnapshot:
    """原子寫入快照；同 ETF、日期與來源不可覆寫。"""

    connection = get_connection(database_path)
    total_weight = sum(item.weight_pct for item in value.positions)
    try:
        cursor = connection.execute(
            """
            INSERT INTO etf_constituent_snapshot (
                etf_code, as_of_date, source_id, source_url, fetched_at,
                total_weight_pct, constituent_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?);
            """,
            (
                value.etf_code,
                value.as_of_date.isoformat(),
                value.source_id,
                value.source_url,
                value.fetched_at.isoformat(),
                float(total_weight),
                len(value.positions),
            ),
        )
        snapshot_id = int(cursor.lastrowid)
        connection.executemany(
            """
            INSERT INTO etf_constituent_position (
                snapshot_id, constituent_id, constituent_name,
                weight_pct, rank
            ) VALUES (?, ?, ?, ?, ?);
            """,
            [
                (
                    snapshot_id,
                    item.constituent_id,
                    item.constituent_name,
                    float(item.weight_pct),
                    item.rank,
                )
                for item in value.positions
            ],
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    result = get_constituent_snapshot(snapshot_id, database_path)
    if result is None:
        raise RuntimeError("成分股快照寫入後未能讀回")
    return result
