"""Pruebas de las sondas de salud usadas por Kubernetes para la autorrecuperación."""
import signal
import time

import pytest

from app import create_app
from config import TestConfig
from routes import health


@pytest.fixture(autouse=True)
def reset_health_state():
    health._state["hung"] = False
    yield
    health._state["hung"] = False


class ChaosConfig(TestConfig):
    ENABLE_CHAOS = True


class NoModelConfig(TestConfig):
    MODEL_PATH = "no_existe/demand_model.joblib"
    MODEL_METADATA_PATH = "no_existe/model_metadata.json"


def test_liveness_ok(client):
    response = client.get("/health/live")
    assert response.status_code == 200
    body = response.get_json()
    assert body["status"] == "ok"
    assert body["pod"]


def test_readiness_checks_database_and_model(client):
    response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.get_json()["checks"] == {"database": "ok", "model": "ok"}


def test_readiness_fails_without_model():
    client = create_app(NoModelConfig).test_client()
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.get_json()["checks"]["model"] == "no disponible"
    # El proceso sigue vivo: Kubernetes no lo reinicia, solo lo saca del balanceo
    assert client.get("/health/live").status_code == 200


def test_chaos_endpoints_disabled_by_default(client):
    assert client.post("/health/chaos/hang").status_code == 404
    assert client.post("/health/chaos/crash").status_code == 404
    assert client.get("/health/live").status_code == 200


def test_chaos_hang_makes_probes_fail():
    client = create_app(ChaosConfig).test_client()
    assert client.post("/health/chaos/hang").status_code == 200
    assert client.get("/health/live").status_code == 503
    assert client.get("/health/ready").status_code == 503
    # La réplica colgada tampoco atiende páginas: por eso readiness la saca del balanceo
    assert client.get("/predictions/api/model").status_code == 503


def test_chaos_crash_terminates_main_process(monkeypatch):
    calls = []
    monkeypatch.setattr(health.os, "kill", lambda pid, sig: calls.append((pid, sig)))
    client = create_app(ChaosConfig).test_client()
    response = client.post("/health/chaos/crash")
    assert response.status_code == 200
    for _ in range(40):
        if calls:
            break
        time.sleep(0.05)
    assert calls == [(1, signal.SIGTERM)]
