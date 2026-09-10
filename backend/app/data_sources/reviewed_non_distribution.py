"""Replay only the two owner-reviewed transcriptions; no automatic source fetch."""

import argparse
from contextlib import closing
from datetime import date
from pathlib import Path
import sqlite3

from backend.app.database.init_db import initialize_database
from backend.app.models.non_distribution import NonDistributionNotice
from backend.app.repositories.non_distribution_repository import save_non_distribution_notices


def reviewed_notices() -> list[NonDistributionNotice]:
    records = [
        ("00660", "元大已開發國家傘型證券投資信託基金之元大歐洲50證券投資信託基金",
         "2025-09-30", "2025-10-01", "www.twse.com.tw", "A00005"),
        ("00920", "富邦全球ESG綠色電力ETF證券投資信託基金",
         "2025-12-31", "2026-01-02", "wwwc.twse.com.tw", "A00010"),
    ]
    return [NonDistributionNotice(
        etf_code=code, legal_name=name, evaluation_date=evaluation,
        publication_date=publication, reviewed_on=date(2026, 9, 10),
        source_url=(f"https://{host}/zh/ETFortune/announcement?company={company}"
                    f"&date={publication.replace('-', '')}&fund={code}&seq=1&type=all"),
        review_reference="https://github.com/twstockanalysis/goodcat-website/issues/133",
    ) for code, name, evaluation, publication, host, company in records]


def create_candidate(source_db: Path, target_db: Path, *, evaluated_on: date) -> int:
    notices = reviewed_notices()
    if any(n.publication_date > evaluated_on for n in notices):
        raise ValueError("Publication after evaluation date")
    source_db = source_db.resolve(strict=True)
    target_db = target_db.resolve()
    target_db.parent.mkdir(parents=True, exist_ok=True)
    with target_db.open("xb"):
        pass
    with closing(sqlite3.connect(source_db.as_uri() + "?mode=ro", uri=True)) as source, \
            closing(sqlite3.connect(target_db)) as target:
        source.backup(target)
    initialize_database(target_db)
    return save_non_distribution_notices(notices, target_db, evaluated_on=evaluated_on)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-db", type=Path, required=True)
    parser.add_argument("--target-db", type=Path, required=True)
    parser.add_argument("--evaluated-on", type=date.fromisoformat, required=True)
    args = parser.parse_args()
    print(create_candidate(args.source_db, args.target_db, evaluated_on=args.evaluated_on))


if __name__ == "__main__":
    main()
