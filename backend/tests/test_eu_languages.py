"""EU-language contract test (de/fr/es/it) — tmp/i18n-eu-2026-10/CONTRACT.md.

BLACK-BOX GUARD: this file pins the whole EU flow end-to-end — languages.py,
main.py create/PATCH gates, _build_system_prompt directive+reminder slots,
and the guardian language instruction. It is EXPECTED RED until the parallel
agents (A1 languages.py, A3 guardian sweep, A4 main integration) land.
Nothing here fixes a bug — it only asserts the contract.

Design rules (per CONTRACT.md):
  - `languages` is imported via pytest.importorskip where a test genuinely
    needs it (a missing module must SKIP, never break collection of the suite).
  - main.py / guardian.py tests import inside the function and FAIL correctly
    when the integration is missing — they must not skip.
  - en/sv backward-compatibility tests are green today and must stay green.
"""

import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

EU_LANGS = ["de", "fr", "es", "it"]

# Directive line-0 markers, pinned by CONTRACT A4/A1:
#   en [LANGUAGE: ...] · sv [SPRÅK: ...] · fr [LANGUE: ...]
#   es [IDIOMA: ...]  · it [LINGUA: ...]
DIRECTIVE_MARKERS = {
    "de": "[LANGUAGE: DEUTSCH]",
    "fr": "[LANGUE: FRANÇAIS]",
    "es": "[IDIOMA: ESPAÑOL]",
}

# Guardian post-DM instruction markers (A3: English sentences, target language
# named in caps): "[IMPORTANT: Write all user-facing text ... in GERMAN ...]"
GUARDIAN_MARKERS = {"de": "GERMAN", "fr": "FRENCH", "es": "SPANISH", "it": "ITALIAN"}


def _make_state(lang="de", **meta_extra):
    """Minimal awakening-ready campaign state (recipe from
    test_system_prompt_travel.py: meta.user + transcript are required)."""
    meta = {
        "campaign_id": "test-eu-lang",
        "language": lang,
        "user": "eu_tester",
        "campaign_name": "EU Test",
        "turn_count": 1,
    }
    meta.update(meta_extra)
    return {
        "meta": meta,
        "character": {"name": "Vespera", "class": "Fighter", "level": 1,
                      "hp": {"current": 10, "max": 10, "temp": 0}, "ac": 12,
                      "abilities": {}},
        "inventory": [],
        "currency": {"pp": 0, "gp": 0, "sp": 0, "cp": 0},
        "npcs": [],
        "quests": [],
        "world": {"current_location": "", "visited_locations": [], "time": "", "weather": ""},
        "lore": [],
        "locations": [],
        "transcript": [],
    }


@pytest.fixture
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


# ═══════════════════════════════════════════════════════════════════════
# 1. languages.py module contract (A1)
# ═══════════════════════════════════════════════════════════════════════

def test_supported_languages_include_eu():
    languages = pytest.importorskip("languages")
    for code in ["en", "sv"] + EU_LANGS:
        assert code in languages.SUPPORTED_LANGUAGES, f"{code} missing from SUPPORTED_LANGUAGES"
    assert set(languages.LANG_NAMES) >= {"en", "sv"} | set(EU_LANGS)
    assert set(languages.LANG_FLAGS) >= {"en", "sv"} | set(EU_LANGS)


def test_is_supported_accepts_eu_rejects_garbage():
    languages = pytest.importorskip("languages")
    for code in EU_LANGS:
        assert languages.is_supported(code) is True, code
    assert languages.is_supported("xx") is False
    assert languages.is_supported("") is False
    # en/sv must stay supported (backward compat)
    assert languages.is_supported("en") is True
    assert languages.is_supported("sv") is True


def test_opening_styles_five_entries_same_keys_across_langs():
    languages = pytest.importorskip("languages")
    de = languages.get_opening_styles("de")
    assert len(de) == 5
    de_keys = {k for k, _ in de}
    assert de_keys == {"meeting", "alone", "in_media_res", "awakening", "summoned"}
    for code in ["en", "sv", "fr", "es", "it"]:
        other = languages.get_opening_styles(code)
        assert len(other) == 5, code
        assert {k for k, _ in other} == de_keys, f"key set drift in {code}"


