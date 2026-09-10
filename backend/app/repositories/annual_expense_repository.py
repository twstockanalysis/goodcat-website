"""Append-only annual expense evidence; no master-row mutation or auto-migration."""

from datetime import date
from pathlib import Path
import sqlite3

from backend.app.database.connection import get_connection
from backend.app.models.annual_expense import AnnualExpenseEvidence


def annual_expense_catalog(connection: sqlite3.Connection, *, evaluated_on: date) -> dict:
    """Old databases remain readable; missing table means missing evidence."""
    if connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='etf_annual_expense_evidence'"
    ).fetchone() is None:
        return {}
    result = {}
    for row in connection.execute(
        """SELECT evidence_json FROM etf_annual_expense_evidence
        WHERE reporting_year < ? AND publication_date <= ?
        ORDER BY etf_code, reporting_year DESC""",
        (evaluated_on.year, evaluated_on.isoformat()),
    ):
        evidence = AnnualExpenseEvidence.model_validate_json(row[0])
        result.setdefault(evidence.etf_code, evidence)
    return result


def enrich_expense(item: dict, catalog: dict) -> dict:
    evidence = catalog.get(item["code"])
    if evidence is not None:
        item["expense_ratio"] = float(evidence.expense_ratio_pct)
        item["annual_expense"] = evidence.model_dump(mode="json")
    return item


def save_annual_expenses(values: list[AnnualExpenseEvidence], database_path: str | Path,
                         *, evaluated_on: date) -> int:
    """Atomic insert; existing (ETF, year) facts cannot silently be replaced."""
    target = Path(database_path)
    if not target.is_file():
        raise FileNotFoundError(target)
    connection = get_connection(target)
    try:
        connection.execute("BEGIN IMMEDIATE")
        inserted = 0
        for value in values:
            # Revalidate even instances constructed without validation by callers.
            value = AnnualExpenseEvidence.model_validate(value.model_dump())
            if value.publication_date > evaluated_on:
                raise ValueError("Publication is after evaluation date")
            master = connection.execute(
                "SELECT listing_date FROM etf_master WHERE code=?", (value.etf_code,)
            ).fetchone()
            if master is None:
                raise ValueError("ETF master not found")
            if not master[0] or date.fromisoformat(master[0]) > date(value.reporting_year, 1, 1):
                raise ValueError("Full-year ETF identity history unavailable")
            existing = connection.execute(
                "SELECT evidence_json FROM etf_annual_expense_evidence WHERE etf_code=? AND reporting_year=?",
                (value.etf_code, value.reporting_year),
            ).fetchone()
            if existing:
                prior = AnnualExpenseEvidence.model_validate_json(existing[0])
                if prior.model_dump(exclude={"retrieved_at"}) != value.model_dump(exclude={"retrieved_at"}):
                    raise ValueError("Conflicting immutable annual expense evidence")
                continue
            connection.execute(
                """INSERT INTO etf_annual_expense_evidence
                (etf_code,reporting_year,publication_date,evidence_json) VALUES (?,?,?,?)""",
                (value.etf_code, value.reporting_year, str(value.publication_date), value.model_dump_json()),
            )
            inserted += 1
        connection.commit()
        return inserted
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
