"""Everything the web layer can be told, read from the environment only.

The same image runs in every environment; what differs between staging and
production is these variables, set by the deployment (12-factor, factor III).
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    redis_url: str
    max_upload_bytes: int
    result_ttl_seconds: int
    #: Empty turns the password off, which is only meant for a laptop.
    access_password: str
    job_timeout_seconds: int
    worker_metrics_port: int

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if env is None else env
        return cls(
            redis_url=env.get("REDIS_URL", "redis://localhost:6379/0"),
            max_upload_bytes=_positive(env, "MAX_UPLOAD_MB", 100) * 1024 * 1024,
            result_ttl_seconds=_positive(env, "RESULT_TTL_HOURS", 24) * 3600,
            access_password=env.get("UI_ACCESS_PASSWORD", ""),
            job_timeout_seconds=_positive(env, "JOB_TIMEOUT_SECONDS", 3600),
            worker_metrics_port=_positive(env, "WORKER_METRICS_PORT", 9100),
        )


def _positive(env: Mapping[str, str], name: str, default: int) -> int:
    raw = env.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(f"{name} must be a whole number, not {raw!r}.") from None
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero, not {value}.")
    return value
