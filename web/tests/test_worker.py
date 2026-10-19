from pathlib import Path

from qurantext.utils.progress import ProgressEvent

from qalun_web.store import JobStore
from qalun_web.worker import process_job


def _queued(redis, *, audio=b"RIFF....", filename="furqan 7-11.mp3", mode="recitation", surah=25):
    store = JobStore(redis, ttl_seconds=60)
    return store, store.create(audio=audio, filename=filename, mode=mode, surah=surah)


def test_the_runner_gets_the_recording_and_the_choices(redis):
    store, job_id = _queued(redis)
    seen = {}

    def runner(audio: Path, *, mode, surah, workdir: Path, progress):
        seen.update(audio=audio.read_bytes(), suffix=audio.suffix, mode=mode, surah=surah)
        out = workdir / "out.srt"
        out.write_bytes(b"1\n")
        return {"srt": out}

    process_job(job_id, store=store, runner=runner)

    assert seen == {"audio": b"RIFF....", "suffix": ".mp3", "mode": "recitation", "surah": 25}


def test_the_runners_files_become_the_jobs_downloads(redis):
    store, job_id = _queued(redis)

    def runner(audio, *, mode, surah, workdir, progress):
        (workdir / "a.srt").write_bytes(b"1\n00:00:00,000 --> 00:00:01,000\nx\n")
        (workdir / "a.json").write_bytes(b"{}")
        return {"srt": workdir / "a.srt", "json": workdir / "a.json"}

    process_job(job_id, store=store, runner=runner)

    job = store.get(job_id)
    assert job.status == "done"
    assert job.files == ["json", "srt"]
    assert store.file(job_id, "json") == b"{}"


def test_a_failing_runner_fails_the_job_without_raising(redis):
    store, job_id = _queued(redis)

    def runner(audio, *, mode, surah, workdir, progress):
        raise RuntimeError("ffmpeg could not read /tmp/secret/path.mp3")

    process_job(job_id, store=store, runner=runner)

    job = store.get(job_id)
    assert job.status == "failed"
    # The person sees a plain sentence, not the server's paths.
    assert "/tmp/secret" not in job.error
    assert job.error


def test_progress_from_the_pipeline_reaches_the_job(redis):
    store, job_id = _queued(redis)
    during = {}

    def runner(audio, *, mode, surah, workdir, progress):
        progress(ProgressEvent(stage="transcribe", message="Transcribing", fraction=0.5))
        job = store.get(job_id)
        during.update(status=job.status, stage=job.stage, fraction=job.fraction)
        return {}

    process_job(job_id, store=store, runner=runner)

    assert during == {"status": "running", "stage": "transcribe", "fraction": 0.5}


def test_an_expired_job_is_skipped(redis):
    store = JobStore(redis, ttl_seconds=60)
    called = []

    process_job("gone", store=store, runner=lambda *a, **k: called.append(1))

    assert called == []
