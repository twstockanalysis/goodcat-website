"""ETF奈米戶 FastAPI 應用程式入口。"""

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

from backend.app.api.router import api_router
from backend.app.api.exception_handlers import etf_not_found_handler
from backend.app.exceptions import ETFNotFoundError
from backend.app.security import (
    SecurityBoundaryMiddleware,
    sanitized_internal_exception_handler,
    sanitized_validation_exception_handler,
)


def create_app(
    *,
    public_rate_limit: int | None = None,
    private_rate_limit: int | None = None,
) -> FastAPI:
    """建立並設定 FastAPI 應用程式。

    Returns:
        FastAPI: 完成設定的 FastAPI 應用程式。
    """

    application = FastAPI(
        title="ETF奈米戶 API",
        description="台灣 ETF 分析網站後端 API",
        version="0.1.0",
        debug=False,
    )

    application.add_middleware(
        SecurityBoundaryMiddleware,
        public_rate_limit=public_rate_limit,
        private_rate_limit=private_rate_limit,
    )
    application.add_exception_handler(
        RequestValidationError,
        sanitized_validation_exception_handler,
    )
    application.add_exception_handler(
        Exception,
        sanitized_internal_exception_handler,
    )

    application.add_exception_handler(ETFNotFoundError, etf_not_found_handler)

    application.include_router(api_router)

    return application


app = create_app()
