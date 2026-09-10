"""ETF 主資料 Repository。"""

import sqlite3
from datetime import date
from pathlib import Path
from typing import Any

from backend.app.database.connection import get_connection
from backend.app.repositories.annual_expense_repository import annual_expense_catalog, enrich_expense


ETF_SELECT_COLUMNS = """
    code,
    name,
    is_active,
    is_bond,
    listing_date,
    fund_size,
    expense_ratio
"""


def row_to_dictionary(
    row: sqlite3.Row,
) -> dict[str, Any]:
    """將 SQLite Row 轉換成一般字典。

    Args:
        row: SQLite 查詢結果。

    Returns:
        dict[str, Any]: 可交由 API 處理的字典。
    """

    return {
        key: row[key]
        for key in row.keys()
    }


def build_filter_clause(
    keyword: str | None = None,
    is_active: bool | None = None,
    is_bond: bool | None = None,
) -> tuple[str, list[Any]]:
    """建立 ETF 查詢條件及 SQL 參數。

    Args:
        keyword:
            搜尋 ETF 代號或名稱。
        is_active:
            是否篩選主動式 ETF。
        is_bond:
            是否篩選債券 ETF。

    Returns:
        tuple[str, list[Any]]:
            SQL WHERE 子句及對應參數。
    """

    conditions: list[str] = []
    parameters: list[Any] = []

    if keyword is not None:
        normalized_keyword = keyword.strip()

        if normalized_keyword:
            search_pattern = f"%{normalized_keyword}%"

            conditions.append(
                """
                (
                    code LIKE ? COLLATE NOCASE
                    OR name LIKE ?
                )
                """
            )

            parameters.extend(
                [
                    search_pattern,
                    search_pattern,
                ]
            )

    if is_active is not None:
        conditions.append(
            "is_active = ?"
        )
        parameters.append(
            int(is_active)
        )

    if is_bond is not None:
        conditions.append(
            "is_bond = ?"
        )
        parameters.append(
            int(is_bond)
        )

    if not conditions:
        return "", parameters

    where_clause = (
        "WHERE "
        + " AND ".join(conditions)
    )

    return where_clause, parameters


def list_etfs(
    database_path: str | Path | None = None,
    keyword: str | None = None,
    is_active: bool | None = None,
    is_bond: bool | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """取得符合條件的 ETF 分頁資料。

    Args:
        database_path:
            指定資料庫路徑。
        keyword:
            搜尋 ETF 代號或名稱。
        is_active:
            是否篩選主動式 ETF。
        is_bond:
            是否篩選債券 ETF。
        limit:
            單次回傳筆數。
        offset:
            略過筆數。

    Returns:
        list[dict[str, Any]]: ETF 資料列表。
    """

    where_clause, parameters = (
        build_filter_clause(
            keyword=keyword,
            is_active=is_active,
            is_bond=is_bond,
        )
    )

    query_parameters = [
        *parameters,
        limit,
        offset,
    ]

    connection = get_connection(
        database_path
    )

    try:
        rows = connection.execute(
            f"""
            SELECT
                {ETF_SELECT_COLUMNS}
            FROM etf_master
            {where_clause}
            ORDER BY code
            LIMIT ?
            OFFSET ?;
            """,
            query_parameters,
        ).fetchall()

        expenses = annual_expense_catalog(connection, evaluated_on=date.today())
        return [
            enrich_expense(row_to_dictionary(row), expenses)
            for row in rows
        ]

    finally:
        connection.close()


def count_etfs(
    database_path: str | Path | None = None,
    keyword: str | None = None,
    is_active: bool | None = None,
    is_bond: bool | None = None,
) -> int:
    """計算符合查詢條件的 ETF 總筆數。

    Args:
        database_path:
            指定資料庫路徑。
        keyword:
            搜尋 ETF 代號或名稱。
        is_active:
            是否篩選主動式 ETF。
        is_bond:
            是否篩選債券 ETF。

    Returns:
        int: 符合條件的 ETF 總筆數。
    """

    where_clause, parameters = (
        build_filter_clause(
            keyword=keyword,
            is_active=is_active,
            is_bond=is_bond,
        )
    )

    connection = get_connection(
        database_path
    )

    try:
        result = connection.execute(
            f"""
            SELECT COUNT(*) AS total
            FROM etf_master
            {where_clause};
            """,
            parameters,
        ).fetchone()

        return int(result["total"])

    finally:
        connection.close()


def get_etf_by_code(
    code: str,
    database_path: str | Path | None = None,
) -> dict[str, Any] | None:
    """依 ETF 代號取得單筆主資料。

    Args:
        code: ETF 證券代號。
        database_path:
            指定資料庫路徑。

    Returns:
        dict[str, Any] | None:
            找到時回傳資料，否則回傳 None。
    """

    normalized_code = code.strip().upper()

    if not normalized_code:
        return None

    connection = get_connection(
        database_path
    )

    try:
        row = connection.execute(
            f"""
            SELECT
                {ETF_SELECT_COLUMNS}
            FROM etf_master
            WHERE code = ?;
            """,
            (normalized_code,),
        ).fetchone()

        if row is None:
            return None

        return enrich_expense(row_to_dictionary(row), annual_expense_catalog(connection, evaluated_on=date.today()))

    finally:
        connection.close()
