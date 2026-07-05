import json

import pytest

import app as app_module


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AUDIT_LOG_PATH", str(tmp_path / "audit.json"))
    monkeypatch.setenv("CONTENT_STORE_PATH", str(tmp_path / "content.json"))

    monkeypatch.setattr(
        app_module,
        "groq_signal",
        lambda text: {"score": 0.9, "reasoning": "mocked test result"},
    )
    monkeypatch.setattr(
        app_module,
        "stylometric_signal",
        lambda text: {"score": 0.8, "metrics": {"word_count": len(text.split())}},
    )

    test_app = app_module.create_app()
    test_app.config.update(TESTING=True)
    with test_app.test_client() as client:
        yield client


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json()["status"] == "ok"


def test_submit_writes_structured_log(client):
    response = client.post(
        "/submit",
        json={"text": "A sufficiently clear test passage for attribution.", "creator_id": "u1"},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["content_id"]
    assert payload["attribution"] == "likely_ai"
    assert "confidence" in payload
    assert "label" in payload

    log_response = client.get("/log")
    entries = log_response.get_json()["entries"]
    assert len(entries) == 1
    assert entries[0]["event_type"] == "classification"
    assert entries[0]["groq_score"] == 0.9
    assert entries[0]["stylometric_score"] == 0.8


def test_appeal_updates_status_and_logs_reasoning(client):
    submit = client.post(
        "/submit",
        json={"text": "A test passage for an appeal workflow.", "creator_id": "creator-7"},
    ).get_json()

    response = client.post(
        "/appeal",
        json={
            "content_id": submit["content_id"],
            "creator_reasoning": "I wrote this myself from personal experience.",
        },
    )
    assert response.status_code == 200
    assert response.get_json()["status"] == "under_review"

    entries = client.get("/log").get_json()["entries"]
    assert len(entries) == 2
    assert entries[-1]["event_type"] == "appeal"
    assert entries[-1]["status"] == "under_review"
    assert "personal experience" in entries[-1]["appeal_reasoning"]


def test_submit_rate_limit_reaches_429(client):
    statuses = []
    for _ in range(12):
        response = client.post(
            "/submit",
            json={"text": "Rate limit test passage with enough text.", "creator_id": "rate-user"},
        )
        statuses.append(response.status_code)

    assert 429 in statuses
