# Qalun web

A small web layer over [QuranText](https://github.com/Grazyen96/QalunTextAlignment):
upload a Quran recitation or a lecture, get its subtitles back as SRT and WebVTT,
plus QuranText's match JSON. It is the workload this fork deploys; the desktop
app upstream stays as it is.

It lives entirely in `web/` and calls QuranText as a library, so the fork can be
rebased onto upstream without conflicts.

## How it fits together

```
browser ──HTTPS──▶ api (FastAPI, ≥2 replicas) ──▶ Valkey/Redis ◀── worker (RQ, 1 job at a time)
                     /  /api/*  /healthz /readyz /metrics           runs QuranText's local engine
```

- **api** checks an upload, stores it in Redis and queues the job's id. It never
  runs QuranText itself, so every replica is stateless and interchangeable.
- **worker** takes one job at a time, runs detection with QuranText's local
  engine (no WhisperX, nothing uploaded anywhere), writes the subtitles, and
  stores the files in Redis. More throughput means more worker replicas.
- **Valkey/Redis** is the backing service: queue, job status and files. Every
  key expires after `RESULT_TTL_HOURS`, so nothing grows without bound and losing
  it loses at most a day of results.

One image runs both: the default command is the API, `qalun-web-worker` is the
worker. The speech model and the Quran store are baked in at build time.

## Run it on your machine

From the repository root:

```bash
docker compose -f web/compose.yaml up --build
```

Open <http://localhost:8000>. The password is `dev` with any user name; start
with `UI_ACCESS_PASSWORD=` (empty) to turn it off. Compose is for development
only; staging and production run on Kubernetes.

## Configuration

Environment variables only, the same image in every environment.

| Variable | Default | Meaning |
|---|---|---|
| `REDIS_URL` | `redis://localhost:6379/0` | The backing service. Each environment uses its own instance. |
| `UI_ACCESS_PASSWORD` | *(empty: no password)* | Shared password for the page and the API. Always set it outside a laptop. |
| `MAX_UPLOAD_MB` | `100` | Larger uploads are refused with 413. |
| `RESULT_TTL_HOURS` | `24` | How long jobs, recordings and results are kept. |
| `JOB_TIMEOUT_SECONDS` | `3600` | A job running longer is stopped by RQ. |
| `WORKER_METRICS_PORT` | `9100` | Where the worker serves its own `/metrics`. |

## Endpoints

| Path | Password | Purpose |
|---|---|---|
| `GET /` | yes | The upload page. |
| `GET /api/surahs` | yes | Surah numbers and names for the picker. |
| `POST /api/jobs` | yes | Multipart: `file`, `mode` (`recitation`/`lecture`), optional `surah` (1–114). Returns 202 and the job id. |
| `GET /api/jobs/{id}` | yes | Status, progress and the list of downloads. |
| `GET /api/jobs/{id}/files/{srt,vtt,json}` | yes | A result file, named after the recording. |
| `GET /healthz` | no | Liveness: the process answers. |
| `GET /readyz` | no | Readiness: 503 while Redis is unreachable. |
| `GET /metrics` | no | Prometheus. Keep it off the public ingress. |

## Metrics

| Metric | Where | What |
|---|---|---|
| `qalun_page_views_total` | api | Times the page was opened. |
| `qalun_uploads_total{mode,result}` | api | `result` is `accepted`, or why it was refused: `too_large`, `wrong_type`, `empty`, `bad_surah`, `bad_mode`. |
| `qalun_downloads_total{file}` | api | Result files downloaded. |
| `qalun_jobs_waiting` | api | Queue length. Every replica reports the same queue: use `max()`. |
| `qalun_jobs_finished_total{mode,result}` | worker | `done` or `failed`. |
| `qalun_job_duration_seconds{mode}` | worker | Histogram, from start to stored files. |

## Tests

```bash
python -m pip install -e . -e "web[dev]"
cd web && pytest
```

The tests use a fake Redis and a stand-in for QuranText, except one end-to-end
test that runs the real pipeline on a recording you name (it is not in the repo):

```bash
QALUN_E2E_AUDIO=~/clips/furqan-7-11.mp3 QALUN_E2E_SURAH=25 pytest -m e2e
```

## Indication of source

The code in `web/` was generated with an AI assistant (Claude Code). Every such
commit is titled `[ai:opus] …` and carries the prompts that led to it in its
message, as the course requires.
