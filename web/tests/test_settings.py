import pytest

from qalun_web.settings import Settings


def test_defaults_when_nothing_is_set():
    settings = Settings.from_env({})

    assert settings.redis_url == "redis://localhost:6379/0"
    assert settings.max_upload_bytes == 100 * 1024 * 1024
    assert settings.result_ttl_seconds == 24 * 3600
    assert settings.access_password == ""
    assert settings.job_timeout_seconds == 3600
    assert settings.worker_metrics_port == 9100


def test_values_come_from_the_environment():
    settings = Settings.from_env(
        {
            "REDIS_URL": "redis://redis.staging:6379/1",
            "MAX_UPLOAD_MB": "5",
            "RESULT_TTL_HOURS": "2",
            "UI_ACCESS_PASSWORD": "sesame",
            "JOB_TIMEOUT_SECONDS": "60",
            "WORKER_METRICS_PORT": "9200",
        }
    )

    assert settings.redis_url == "redis://redis.staging:6379/1"
    assert settings.max_upload_bytes == 5 * 1024 * 1024
    assert settings.result_ttl_seconds == 7200
    assert settings.access_password == "sesame"
    assert settings.job_timeout_seconds == 60
    assert settings.worker_metrics_port == 9200


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("MAX_UPLOAD_MB", "lots"),
        ("MAX_UPLOAD_MB", "0"),
        ("RESULT_TTL_HOURS", "-1"),
        ("JOB_TIMEOUT_SECONDS", "0"),
    ],
)
def test_a_bad_number_is_refused_by_name(name, value):
    with pytest.raises(ValueError, match=name):
        Settings.from_env({name: value})
