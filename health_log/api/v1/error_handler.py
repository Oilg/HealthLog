import logging

from fastapi import Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from health_log.errors import BaseError

logger = logging.getLogger(__name__)


class ErrorResponse(BaseModel):
    message: str
    code: str


async def error_handler(request: Request, exc: Exception) -> JSONResponse:
    status_code = getattr(exc, "status_code", status.HTTP_500_INTERNAL_SERVER_ERROR)
    if status_code == status.HTTP_500_INTERNAL_SERVER_ERROR and not isinstance(exc, BaseError):
        logger.exception("Unhandled exception on %s %s", request.method, request.url.path, exc_info=exc)
    base_error = BaseError()
    content = ErrorResponse(
        message=getattr(exc, "message", base_error.message),
        code=getattr(exc, "code", base_error.code),
    ).model_dump()
    return JSONResponse(
        status_code=status_code,
        content=content,
    )

EXCEPTION_HANDLERS = {BaseError: error_handler}