def test_awakening_open_holds_placeholders():
    languages = pytest.importorskip("languages")
    for code in EU_LANGS:
        block = languages.get_awakening_open(code)
        assert "{opening_style}" in block, f"{code}: literal {{opening_style}} required"
        ask = languages.get_awakening_ask(code)
        assert isinstance(ask, str) and ask.strip(), f"{code}: AWAKENING_ASK empty"
        # must be translated, not the English block
        assert ask != languages.get_awakening_ask("en"), f"{code}: ask not translated"


def test_directive_markers_per_language():
    languages = pytest.importorskip("languages")
    for code, marker in DIRECTIVE_MARKERS.items():
        d = languages.get_directive(code)
        assert d.lstrip().startswith(marker), f"{code}: directive must start with {marker!r}"
    it = languages.get_directive("it").lstrip()
    assert it.startswith("[LINGUA:"), "it: directive must start with [LINGUA: ...]"
    # Every directive must exempt the Swedish protocol tags (they stay SV).
    for code in EU_LANGS:
        assert "[KAST:]" in languages.get_directive(code), \
            f"{code}: directive must name the [KAST:]-tag exemption"


def test_reminders_present_for_all_six_languages():
    languages = pytest.importorskip("languages")
    for code in ["en", "sv"] + EU_LANGS:
        assert languages.get_reminder(code).strip(), f"{code}: empty reminder"
    # EU reminders must differ from both the EN and the SV one.
    for code in EU_LANGS:
        r = languages.get_reminder(code)
        assert r != languages.get_reminder("en"), f"{code}: reminder is English"
        assert "SVENSKA" not in r, f"{code}: reminder is Swedish"


def test_languages_fallback_to_english():
    languages = pytest.importorskip("languages")
    assert languages.get_directive("xx") == languages.get_directive("en")
    assert languages.get_reminder("xx") == languages.get_reminder("en")
    assert languages.get_opening_styles("xx") == languages.get_opening_styles("en")
    assert languages.get_awakening_open("xx") == languages.get_awakening_open("en")
    assert languages.get_awakening_ask("xx") == languages.get_awakening_ask("en")
    assert languages.get_directive("") == languages.get_directive("en")


def test_default_campaign_names_and_tts_hints():
    languages = pytest.importorskip("languages")
    for code in ["en", "sv"] + EU_LANGS:
        assert code in languages.DEFAULT_CAMPAIGN_NAMES
        assert languages.DEFAULT_CAMPAIGN_NAMES[code].strip()
    # en/sv hints stay untouched (empty); EU hints exist, English text, <=90 chars
    for code in ("en", "sv"):
        assert languages.TTS_PRONUNCIATION_HINTS.get(code, "") == ""
    for code in EU_LANGS:
        hint = languages.TTS_PRONUNCIATION_HINTS[code]
        assert hint and len(hint) <= 90, f"{code}: hint must be 1..90 chars"


# ═══════════════════════════════════════════════════════════════════════
# 2. POST /api/campaign language gate (A4)
# ═══════════════════════════════════════════════════════════════════════

def _create_campaign(client, username, lang):
    from auth import create_token
    tok = create_token(username, "player")
    r = client.post("/api/campaign", json={"name": "EU Gate Test", "language": lang},
                    cookies={"morkrets_token": tok})
    return tok, r


def test_create_campaign_accepts_german(client):
    """de must reach state.meta.language (contract A4: is_supported gate)."""
    import main
    tok, r = _create_campaign(client, "eu_de_player", "de")
    assert r.status_code == 200, r.text
    state = main.store.get("eu_de_player")
    assert state["meta"]["language"] == "de"


def test_create_campaign_rejects_unsupported_language(client):
    """xx → HTTP 400 (English detail), campaign must NOT be created."""
    tok, r = _create_campaign(client, "eu_xx_player", "xx")
    assert r.status_code == 400, f"expected 400 for language='xx', got {r.status_code}: {r.text}"


