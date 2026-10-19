from qalun_web.store import JobStore


def test_a_new_job_waits_in_the_queue_with_what_was_asked(redis):
    store = JobStore(redis, ttl_seconds=60)

    job_id = store.create(audio=b"ID3...", filename="furqan.mp3", mode="recitation", surah=25)
    job = store.get(job_id)

    assert job.status == "queued"
    assert (job.mode, job.surah, job.filename) == ("recitation", 25, "furqan.mp3")
    assert job.files == []
    assert store.audio(job_id) == b"ID3..."


def test_a_job_without_a_surah_keeps_none(redis):
    store = JobStore(redis, ttl_seconds=60)

    job = store.get(store.create(audio=b"x", filename="a.mp3", mode="lecture", surah=None))

    assert job.surah is None


def test_every_key_of_a_job_expires(redis):
    store = JobStore(redis, ttl_seconds=60)
    job_id = store.create(audio=b"x", filename="a.mp3", mode="lecture", surah=None)
    store.mark_done(job_id, {"srt": b"1\n"})

    keys = redis.keys(f"*{job_id}*")

    assert keys
    assert all(0 < redis.ttl(key) <= 60 for key in keys)


def test_an_unknown_job_is_none(redis):
    assert JobStore(redis, ttl_seconds=60).get("does-not-exist") is None


def test_done_keeps_the_files_and_drops_the_recording(redis):
    store = JobStore(redis, ttl_seconds=60)
    job_id = store.create(audio=b"x", filename="a.mp3", mode="recitation", surah=None)

    store.mark_done(job_id, {"srt": b"1\n", "vtt": b"WEBVTT\n"})
    job = store.get(job_id)

    assert job.status == "done"
    assert job.files == ["srt", "vtt"]
    assert store.file(job_id, "vtt") == b"WEBVTT\n"
    assert store.file(job_id, "json") is None
    assert store.audio(job_id) is None


def test_failed_says_why_and_drops_the_recording(redis):
    store = JobStore(redis, ttl_seconds=60)
    job_id = store.create(audio=b"x", filename="a.mp3", mode="recitation", surah=None)

    store.mark_failed(job_id, "No ayat found in this recording.")
    job = store.get(job_id)

    assert job.status == "failed"
    assert job.error == "No ayat found in this recording."
    assert store.audio(job_id) is None


def test_progress_is_kept_while_running(redis):
    store = JobStore(redis, ttl_seconds=60)
    job_id = store.create(audio=b"x", filename="a.mp3", mode="recitation", surah=None)

    store.mark_running(job_id)
    store.set_progress(job_id, stage="transcribe", fraction=0.25)
    job = store.get(job_id)

    assert job.status == "running"
    assert (job.stage, job.fraction) == ("transcribe", 0.25)
