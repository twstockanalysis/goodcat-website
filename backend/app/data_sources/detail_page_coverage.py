"""V5 detailed-page data coverage and provenance report."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from backend.app.database.connection import get_connection
from backend.app.repositories.annual_expense_repository import annual_expense_catalog


PERFORMANCE_PERIODS = ("1M", "3M", "6M", "1Y")


def sha256_file(file_path: str | Path) -> str:
    """Return the lowercase SHA-256 of an immutable candidate database."""

    digest = hashlib.sha256()
    with Path(file_path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _availability(
    available: bool,
    *,
    as_of: str | None = None,
    reason: str | None = None,
) -> dict[str, str | None]:
    return {
        "status": "AVAILABLE" if available else "UNAVAILABLE",
        "as_of": as_of if available else None,
        "reason": None if available else reason,
    }


def _field_summary(
    items: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    fields = sorted(
        {
            field
            for item in items
            for field in item["fields"]
        }
    )
    result: dict[str, dict[str, Any]] = {}
    for field in fields:
        statuses = Counter(
            item["fields"][field]["status"]
            for item in items
        )
        reasons = Counter(
            item["fields"][field]["reason"]
            for item in items
            if item["fields"][field]["reason"]
        )
        result[field] = {
            "available_count": statuses["AVAILABLE"],
            "unavailable_count": statuses["UNAVAILABLE"],
            "unavailable_reasons": dict(sorted(reasons.items())),
        }
    return result


def build_detail_page_coverage(
    database_path: str | Path,
    *,
    generated_at: datetime | None = None,
    evaluated_on: date | None = None,
) -> dict[str, Any]:
    """Build a per-ETF ledger for every currently visible detail-page fact."""

    target = Path(database_path).resolve()
    if not target.is_file():
        raise FileNotFoundError(f"database does not exist: {target}")
    generated_at = generated_at or datetime.now(timezone.utc)
    if generated_at.tzinfo is None:
        raise ValueError("generated_at must include timezone")

    connection = get_connection(target)
    try:
        annual_expenses = annual_expense_catalog(
            connection, evaluated_on=evaluated_on or generated_at.date())
        rows = connection.execute(
            """
            SELECT
                m.code,
                m.name,
                m.is_active,
                m.is_bond,
                m.listing_date,
                m.fund_size,
                m.expense_ratio,
                (
                    SELECT COUNT(*)
                    FROM etf_daily_close c
                    WHERE c.etf_code = m.code
                ) AS close_count,
                (
                    SELECT MAX(c.trade_date)
                    FROM etf_daily_close c
                    WHERE c.etf_code = m.code
                ) AS latest_close_date,
                (
                    SELECT COUNT(DISTINCT d.id)
                    FROM etf_dividend d
                    WHERE d.etf_code = m.code
                ) AS dividend_count,
                (
                    SELECT MAX(COALESCE(
                        d.payment_date,
                        d.ex_dividend_date,
                        d.record_date,
                        d.announcement_date
                    ))
                    FROM etf_dividend d
                    WHERE d.etf_code = m.code
                ) AS latest_dividend_date,
                (
                    SELECT COUNT(*)
                    FROM etf_dividend d
                    JOIN etf_dividend_summary_metric sm
                      ON sm.dividend_id = d.id
                    WHERE d.etf_code = m.code
                      AND sm.distribution_period IS NOT NULL
                ) AS distribution_period_count,
                (
                    SELECT COUNT(*)
                    FROM etf_dividend d
                    JOIN etf_dividend_summary_metric sm
                      ON sm.dividend_id = d.id
                    WHERE d.etf_code = m.code
                      AND sm.yield_pct IS NOT NULL
                ) AS yield_count,
                (
                    SELECT COUNT(DISTINCT d.id)
                    FROM etf_dividend d
                    JOIN etf_dividend_component c
                      ON c.dividend_id = d.id
                    WHERE d.etf_code = m.code
                      AND c.component_basis = 'ESTIMATED'
                ) AS estimated_component_event_count,
                (
                    SELECT COUNT(DISTINCT d.id)
                    FROM etf_dividend d
                    JOIN etf_dividend_component c
                      ON c.dividend_id = d.id
                    WHERE d.etf_code = m.code
                      AND c.component_basis = 'ACTUAL'
                ) AS actual_component_event_count,
                (
                    SELECT COUNT(DISTINCT d.id)
                    FROM etf_dividend d
                    JOIN etf_dividend_component c
                      ON c.dividend_id = d.id
                    WHERE d.etf_code = m.code
                      AND c.component_basis = 'ACTUAL'
                      AND c.component_code = '76W'
                ) AS actual_76w_event_count,
                (
                    SELECT COUNT(*)
                    FROM dividend_source_review_queue q
                    JOIN etf_dividend d ON d.id = q.dividend_id
                    WHERE d.etf_code = m.code
                      AND q.status IN ('PENDING', 'IN_REVIEW')
                ) AS open_review_count
            FROM etf_master m
            ORDER BY m.code;
            """
        ).fetchall()

        performance = {
            (row["etf_code"], row["period_code"]): {
                "as_of_date": row["as_of_date"],
                "source_id": row["source_id"],
            }
            for row in connection.execute(
                """
                SELECT p.etf_code, p.period_code, p.as_of_date, p.source_id
                FROM etf_performance p
                JOIN (
                    SELECT etf_code, period_code, MAX(as_of_date) AS as_of_date
                    FROM etf_performance
                    WHERE metric_code = 'PRICE_RETURN'
                      AND period_code IN ('1M', '3M', '6M', '1Y')
                    GROUP BY etf_code, period_code
                ) latest
                  ON latest.etf_code = p.etf_code
                 AND latest.period_code = p.period_code
                 AND latest.as_of_date = p.as_of_date
                WHERE p.metric_code = 'PRICE_RETURN';
                """
            ).fetchall()
        }

        import_batches = [
            dict(row)
            for row in connection.execute(
                """
                SELECT pipeline_name, source_id, endpoint_id, status,
                       started_at, completed_at, raw_record_count,
                       accepted_record_count, rejected_record_count,
                       checksum_sha256, error_message
                FROM import_batch
                ORDER BY id;
                """
            ).fetchall()
        ]
        integrity = connection.execute(
            "PRAGMA integrity_check;"
        ).fetchone()[0]
        foreign_key_violations = len(
            connection.execute("PRAGMA foreign_key_check;").fetchall()
        )
    finally:
        connection.close()

    items: list[dict[str, Any]] = []
    for row in rows:
        code = str(row["code"])
        fields: dict[str, dict[str, str | None]] = {
            "identity": _availability(bool(code and row["name"])),
            "classification": _availability(
                row["is_active"] is not None and row["is_bond"] is not None
            ),
            "listing_date": _availability(
                bool(row["listing_date"]),
                as_of=row["listing_date"],
                reason="MASTER_LISTING_DATE_MISSING",
            ),
            "fund_size": _availability(
                row["fund_size"] is not None,
                reason="NO_VERIFIED_OFFICIAL_AUM_SOURCE",
            ),
            "expense_ratio": _availability(
                code in annual_expenses or row["expense_ratio"] is not None,
                as_of=(f"{annual_expenses[code].reporting_year}-12-31"
                       if code in annual_expenses else None),
                reason="NO_VERIFIED_TOTAL_EXPENSE_RATIO_SOURCE",
            ),
            "price_history": _availability(
                int(row["close_count"]) > 0,
                as_of=row["latest_close_date"],
                reason="NO_OFFICIAL_DAILY_CLOSE",
            ),
            "dividend_history": _availability(
                int(row["dividend_count"]) > 0,
                as_of=row["latest_dividend_date"],
                reason="NO_OFFICIAL_DIVIDEND_EVENT",
            ),
            "distribution_period": _availability(
                int(row["distribution_period_count"]) > 0,
                reason="SOURCE_DOES_NOT_DISCLOSE_DISTRIBUTION_PERIOD",
            ),
            "dividend_yield": _availability(
                int(row["yield_count"]) > 0,
                reason="NO_OFFICIAL_OR_CALCULABLE_REFERENCE_CLOSE",
            ),
            "stock_dividend": _availability(
                False,
                reason="NO_VERIFIED_SOURCE_AND_SCHEMA_FIELD",
            ),
            "estimated_components": _availability(
                int(row["estimated_component_event_count"]) > 0,
                reason="NO_COMPLETE_ETFORTUNE_ESTIMATE",
            ),
            "actual_components": _availability(
                int(row["actual_component_event_count"]) > 0,
                reason="NO_REVIEWED_ACTUAL_COMPONENT_NOTICE",
            ),
            "actual_76w": _availability(
                int(row["actual_76w_event_count"]) > 0,
                reason="NO_REVIEWED_ACTUAL_76W_DISCLOSURE",
            ),
            "historical_quality_grade": _availability(
                False,
                reason="PUBLICATION_EVIDENCE_GATE_NOT_MET",
            ),
        }
        for period in PERFORMANCE_PERIODS:
            fact = performance.get((code, period))
            fields[f"price_return_{period.lower()}"] = _availability(
                fact is not None,
                as_of=fact["as_of_date"] if fact else None,
                reason="INSUFFICIENT_OR_FAILED_PRICE_HISTORY",
            )

        items.append(
            {
                "etf_code": code,
                "name": row["name"],
                "is_active": bool(row["is_active"]),
                "is_bond": bool(row["is_bond"]),
                "counts": {
                    "daily_close": int(row["close_count"]),
                    "dividend": int(row["dividend_count"]),
                    "distribution_period": int(row["distribution_period_count"]),
                    "yield": int(row["yield_count"]),
                    "estimated_component_event": int(
                        row["estimated_component_event_count"]
                    ),
                    "actual_component_event": int(
                        row["actual_component_event_count"]
                    ),
                    "actual_76w_event": int(row["actual_76w_event_count"]),
                    "open_review_queue": int(row["open_review_count"]),
                },
                "fields": fields,
            }
        )

    batch_status = Counter(batch["status"] for batch in import_batches)
    return {
        "schema_version": 1,
        "generated_at": generated_at.astimezone(timezone.utc).isoformat(),
        "database": {
            "file_name": target.name,
            "size_bytes": target.stat().st_size,
            "sha256": sha256_file(target),
            "integrity_check": integrity,
            "foreign_key_violation_count": foreign_key_violations,
        },
        "universe_count": len(items),
        "field_coverage": _field_summary(items),
        "import_reconciliation": {
            "batch_count": len(import_batches),
            "status_counts": dict(sorted(batch_status.items())),
            "batches": import_batches,
        },
        "items": items,
        "notes": [
            "Missing official facts remain UNAVAILABLE and are never zero-filled.",
            "EST_REALIZED_CAPITAL_GAIN is not formal ACTUAL 76W.",
            "Historical quality remains unavailable until its publication evidence gate passes.",
        ],
    }


def write_coverage_report(
    report: dict[str, Any],
    output_path: str | Path,
) -> Path:
    target = Path(output_path)
    if target.exists():
        raise FileExistsError(f"output already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build V5 detailed-page data coverage evidence."
    )
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    report = build_detail_page_coverage(args.database)
    write_coverage_report(report, args.output)
    print(json.dumps(report["field_coverage"], ensure_ascii=False, indent=2))
    return 0 if report["database"]["integrity_check"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
