"""exceptions/schemas.py - 错误响应模型 (Pydantic)

所有 controller 报错都返回这套结构, 前端按 .error / .type / .path 展示。
"""
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    """统一错误响应 schema"""
    error: str = Field(..., description="人类可读的错误消息")
    type: str = Field("error", description="错误类型 (与 exceptions/domain.py 的 code 对应)")
    path: Optional[str] = Field(None, description="请求路径")
    details: Optional[Dict[str, Any]] = Field(None, description="额外上下文 (字段名, 索引等)")

    @classmethod
    def from_exception(cls, exc, *, path: Optional[str] = None) -> "ErrorResponse":
        if hasattr(exc, "code") and hasattr(exc, "message"):
            return cls(error=exc.message, type=exc.code, path=path,
                       details=getattr(exc, "details", None) or None)
        return cls(error=str(exc), type=type(exc).__name__, path=path)