"""Translate explicit domain failures without masking programming errors."""

from fastapi import Request, status
from fastapi.responses import JSONResponse

from backend.app.exceptions import ETFNotFoundError


async def etf_not_found_handler(
    request: Request, exception: ETFNotFoundError,
) -> JSONResponse:
    """Preserve the public ETF-not-found response for single or multiple codes."""
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": "找不到 ETF：" + ", ".join(exception.codes)},
    )