def test_create_campaign_german_opening_style_localized(client):
    """meta.opening_key ∈ the 5 de keys; meta.opening_style is DEUTSCH text,
    not the English or Swedish default list."""
    languages = pytest.importorskip("languages")  # cross-check needs A1
    import main
    tok, r = _create_campaign(client, "eu_style_player", "de")
    assert r.status_code == 200, r.text
    state = main.store.get("eu_style_player")
    styles_de = languages.get_opening_styles("de")
    keys = {k for k, _ in styles_de}
    texts = {t for _, t in styles_de}
    assert state["meta"].get("opening_key") in keys
    assert state["meta"].get("opening_style") in texts, \
        "opening_style must come from get_opening_styles('de'), not en/sv defaults"
    # backward compat: en campaigns still draw from the English list
    tok, r = _create_campaign(client, "eu_style_en", "en")
    assert r.status_code == 200
    state_en = main.store.get("eu_style_en")
    texts_en = {t for _, t in languages.get_opening_styles("en")}
    assert state_en["meta"].get("opening_style") in texts_en


# ═══════════════════════════════════════════════════════════════════════
# 3. PATCH /api/campaign/language (A4)
# ═══════════════════════════════════════════════════════════════════════

def test_patch_language_accepts_italian(client):
    """Post-integration: 'it' → 200 + meta.language == 'it'.
    (Current code 400s anything outside en/sv — RED until A4.)"""
    import main
    tok, r = _create_campaign(client, "eu_it_player", "en")
    assert r.status_code == 200
    r2 = client.patch("/api/campaign/language", json={"language": "it"},
                      cookies={"morkrets_token": tok})
    assert r2.status_code == 200, f"expected 200 for language='it', got {r2.status_code}: {r2.text}"
    state = main.store.get("eu_it_player")
    assert state["meta"]["language"] == "it"


def test_patch_language_rejects_unsupported(client):
    import main
    tok, r = _create_campaign(client, "eu_patch_xx", "en")
    assert r.status_code == 200
    r2 = client.patch("/api/campaign/language", json={"language": "xx"},
                      cookies={"morkrets_token": tok})
    assert r2.status_code == 400, r2.text
    # unchanged: the rejected PATCH must not mutate the campaign language
    state = main.store.get("eu_patch_xx")
    assert state["meta"]["language"] == "en"


def test_patch_language_en_sv_still_work(client):
    """Backward compat: the old en/sv values keep returning 200."""
    import main
    tok, r = _create_campaign(client, "eu_patch_compat", "sv")
    assert r.status_code == 200
    for code in ("en", "sv"):
        r2 = client.patch("/api/campaign/language", json={"language": code},
                          cookies={"morkrets_token": tok})
        assert r2.status_code == 200, f"{code}: {r2.status_code} {r2.text}"
        assert main.store.get("eu_patch_compat")["meta"]["language"] == code


# ═══════════════════════════════════════════════════════════════════════
# 4. _build_system_prompt directive (line 0) + reminder (tail)
# ═══════════════════════════════════════════════════════════════════════

def test_system_prompt_german_directive_and_reminder():
    import main
    try:
        import languages
    except ImportError:
        languages = None
    p = main._build_system_prompt(_make_state("de"))
    first_line = p.splitlines()[0]
    assert "[LANGUAGE: DEUTSCH]" in first_line, \
        f"line 0 must carry the German directive, got: {first_line[:80]!r}"
    assert "[SPRÅK: SVENSKA]" not in p
    assert "[SPRÅKPÅMINNELSE]" not in p, "Swedish reminder must not leak into a de campaign"
    if languages is not None:
        assert languages.get_reminder("de") in p, "German reminder must be the tail block"


def test_system_prompt_french_directive():
    import main
    p = main._build_system_prompt(_make_state("fr"))
    assert "[LANGUE: FRANÇAIS]" in p.splitlines()[0]
    assert "[SPRÅK:" not in p
    assert "[SPRÅKPÅMINNELSE]" not in p


def test_system_prompt_swedish_unchanged():
    """GREEN TODAY — and it must stay green: sv keeps the exact current SV
    directive/reminder pair (contract: sv-beteende oförändrat)."""
    import main
    p = main._build_system_prompt(_make_state("sv"))
    assert "[SPRÅK: SVENSKA]" in p.splitlines()[0]
    assert "Du MÅSTE skriva ALL narration" in p
    assert "[SPRÅKPÅMINNELSE]" in p
    assert "[LANGUAGE:" not in p


