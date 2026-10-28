"""B1 — charakärsarks-prosa på kampanjspråket (CONTRACT-B.md, våg 3).

Pins:
  (i)   languages.get_char_sheet_output_directive: de/fr/es/it carry the English
        meta-directive ('OUTPUT LANGUAGE', 'machine keys'); en/sv/unknown → ''
        (no directive — byte-identical char-gen behavior for them).
  (ii)  /api/character/generate: 'de' campaign → user_msg ends with the GERMAN
        directive, system prompt stays CHARACTER_PROMPT_EN untouched;
        'en'/'sv' → user_msg byte-identical to the pre-B1 build
        (prefix + _build_chargen_seed_block, no 'OUTPUT LANGUAGE').
  (iii) /api/character/generate/stream: same injection for 'fr'.
  (iv)  /api/vault/generate/stream: req.lang='de' is NO LONGER silently coerced
        to 'en' — the GERMAN directive reaches the prompt; 'sv' keeps the
        Swedish prefix + SV prompt; junk ('xx') → 'en' fallback, no directive.
  (v)   guardian build_extract_mechanics_messages(language='fr'): system block
        names FRENCH and the extended text list ('item names and lore');
        en/sv instructions stay verbatim (BY_LANG-only extension).

Fixture recipe follows tests/test_main_language_integration.py (users_file,
store_tmp, tier2 seed). The LLM seams are faked: they capture `messages` and
raise, so the endpoints' post-processing never runs — this file tests prompt
construction only.
"""

import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


@pytest.fixture(autouse=True)
def users_file(tmp_path, monkeypatch):
    import auth
    f = tmp_path / "users.json"
    monkeypatch.setattr(auth, "USERS_FILE", f)
    return f


@pytest.fixture(autouse=True)
def store_tmp(tmp_path, monkeypatch):
    """Never touch real backend/data/campaigns during these tests."""
    import state_manager as sm
    d = tmp_path / "campaigns"
    d.mkdir()
    monkeypatch.setattr(sm, "CAMPAIGNS_DIR", d)
    import main
    monkeypatch.setattr(main, "CAMPAIGNS_DIR", d)
    return d


@pytest.fixture
def client(store_tmp):
    import main
    from fastapi.testclient import TestClient
    with TestClient(main.app) as c:
        yield c


def _seed_tier2(username):
    import auth
    import main
    main.save_users({
        username: {"password_hash": auth.hash_password("secret123"), "role": "player",
                   "turn_cap": 50, "turns_used": 0, "turn_bonus": 0,
                   "reset_date": "2026-08-04",
                   "subscription_status": "tier2",
                   "subscription_until": "2027-01-01"},
    })
    return auth.create_token(username, "player")


def _deterministic_seed(monkeypatch, username):
    """Pin the randomness + recent-names lookup of _build_chargen_seed_block
    so tests can recompute the exact expected user_msg."""
    import main
    monkeypatch.setattr(main.random, "randrange", lambda n: 0)
    monkeypatch.setattr(main, "_recent_character_names", lambda u: [])


def _capture_llm(monkeypatch):
    """Fake _call_llm: record messages, then abort the endpoint (502)."""
    import main
    seen = []

    async def fake_call(model_id, messages, **kw):
        seen.append(messages)
        raise RuntimeError("b1-test-stop")

    monkeypatch.setattr(main, "_call_llm", fake_call)
    return seen


def _capture_stream(monkeypatch):
    """Fake _stream_llm: record messages, then abort the SSE stream."""
    import main
    seen = []

    async def fake_stream(model_id, messages, **kw):
        seen.append(messages)
        raise RuntimeError("b1-test-stop")
        yield  # keep this an async generator

    monkeypatch.setattr(main, "_stream_llm", fake_stream)
    return seen


def _user_content(messages):
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    return messages[1]["content"]


# ── (i) the directive table itself ──────────────────────────────────────

