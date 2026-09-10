"""Hash-locked import of reviewed evidence, not a generic PDF/approval parser."""

import argparse
from contextlib import closing
from datetime import date, datetime
import hashlib
from pathlib import Path
import sqlite3

from backend.app.database.init_db import initialize_database
from backend.app.models.annual_expense import AnnualExpenseEvidence
from backend.app.repositories.annual_expense_repository import save_annual_expenses


REVIEWED_SHA256 = "b098c8bd46ccc01037fbbf319c10465646475ba69598542941ebd2b3a2b39e50"
SOURCE_URL = "https://www.yuantafunds.com/fund/download/1084台灣高股息-簡式公開說明書.pdf"
REVIEW_REFERENCE = "https://github.com/twstockanalysis/goodcat-website/issues/130"


def reviewed_observations(pdf_path: Path) -> list[AnnualExpenseEvidence]:
    with pdf_path.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    if digest != REVIEWED_SHA256:
        raise ValueError("Unknown document hash; new document review required")
    # Transcription of visually reviewed page 3, bound to the exact document.
    # No arbitrary file parsing, fuzzy identity matching or NA-to-zero conversion.
    return [AnnualExpenseEvidence(
        etf_code="0056", issuer_product_id="1084",
        legal_name="元大台灣高股息證券投資信託基金",
        reporting_year=year, expense_ratio_pct=ratio,
        publication_date=date(2026, 7, 29),
        retrieved_at=datetime.fromisoformat("2026-09-08T14:38:05+00:00"),
        source_url=SOURCE_URL,
        identity_url="https://www.yuantafunds.com/myfund/information/1084",
        document_sha256=digest, document_page=3,
        review_reference=REVIEW_REFERENCE,
    ) for year, ratio in zip(range(2021, 2026), ("0.74", "0.86", "0.56", "0.60", "0.57"))]


def create_candidate(source_db: Path, target_db: Path, pdf_path: Path, *, evaluated_on: date) -> int:
    values = reviewed_observations(pdf_path)
    if any(v.publication_date > evaluated_on for v in values):
        raise ValueError("Document publication is after evaluation date")
    source_db = source_db.resolve(strict=True)
    target_db = target_db.resolve()
    target_db.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation prevents overwriting any source/candidate, including aliases.
    with target_db.open("xb"):
        pass
    with closing(sqlite3.connect(source_db.as_uri() + "?mode=ro", uri=True)) as source, \
            closing(sqlite3.connect(target_db)) as target:
        source.backup(target)
    initialize_database(target_db)
    return save_annual_expenses(values, target_db, evaluated_on=evaluated_on)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-db", type=Path, required=True)
    parser.add_argument("--target-db", type=Path, required=True)
    parser.add_argument("--reviewed-pdf", type=Path, required=True)
    parser.add_argument("--evaluated-on", type=date.fromisoformat, required=True)
    args = parser.parse_args()
    print(create_candidate(args.source_db, args.target_db, args.reviewed_pdf,
                           evaluated_on=args.evaluated_on))


if __name__ == "__main__":
    main()
