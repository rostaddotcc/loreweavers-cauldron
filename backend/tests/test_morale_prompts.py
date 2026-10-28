"""Morale prompt-layer wiring (P1a) — LLM-fria tester.

Två vägar måste lära sig moral-motorn, identiskt:
  (1) GUARDIAN_POST_SYSTEM → extraktionsfältet `morale_checks`
  (2) DM-prompten (models.py) → taggen [MORALE:target|trigger]
Båda är BEGÄRAN — servern rullar (combat.morale_check), LLM:en dikterar
aldrig utfallet. Trigger-enumen är maskinkontrakt (svensk prompttext runt
om, engelska trigger-namn) och måste matcha guardian._apply_morale_checks.

Tester: prompt-textstring-asserts + _sanitize_mechanics-validering.
"""
import pytest

import guardian
import models


VALID_TRIGGERS = ("first_casualty", "half_down", "leader_down", "fear_effect")


# ── 1. Guardian-prompten lär ut extraktionsfältet morale_checks ─────────────

class TestGuardianPromptTeachesMoraleChecks:
    def test_field_name_present(self):
        assert "morale_checks" in guardian.GUARDIAN_POST_SYSTEM

    def test_json_shape_taught(self):
        prompt = guardian.GUARDIAN_POST_SYSTEM
        assert '"target"' in prompt
        assert '"trigger"' in prompt
        assert '"note"' in prompt
        # 'all' = alla levande fiender
        assert '"all"' in prompt

    def test_all_triggers_taught(self):
        prompt = guardian.GUARDIAN_POST_SYSTEM
        for trg in VALID_TRIGGERS:
            assert trg in prompt, f"trigger {trg} saknas i GUARDIAN_POST_SYSTEM"

    def test_max_one_per_target_trigger(self):
        prompt = guardian.GUARDIAN_POST_SYSTEM.lower()
        assert "max en post per (target, trigger)" in prompt

    def test_it_is_a_request_server_rolls(self):
        prompt = guardian.GUARDIAN_POST_SYSTEM.lower()
        # LLM:en får ALDRIG diktera utfallet — servern rullar.
        assert "begäran" in prompt
        assert "servern rullar" in prompt
        assert "aldrig utfallet" in prompt

    def test_format_block_lists_field(self):
        # Format-JSON-blocket ska innehålla fältet (tomt fält = [] enligt
        # "Tomma fält"-regeln, men fältet får ALDRIG utelämnas).
        assert '"morale_checks"' in guardian.GUARDIAN_POST_SYSTEM


# ── 2. DM-prompten lär ut [MORALE:target|trigger]-taggen ────────────────────

class TestDMPromptTeachesMoraleTag:
    def _dm_text(self) -> str:
        return models.DM_CORE_PROMPT + models.DM_COMBAT_PROMPT

    def test_tag_format_taught_in_core(self):
        assert "[MORALE:target|trigger]" in models.DM_CORE_PROMPT

    def test_tag_format_taught_in_combat(self):
        assert "[MORALE:target|trigger]" in models.DM_COMBAT_PROMPT

    def test_all_triggers_taught(self):
        text = self._dm_text()
        for trg in VALID_TRIGGERS:
            assert trg in text, f"trigger {trg} saknas i DM-prompten"

    def test_all_target_taught(self):
        assert '"all"' in models.DM_COMBAT_PROMPT or "'all'" in models.DM_COMBAT_PROMPT

    def test_only_when_fiction_justified(self):
        prompt = models.DM_COMBAT_PROMPT.lower()
        assert "only when the fiction justifies it" in prompt
        # speglar guardian-vägen: bara vid brytpunkt (casualties/leader/fear)
        assert "first_casualty" in models.DM_COMBAT_PROMPT
        assert "leader_down" in models.DM_COMBAT_PROMPT
        assert "fear_effect" in models.DM_COMBAT_PROMPT

    def test_request_not_outcome(self):
        prompt = models.DM_COMBAT_PROMPT.lower()
        assert "the engine rolls the morale check" in prompt
        assert "never decide or narrate the outcome" in prompt

    def test_parity_trigger_enum_matches_between_paths(self):
        """Båda vägarna måste lära ut SAMMA trigger-enum (parity-test)."""
        g = guardian.GUARDIAN_POST_SYSTEM
        d = models.DM_CORE_PROMPT + models.DM_COMBAT_PROMPT
        for trg in VALID_TRIGGERS:
            assert trg in g and trg in d, f"parity-brott för trigger {trg}"


