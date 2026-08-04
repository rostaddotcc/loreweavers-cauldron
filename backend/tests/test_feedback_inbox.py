"""Test: feedback-flödet — spelare POST:ar feedback → admin hämtar den.

POST /api/feedback (cookie-auth) skriver till backend/data/feedback.jsonl.
GET /api/admin/feedback (admin-only) läser JSONL:en, senaste först, och
404/403-skyddar för icke-admins. Ingen riktig data rörs (monkeypatch på
FEEDBACK_DIR via _feedback_path).
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main  # noqa: E402
from auth import create_token  # noqa: E402


@pytest.fixture
def tmp_feedback(tmp_path, monkeypatch):
    """Peka feedback-filen mot en temporär mapp."""
    monkeypatch.setattr(main, "_FEEDBACK_DIR", tmp_path)
    return tmp_path


@pytest.fixture
def client(tmp_feedback):
    from fastapi.testclient import TestClient
    with TestClient(main.app) as c:
        yield c


def _fb_path():
    return main._FEEDBACK_DIR / "feedback.jsonl"


def test_feedback_requires_cookie(client):
    r = client.post("/api/feedback", json={"message": "Hej"})
    assert r.status_code == 401


def test_feedback_requires_message(client):
    tok = create_token("player_one", "player")
    r = client.post("/api/feedback", json={"message": "   "},
                    cookies={"morkrets_token": tok})
    assert r.status_code == 400


def test_feedback_stores_and_admin_reads_latest_first(tmp_feedback, client):
    tok = create_token("player_one", "player")
    # Två meddelanden — senaste ska komma först i admin-vyn
    for msg in ["First note", "Second note"]:
        r = client.post("/api/feedback", json={"email": "p@x.se", "message": msg},
                        cookies={"morkrets_token": tok})
        assert r.status_code == 200
        assert r.json() == {"ok": True}

    # Filen ska finnas med två rader
    assert _fb_path().exists()
    lines = [json.loads(l) for l in _fb_path().read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) == 2
    assert lines[0]["message"] == "First note"
    assert lines[0]["email"] == "p@x.se"

    # Admin hämtar — senaste först
    atok = create_token("the_admin", "admin")
    r = client.get("/api/admin/feedback", cookies={"morkrets_token": atok})
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 2
    assert data["items"][0]["message"] == "Second note"
    assert data["items"][1]["message"] == "First note"


def test_admin_feedback_blocks_non_admin(client):
    tok = create_token("player_one", "player")
    r = client.get("/api/admin/feedback", cookies={"morkrets_token": tok})
    assert r.status_code == 403


def test_admin_feedback_empty_inbox_is_ok(tmp_feedback, client):
    atok = create_token("the_admin", "admin")
    r = client.get("/api/admin/feedback", cookies={"morkrets_token": atok})
    assert r.status_code == 200
    assert r.json() == {"total": 0, "items": []}
