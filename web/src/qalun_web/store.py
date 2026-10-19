"""Jobs in Redis: what was asked, how far along it is, and what came out.

Redis holds everything, the recording and the results included, so neither the
API nor the worker keeps anything on its own disk and any replica can answer for
any job. Every key expires, which is what keeps the store from growing: the
course allows the persistence layer to be ephemeral, and nothing here is meant
to outlive a day.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

from redis import Redis

_PREFIX = "qalun:job:"


@dataclass(frozen=True)
class Job:
    id: str
    status: str  # queued | running | done | failed
    mode: str
    surah: int | None
    filename: str
    created_at: float
    stage: str
    fraction: float | None
    error: str
    files: list[str]


class JobStore:
    def __init__(self, redis: Redis, *, ttl_seconds: int):
        self._redis = redis
        self._ttl = ttl_seconds

    def create(self, *, audio: bytes, filename: str, mode: str, surah: int | None) -> str:
        job_id = uuid.uuid4().hex
        with self._redis.pipeline() as pipe:
            pipe.hset(
                _key(job_id),
                mapping={
                    "status": "queued",
                    "mode": mode,
                    "surah": "" if surah is None else str(surah),
                    "filename": filename,
                    "created_at": repr(time.time()),
                    "stage": "",
                    "fraction": "",
                    "error": "",
                    "files": "",
                },
            )
            pipe.expire(_key(job_id), self._ttl)
            pipe.set(_audio_key(job_id), audio, ex=self._ttl)
            pipe.execute()
        return job_id

    def get(self, job_id: str) -> Job | None:
        raw = self._redis.hgetall(_key(job_id))
        if not raw:
            return None
        fields = {k.decode(): v.decode() for k, v in raw.items()}
        return Job(
            id=job_id,
            status=fields["status"],
            mode=fields["mode"],
            surah=int(fields["surah"]) if fields["surah"] else None,
            filename=fields["filename"],
            created_at=float(fields["created_at"]),
            stage=fields["stage"],
            fraction=float(fields["fraction"]) if fields["fraction"] else None,
            error=fields["error"],
            files=[name for name in fields["files"].split(",") if name],
        )

    def audio(self, job_id: str) -> bytes | None:
        return self._redis.get(_audio_key(job_id))

    def file(self, job_id: str, name: str) -> bytes | None:
        return self._redis.get(_file_key(job_id, name))

    def mark_running(self, job_id: str) -> None:
        self._update(job_id, status="running")

    def set_progress(self, job_id: str, *, stage: str, fraction: float | None) -> None:
        self._update(job_id, stage=stage, fraction="" if fraction is None else repr(fraction))

    def mark_done(self, job_id: str, files: dict[str, bytes]) -> None:
        with self._redis.pipeline() as pipe:
            for name, content in files.items():
                pipe.set(_file_key(job_id, name), content, ex=self._ttl)
            pipe.hset(
                _key(job_id),
                mapping={"status": "done", "files": ",".join(sorted(files)), "error": ""},
            )
            pipe.expire(_key(job_id), self._ttl)
            # The recording is the large part and nothing needs it any more.
            pipe.delete(_audio_key(job_id))
            pipe.execute()

    def mark_failed(self, job_id: str, error: str) -> None:
        with self._redis.pipeline() as pipe:
            pipe.hset(_key(job_id), mapping={"status": "failed", "error": error})
            pipe.expire(_key(job_id), self._ttl)
            pipe.delete(_audio_key(job_id))
            pipe.execute()

    def _update(self, job_id: str, **fields: str) -> None:
        with self._redis.pipeline() as pipe:
            pipe.hset(_key(job_id), mapping=fields)
            pipe.expire(_key(job_id), self._ttl)
            pipe.execute()


def _key(job_id: str) -> str:
    return f"{_PREFIX}{job_id}"


def _audio_key(job_id: str) -> str:
    return f"{_PREFIX}{job_id}:audio"


def _file_key(job_id: str, name: str) -> str:
    return f"{_PREFIX}{job_id}:file:{name}"
