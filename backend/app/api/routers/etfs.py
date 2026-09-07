"""ETF 主資料 API 路由。"""

from datetime import date
from pathlib import Path
from typing import Annotated, Any

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
)

from backend.app.api.dependencies import (
    get_database_path,
)
from backend.app.models.etf import (
    ETFListResponse,
    ETFResponse,
)
from backend.app.models.etf_comparison_api import (
    ETFComparisonResponse,
)
from backend.app.models.etf_data_profile_api import (
    ETFDataProfileResponse,
)
from backend.app.models.quality_grade_api import (
    ETFHistoricalQualityGradeResponse,
)
from backend.app.repositories.etf_comparison_repository import (
    build_etf_comparison,
    parse_comparison_codes,
)
from backend.app.repositories.etf_data_profile_repository import (
    build_etf_data_profile,
)
from backend.app.repositories.etf_repository import (
    count_etfs,
    get_etf_by_code,
    list_etfs,
)
from backend.app.services.quality_grade_catalog import (
    DEFAULT_PUBLIC_GRADE_HISTORY_YEARS,
    build_quality_grade_catalog,
    normalize_quality_grade_codes,
)


DatabasePath = Annotated[
    Path,
    Depends(get_database_path),
]


router = APIRouter(
    prefix="/api/v1/etfs",
    tags=["ETFs"],
)


@router.get(
    "/historical-quality-grades",
    response_model=ETFHistoricalQualityGradeResponse,
    summary="取得 ETF 歷史品質評等",
)
def read_historical_quality_grades(
    database_path: DatabasePath,
    codes: Annotated[
        str,
        Query(
            min_length=1,
            max_length=1099,
            description="逗號分隔的 1 至 100 個 ETF 代號",
        ),
    ],
) -> dict[str, Any]:
    """為公開探索頁提供與配置流程相同的版本化評等語意。"""

    try:
        normalized_codes = normalize_quality_grade_codes(codes)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        ) from error

    catalog = build_quality_grade_catalog(database_path)
    unknown_codes = [code for code in normalized_codes if code not in catalog]
    if unknown_codes:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="找不到 ETF：" + "、".join(unknown_codes),
        )

    return {
        "analysis_date": date.today(),
        "history_years": DEFAULT_PUBLIC_GRADE_HISTORY_YEARS,
        "items": [
            {
                "etf_code": code,
                "historical_quality_grade": catalog[code],
            }
            for code in normalized_codes
        ],
    }


@router.get(
    "",
    response_model=ETFListResponse,
    summary="取得 ETF 列表",
)
def read_etfs(
    database_path: DatabasePath,
    keyword: Annotated[
        str | None,
        Query(
            min_length=1,
            max_length=50,
            description="搜尋 ETF 代號或名稱",
        ),
    ] = None,
    is_active: Annotated[
        bool | None,
        Query(
            description="篩選主動式或被動式 ETF",
        ),
    ] = None,
    is_bond: Annotated[
        bool | None,
        Query(
            description="篩選債券或非債券 ETF",
        ),
    ] = None,
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=100,
            description="單次回傳筆數",
        ),
    ] = 20,
    offset: Annotated[
        int,
        Query(
            ge=0,
            description="略過筆數",
        ),
    ] = 0,
) -> dict[str, Any]:
    """取得符合條件的 ETF 分頁列表。

    Args:
        database_path:
            FastAPI 注入的資料庫路徑。
        keyword:
            ETF 代號或名稱關鍵字。
        is_active:
            是否為主動式 ETF。
        is_bond:
            是否為債券 ETF。
        limit:
            單次回傳筆數。
        offset:
            略過筆數。

    Returns:
        dict[str, Any]: ETF 分頁資料。
    """

    items = list_etfs(
        database_path=database_path,
        keyword=keyword,
        is_active=is_active,
        is_bond=is_bond,
        limit=limit,
        offset=offset,
    )

    total = count_etfs(
        database_path=database_path,
        keyword=keyword,
        is_active=is_active,
        is_bond=is_bond,
    )

    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get(
    "/comparison",
    response_model=ETFComparisonResponse,
    summary="比較 2 至 4 檔 ETF",
)
def read_etf_comparison(
    database_path: DatabasePath,
    codes: Annotated[
        str,
        Query(
            min_length=1,
            description=(
                "逗號分隔的 2 至 4 個 ETF 代號"
            ),
            examples=["0050,0056"],
        ),
    ],
) -> dict[str, Any]:
    """回傳 ETF 基本資料、績效、配息、76W 與完整度。"""

    try:
        normalized_codes = (
            parse_comparison_codes(
                codes
            )
        )

    except ValueError as error:
        raise HTTPException(
            status_code=(
                status.HTTP_422_UNPROCESSABLE_ENTITY
            ),
            detail=str(error),
        ) from error

    return build_etf_comparison(
        codes=normalized_codes,
        database_path=database_path,
    )


@router.get(
    "/{code}/data-profile",
    response_model=ETFDataProfileResponse,
    summary="取得 ETF 資料來源與新鮮度",
)
def read_etf_data_profile(
    code: str,
    database_path: DatabasePath,
) -> dict[str, Any]:
    """回傳單一 ETF 的來源、覆蓋與最新日期。"""

    normalized_code = (
        code.strip().upper()
    )

    profile = build_etf_data_profile(
        etf_code=normalized_code,
        database_path=database_path,
    )

    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"找不到 ETF："
                f"{normalized_code}"
            ),
        )

    return profile


@router.get(
    "/{code}",
    response_model=ETFResponse,
    summary="依代號查詢 ETF",
)
def read_etf(
    code: str,
    database_path: DatabasePath,
) -> dict[str, Any]:
    """依 ETF 代號取得單筆資料。

    Args:
        code: ETF 證券代號。
        database_path:
            FastAPI 注入的資料庫路徑。

    Returns:
        dict[str, Any]: ETF 主資料。

    Raises:
        HTTPException:
            找不到指定 ETF 時回傳 HTTP 404。
    """

    normalized_code = code.strip().upper()

    etf = get_etf_by_code(
        normalized_code,
        database_path,
    )

    if etf is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"找不到 ETF：{normalized_code}",
        )

    return etf
