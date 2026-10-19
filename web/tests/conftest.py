from dataclasses import replace

import fakeredis
import pytest
from fastapi.testclient import TestClient

from qalun_web.app import create_app
from qalun_web.settings import Settings


class RecordingQueue:
    """Stands in for the RQ queue: remembers which jobs were handed to the worker."""

    def __init__(self):
        self.job_ids: list[str] = []

    def __call__(self, job_id: str) -> None:
        self.job_ids.append(job_id)


@pytest.fixture
def redis():
    return fakeredis.FakeRedis()


@pytest.fixture
def settings():
    return replace(Settings.from_env({}), max_upload_bytes=1024)


@pytest.fixture
def queue():
    return RecordingQueue()


@pytest.fixture
def client(settings, redis, queue):
    return TestClient(create_app(settings, redis=redis, enqueue=queue))
