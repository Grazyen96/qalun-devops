"""The HTTP side: the page, the job API, and the endpoints Kubernetes and Prometheus use.

The API never runs QuranText itself. It checks an upload, keeps it in Redis and
hands the job's id to the worker queue, so a request returns in milliseconds and
any number of API replicas can sit behind the ingress.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable
from pathlib import Path, PurePath
from urllib.parse import quote

from fastapi import FastAPI, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.security import HTTPBasic
from fastapi.staticfiles import StaticFiles
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from redis import Redis
from redis.exceptions import RedisError

from qalun_web import metrics as m
from qalun_web.settings import Settings
from qalun_web.store import Job, JobStore

STATIC_DIR = Path(__file__).parent / "static"
MODES = ("recitation", "lecture")
#: What ffmpeg reads and a person is likely to have: audio, and the videos phones record.
RECORDING_SUFFIXES = frozenset(
    {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".opus", ".flac", ".mp4", ".webm", ".mov"}
)
#: What the cluster calls: never behind the password, or probes and scrapes would fail.
OPEN_PATHS = frozenset({"/healthz", "/readyz", "/metrics"})
_CHUNK = 1 << 20
_DOWNLOADS = {
    "srt": ("srt", "application/x-subrip; charset=utf-8"),
    "vtt": ("vtt", "text/vtt; charset=utf-8"),
    "json": ("matches.json", "application/json"),
}


def create_app(
    settings: Settings,
    *,
    redis: Redis,
    enqueue: Callable[[str], None],
    queue_length: Callable[[], int] | None = None,
) -> FastAPI:
    app = FastAPI(title="Qalun web", docs_url=None, redoc_url=None, openapi_url=None)
    store = JobStore(redis, ttl_seconds=settings.result_ttl_seconds)

    # --- open: what the cluster calls ------------------------------------------------

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

    @app.get("/metrics")
    def metrics() -> Response:
        if queue_length is not None:
            try:
                m.JOBS_WAITING.set(queue_length())
            except RedisError:
                pass  # The scrape still succeeds; the gauge keeps its last value.
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    # --- behind the password, when one is set: what a person uses ----------------------

    @app.get("/")
    def page() -> FileResponse:
        m.PAGE_VIEWS.inc()
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/surahs")
    def surah_list() -> list[dict]:
        from qalun_web.pipeline import surahs

        return list(surahs())

    @app.post("/api/jobs", status_code=202)
    async def create_job(
        file: UploadFile, mode: str = Form(...), surah: int | None = Form(None)
    ) -> dict:
        counted_mode = mode if mode in MODES else "other"

        def refuse(status: int, reason: str, message: str) -> HTTPException:
            m.UPLOADS.labels(mode=counted_mode, result=reason).inc()
            return HTTPException(status, message)

        if mode not in MODES:
            raise refuse(400, "bad_mode", f"Mode must be one of: {', '.join(MODES)}.")
        if surah is not None and not 1 <= surah <= 114:
            raise refuse(400, "bad_surah", "Surah must be a number from 1 to 114.")
        filename = PurePath(file.filename or "").name
        if PurePath(filename).suffix.lower() not in RECORDING_SUFFIXES:
            raise refuse(
                415, "wrong_type", "Upload an audio recording (MP3, WAV, M4A, OGG, FLAC, MP4…)."
            )
        audio = await _read_capped(file, settings.max_upload_bytes)
        if audio is None:
            limit_mb = settings.max_upload_bytes // (1024 * 1024)
            raise refuse(413, "too_large", f"The recording is larger than {limit_mb} MB.")
        if not audio:
            raise refuse(400, "empty", "The file is empty.")
        job_id = store.create(audio=audio, filename=filename, mode=mode, surah=surah)
        enqueue(job_id)
        m.UPLOADS.labels(mode=mode, result="accepted").inc()
        return {"id": job_id, "status_url": f"/api/jobs/{job_id}"}

    @app.get("/api/jobs/{job_id}")
    def job_status(job_id: str) -> dict:
        return _describe(_existing(store, job_id))

    @app.get("/api/jobs/{job_id}/files/{name}")
    def download(job_id: str, name: str) -> Response:
        job = _existing(store, job_id)
        content = store.file(job_id, name) if name in job.files and name in _DOWNLOADS else None
        if content is None:
            raise HTTPException(404, "This job has no such file.")
        m.DOWNLOADS.labels(file=name).inc()
        suffix, media_type = _DOWNLOADS[name]
        download_name = f"{PurePath(job.filename).stem}.{suffix}"
        return Response(
            content,
            media_type=media_type,
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(download_name)}"},
        )

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    if settings.access_password:
        app.middleware("http")(_password_guard(settings.access_password))
    return app


def create_app_from_env() -> FastAPI:
    """What uvicorn starts in the container: the real Redis and the real queue."""
    from rq import Queue

    from qalun_web.worker import QUEUE_NAME

    settings = Settings.from_env()
    redis = Redis.from_url(settings.redis_url)
    queue = Queue(QUEUE_NAME, connection=redis)

    def enqueue(job_id: str) -> None:
        queue.enqueue(
            "qalun_web.worker.run_job",
            job_id,
            job_timeout=settings.job_timeout_seconds,
            result_ttl=0,
            failure_ttl=settings.result_ttl_seconds,
        )

    return create_app(settings, redis=redis, enqueue=enqueue, queue_length=lambda: queue.count)


# --- helpers ---------------------------------------------------------------------------


def _existing(store: JobStore, job_id: str) -> Job:
    job = store.get(job_id)
    if job is None:
        raise HTTPException(404, "There is no such job, or it has expired.")
    return job


def _describe(job: Job) -> dict:
    return {
        "id": job.id,
        "status": job.status,
        "mode": job.mode,
        "surah": job.surah,
        "filename": job.filename,
        "stage": job.stage,
        "fraction": job.fraction,
        "error": job.error,
        "files": [{"name": name, "url": f"/api/jobs/{job.id}/files/{name}"} for name in job.files],
    }


async def _read_capped(file: UploadFile, limit: int) -> bytes | None:
    """The upload's bytes, or None as soon as it passes *limit*."""
    chunks: list[bytes] = []
    size = 0
    while chunk := await file.read(_CHUNK):
        size += len(chunk)
        if size > limit:
            return None
        chunks.append(chunk)
    return b"".join(chunks)


_basic = HTTPBasic(auto_error=False, realm="Qalun")


def _password_guard(password: str):
    """One shared password for everything a person uses; the user name is not checked."""
    expected = password.encode()

    async def guard(request: Request, call_next):
        if request.url.path not in OPEN_PATHS:
            credentials = await _basic(request)
            if credentials is None or not secrets.compare_digest(
                credentials.password.encode(), expected
            ):
                return JSONResponse(
                    {"detail": "Password required."},
                    status_code=401,
                    headers={"WWW-Authenticate": 'Basic realm="Qalun"'},
                )
        return await call_next(request)

    return guard
