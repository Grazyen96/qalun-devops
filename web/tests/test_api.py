from dataclasses import replace

from fastapi.testclient import TestClient

from qalun_web.app import create_app
from qalun_web.store import JobStore


def _upload(client, *, name="furqan.mp3", content=b"ID3 audio", mode="recitation", surah=None):
    data = {"mode": mode}
    if surah is not None:
        data["surah"] = str(surah)
    return client.post("/api/jobs", files={"file": (name, content)}, data=data)


def test_an_upload_becomes_a_queued_job_handed_to_the_worker(client, queue):
    response = _upload(client, surah=25)

    assert response.status_code == 202
    job_id = response.json()["id"]
    assert queue.job_ids == [job_id]
    status = client.get(f"/api/jobs/{job_id}").json()
    assert status["status"] == "queued"
    assert (status["mode"], status["surah"], status["filename"]) == ("recitation", 25, "furqan.mp3")


def test_the_surah_is_optional(client):
    assert _upload(client).status_code == 202


def test_a_lecture_can_be_uploaded(client):
    assert _upload(client, mode="lecture").status_code == 202


def test_an_unknown_mode_is_refused(client, queue):
    response = _upload(client, mode="range")

    assert response.status_code == 400
    assert queue.job_ids == []


def test_a_surah_outside_the_quran_is_refused(client, queue):
    for surah in (0, 115):
        assert _upload(client, surah=surah).status_code == 400
    assert queue.job_ids == []


def test_a_recording_over_the_limit_is_refused(client, queue, redis):
    # The fixture's limit is 1 KiB.
    response = _upload(client, content=b"x" * 1025)

    assert response.status_code == 413
    assert queue.job_ids == []
    assert redis.keys("*") == []


def test_a_recording_at_the_limit_is_taken(client):
    assert _upload(client, content=b"x" * 1024).status_code == 202


def test_a_file_that_is_not_a_recording_is_refused(client, queue):
    response = _upload(client, name="notes.pdf")

    assert response.status_code == 415
    assert queue.job_ids == []


def test_an_empty_file_is_refused(client, queue):
    assert _upload(client, content=b"").status_code == 400
    assert queue.job_ids == []


def test_an_unknown_job_is_not_found(client):
    assert client.get("/api/jobs/nope").status_code == 404


def test_a_finished_job_lists_its_downloads(client, settings, redis):
    job_id = _upload(client, name="Furqan 7-11.mp3").json()["id"]
    JobStore(redis, ttl_seconds=60).mark_done(job_id, {"srt": b"1\n", "json": b"{}"})

    files = client.get(f"/api/jobs/{job_id}").json()["files"]

    assert files == [
        {"name": "json", "url": f"/api/jobs/{job_id}/files/json"},
        {"name": "srt", "url": f"/api/jobs/{job_id}/files/srt"},
    ]


def test_a_download_is_named_after_the_recording(client, redis):
    job_id = _upload(client, name="Furqan 7-11.mp3").json()["id"]
    JobStore(redis, ttl_seconds=60).mark_done(job_id, {"srt": b"1\n00:00:00,000 --> x\n"})

    response = client.get(f"/api/jobs/{job_id}/files/srt")

    assert response.status_code == 200
    assert response.content == b"1\n00:00:00,000 --> x\n"
    assert "attachment" in response.headers["content-disposition"]
    assert "Furqan%207-11.srt" in response.headers["content-disposition"]


def test_a_download_the_job_did_not_produce_is_not_found(client, redis):
    job_id = _upload(client).json()["id"]
    JobStore(redis, ttl_seconds=60).mark_done(job_id, {"srt": b"1\n"})

    assert client.get(f"/api/jobs/{job_id}/files/vtt").status_code == 404
    assert client.get(f"/api/jobs/{job_id}/files/..%2Faudio").status_code == 404


def test_the_page_offers_the_upload_form(client):
    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "<form" in response.text


def test_the_surah_list_comes_from_quran_text(client):
    surahs = client.get("/api/surahs").json()

    assert len(surahs) == 114
    assert surahs[0]["surah_num"] == 1


# --- the shared password ------------------------------------------------------------------


def _guarded(settings, redis, queue):
    return TestClient(
        create_app(replace(settings, access_password="sesame"), redis=redis, enqueue=queue)
    )


def test_with_a_password_the_page_and_the_api_ask_for_it(settings, redis, queue):
    client = _guarded(settings, redis, queue)

    for path in ("/", "/api/surahs", "/api/jobs/x", "/static/app.js"):
        response = client.get(path)
        assert response.status_code == 401, path
        assert response.headers["www-authenticate"].startswith("Basic")
    assert _upload(client).status_code == 401
    assert queue.job_ids == []


def test_the_right_password_lets_anyone_in_whatever_the_user_name(settings, redis, queue):
    client = _guarded(settings, redis, queue)

    assert client.get("/", auth=("anyone", "sesame")).status_code == 200
    assert client.get("/", auth=("anyone", "wrong")).status_code == 401


def test_probes_and_metrics_never_ask_for_the_password(settings, redis, queue):
    client = _guarded(settings, redis, queue)

    for path in ("/healthz", "/readyz", "/metrics"):
        assert client.get(path).status_code == 200, path
