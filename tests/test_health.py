from fastapi.testclient import TestClient

from dealerai_ops.core.config import Settings
from dealerai_ops.main import create_app


def test_health_endpoint_returns_service_metadata() -> None:
    app = create_app(Settings(environment="test"))
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "DealerAI Ops",
        "version": "0.1.0",
        "environment": "test",
    }


def test_ready_endpoint_checks_database() -> None:
    app = create_app(Settings(environment="test", database_url="sqlite+pysqlite:///:memory:"))
    client = TestClient(app)

    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "checks": {"database": True}}


def test_ready_endpoint_returns_not_ready_when_database_check_fails() -> None:
    app = create_app(Settings(environment="test", database_url="not-a-real-url"))
    client = TestClient(app)

    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready", "checks": {"database": False}}
