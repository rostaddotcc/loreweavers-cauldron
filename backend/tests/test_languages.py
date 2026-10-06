"""Tests for the central language module (i18n-eu 2026-10, task A1).

Covers: SUPPORTED_LANGUAGES, is_supported rejection, EN fallback for every
getter, 5 opening styles per language with identical key sets, the verbatim
{opening_style} placeholder in every AWAKENING_OPEN variant, directive +
reminder presence for all 6 languages, the protocol-tag exemption wording in
the new de/fr/es/it directives, and the TTS hint length budget.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import languages as L  # noqa: E402

ALL_LANGS = ["en", "sv", "de", "fr", "es", "it"]
EU_LANGS = ["de", "fr", "es", "it"]
EXPECTED_KEYS = {"meeting", "alone", "in_media_res", "awakening", "summoned"}
PROTOCOL_TAGS = ["[KAST:]", "[STRID:]", "[NPC:]", "[PLATS:]", "[TID:]", "[QUEST:]", "[NY_DAG:]"]


# ── registry ──────────────────────────────────────────────────────────────

def test_supported_languages_exact():
    assert L.SUPPORTED_LANGUAGES == ALL_LANGS
    assert set(L.LANG_NAMES) == set(ALL_LANGS)
    assert set(L.LANG_FLAGS) == set(ALL_LANGS)


@pytest.mark.parametrize("lang", ALL_LANGS)
def test_is_supported_accepts_all_six(lang):
    assert L.is_supported(lang) is True


@pytest.mark.parametrize("bad", ["xx", "", "  ", "deutsch", "EN-x", "pol", "pt"])
def test_is_supported_rejects_unknown(bad):
    assert L.is_supported(bad) is False


def test_is_supported_rejects_non_string():
    assert L.is_supported(None) is False
    assert L.is_supported(2) is False


# ── fallback behavior ─────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "getter",
    [
        L.get_opening_styles,
        L.get_awakening_ask,
        L.get_awakening_open,
        L.get_directive,
        L.get_reminder,
    ],
    ids=["styles", "ask", "open", "directive", "reminder"],
)
@pytest.mark.parametrize("bad", ["xx", "", "de-DE-x-nope", None])
def test_unknown_language_falls_back_to_en(getter, bad):
    assert getter(bad) == getter("en")


def test_getters_are_case_and_space_tolerant():
    assert L.get_directive(" DE ") == L.get_directive("de")
    assert L.get_reminder("FR") == L.get_reminder("fr")


# ── directives & reminders ────────────────────────────────────────────────

@pytest.mark.parametrize("lang", ALL_LANGS)
def test_directive_and_reminder_exist_for_every_language(lang):
    assert L.LANGUAGE_DIRECTIVES[lang].strip()
    assert L.LANGUAGE_REMINDERS[lang].strip()


@pytest.mark.parametrize(
    "lang,marker",
    [
        ("en", "[LANGUAGE: ENGLISH]"),
        ("sv", "[SPRÅK: SVENSKA]"),
        ("de", "[LANGUAGE: DEUTSCH]"),
        ("fr", "[LANGUE: FRANÇAIS]"),
        ("es", "[IDIOMA: ESPAÑOL]"),
        ("it", "[LINGUA: ITALIANO]"),
    ],
)
def test_directive_opens_with_its_language_keyword(lang, marker):
    assert L.LANGUAGE_DIRECTIVES[lang].startswith(marker)


@pytest.mark.parametrize("lang", EU_LANGS)
def test_eu_directives_declare_instructions_internal_and_tags_exempt(lang):
    directive = L.LANGUAGE_DIRECTIVES[lang]
    # English instructions are internal, not the output language.
    assert "engelska" not in directive  # no Swedish leakage
    for tag in ("[KAST:]", "[STRID:]", "[NPC:]", "[PLATS:]", "[TID:]", "[QUEST:]", "[NY_DAG:]"):
        assert tag in directive, f"{lang} directive must exempt {tag}"


@pytest.mark.parametrize("lang", ALL_LANGS)
def test_reminders_start_with_newline_for_prompt_concat(lang):
    assert L.LANGUAGE_REMINDERS[lang].startswith("\n")


# ── opening styles ────────────────────────────────────────────────────────

def test_every_language_has_five_identical_keyed_styles():
    keysets = []
    for lang in ALL_LANGS:
        styles = L.OPENING_STYLES_BY_LANG[lang]
        assert len(styles) == 5, lang
        keys = [k for k, _ in styles]
        assert len(set(keys)) == 5, lang
        keysets.append(set(keys))
        for text in (t for _, t in styles):
            assert text.strip()
    # 5 == 5 == 5 == 5 == 5 == 5 with IDENTICAL key sets
    assert all(ks == EXPECTED_KEYS for ks in keysets)
    assert all(ks == keysets[0] for ks in keysets)


def test_opening_styles_order_identical_across_languages():
    orders = [[k for k, _ in L.OPENING_STYLES_BY_LANG[lang]] for lang in ALL_LANGS]
    assert all(o == orders[0] for o in orders)


def test_get_opening_styles_returns_copy_of_five():
    a = L.get_opening_styles("de")
    b = L.get_opening_styles("de")
    assert a == b and a is not b
    assert len(a) == 5


# ── awakening blocks ──────────────────────────────────────────────────────

@pytest.mark.parametrize("lang", ALL_LANGS)
def test_awakening_open_contains_placeholder_verbatim(lang):
    assert "{opening_style}" in L.AWAKENING_OPEN_BY_LANG[lang]


@pytest.mark.parametrize("lang", ALL_LANGS)
def test_awakening_open_format_works(lang):
    out = L.AWAKENING_OPEN_BY_LANG[lang].format(opening_style="STYLE-TEXT")
    assert "STYLE-TEXT" in out and "{opening_style}" not in out


@pytest.mark.parametrize("lang", ALL_LANGS)
def test_awakening_ask_has_four_numbered_steps_and_two_mandatory_questions(lang):
    block = L.AWAKENING_ASK_BY_LANG[lang]
    for n in ("1.", "2.", "3.", "4."):
        assert n in block, f"{lang}: missing step {n}"
    assert "3-4" in block


@pytest.mark.parametrize("lang", EU_LANGS)
def test_eu_awakening_open_keeps_protocol_tags_and_skip_step1(lang):
    block = L.AWAKENING_OPEN_BY_LANG[lang]
    assert "[PLATS:" in block and "[TID:" in block and "[NPC:" in block and "[QUEST:" in block
    # skip-step-1 branch with target-language example words + the unchanged EN
    # example that the SV original keeps ("over to you").
    assert "over to you" in block
    assert "1" in block


@pytest.mark.parametrize("lang", ALL_LANGS)
def test_awakening_ask_is_nonempty_string(lang):
    assert isinstance(L.AWAKENING_ASK_BY_LANG[lang], str)
    assert len(L.AWAKENING_ASK_BY_LANG[lang]) > 400


# ── default names & TTS hints ─────────────────────────────────────────────

@pytest.mark.parametrize("lang", ALL_LANGS)
def test_default_campaign_names_present(lang):
    assert L.DEFAULT_CAMPAIGN_NAMES[lang].strip()


def test_default_names_match_legacy_en_sv():
    assert L.DEFAULT_CAMPAIGN_NAMES["en"] == "An Untitled Adventure"
    assert L.DEFAULT_CAMPAIGN_NAMES["sv"] == "Ett namnlöst äventyr"


@pytest.mark.parametrize("lang", ALL_LANGS)
def test_tts_hints_enqueue_constraints(lang):
    hint = L.TTS_PRONUNCIATION_HINTS[lang]
    assert len(hint) <= 90
    if lang in ("en", "sv"):
        assert hint == ""
    else:
        assert hint.startswith("Speak ") and hint.endswith("rhythm.")


# ── backward compatibility: en/sv copied verbatim ─────────────────────────

def test_en_directive_matches_main_py_literal():
    assert L.LANGUAGE_DIRECTIVES["en"] == (
        "[LANGUAGE: ENGLISH] You MUST write ALL narration, dialogue, NPC speech, "
        "descriptions, and every single word of your response in English. "
        "This overrides any Swedish text in the instructions below — those are "
        "internal system notes, NOT the output language.\n"
    )


def test_sv_directive_matches_main_py_literal():
    assert L.LANGUAGE_DIRECTIVES["sv"] == (
        "[SPRÅK: SVENSKA] Du MÅSTE skriva ALL narration, dialog, NPC-repliker, "
        "beskrivningar och varje ord i ditt svar på svenska.\n"
    )


def test_en_reminder_matches_main_py_literal():
    assert L.LANGUAGE_REMINDERS["en"] == (
        "\n[LANGUAGE REMINDER] Your response THIS TURN must be written entirely in English — "
        "every word of narration, dialogue, and description. Never switch to Swedish, no matter "
        "what the conversation history contains."
    )


def test_sv_reminder_matches_main_py_literal():
    assert L.LANGUAGE_REMINDERS["sv"] == (
        "\n[SPRÅKPÅMINNELSE] Ditt svar DENNA TUR måste skrivas helt på svenska — varenda ord av "
        "narration, dialog och beskrivning. Byt aldrig till engelska, oavsett vad samtalshistoriken innehåller."
    )


def test_en_and_sv_opening_styles_match_main_py_lists():
    en = L.get_opening_styles("en")
    assert en[0][0] == "meeting"
    assert en[0][1] == (
        "The adventure begins with the player meeting an interesting NPC. "
        "Give them a name, a personality, and a reason to be there."
    )
    sv = L.get_opening_styles("sv")
    assert sv[0][0] == "meeting"
    assert sv[0][1] == (
        "Äventyret börjar med att spelaren möter en intressant NPC. Ge dem ett namn, "
        "en personlighet och en anledning att vara där."
    )


def test_eu_languages_never_contain_swedish_directive_keyword():
    for lang in EU_LANGS:
        assert "[SPRÅK:" not in L.LANGUAGE_DIRECTIVES[lang]
        assert "[SPRÅKPÅMINNELSE]" not in L.LANGUAGE_REMINDERS[lang]