# ── 3. _sanitize_mechanics — morale_checks-validering ───────────────────────

class TestSanitizeMoraleChecks:
    def test_good_entry_kept(self):
        mech = guardian._sanitize_mechanics({"morale_checks": [
            {"target": "goblin", "trigger": "first_casualty", "note": "kamraten faller"},
        ]})
        assert mech["morale_checks"] == [
            {"target": "goblin", "trigger": "first_casualty", "note": "kamraten faller"}]

    def test_good_entry_all_target_kept(self):
        mech = guardian._sanitize_mechanics({"morale_checks": [
            {"target": "all", "trigger": "half_down", "note": ""},
        ]})
        assert len(mech["morale_checks"]) == 1
        assert mech["morale_checks"][0]["target"] == "all"

    def test_bad_trigger_dropped(self):
        mech = guardian._sanitize_mechanics({"morale_checks": [
            {"target": "goblin", "trigger": "ran_away_scared", "note": ""},
            {"target": "goblin", "trigger": "FIRST_CASUALTY", "note": ""},  # fel skiftläge
            {"target": "goblin", "trigger": "", "note": ""},
            {"target": "goblin", "note": ""},  # trigger saknas
            {"target": "wolf", "trigger": "leader_down", "note": ""},
        ]})
        assert [e["target"] for e in mech["morale_checks"]] == ["wolf"]

    def test_missing_or_bad_target_dropped(self):
        mech = guardian._sanitize_mechanics({"morale_checks": [
            {"trigger": "first_casualty", "note": ""},          # target saknas
            {"target": "", "trigger": "first_casualty", "note": ""},
            {"target": "   ", "trigger": "first_casualty", "note": ""},
            {"target": 42, "trigger": "first_casualty", "note": ""},
            {"target": None, "trigger": "first_casualty", "note": ""},
            {"target": "goblin", "trigger": "first_casualty", "note": ""},
        ]})
        assert mech["morale_checks"] == [
            {"target": "goblin", "trigger": "first_casualty", "note": ""}]

    def test_non_dict_entries_dropped_no_raise(self):
        mech = guardian._sanitize_mechanics({"morale_checks": [
            "garbage", None, 5, ["goblin"],
            {"target": "goblin", "trigger": "fear_effect", "note": "skrämd"},
        ]})
        assert mech["morale_checks"] == [
            {"target": "goblin", "trigger": "fear_effect", "note": "skrämd"}]

    def test_non_list_coerced_to_empty(self):
        for bad in ("nope", 7, {"target": "x"}, None):
            mech = guardian._sanitize_mechanics({"morale_checks": bad})
            assert mech["morale_checks"] == []

    def test_missing_key_gets_empty_list(self):
        mech = guardian._sanitize_mechanics({})
        assert mech["morale_checks"] == []

    def test_note_coerced_to_str_and_target_stripped(self):
        mech = guardian._sanitize_mechanics({"morale_checks": [
            {"target": "  goblin  ", "trigger": "half_down", "note": None},
        ]})
        assert mech["morale_checks"] == [
            {"target": "goblin", "trigger": "half_down", "note": "None"}]

    def test_never_raises_on_garbage(self):
        # Rörig LLM-skrift — saneringen får ALDRIG kasta.
        mech = guardian._sanitize_mechanics({"morale_checks": [
            {"target": {"nested": 1}, "trigger": ["x"], "note": object()},
            3.14, "", [], {"trigger": None},
        ]})
        assert mech["morale_checks"] == []


# ── 4. Parity: guardian-vägen och [MORALE:]-taggen delar samma konsumering ──

class TestPathParity:
    def test_tag_path_consumes_via_same_helper(self):
        """main.py [MORALE:]-vägen ska anropa guardian._apply_morale_checks
        (identisk semantik) — kontrollera att hjälpfunktionen finns."""
        assert hasattr(guardian, "_apply_morale_checks")
        assert callable(guardian._apply_morale_checks)

    def test_sanitize_feeds_consume_shape(self):
        """Sanerad output ska vara exakt den form _apply_morale_checks äter."""
        mech = guardian._sanitize_mechanics({"morale_checks": [
            {"target": "goblin", "trigger": "leader_down", "note": "shamanen faller"},
        ]})
        entry = mech["morale_checks"][0]
        assert set(entry) == {"target", "trigger", "note"}
        assert isinstance(entry["target"], str) and entry["target"]
        assert entry["trigger"] in VALID_TRIGGERS
