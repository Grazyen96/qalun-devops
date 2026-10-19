"""The worker: takes a job from the queue, runs QuranText on it, stores what came out.

It runs as RQ's SimpleWorker, one job at a time in its own process, because a
job holds about a gigabyte of memory while it transcribes; more throughput means
more worker replicas, not more jobs per worker.
"""

from __future__ import annotations

import logging
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

from qurantext.utils.progress import ProgressEvent
from redis import Redis

from qalun_web import metrics as m
from qalun_web.settings import Settings
from qalun_web.store import JobStore

QUEUE_NAME = "qalun"
FAILED_MESSAGE = (
    "This recording could not be processed. Check that it is an audio file of a "
    "Quran recitation or a lecture, and try again."
)

log = logging.getLogger(__name__)

Runner = Callable[..., dict[str, Path]]


def process_job(job_id: str, *, store: JobStore, runner: Runner) -> None:
    job = store.get(job_id)
    audio = store.audio(job_id)
    if job is None or audio is None:
        log.warning("Job %s expired before a worker reached it.", job_id)
        return

    store.mark_running(job_id)
    started = time.monotonic()

    def progress(event: ProgressEvent) -> None:
        store.set_progress(job_id, stage=event.stage, fraction=event.fraction)

    with tempfile.TemporaryDirectory(prefix="qalun-job-") as tmp:
        workdir = Path(tmp)
        recording = workdir / f"recording{Path(job.filename).suffix.lower()}"
        recording.write_bytes(audio)
        try:
            outputs = runner(
                recording, mode=job.mode, surah=job.surah, workdir=workdir, progress=progress
            )
            files = {name: path.read_bytes() for name, path in outputs.items()}
        except Exception:
            # The details go to the log; the person gets a sentence without server paths.
            log.exception("Job %s failed.", job_id)
            store.mark_failed(job_id, FAILED_MESSAGE)
            _count(job.mode, "failed", started)
            return
    store.mark_done(job_id, files)
    _count(job.mode, "done", started)


def _count(mode: str, result: str, started: float) -> None:
    m.JOBS_FINISHED.labels(mode=mode, result=result).inc()
    m.JOB_DURATION.labels(mode=mode).observe(time.monotonic() - started)


def run_job(job_id: str) -> None:
    """What RQ calls: the real store and the real pipeline."""
    from qalun_web.pipeline import run_qurantext

    settings = Settings.from_env()
    store = JobStore(Redis.from_url(settings.redis_url), ttl_seconds=settings.result_ttl_seconds)
    process_job(job_id, store=store, runner=run_qurantext)


def main() -> None:
    from prometheus_client import start_http_server
    from rq import Queue, SimpleWorker

    logging.basicConfig(level=logging.INFO)
    settings = Settings.from_env()
    # SimpleWorker runs each job in this process, so its counters are the ones served here.
    start_http_server(settings.worker_metrics_port)
    redis = Redis.from_url(settings.redis_url)
    SimpleWorker([Queue(QUEUE_NAME, connection=redis)], connection=redis).work()
