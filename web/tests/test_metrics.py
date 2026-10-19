"""Every user action is counted, so the web layer is measurable from Grafana.

Counters live in prometheus_client's process-wide registry, so each test reads
the value before and after and asserts the difference.
"""

from fastapi.testclient import TestClient
from prometheus_client import REGISTRY

from qalun_web.app import create_app
from qalun_web.store import JobStore
from qalun_web.worker import process_job


def _value(name, **labels):
    return REGISTRY.get_sample_value(name, labels) or 0.0


def _upload(client, *, name="a.mp3", content=b"ID3", mode="recitation", surah=None):
    data = {"mode": mode} | ({"surah": str(surah)} if surah is not None else {})
    return client.post("/api/jobs", files={"file": (name, content)}, data=data)


def test_opening_the_page_counts_a_view(client):
    before = _value("qalun_page_views_total")

    client.get("/")

    assert _value("qalun_page_views_total") == before + 1


def test_an_accepted_upload_is_counted_by_mode(client):
    before = _value("qalun_uploads_total", mode="lecture", result="accepted")

    _upload(client, mode="lecture")

    assert _value("qalun_uploads_total", mode="lecture", result="accepted") == before + 1


def test_each_refusal_is_counted_by_its_reason(client):
    cases = [
        ({"content": b"x" * 2048}, "recitation", "too_large"),
        ({"name": "notes.pdf"}, "recitation", "wrong_type"),
        ({"content": b""}, "recitation", "empty"),
        ({"surah": 115}, "recitation", "bad_surah"),
        ({"mode": "range"}, "other", "bad_mode"),
    ]
    for kwargs, mode, result in cases:
        before = _value("qalun_uploads_total", mode=mode, result=result)

        _upload(client, **kwargs)

        assert _value("qalun_uploads_total", mode=mode, result=result) == before + 1, result


def test_a_download_is_counted_by_file(client, redis):
    job_id = _upload(client).json()["id"]
    JobStore(redis, ttl_seconds=60).mark_done(job_id, {"vtt": b"WEBVTT\n"})
    before = _value("qalun_downloads_total", file="vtt")

    client.get(f"/api/jobs/{job_id}/files/vtt")

    assert _value("qalun_downloads_total", file="vtt") == before + 1


def test_a_missing_download_is_not_counted(client, redis):
    job_id = _upload(client).json()["id"]
    before = _value("qalun_downloads_total", file="vtt")

    client.get(f"/api/jobs/{job_id}/files/vtt")

    assert _value("qalun_downloads_total", file="vtt") == before


def test_the_scrape_reports_how_many_jobs_are_waiting(settings, redis, queue):
    client = TestClient(create_app(settings, redis=redis, enqueue=queue, queue_length=lambda: 3))

    body = client.get("/metrics").text

    assert "qalun_jobs_waiting 3.0" in body


def test_a_finished_job_is_counted_and_timed(redis):
    store = JobStore(redis, ttl_seconds=60)
    job_id = store.create(audio=b"x", filename="a.mp3", mode="recitation", surah=None)
    done_before = _value("qalun_jobs_finished_total", mode="recitation", result="done")
    timed_before = _value("qalun_job_duration_seconds_count", mode="recitation")

    process_job(job_id, store=store, runner=lambda *a, **k: {})

    assert _value("qalun_jobs_finished_total", mode="recitation", result="done") == done_before + 1
    assert _value("qalun_job_duration_seconds_count", mode="recitation") == timed_before + 1


def test_a_failed_job_is_counted_as_failed(redis):
    store = JobStore(redis, ttl_seconds=60)
    job_id = store.create(audio=b"x", filename="a.mp3", mode="lecture", surah=None)
    before = _value("qalun_jobs_finished_total", mode="lecture", result="failed")

    def runner(*args, **kwargs):
        raise RuntimeError("boom")

    process_job(job_id, store=store, runner=runner)

    assert _value("qalun_jobs_finished_total", mode="lecture", result="failed") == before + 1
