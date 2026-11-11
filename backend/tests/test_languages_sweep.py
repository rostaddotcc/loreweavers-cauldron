"""A3 i18n sweep — de/fr/es/it fall back to the EN branch everywhere.

Contract: backend/tmp/i18n-eu-2026-10 A3. Rule: Swedish text only when
language == 'sv'; 'en' unchanged; all other codes (de/fr/es/it/okänd) →
English chrome + (where applicable) an English target-language directive.
These prompt builders are pure functions — no state fallback needed.
"""

import combat
import extraction
import guardian
import locations
import logbook


# ── helpers ──────────────────────────────────────────────────────────────

SV_COMBAT_WORDS = ("Runda", "Turordning", "Fiender", "Allierade", "STRID")

SWEDISH_ONLY_MARKERS = ("Nivå", "Klass", "Plats:", "Aktiva uppdrag", "Valuta",
                        "död", "levande")


def _combat_state():
    return {
        "character": {"name": "Vera", "hp": {"current": 7, "max": 10}, "ac": 14,
                      "spell_slots": {}, "statuses": []},
        "world": {"combat": {
            "active": True, "round": 2, "current_index": 0,
            "turn_order": [{"key": "p:vera", "name": "Vera", "initiative": 15},
                            {"key": "e:gob", "name": "Goblin", "initiative": 9}],
            "enemies": [{"name": "Goblin", "hp": 5, "max_hp": 7, "ac": 13,
                          "alive": True, "statuses": []}],
            "allies": [],
            "player_actions": {"action": True, "bonus": False, "reaction": True},
        }},
    }


def _rich_state():
    return {
        "character": {"name": "Vera", "class": "Krigare", "level": 3,
                      "hp": {"current": 20, "max": 24}, "ac": 16,
                      "xp": {"current": 100, "next_level": 300},
                      "abilities": {}, "proficiency": 2, "statuses": []},
        "inventory": [{"name": "Dolk", "qty": 1}],
        "currency": {"pp": 0, "gp": 5, "sp": 2, "cp": 0},
        "npcs": [{"name": "Maren", "relation": "allierad", "alive": True},
                  {"name": "Goblin", "relation": "fiende", "alive": False}],
        "quests": [{"id": "abcd1234", "name": "Hitta lanten", "status": "aktiv"},
                    {"name": "Rädda byn", "status": "slutförd"}],
        "world": {"current_location": "Gråvakt", "day": 4},
    }


# ── combat.build_combat_context ──────────────────────────────────────────

def test_combat_context_sv_keeps_swedish():
    ctx = combat.build_combat_context(_combat_state(), "sv")
    assert "STRID — Runda 2" in ctx
    assert "Turordning:" in ctx
    assert "Fiender:" in ctx


def test_combat_context_en_unchanged():
    ctx = combat.build_combat_context(_combat_state(), "en")
    assert "COMBAT — Round 2" in ctx
    assert "Turn order:" in ctx
    assert "Enemies:" in ctx
    for w in SV_COMBAT_WORDS:
        assert w not in ctx


def test_combat_context_eu_langs_get_english():
    for lang in ("de", "fr", "es", "it", "xx"):
        ctx = combat.build_combat_context(_combat_state(), lang)
        assert "COMBAT — Round 2" in ctx, lang
        assert "Turn order:" in ctx, lang
        for w in SV_COMBAT_WORDS:
            assert w not in ctx, (lang, w)


# ── guardian: language instruction selector ─────────────────────────────

def test_lang_instruction_selector():
    assert "SVENSKA" in guardian._lang_instruction("sv")
    en = guardian._lang_instruction("en")
    assert "ENGLISH" in en and "GERMAN" not in en
    for lang, word in (("de", "GERMAN"), ("fr", "FRENCH"),
                        ("es", "SPANISH"), ("it", "ITALIAN")):
        ins = guardian._lang_instruction(lang)
        assert word in ins, lang
        assert "SVENSKA" not in ins, lang
    # okänt → EN fallback
    assert guardian._lang_instruction("xx") == en


def test_extract_mechanics_messages_de_uses_english_frame_and_german_directive():
    msgs = guardian.build_extract_mechanics_messages(
        dm_reply="Der Goblin greift an.", player_msg="Ich verteidige mich.",
        state=_rich_state(), turn=7, language="de")
    system = msgs[0]["content"]
    user = msgs[1]["content"]
    assert "in GERMAN — every sentence." in system
    assert "[VIKTIGT" not in system  # no Swedish instruction
    assert "## Current state" in user
    assert "## Nuvarande tillstånd" not in user


