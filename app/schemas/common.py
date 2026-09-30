from pydantic import BaseModel
from typing import Generic, TypeVar, Optional, Any

T = TypeVar("T")

class BaseResponse(BaseModel, Generic[T]):
    """성공 응답 공통 규격"""
    success: bool = True
    data: Optional[T] = None
    message: Optional[str] = None

class ErrorResponse(BaseModel):
    """실패 응답 공통 규격"""
    success: bool = False
    code: str
    message: str
    data: Optional[Any] = None
