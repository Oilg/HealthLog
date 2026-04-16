import asyncio

import uvicorn
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from health_log.api.v1.analysis import router as analysis_router
from health_log.api.v1.auth import router as auth_router
from health_log.api.v1.error_handler import ErrorResponse, error_handler
from health_log.api.v1.handlers import request_exception_handler
from health_log.api.v1.sync import router as sync_router
from health_log.api.v1.users import router as users_router
from health_log.errors import BaseError
from health_log.limiter import limiter

SERVICE_NAME = "health-log"


def create_app() -> FastAPI:
    app = FastAPI(
        title=SERVICE_NAME,
        responses={
            500: {"model": ErrorResponse},
            400: {"model": ErrorResponse},
        }
    )

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]
    app.add_exception_handler(BaseError, error_handler)
    app.add_exception_handler(500, error_handler)
    app.add_exception_handler(RequestValidationError, request_exception_handler)  # type: ignore[arg-type]
    app.include_router(auth_router)
    app.include_router(users_router)
    app.include_router(sync_router)
    app.include_router(analysis_router)

    @app.on_event("startup")
    async def _start_scheduler() -> None:
        from health_log.services.sync_scheduler import run_sync_scheduler
        task = asyncio.create_task(run_sync_scheduler())
        app.state.scheduler_task = task

    @app.on_event("shutdown")
    async def _stop_scheduler() -> None:
        task = getattr(app.state, "scheduler_task", None)
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    return app


if __name__ == "__main__":
    app_ = create_app()
    uvicorn.run(app_)
