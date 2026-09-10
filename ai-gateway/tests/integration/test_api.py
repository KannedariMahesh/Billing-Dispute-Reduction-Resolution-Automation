from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.headers["X-Correlation-ID"]


def test_anomaly_scan_returns_cases():
    response = client.get("/api/v1/anomalies?as_of=2026-09-05")
    assert response.status_code == 200
    assert response.json()["cases"]