def test_directive_markers_and_empty_for_en_sv():
    import languages
    de = languages.get_char_sheet_output_directive("de")
    assert "OUTPUT LANGUAGE" in de and "GERMAN" in de and "machine keys" in de
    assert "item names AND item lore" in de and "Gemeinsprache" in de
    for code, marker, word in (("fr", "FRENCH", "Commun"),
                               ("es", "SPANISH", "Común"),
                               ("it", "ITALIAN", "Comune")):
        d = languages.get_char_sheet_output_directive(code)
        assert marker in d and "machine keys" in d and word in d
        assert "class and race" in d
    # en/sv/unknown/None → no directive at all
    assert languages.get_char_sheet_output_directive("en") == ""
    assert languages.get_char_sheet_output_directive("sv") == ""
    assert languages.get_char_sheet_output_directive("xx") == ""
    assert languages.get_char_sheet_output_directive(None) == ""
    # contract: the dict must NOT carry en/sv entries
    assert set(languages.CHAR_SHEET_OUTPUT_DIRECTIVES) == {"de", "fr", "es", "it"}


# ── (ii) POST /api/character/generate ───────────────────────────────────

def test_generate_de_user_msg_ends_with_german_directive(client, monkeypatch):
    import main
    import languages
    seen = _capture_llm(monkeypatch)
    tok = _seed_tier2("b1_de")
    r = client.post("/api/campaign", json={"name": "B1 DE", "language": "de"},
                    cookies={"morkrets_token": tok})
    assert r.status_code == 200, r.text
    client.post("/api/character/generate",
                json={"prompt": "Ein Waldläufer", "model_id": main.DEFAULT_PLAYER_MODEL},
                cookies={"morkrets_token": tok})
    assert seen, "char-gen never reached the LLM seam"
    user_msg = _user_content(seen[0])
    directive = languages.get_char_sheet_output_directive("de")
    assert "GERMAN" in user_msg
    assert user_msg.endswith(directive)          # injected LAST, after the seed block
    assert "OUTPUT LANGUAGE" in user_msg
    assert seen[0][0]["content"] == main.CHARACTER_PROMPT_EN  # master prompt untouched


def test_generate_en_user_msg_byte_identical(client, monkeypatch):
    """'en': NO directive — user_msg equals the pre-B1 construction exactly."""
    import main
    _deterministic_seed(monkeypatch, "b1_en")
    expected_user = ("Create a character: A knight"
                     + main._build_chargen_seed_block("b1_en", "en"))
    seen = _capture_llm(monkeypatch)
    tok = _seed_tier2("b1_en")
    r = client.post("/api/campaign", json={"name": "B1 EN", "language": "en"},
                    cookies={"morkrets_token": tok})
    assert r.status_code == 200, r.text
    client.post("/api/character/generate",
                json={"prompt": "A knight", "model_id": main.DEFAULT_PLAYER_MODEL},
                cookies={"morkrets_token": tok})
    user_msg = _user_content(seen[0])
    assert "OUTPUT LANGUAGE" not in user_msg
    assert user_msg == expected_user


def test_generate_sv_user_msg_byte_identical(client, monkeypatch):
    """'sv': unchanged — Swedish prefix + seed block, no directive."""
    import main
    _deterministic_seed(monkeypatch, "b1_sv")
    expected_user = ("Skapa en karaktär: En riddare"
                     + main._build_chargen_seed_block("b1_sv", "sv"))
    seen = _capture_llm(monkeypatch)
    tok = _seed_tier2("b1_sv")
    r = client.post("/api/campaign", json={"name": "B1 SV", "language": "sv"},
                    cookies={"morkrets_token": tok})
    assert r.status_code == 200, r.text
    client.post("/api/character/generate",
                json={"prompt": "En riddare", "model_id": main.DEFAULT_PLAYER_MODEL},
                cookies={"morkrets_token": tok})
    user_msg = _user_content(seen[0])
    assert "OUTPUT LANGUAGE" not in user_msg
    assert user_msg == expected_user
    assert seen[0][0]["content"] == main.CHARACTER_PROMPT_SV


# ── (iii) POST /api/character/generate/stream ───────────────────────────

