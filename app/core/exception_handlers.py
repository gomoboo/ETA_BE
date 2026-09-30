import logging
from http import HTTPStatus
from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import AppException, ErrorCode
from app.schemas.common import ErrorResponse

logger = logging.getLogger(__name__)

# HTTPException 상태 코드 -> 표준 에러 코드 매핑
_STATUS_TO_ERROR_CODE = {
    400: ErrorCode.INVALID_INPUT,
    401: ErrorCode.UNAUTHORIZED,
    403: ErrorCode.FORBIDDEN,
    404: ErrorCode.NOT_FOUND,
    405: ErrorCode.METHOD_NOT_ALLOWED,
    409: ErrorCode.CONFLICT,
}


def _error_response(status_code: int, code: str, message: str, data: Optional[Any] = None) -> JSONResponse:
    body = ErrorResponse(code=code, message=message, data=data)
    return JSONResponse(status_code=status_code, content=body.model_dump())


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    return _error_response(exc.status_code, exc.code, exc.message)


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    error_code = _STATUS_TO_ERROR_CODE.get(exc.status_code)
    code = error_code.name if error_code else f"HTTP_{exc.status_code}"
    # detail 미지정 시 Starlette가 넣는 기본 문구("Not Found" 등)는 표준 메시지로 대체
    default_phrase = HTTPStatus(exc.status_code).phrase
    if isinstance(exc.detail, str) and exc.detail and exc.detail != default_phrase:
        message = exc.detail
    else:
        message = error_code.message if error_code else "요청을 처리할 수 없습니다."
    return _error_response(exc.status_code, code, message)


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = [
        {
            # loc 첫 요소는 위치(body/query/path/header/cookie)이므로 제외
            "field": ".".join(str(loc) for loc in err["loc"][1:]),
            # 커스텀 validator 메시지에 Pydantic이 붙이는 접두어 제거
            "reason": err["msg"].removeprefix("Value error, "),
        }
        for err in exc.errors()
    ]
    error_code = ErrorCode.INVALID_INPUT
    return _error_response(error_code.status_code, error_code.name, error_code.message, errors)


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception: %s %s", request.method, request.url.path)
    error_code = ErrorCode.INTERNAL_SERVER_ERROR
    return _error_response(error_code.status_code, error_code.name, error_code.message)


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
