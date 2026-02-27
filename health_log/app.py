import uvicorn
from importlib.util import find_spec

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

from health_log.api.v1.error_handler import ErrorResponse, error_handler
from health_log.api.v1.handlers import request_exception_handler
from health_log.errors import BaseError

SERVICE_NAME = "health-log"


def create_app() -> FastAPI:
    app = FastAPI(
        title=SERVICE_NAME,
        responses={
            500: {"model": ErrorResponse},
            400: {"model": ErrorResponse},
        }
    )

    app.add_exception_handler(BaseError, error_handler)
    app.add_exception_handler(500, error_handler)
    app.add_exception_handler(RequestValidationError, request_exception_handler)
    if find_spec("multipart"):
        from health_log.api.v1.uploads import router as uploads_router

        app.include_router(uploads_router)

    return app


if __name__ == "__main__":
    app_ = create_app()
    uvicorn.run(app_)
