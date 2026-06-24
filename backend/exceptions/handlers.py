"""exceptions/handlers.py - FastAPI 全局异常处理

注册的 handler:
- domain_exception_handler: 业务异常 (StrategyCompileError 等) → 400 + ErrorResponse
- validation_exception_handler: Pydantic 422 → 友好中文消息
- global_exception_handler: 兜底 → 500 + ErrorResponse
"""
import traceback
from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from backend.core.logging import log
from backend.exceptions.domain import DomainError
from backend.exceptions.schemas import ErrorResponse


async def domain_exception_handler(request: Request, exc: DomainError):
    """业务异常 → 400 + 结构化 ErrorResponse"""
    log.warning(f"[DOMAIN] {request.method} {request.url.path} → {exc.type if hasattr(exc, 'type') else type(exc).__name__}: {exc}")
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content=ErrorResponse.from_exception(exc, path=request.url.path).model_dump(exclude_none=True),
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Pydantic 校验错误 → 422 + 中文友好消息"""
    errs = exc.errors()
    first = errs[0] if errs else {}
    loc = ".".join(str(x) for x in first.get("loc", []))
    msg = first.get("msg", "校验失败")
    typ = first.get("type", "validation_error")
    log.warning(f"[VALIDATION] {request.method} {request.url.path} → "
                f"loc={loc} type={typ} msg={msg}")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=ErrorResponse(
            error=f"参数校验失败: {msg} ({loc})",
            type=typ,
            path=request.url.path,
            details={"loc": loc, "errors": errs},
        ).model_dump(exclude_none=True),
    )


async def global_exception_handler(request: Request, exc: Exception):
    """兜底异常处理: 任何没被 endpoint 捕获的异常都进日志, 前端拿到结构化错误"""
    tb = traceback.format_exc()
    log.error(f"[UNCAUGHT] {request.method} {request.url.path} → "
              f"{type(exc).__name__}: {exc}\n{tb}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse(
            error=f"{type(exc).__name__}: {exc}",
            type=type(exc).__name__,
            path=request.url.path,
        ).model_dump(exclude_none=True),
    )


def register_exception_handlers(app):
    """在 FastAPI app 上注册所有 handler (app.py 里调一次)

    用法:
        from backend.exceptions.handlers import register_exception_handlers
        register_exception_handlers(app)
    """
    app.add_exception_handler(DomainError, domain_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, global_exception_handler)