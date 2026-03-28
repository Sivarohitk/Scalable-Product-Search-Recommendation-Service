import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request, Response

from app import __version__
from app.api.router import api_router
from app.cache.client import RedisProbe
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.request_context import reset_request_id, set_request_id
from app.db.session import DatabaseProbe
from app.observability.metrics import record_http_request
from app.services.health import HealthService

http_logger = logging.getLogger("app.http")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings)

    database_probe = DatabaseProbe(settings.database_url, settings.health_timeout_seconds)
    redis_probe = RedisProbe(settings.redis_url, settings.health_timeout_seconds)
    app.state.health_service = HealthService(
        service_name=settings.service_name,
        environment=settings.environment,
        checks=(database_probe, redis_probe),
    )
    app.state.database_probe = database_probe
    app.state.redis_probe = redis_probe

    yield

    await redis_probe.close()
    await database_probe.close()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Scalable Product Search & Recommendation Service",
        description=(
            "Hybrid search, autocomplete, and recommendations backend "
            "for product discovery demos."
        ),
        version=__version__,
        lifespan=lifespan,
    )

    @app.middleware("http")
    async def observability_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = request.headers.get("X-Request-ID", str(uuid4()))
        context_token = set_request_id(request_id)
        started_at = perf_counter()
        status_code = 500

        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        except Exception:
            http_logger.exception(
                "request.failed",
                extra={"method": request.method, "path": request.url.path},
            )
            raise
        finally:
            elapsed_seconds = perf_counter() - started_at
            duration_ms = round(elapsed_seconds * 1000, 2)
            record_http_request(request.method, request.url.path, str(status_code), elapsed_seconds)
            http_logger.info(
                "request.completed",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": status_code,
                    "duration_ms": duration_ms,
                },
            )
            reset_request_id(context_token)

    @app.get("/", tags=["meta"])
    async def root() -> dict[str, str]:
        return {
            "service": settings.service_name,
            "environment": settings.environment,
            "docs_url": "/docs",
        }

    app.include_router(api_router)
    return app


app = create_app()
