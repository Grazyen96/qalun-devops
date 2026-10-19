"""What the web layer counts, for Prometheus to scrape and Grafana to show.

Every person-facing action is measured: opening the page, each upload (and why
one was refused), each download, and each job's outcome and duration. The API
replicas serve the first three on /metrics; the worker serves its job metrics on
its own port, because it is a separate process with its own counters.
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

PAGE_VIEWS = Counter("qalun_page_views", "Times the upload page was opened.")
UPLOADS = Counter(
    "qalun_uploads",
    "Uploads, by mode and by result: accepted, or the reason it was refused.",
    ["mode", "result"],
)
DOWNLOADS = Counter("qalun_downloads", "Result files downloaded, by file.", ["file"])
JOBS_WAITING = Gauge(
    "qalun_jobs_waiting",
    "Jobs in the queue that no worker has started yet. Every API replica reports the "
    "same queue, so take max(), not sum().",
)
JOBS_FINISHED = Counter(
    "qalun_jobs_finished", "Jobs a worker finished, by mode and result.", ["mode", "result"]
)
JOB_DURATION = Histogram(
    "qalun_job_duration_seconds",
    "Time from a worker starting a job to its files being stored or its failure.",
    ["mode"],
    buckets=(5, 10, 30, 60, 120, 300, 600, 1200, 1800, 3600),
)
