"""The HTTP side: the page, the job API, and the endpoints Kubernetes and Prometheus use."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from redis import Redis
from redis.exceptions import RedisError

from qalun_web.settings import Settings


def create_app(settings: Settings, *, redis: Redis, enqueue: Callable[[str], None]) -> FastAPI:
    app = FastAPI(title="Qalun web", docs_url=None, redoc_url=None)

    @app.get("/healthz")
    def healthz() -> dict:
        # Liveness only: the process answers. Redis being down must not get the pod killed.
        return {"status": "ok"}

    @app.get("/readyz")
    def readyz() -> JSONResponse:
        # Readiness: without Redis no job can be accepted, so take this pod out of rotation.
        try:
            redis.ping()
        except RedisError:
            return JSONResponse({"status": "redis unavailable"}, status_code=503)
        return JSONResponse({"status": "ok"})

    return app
