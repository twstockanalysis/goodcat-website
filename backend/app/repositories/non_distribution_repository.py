"""Append-only notice storage, deliberately outside all payment/solver readers."""

from contextlib import closing
from datetime import date
from pathlib import Path

from backend.app.database.connection import get_connection
from backend.app.models.non_distribution import NonDistributionEvidence, NonDistributionNotice


def read_non_distribution_evidence(code: str, database_path: str | Path,
                                   *, evaluated_on: date) -> NonDistributionEvidence:
    if not Path(database_path).is_file():
        raise FileNotFoundError(database_path)
    items = []
    with closing(get_connection(database_path)) as conn:
        exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' "
                              "AND name='etf_non_distribution_notice'").fetchone()
        if exists:
            for row in conn.execute(
                "SELECT evidence_json FROM etf_non_distribution_notice WHERE etf_code=? "
                "ORDER BY evaluation_date DESC", (code,)
            ):
                notice = NonDistributionNotice.model_validate_json(row[0])
                if notice.etf_code != code:
                    raise ValueError("Stored notice identity mismatch")
                if notice.publication_date <= evaluated_on:
                    items.append(notice)
    return NonDistributionEvidence(
        status="REVIEWED_NOTICES" if items else "NO_REVIEWED_NOTICE", items=items
    )


def save_non_distribution_notices(notices: list[NonDistributionNotice],
                                  database_path: str | Path, *, evaluated_on: date) -> int:
    if not Path(database_path).is_file():
        raise FileNotFoundError(database_path)
    with closing(get_connection(database_path)) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        inserted = 0
        for notice in notices:
            notice = NonDistributionNotice.model_validate(notice.model_dump())
            if notice.publication_date > evaluated_on:
                raise ValueError("Publication after evaluation date")
            master = conn.execute("SELECT listing_date FROM etf_master WHERE code=?",
                                  (notice.etf_code,)).fetchone()
            if master is None:
                raise ValueError("Unknown ETF")
            if not master[0] or date.fromisoformat(master[0]) > notice.evaluation_date:
                raise ValueError("ETF listing history does not cover evaluation")
            prior = conn.execute(
                "SELECT evidence_json FROM etf_non_distribution_notice "
                "WHERE etf_code=? AND evaluation_date=?",
                (notice.etf_code, str(notice.evaluation_date)),
            ).fetchone()
            if prior:
                if NonDistributionNotice.model_validate_json(prior[0]) != notice:
                    raise ValueError("Conflicting immutable non-distribution notice")
                continue
            conn.execute("INSERT INTO etf_non_distribution_notice VALUES (?,?,?)",
                         (notice.etf_code, str(notice.evaluation_date), notice.model_dump_json()))
            inserted += 1
        return inserted