def test_generate_stream_french_directive(client, monkeypatch):
    import main
    import languages
    seen = _capture_stream(monkeypatch)
    tok = _seed_tier2("b1_fr")
    r = client.post("/api/campaign", json={"name": "B1 FR", "language": "fr"},
                    cookies={"morkrets_token": tok})
    assert r.status_code == 200, r.text
    client.post("/api/character/generate/stream",
                json={"prompt": "Un roublard", "model_id": main.DEFAULT_PLAYER_MODEL},
                cookies={"morkrets_token": tok})
    assert seen, "streamed char-gen never reached the LLM seam"
    user_msg = _user_content(seen[0])
    assert "FRENCH" in user_msg
    assert user_msg.endswith(languages.get_char_sheet_output_directive("fr"))
    assert seen[0][0]["content"] == main.CHARACTER_PROMPT_EN


# ── (iv) POST /api/vault/generate/stream (The Forge) ────────────────────

def _vault(client, tok, lang):
    return client.post("/api/vault/generate/stream",
                       json={"prompt": "x", "model_id": "local:test", "lang": lang},
                       cookies={"morkrets_token": tok})


def test_vault_de_no_longer_coerced_to_en(client, monkeypatch):
    """The B1 bug: vault req.lang='de' used to collapse to 'en'. It must now
    keep 'de' and inject the GERMAN directive."""
    import main
    import languages
    seen = _capture_stream(monkeypatch)
    tok = _seed_tier2("b1_vde")
    r = _vault(client, tok, "de")
    assert r.status_code == 200, r.text
    user_msg = _user_content(seen[0])
    assert "GERMAN" in user_msg
    assert user_msg.endswith(languages.get_char_sheet_output_directive("de"))
    # prompt choice unchanged for EU: EN master prompt, English prefix
    assert seen[0][0]["content"] == main.CHARACTER_PROMPT_EN
    assert user_msg.startswith("Create a character:")


def test_vault_junk_falls_back_to_en(client, monkeypatch):
    import main
    seen = _capture_stream(monkeypatch)
    tok = _seed_tier2("b1_vxx")
    r = _vault(client, tok, "xx")
    assert r.status_code == 200, r.text
    user_msg = _user_content(seen[0])
    assert "OUTPUT LANGUAGE" not in user_msg
    assert seen[0][0]["content"] == main.CHARACTER_PROMPT_EN


def test_vault_sv_keeps_swedish_path(client, monkeypatch):
    """'sv' in the vault stays byte-identical: SV prompt, Swedish prefix,
    no directive ('startswith("sv")' → 'is_supported' both accept 'sv')."""
    import main
    seen = _capture_stream(monkeypatch)
    tok = _seed_tier2("b1_vsv")
    r = _vault(client, tok, "sv")
    assert r.status_code == 200, r.text
    user_msg = _user_content(seen[0])
    assert "OUTPUT LANGUAGE" not in user_msg
    assert user_msg.startswith("Skapa en karaktär:")
    assert seen[0][0]["content"] == main.CHARACTER_PROMPT_SV


# ── (v) guardian: extended EU text list, en/sv verbatim ─────────────────

def _gstate(lang):
    return {"meta": {"language": lang, "user": "b1"}, "character": {},
            "inventory": [], "currency": {}, "npcs": [], "quests": [],
            "transcript": []}


def test_guardian_eu_instruction_names_extra_fields():
    import guardian
    for code, marker in (("de", "GERMAN"), ("fr", "FRENCH"),
                         ("es", "SPANISH"), ("it", "ITALIAN")):
        msg = guardian.build_extract_mechanics_messages(
            "dm", "player", _gstate(code), 2, code)[0]["content"]
        assert marker in msg
        assert "character update notes" in msg
        assert "item names and lore" in msg


def test_guardian_en_sv_instructions_unchanged():
    import guardian
    en = guardian.build_extract_mechanics_messages("x", "y", _gstate("en"), 2, "en")[0]["content"]
    sv = guardian.build_extract_mechanics_messages("x", "y", _gstate("sv"), 2, "sv")[0]["content"]
    assert ("[IMPORTANT: Write all user-facing text (logbook, npc_notes, day_summary, "
            "quest descriptions) in ENGLISH.]") in en
    assert ("[VIKTIGT: Skriv alla användarvända texter (logbook, npc_notes, day_summary, "
            "quest-beskrivningar) på SVENSKA.]") in sv