def test_extract_mechanics_messages_sv_en_unchanged():
    sv = guardian.build_extract_mechanics_messages("x", "y", _rich_state(), 1, "sv")
    assert "[VIKTIGT" in sv[0]["content"]
    assert "## Nuvarande tillstånd" in sv[1]["content"]
    en = guardian.build_extract_mechanics_messages("x", "y", _rich_state(), 1, "en")
    assert "in ENGLISH.]" in en[0]["content"]
    assert "## Current state" in en[1]["content"]


# ── guardian: state/char context + roll-check ───────────────────────────

def test_format_state_for_guardian_eu_english_sv_swedish():
    sv = guardian._format_state_for_guardian(_rich_state(), "sv")
    de = guardian._format_state_for_guardian(_rich_state(), "de")
    assert "Aktiva uppdrag" in sv and "Active quests" in de
    assert "Valuta" in sv and "Currency" in de
    assert "Plats:" in sv and "Location:" in de
    for marker in SWEDISH_ONLY_MARKERS:
        if marker == "Plats:":
            continue
        assert marker not in de, marker
    assert "levande" in sv


def test_format_char_context_eu_english():
    de = guardian._format_char_context(_rich_state(), "de")
    assert "Class:" in de and "Level: 3" in de
    assert "Klass" not in de and "Nivå" not in de


def test_parse_roll_check_result_language_default():
    raw = '{"needs_roll": true, "notation": "1d20"}'
    assert guardian.parse_roll_check_result(raw, "sv")["label"] == "Tärningsslag"
    assert guardian.parse_roll_check_result(raw, "de")["label"] == "Dice roll"
    assert guardian.parse_roll_check_result(raw, "en")["label"] == "Dice roll"


def test_build_roll_check_messages_eu_english():
    state = {"character": {"abilities": {}, "level": 1, "hp": {}}}
    msgs = guardian.build_roll_check_messages("Ich schleiche los", state, "de")
    assert msgs[0]["content"] == guardian.GUARDIAN_PRE_SYSTEM_EN
    assert "Does this require a dice roll?" in msgs[1]["content"]
    sv = guardian.build_roll_check_messages("Jag smyger", state, "sv")
    assert "Kräver detta ett tärningskast?" in sv[1]["content"]


def test_format_guardian_summary_de_no_swedish_labels():
    effects = [{"type": "xp", "value": 50}, {"type": "plats", "value": "Gråvakt"}]
    out = guardian.format_guardian_summary(effects, _rich_state(), "de", mech={})
    assert "Ny plats" not in out
    assert "New location" in out


# ── locations.format_travel_time ─────────────────────────────────────────

def test_travel_time_exact_forms():
    assert locations.format_travel_time(3, "de") == "3 Tage Reise"
    assert locations.format_travel_time(3, "sv") == "3 dagars resa"
    assert locations.format_travel_time(3, "fr") == "3 jours de voyage"
    assert locations.format_travel_time(3, "es") == "3 días de viaje"
    assert locations.format_travel_time(3, "it") == "3 giorni di viaggio"
    assert locations.format_travel_time(3, "en") == "3 days' travel"
    assert locations.format_travel_time(3, "xx") == "3 days' travel"
    # singular
    assert locations.format_travel_time(1, "de") == "1 Tag Reise"
    assert locations.format_travel_time(1, "sv") == "1 dags resa"
    assert locations.format_travel_time(1, "fr") == "1 jour de voyage"
    assert locations.format_travel_time(1, "es") == "1 día de viaje"
    assert locations.format_travel_time(1, "it") == "1 giorno di viaggio"
    assert locations.format_travel_time(1, "en") == "1 day's travel"
    # <1 day + here marker keep en/sv byte-identical, unknown → EN
    assert locations.format_travel_time(0.3, "sv") == "Här är du"
    assert locations.format_travel_time(0.3, "de") == "Sie sind hier"
    assert locations.format_travel_time(0.3, "xx") == "You are here"
    assert locations.format_travel_time(0.7, "fr") == "Moins d'un jour"
    assert locations.format_travel_time(0.7, "sv") == "Mindre än en dag"
    assert locations.format_travel_time(1.5, "en") == "1.5 days' travel"
    assert locations.format_travel_time(1.5, "it") == "1.5 giorni di viaggio"


