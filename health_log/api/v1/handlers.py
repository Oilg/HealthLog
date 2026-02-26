from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import ORJSONResponse


async def request_exception_handler(request: Request, exc: RequestValidationError) -> ORJSONResponse:
    return ORJSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"detail": exc.errors()})
