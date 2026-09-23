import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import app
from app.state import state

client = TestClient(app)


@pytest.fixture(autouse=True)
def fresh_state():
    state.reset()
    yield


def test_starts_stale_and_dark():
    body = client.get("/fingers").json()
    assert body["count"] == 0
    assert body["stale"] is True


def test_post_then_get_returns_count():
    assert client.post("/fingers", json={"count": 3}).status_code == 200
    body = client.get("/fingers").json()
    assert body["count"] == 3
    assert body["stale"] is False


@pytest.mark.parametrize("count", [-1, 6, 9])
def test_refuses_counts_outside_0_to_5(count):
    assert client.post("/fingers", json={"count": count}).status_code == 422


def test_refuses_brightness_outside_0_to_255():
    assert client.post("/fingers", json={"count": 1, "brightness": 300}).status_code == 422


def test_optional_fields_keep_previous_value():
    client.post("/fingers", json={"count": 2, "brightness": 128, "gesture": "peace"})
    client.post("/fingers", json={"count": 4})
    body = client.get("/fingers").json()
    assert (body["count"], body["brightness"], body["gesture"]) == (4, 128, "peace")


def test_goes_dark_when_camera_is_silent(monkeypatch):
    client.post("/fingers", json={"count": 5, "brightness": 200, "sos": True})
    monkeypatch.setattr(config, "STALE_SECONDS", -1)
    body = client.get("/fingers").json()
    assert body == body | {"count": 0, "brightness": 0, "sos": False, "stale": True}


def test_sos_toggle_is_logged_as_event():
    client.post("/fingers", json={"count": 2, "sos": True})
    assert "SOS switched ON" in client.get("/fingers").json()["event"]


def test_esp32_style_parse():
    """The chip does indexOf("\"count\":") then toInt() on what follows."""
    client.post("/fingers", json={"count": 4})
    text = client.get("/fingers").text
    at = text.index('"count":')
    assert text[at + 8] == "4"


def test_history_records_reports():
    for n in (1, 2, 3):
        client.post("/fingers", json={"count": n})
    assert [h["count"] for h in client.get("/history?limit=2").json()] == [2, 3]


def test_api_key_required_when_set(monkeypatch):
    monkeypatch.setattr(config, "API_KEY", "secret")
    assert client.post("/fingers", json={"count": 1}).status_code == 401
    ok = client.post("/fingers", json={"count": 1}, headers={"X-API-Key": "secret"})
    assert ok.status_code == 200
    assert client.get("/fingers").status_code == 200  # the board reads without a key
