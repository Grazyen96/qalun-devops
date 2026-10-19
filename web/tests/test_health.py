import fakeredis
from fastapi.testclient import TestClient

from qalun_web.app import create_app


def test_healthz_answers_without_redis(settings, queue):
    server = fakeredis.FakeServer()
    server.connected = False
    client = TestClient(
        create_app(settings, redis=fakeredis.FakeRedis(server=server), enqueue=queue)
    )

    assert client.get("/healthz").status_code == 200


def test_readyz_is_ok_when_redis_answers(client):
    assert client.get("/readyz").status_code == 200


def test_readyz_refuses_traffic_when_redis_is_down(settings, queue):
    server = fakeredis.FakeServer()
    server.connected = False
    client = TestClient(
        create_app(settings, redis=fakeredis.FakeRedis(server=server), enqueue=queue)
    )

    response = client.get("/readyz")

    assert response.status_code == 503