def test_system_prompt_english_unchanged():
    """GREEN TODAY — en keeps the current EN directive + '[LANGUAGE REMINDER]'
    tail. Backward-compat pin per contract rule 'en must behave exactly as today'."""
    import main
    p = main._build_system_prompt(_make_state("en"))
    assert p.splitlines()[0].startswith("[LANGUAGE: ENGLISH]")
    assert "[LANGUAGE REMINDER]" in p
    assert "[SPRÅK: SVENSKA]" not in p
    assert "[SPRÅKPÅMINNELSE]" not in p


# ═══════════════════════════════════════════════════════════════════════
# 5. Guardian language instruction (A3 sweep)
# ═══════════════════════════════════════════════════════════════════════

def test_guardian_by_lang_instruction_map_exists():
    """A3 pins the module-level selector table _LANG_INSTRUCTION_BY_LANG."""
    import guardian
    assert hasattr(guardian, "_LANG_INSTRUCTION_BY_LANG"), \
        "guardian must expose _LANG_INSTRUCTION_BY_LANG (CONTRACT A3)"
    table = guardian._LANG_INSTRUCTION_BY_LANG
    for code, marker in GUARDIAN_MARKERS.items():
        assert code in table, code
        assert marker in table[code], f"{code}: instruction must name {marker}"
        assert table[code].strip().startswith("[IMPORTANT:"), \
            "guardian instructions are English meta-instructions"


@pytest.mark.parametrize("code", EU_LANGS)
def test_guardian_extract_messages_target_language(code):
    """build_extract_mechanics_messages(language=code) system block must carry
    the target-language instruction — and NOT the Swedish one (RED today:
    anything != 'en' falls into _LANG_INSTRUCTION_SV)."""
    import guardian
    msgs = guardian.build_extract_mechanics_messages(
        dm_reply="Le personnage avance prudemment.",
        player_msg="Je regarde autour de moi.",
        state=_make_state(code),
        turn=3,
        language=code,
    )
    system = msgs[0]["content"]
    assert GUARDIAN_MARKERS[code] in system, f"de/fr/es/it: missing {GUARDIAN_MARKERS[code]}"
    assert "[VIKTIGT:" not in system, "Swedish lang instruction leaked into an EU campaign"


def test_guardian_en_sv_instructions_unchanged():
    """GREEN TODAY: en → English IMPORTANT instruction, sv → Swedish VIKTIGT."""
    import guardian
    en = guardian.build_extract_mechanics_messages("x", "y", _make_state("en"), 2, "en")[0]["content"]
    sv = guardian.build_extract_mechanics_messages("x", "y", _make_state("sv"), 2, "sv")[0]["content"]
    assert "[IMPORTANT:" in en and "ENGLISH" in en and "[VIKTIGT:" not in en
    assert "[VIKTIGT:" in sv and "SVENSKA" in sv and "[IMPORTANT:" not in sv


# ═══════════════════════════════════════════════════════════════════════
# 6. Protocol-tag invariants across the whole flow
# ═══════════════════════════════════════════════════════════════════════

def test_protocol_tags_stay_swedish_in_eu_prompts():
    """CONTRACT global rule: backend protocol tags are Swedish literals in
    every campaign language — [KAST:] [STRID:] [NPC:] [PLATS:] [TID:]
    [QUEST:] must NEVER be translated out of the DM prompt."""
    import main
    PROTOCOL_TAGS = ["[KAST:", "[NPC:", "[STRID:", "[PLATS:", "[TID:", "[QUEST:"]
    for code in EU_LANGS:
        p = main._build_system_prompt(_make_state(code))
        for tag in PROTOCOL_TAGS:
            assert tag in p, f"{code}: protocol tag {tag!r} was translated/lost"


def test_internal_enums_are_code_level_tokens():
    """CONTRACT: quest-status/NPC-relation enums are code-level and stay
    Swedish in the parser regardless of campaign language ('bara visning')."""
    import main
    clean, npcs = main._parse_npcs("[NPC:Mira|Scout|allierad]")
    assert npcs and npcs[0]["relation"] == "allierad"
    _, bad = main._parse_npcs("[NPC:Mira|Scout|verbündet]")  # German relation → normalized
    assert bad[0]["relation"] == "okänd"
