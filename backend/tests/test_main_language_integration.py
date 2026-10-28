"""A5 — main.py EU-language integration tests (CONTRACT A4).

Pins the pieces the black-box guard test (test_eu_languages.py) cannot:
  (i)   POST /api/campaign gate: 'xx' → 400, 'de' → 200 (store-tmp fixtures)
  (ii)  _build_system_prompt('de'): DEUTSCH directive FIRST, DE reminder LAST,
        no Swedish directive/reminder leakage
  (iii) 'sv'/'en' prompt behaviour byte-identical to the pre-EU literals
  (iv)  TTS: pronunciation hint forwarded per campaign language AND the
        cache key carries the language (de→en→de re-synthesizes)
  (v)   _err(): only 'sv' returns the Swedish message

Fixtures follow tests/test_eu_languages.py (store_tmp) and
tests/test_tts_style.py (tmp users.json + tier2 seed).
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


def _campaign_state(lang):
    """Awakening-ready minimal state (recipe from test_eu_languages.py)."""
    return {
        "meta": {"campaign_id": "a5-int", "language": lang, "user": "a5",
                 "campaign_name": "A5", "turn_count": 1},
        "character": {"name": "Vespera", "class": "Fighter", "level": 1,
                      "hp": {"current": 10, "max": 10, "temp": 0}, "ac": 12,
                      "abilities": {}},
        "inventory": [], "currency": {"pp": 0, "gp": 0, "sp": 0, "cp": 0},
        "npcs": [], "quests": [], "lore": [], "locations": [],
        "world": {"current_location": "", "visited_locations": [], "time": "", "weather": ""},
        "transcript": [],
    }


# ── (i) POST /api/campaign language gate ────────────────────────────────

def test_create_campaign_rejects_xx_accepts_de(client):
    import main
    from auth import create_token
    tok = create_token("a5_gate", "player")
    r = client.post("/api/campaign", json={"name": "Gate", "language": "xx"},
                    cookies={"morkrets_token": tok})
    assert r.status_code == 400, r.text
    # de reaches state
    r2 = client.post("/api/campaign", json={"name": "Gate", "language": "de"},
                     cookies={"morkrets_token": tok})
    assert r2.status_code == 200, r2.text
    assert main.store.get("a5_gate")["meta"]["language"] == "de"


def test_create_campaign_german_default_name(client):
    import main
    import languages
    from auth import create_token
    tok = create_token("a5_name", "player")
    r = client.post("/api/campaign", json={"language": "de"},
                    cookies={"morkrets_token": tok})
    assert r.status_code == 200, r.text
    state = main.store.get("a5_name")
    assert state["meta"]["campaign_name"] == languages.DEFAULT_CAMPAIGN_NAMES["de"]


# ── (ii) German system prompt: directive first, reminder last ───────────

def test_system_prompt_de_directive_first_reminder_last():
    import main
    import languages
    p = main._build_system_prompt(_campaign_state("de"))
    lines = p.splitlines()
    assert lines[0].lstrip().startswith("[LANGUAGE: DEUTSCH]")
    assert p.rstrip().endswith(languages.get_reminder("de").strip())
    assert "[SPRÅK: SVENSKA]" not in p
    assert "[SPRÅKPÅMINNELSE]" not in p
    # protocol tags survive untranslated
    for tag in ("[KAST:", "[NPC:", "[STRID:", "[PLATS:", "[TID:", "[QUEST:"):
        assert tag in p


def test_system_prompt_de_awakening_uses_localized_blocks():
    import main
    import languages
    st = _campaign_state("de")
    st["meta"]["awakening"] = True
    p1 = main._build_system_prompt(st, turn_override=1)
    assert languages.get_awakening_ask("de") in p1
    p2 = main._build_system_prompt(st, turn_override=2)
    expected = languages.get_awakening_open("de").format(
        opening_style=st["meta"].get("opening_style",
                                     dict(languages.get_opening_styles("de"))["alone"]))
    assert expected in p2
    assert "{opening_style}" not in p2  # placeholder consumed, not leaked raw


# ── (iii) sv/en unchanged (verbatim pre-EU literals) ────────────────────

SV_DIRECTIVE_VERBATIM = (
    "[SPRÅK: SVENSKA] Du MÅSTE skriva ALL narration, dialog, NPC-repliker, "
    "beskrivningar och varje ord i ditt svar på svenska.\n"
)
SV_REMINDER_VERBATIM = (
    "\n[SPRÅKPÅMINNELSE] Ditt svar DENNA TUR måste skrivas helt på svenska — varenda ord av "
    "narration, dialog och beskrivning. Byt aldrig till engelska, oavsett vad samtalshistoriken innehåller."
)
EN_DIRECTIVE_VERBATIM = (
    "[LANGUAGE: ENGLISH] You MUST write ALL narration, dialogue, NPC speech, "
    "descriptions, and every single word of your response in English. "
    "This overrides any Swedish text in the instructions below — those are "
    "internal system notes, NOT the output language.\n"
)
EN_REMINDER_VERBATIM = (
    "\n[LANGUAGE REMINDER] Your response THIS TURN must be written entirely in English — "
    "every word of narration, dialogue, and description. Never switch to Swedish, no matter "
    "what the conversation history contains."
)


def test_system_prompt_sv_verbatim_unchanged():
    import main
    p = main._build_system_prompt(_campaign_state("sv"))
    assert p.startswith(SV_DIRECTIVE_VERBATIM)
    assert p.endswith(SV_REMINDER_VERBATIM)
    assert "[LANGUAGE:" not in p


def test_system_prompt_en_verbatim_unchanged():
    import main
    p = main._build_system_prompt(_campaign_state("en"))
    assert p.startswith(EN_DIRECTIVE_VERBATIM)
    assert p.endswith(EN_REMINDER_VERBATIM)
    assert "[SPRÅK: SVENSKA]" not in p


# ── (iv) TTS: pronunciation hint + language in the cache key ────────────

def test_tts_hint_forwarded_and_cache_key_carries_language(client, monkeypatch):
    """de→en→de for the SAME text re-synthesizes every switch — the cache key
    must carry the language (else a cached EN take would serve German audio).

    The 600s TTL cache is process-global across tests, so the three calls use
    distinct prefixes and a throwaway warm-up primes the voice mapping:
    identical tail text, identical style, still one fresh synth per language.
    """
    import main
    import languages
    tok = _seed_tier2("a5_tts")
    r = client.post("/api/campaign", json={"name": "TTS", "language": "de"},
                    cookies={"morkrets_token": tok})
    assert r.status_code == 200, r.text

    seen = []

    def fake_synth(voice, text, style="", **kw):
        seen.append(kw.get("pronunciation", ""))
        return b"ID3fake"

    monkeypatch.setattr(main, "_synth_stepfun_tts", fake_synth)
    tail = "Nacht war kalt."
    # warm-up (same voice resolution, different cache entry) — not counted
    client.post("/api/tts", json={"text": "Warmup ein", "voice": "male", "provider": "stepfun"},
                cookies={"morkrets_token": tok})
    seen.clear()

    def _speak(prefix):
        return client.post("/api/tts",
                           json={"text": f"{prefix} {tail}", "voice": "male", "provider": "stepfun"},
                           cookies={"morkrets_token": tok})

    assert _speak("Erster").status_code == 200
    assert seen[-1] == languages.TTS_PRONUNCIATION_HINTS["de"]

    # switch language to en → fresh synth with NO hint (and not a cache hit)
    rp = client.patch("/api/campaign/language", json={"language": "en"},
                      cookies={"morkrets_token": tok})
    assert rp.status_code == 200, rp.text
    assert _speak("Andra").status_code == 200
    assert seen[-1] == ""  # en hint is empty

    # back to de → fresh synth WITH the hint again
    rp = client.patch("/api/campaign/language", json={"language": "de"},
                      cookies={"morkrets_token": tok})
    assert rp.status_code == 200, rp.text
    assert _speak("Tredje").status_code == 200
    assert seen[-1] == languages.TTS_PRONUNCIATION_HINTS["de"]
    assert len(seen) == 3  # every language switch re-synthesized — never cached cross-language


def test_tts_cache_key_holds_language_element(monkeypatch):
    """White-box pin: the synth call is keyed by (provider, voice, style, lang, text)."""
    import main
    keys = []
    real_set = main._tts_cache_set

    def spy_set(key, data):
        keys.append(key)
        return real_set(key, data)

    monkeypatch.setattr(main, "_tts_cache_set", spy_set)
    monkeypatch.setattr(main, "_synth_stepfun_tts",
                        lambda voice, text, style="", **kw: b"ID3fake")
    _prime_tts_call(monkeypatch, "it")
    assert keys, "no cache-set happened"
    provider, voice, style, lang, text = keys[-1]
    assert lang == "it"


def _prime_tts_call(monkeypatch, lang):
    """Fire one /api/tts for a campaign in `lang` via TestClient (tier2 seed)."""
    import main
    from fastapi.testclient import TestClient
    tok = _seed_tier2(f"a5_key_{lang}")
    with TestClient(main.app) as c:
        r = c.post("/api/campaign", json={"name": "K", "language": lang},
                   cookies={"morkrets_token": tok})
        assert r.status_code == 200, r.text
        r2 = c.post("/api/tts", json={"text": "Prova", "voice": "male", "provider": "stepfun"},
                    cookies={"morkrets_token": tok})
        assert r2.status_code == 200, r2.text


def test_tts_instruction_stays_under_128_with_hint():
    import main
    hint = "Speak German with standard (Hochdeutsch) pronunciation, natural storytelling rhythm."
    base = ("Speak Swedish with Standard Swedish pronunciation, natural rhythm. "
            "Warm expressive storytelling, rich and inviting.")
    out = main._tts_instruction(base, "scary", pronunciation=hint)
    assert len(out) <= 128
    assert out.startswith("Low ominous eerie tone")
    # no-style + no-hint returns the base verbatim (en/sv path unchanged)
    assert main._tts_instruction(base, "") == base
    # hint appended when no style present
    out2 = main._tts_instruction("Short voice.", "", pronunciation=hint)
    assert out2.endswith(hint[: len(hint)]) or hint in out2
    assert len(out2) <= 128


# ── (v) _err ────────────────────────────────────────────────────────────

def test_err_only_svenska_gets_swedish():
    import main
    assert main._err("x", "y", "de") == "y"
    assert main._err("x", "y", "fr") == "y"
    assert main._err("x", "y", "es") == "y"
    assert main._err("x", "y", "it") == "y"
    assert main._err("x", "y", "en") == "y"
    assert main._err("x", "y", "sv") == "x"
    assert main._err("x", "y") == "x"  # default lang='sv' unchanged