def test_locations_with_travel_marker_per_lang():
    state = {"meta": {"campaign_id": "c1"},
             "world": {"current_location": "A", "visited_locations": ["A", "B"]},
             "locations": [{"name": "A", "x": 10, "y": 10, "terrain": "skog"},
                            {"name": "B", "x": 80, "y": 10, "terrain": "skog"}]}
    out = {l["name"]: l for l in locations.get_locations_with_travel(state, "de")}
    assert out["A"]["travel_text"] == "Sie sind hier"
    assert "Tage" in out["B"]["travel_text"] or "Tag " in out["B"]["travel_text"]
    out_sv = {l["name"]: l for l in locations.get_locations_with_travel(state, "sv")}
    assert out_sv["A"]["travel_text"] == "Du är här"
    out_xx = {l["name"]: l for l in locations.get_locations_with_travel(state, "xx")}
    assert out_xx["A"]["travel_text"] == "You are here"


# ── logbook.build_log_prompt ─────────────────────────────────────────────

def test_log_prompt_directives():
    p = logbook.build_log_prompt("transkript", "", "Namn", "de")
    assert "Write the entire journal entry in GERMAN." in p
    assert "Du är en krönikör" not in p  # EN base, not the SV prompt
    assert "Chronicle" in p or "chronicler" in p
    assert "## Transcript" in p  # EN labels for campaign/transcript
    assert "Campaign: Namn" in p
    for lang, word in (("fr", "FRENCH"), ("es", "SPANISH"), ("it", "ITALIAN")):
        assert word in logbook.build_log_prompt("t", "", "c", lang)
    # en + sv oförändrade, inget direktiv
    en = logbook.build_log_prompt("t", "", "c", "en")
    assert "GERMAN" not in en and "chronicler" in en
    sv = logbook.build_log_prompt("t", "", "c", "sv")
    assert "GERMAN" not in sv and "Du är en krönikör" in sv
    assert "Transkript" in sv and "Kampanj" in sv
    # okänt → EN utan direktiv
    xx = logbook.build_log_prompt("t", "", "c", "xx")
    assert "GERMAN" not in xx and "chronicler" in xx


# ── extraction ───────────────────────────────────────────────────────────

def test_facts_block_labels_eu_english():
    facts = [extraction.Fact(category="location", text="X", source_turn=2),
             extraction.Fact(category="event", text="Y", source_turn=3)]
    sv = extraction.format_facts_block(facts, "sv")
    assert "FAKTAREGISTER" in sv and "[PLATS]" in sv and "(tur 2)" in sv
    for lang in ("de", "fr", "es", "it", "xx", "en"):
        out = extraction.format_facts_block(facts, lang)
        assert "FACT REGISTER" in out, lang
        assert "[LOCATION]" in out and "[EVENT]" in out, lang
        assert "PLATS" not in out and "(tur " not in out, lang


def test_extraction_messages_eu_english_prompt_plus_directive():
    msgs = extraction.build_extraction_messages("DM svar", "spelare", 5, "(tomt)", "de")
    assert "Extract and write the fact texts in GERMAN." in msgs[0]["content"]
    assert msgs[0]["content"].startswith(extraction.EXTRACTION_SYSTEM_PROMPT_EN[:60])
    fr = extraction.build_extraction_messages("x", "y", 1, "(tomt)", "fr")
    assert "in FRENCH." in fr[0]["content"]
    # 'en' → base EN prompt, inget extra direktiv (oförändrat beteende)
    en = extraction.build_extraction_messages("x", "y", 1, "(tomt)", "en")
    assert en[0]["content"] == extraction.EXTRACTION_SYSTEM_PROMPT_EN
    # 'sv' → SV-prompt, inget främmande direktiv
    sv = extraction.build_extraction_messages("x", "y", 1, "(tomt)", "sv")
    assert sv[0]["content"] == extraction.EXTRACTION_SYSTEM_PROMPT
    # okänt → EN utan direktiv
    xx = extraction.build_extraction_messages("x", "y", 1, "(tomt)", "xx")
    assert xx[0]["content"] == extraction.EXTRACTION_SYSTEM_PROMPT_EN
