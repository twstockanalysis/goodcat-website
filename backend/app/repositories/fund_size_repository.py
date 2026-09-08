"""Atomic immutable evidence and latest-date projection; explicit DB required."""

from datetime import date
from decimal import Decimal
from pathlib import Path

from backend.app.database.connection import get_connection
from backend.app.models.fund_size import FundSizeEvidence


def save_fund_size_evidence(value: FundSizeEvidence, database_path: str | Path, *,
                           evaluated_on: date) -> str:
    if not 0 <= (evaluated_on - value.as_of_date).days <= 7:
        raise ValueError("Fund-size evidence future or stale")
    connection = get_connection(database_path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        master = connection.execute("SELECT fund_size FROM etf_master WHERE code=?",
                                    (value.etf_code,)).fetchone()
        if master is None:
            raise ValueError("ETF master not found")
        same = connection.execute(
            "SELECT * FROM etf_fund_size_evidence WHERE etf_code=? AND as_of_date=? AND source_id=?",
            (value.etf_code, str(value.as_of_date), value.source_id)).fetchone()
        if same is not None:
            if (Decimal(same["total_net_assets_twd"]) != value.total_net_assets_twd
                    or same["fund_code"] != value.fund_code or same["currency"] != value.currency):
                raise ValueError("Conflicting immutable fund-size evidence")
            connection.commit()
            return "UNCHANGED"
        latest = connection.execute(
            "SELECT as_of_date FROM etf_fund_size_evidence WHERE etf_code=? ORDER BY as_of_date DESC LIMIT 1",
            (value.etf_code,)).fetchone()
        if latest is None and master["fund_size"] is not None:
            raise ValueError("Existing fund size has no managed provenance; review required")
        connection.execute(
            """INSERT INTO etf_fund_size_evidence
            (etf_code,fund_code,as_of_date,fetched_at,currency,total_net_assets_twd,
             source_id,source_url,evidence_sha256,evidence_json)
            VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (value.etf_code, value.fund_code, str(value.as_of_date), value.fetched_at.isoformat(),
             value.currency, str(value.total_net_assets_twd), value.source_id, value.source_url,
             value.evidence_sha256, value.evidence_json))
        if latest is None or str(value.as_of_date) > latest["as_of_date"]:
            connection.execute("UPDATE etf_master SET fund_size=? WHERE code=?",
                               (float(value.fund_size), value.etf_code))
        connection.commit()
        return "IMPORTED"
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
