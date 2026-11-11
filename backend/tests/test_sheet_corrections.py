"""Karaktärsval går att rätta — write-path för spells/features/fighting style (2026-10-21).

Bakgrund (spelarfeedback 2026-10-21, spelaren bakom player2@example.com,
karaktären Pemba i "The Great Trail"):

  "the system assumed spells and feats i did not want, but now i cant change
   them in the codex. Also choosing a fighting style. Both the DM and
   lorekeeper logs it as updated, but the page does not actually change."

Rotorsak: `character_updates` var logg-only, `spells_add` var add-only och det
fanns ingen `spells_remove` / `features_remove` / `fighting_style` alls —
dessutom tog PATCH /api/campaign/character bara notes + max_weight_lbs.
Dessa tester låser den nya vägen:

  A. Guardian: spells_remove / features_remove / features_add / fighting_style
     appliceras på ARKET (inte bara i loggen), med namnmatchning som tål
     delnamn ("Observant" → "Observant (Variant Human Feat)").
  B. _sanitize_mechanics: skräp från LLM:en (sträng i stället för lista,
     dict som fighting_style) kraschar inte apply_mechanics.
  C. PATCH /api/campaign/character: spelaren får rätta sina egna val,
     får 400 på skräp, och abilities/hp/ac/xp är fortfarande spärrade.
"""

import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import auth  # noqa: E402
import guardian  # noqa: E402
import main  # noqa: E402
from auth import create_token, hash_password  # noqa: E402


# ── Fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture
def users_file(tmp_path, monkeypatch):
    f = tmp_path / "users.json"
    monkeypatch.setattr(auth, "USERS_FILE", f)
    return f


@pytest.fixture
def campaigns_dir(tmp_path, monkeypatch):
    import state_manager as sm
    d = tmp_path / "campaigns"
    monkeypatch.setattr(sm, "CAMPAIGNS_DIR", d)
    monkeypatch.setattr(main, "CAMPAIGNS_DIR", d)
    return d


@pytest.fixture
def client(users_file, campaigns_dir):
    from fastapi.testclient import TestClient
    with TestClient(main.app) as c:
        yield c


# ── Hjälpare ─────────────────────────────────────────────────────────────

def _pemba_state() -> dict:
    """Pembas ark i det skick buggen lämnade det: Observant kvar trots att
    loggen påstår Sharpshooter, Cure Wounds kvar trots "removed", och en
    Fighting Style-feature utan val."""
    return {
        "meta": {"turn_count": 63, "campaign_id": "a8850466f871", "language": "en"},
        "character": {
            "name": "Pemba",
            "class": "Ranger",
            "level": 2,
            "hp": {"current": 19, "max": 19, "temp": 0},
            "ac": 15,
            "proficiency": 2,
            "abilities": {
                "STR": {"score": 13, "mod": 1},
                "DEX": {"score": 19, "mod": 4},
                "CON": {"score": 14, "mod": 2},
            },
            "spells": [
                {"name": "Druidcraft", "level": 0, "school": "Transmutation"},
                {"name": "Resistance", "level": 0, "school": "Abjuration"},
                {"name": "Hunter's Mark", "level": 1, "school": "Divination"},
                {"name": "Cure Wounds", "level": 1, "school": "Abjuration"},
                {"name": "Goodberry", "level": 1, "school": "transmutation"},
            ],
            "features": [
                {"name": "Favored Enemy (Orcs)", "level": 1, "description": "..."},
                {"name": "Observant (Variant Human Feat)", "level": 1, "description": "+5 passive Perception."},
                {"name": "Fighting Style", "level": 2, "description": "Choose a fighting style."},
            ],
        },
        "npcs": [],
        "world": {},
        "inventory": [],
        "currency": {},
    }


def _mech(**overrides) -> dict:
    mech = guardian.mechanics_empty_template()
    mech.update(overrides)
    return mech


def _names(items) -> list[str]:
    return [i.get("name") for i in items]


# ── A. Guardian applicerar valen på arket ────────────────────────────────

def test_spells_remove_deletes_the_spell_and_logs_truthfully():
    state = _pemba_state()
    effects = guardian.apply_mechanics(state, _mech(spells_remove=[{"name": "Cure Wounds"}]))

    assert "Cure Wounds" not in _names(state["character"]["spells"])
    assert "Hunter's Mark" in _names(state["character"]["spells"])  # orörd
    assert any(e.get("type") == "spell_remove" and e.get("value") == "Cure Wounds" for e in effects)
    # Loggen ska nu vara SANN — den beskriver något som faktiskt hände
    last = state["character"]["updates"][-1]
    assert last["field"] == "sheet"
    assert "Cure Wounds" in last["text"]
    assert last["turn"] == 63


def test_spells_remove_is_case_insensitive_and_tolerates_plain_strings():
    state = _pemba_state()
    guardian.apply_mechanics(state, _mech(spells_remove=["cure wounds"]))
    assert "Cure Wounds" not in _names(state["character"]["spells"])


def test_features_remove_matches_partial_name():
    """DM:en skriver 'Observant'; arket har 'Observant (Variant Human Feat)'."""
    state = _pemba_state()
    guardian.apply_mechanics(state, _mech(features_remove=[{"name": "Observant"}]))
    assert not any("Observant" in n for n in _names(state["character"]["features"]))


def test_features_add_puts_the_feat_on_the_sheet_and_dedupes():
    state = _pemba_state()
    mech = _mech(features_add=[{"name": "Sharpshooter", "level": 1, "description": "No disadvantage at long range."}])
    guardian.apply_mechanics(state, mech)
    names = _names(state["character"]["features"])
    assert "Sharpshooter" in names

    # Andra gången → ingen dubblett (LLM:er upprepar sig)
    guardian.apply_mechanics(state, _mech(features_add=[{"name": "Sharpshooter", "level": 1}]))
    assert _names(state["character"]["features"]).count("Sharpshooter") == 1


def test_fighting_style_is_stored_and_visible_in_the_feature_list():
    state = _pemba_state()
    effects = guardian.apply_mechanics(state, _mech(fighting_style="archery"))

    ch = state["character"]
    assert ch["fighting_style"] == "Archery"  # kanoniskt namn, inte LLM-skiftläge
    fs = [f for f in ch["features"] if f["name"].startswith("Fighting Style")]
    assert len(fs) == 1
    # Uppmaningen "Choose a fighting style." ersatt av VALET
    assert fs[0]["name"] == "Fighting Style (Archery)"
    assert "ranged weapons" in fs[0]["description"]
    assert any(e.get("type") == "fighting_style" for e in effects)
    assert "Archery" in ch["updates"][-1]["text"]


def test_fighting_style_change_logs_from_and_to():
    state = _pemba_state()
    state["character"]["fighting_style"] = "Defense"
    guardian.apply_mechanics(state, _mech(fighting_style="Archery"))
    assert state["character"]["fighting_style"] == "Archery"
    assert "Defense" in state["character"]["updates"][-1]["text"]
    assert "Archery" in state["character"]["updates"][-1]["text"]


def test_fighting_style_variant_text_resolves_to_known_style():
    """DM kan skicka hela meningen i stället för bara namnet."""
    state = _pemba_state()
    guardian.apply_mechanics(state, _mech(fighting_style="Archery (+2 bonus to all attack rolls made with ranged weapons)"))
    assert state["character"]["fighting_style"] == "Archery"


def test_legacy_free_text_style_is_replaced_not_duplicated():
    """14 riktiga kampanjer har valet som fritext: 'Fighting Style: Defense'."""
    state = _pemba_state()
    state["character"]["features"] = [
        {"name": "Favored Enemy (Orcs)", "level": 1, "description": "..."},
        {"name": "Fighting Style: Defense", "level": 2, "description": "+1 AC."},
    ]
    guardian.apply_mechanics(state, _mech(fighting_style="Archery"))
    fs = [f["name"] for f in state["character"]["features"] if "fighting style" in f["name"].lower()]
    assert fs == ["Fighting Style (Archery)"], fs


def test_multiple_fighting_style_features_collapse_to_one():
    state = _pemba_state()
    state["character"]["features"] = [
        {"name": "Defensive Fighting Style", "level": 1, "description": "..."},
        {"name": "Fighting Style (Dueling)", "level": 2, "description": "..."},
    ]
    guardian.apply_mechanics(state, _mech(fighting_style="Two-Weapon Fighting"))
    fs = [f["name"] for f in state["character"]["features"] if "fighting style" in f["name"].lower()]
    assert fs == ["Fighting Style (Two-Weapon Fighting)"], fs


def test_character_updates_still_log_only():
    """Regression: berättande uppdateringar får ALDRIG skriva om arket."""
    state = _pemba_state()
    before_spells = _names(state["character"]["spells"])
    guardian.apply_mechanics(state, _mech(character_updates=[{"field": "spells", "text": "Learned Zephyr Strike."}]))
    assert _names(state["character"]["spells"]) == before_spells
    assert not any("Zephyr" in n for n in _names(state["character"]["spells"]))
    assert state["character"]["updates"][-1]["field"] == "spells"


# ── B. Sanering: skräp från LLM:en kraschar inte ─────────────────────────

def test_sanitize_turns_strings_into_lists():
    mech = guardian._sanitize_mechanics({
        "spells_remove": "Cure Wounds",
        "features_remove": {"name": "Observant"},
        "features_add": "Sharpshooter",
        "fighting_style": {"name": "Archery"},
    })
    assert mech["spells_remove"] == []
    assert mech["features_remove"] == []
    assert mech["features_add"] == []
    assert mech["fighting_style"] == "Archery"  # dict → .name


def test_empty_template_has_the_new_fields():
    mech = guardian.mechanics_empty_template()
    for key in ("spells_remove", "features_add", "features_remove", "fighting_style"):
        assert key in mech


# ── C. PATCH /api/campaign/character — spelarens egen rättelse ───────────

def _seed(username: str = "hero2") -> str:
    users = main.load_users()
    users[username] = {"password_hash": hash_password("secret123"), "role": "player"}
    main.save_users(users)
    state = main.store.create(username, name="The Great Trail", language="en")
    ch = state.setdefault("character", {})
    ch.update({
        "name": "Pemba",
        "class": "Ranger",
        "level": 2,
        "abilities": {"STR": {"score": 13, "mod": 1}, "DEX": {"score": 19, "mod": 4}},
        "hp": {"current": 19, "max": 19, "temp": 0},
        "ac": 15,
        "spells": [{"name": "Cure Wounds", "level": 1, "school": "Abjuration"}],
        "features": [
            {"name": "Observant (Variant Human Feat)", "level": 1, "description": "+5 passive Perception."},
            {"name": "Fighting Style", "level": 2, "description": "Choose a fighting style."},
        ],
    })
    main.store.save(state)
    return create_token(username, "player")


def _auth(token: str) -> dict:
    return {"morkrets_token": token}


def test_patch_lets_the_player_replace_a_spell(client):
    token = _seed()
    r = client.patch("/api/campaign/character", json={
        "spells": [
            {"name": "Zephyr Strike", "level": 1, "school": "Transmutation", "description": "Move without provoking."},
        ],
    }, cookies=_auth(token))
    assert r.status_code == 200, r.text
    spells = _names(r.json()["character"]["spells"])
    assert spells == ["Zephyr Strike"]

    state = main.store.get("hero2")
    assert _names(state["character"]["spells"]) == ["Zephyr Strike"]  # persisterat
    assert state["character"]["updates"][-1]["field"] == "sheet"
    assert "Zephyr Strike" in state["character"]["updates"][-1]["text"]


def test_patch_lets_the_player_swap_a_feat_and_pick_a_fighting_style(client):
    token = _seed()
    r = client.patch("/api/campaign/character", json={
        "features": [
            {"name": "Sharpshooter", "level": 1, "description": "No disadvantage at long range."},
            {"name": "Fighting Style", "level": 2, "description": "Choose a fighting style."},
        ],
        "fighting_style": "Archery",
    }, cookies=_auth(token))
    assert r.status_code == 200, r.text

    state = main.store.get("hero2")
    names = _names(state["character"]["features"])
    assert "Sharpshooter" in names
    assert not any("Observant" in n for n in names)
    assert state["character"]["fighting_style"] == "Archery"
    assert "Fighting Style (Archery)" in names


def test_patch_clears_fighting_style(client):
    token = _seed()
    client.patch("/api/campaign/character", json={"fighting_style": "Defense"}, cookies=_auth(token))
    r = client.patch("/api/campaign/character", json={"fighting_style": ""}, cookies=_auth(token))
    assert r.status_code == 200
    assert "fighting_style" not in main.store.get("hero2")["character"]


def test_patch_rejects_junk_payloads(client):
    token = _seed()
    bad = [
        {"spells": "Cure Wounds"},
        {"spells": [{"level": 1}]},
        {"spells": [{"name": "Boom", "level": 42}]},
        {"features": [{"name": ""}]},
        {"features": ["Sharpshooter"]},
        {"fighting_style": 42},
    ]
    for payload in bad:
        r = client.patch("/api/campaign/character", json=payload, cookies=_auth(token))
        assert r.status_code == 400, f"{payload} gav {r.status_code}"


def test_patch_cannot_touch_abilities_hp_or_ac(client):
    token = _seed()
    r = client.patch("/api/campaign/character", json={
        "abilities": {"STR": {"score": 30, "mod": 10}},
        "hp": {"current": 999, "max": 999},
        "ac": 30,
        "xp": {"current": 999999},
    }, cookies=_auth(token))
    assert r.status_code == 200
    ch = main.store.get("hero2")["character"]
    assert ch["abilities"]["STR"]["score"] == 13
    assert ch["hp"]["max"] == 19
    assert ch["ac"] == 15


def test_patch_notes_still_works(client):
    token = _seed()
    r = client.patch("/api/campaign/character", json={"notes": "Pemba, mountain guide."}, cookies=_auth(token))
    assert r.status_code == 200
    assert main.store.get("hero2")["character"]["notes"] == "Pemba, mountain guide."


def test_patch_requires_auth(client):
    r = client.patch("/api/campaign/character", json={"fighting_style": "Archery"})
    assert r.status_code in (401, 403)


# ── D. 5e-grindar: rättelse, inte förstärkning (rostads beslut 2026-10-21) ──

def _lim(**ch):
    base = {"class": "Ranger", "level": 2, "spells": [], "features": []}
    base.update(ch)
    return guardian.spell_limits(base)


def test_limits_for_ranger_two_grandfathers_existing_sheet():
    lim = _lim(spells=[{"name": "Druidcraft", "level": 0}, {"name": "Resistance", "level": 0},
                       {"name": "Cure Wounds", "level": 1}, {"name": "Hunter's Mark", "level": 1},
                       {"name": "Goodberry", "level": 1}])
    assert lim["caster_kind"] == "half"
    assert lim["max_level"] == 1          # half caster, nivå 2
    assert lim["max_cantrips"] == 0       # ranger har inga cantrips i 5e
    assert lim["max_spells"] == 2
    # …men arket har redan 2 cantrips + 3 spells ⇒ de får behållas
    assert lim["allow_cantrips"] == 2
    assert lim["allow_spells"] == 3
    assert lim["allow_level"] == 1


def test_limits_for_full_caster_scale_with_level():
    wiz1 = _lim(**{"class": "Wizard", "level": 1})
    wiz5 = _lim(**{"class": "Wizard", "level": 5})
    assert (wiz1["max_level"], wiz1["max_cantrips"]) == (1, 3)
    assert wiz5["max_level"] == 3
    assert wiz5["max_cantrips"] == 4
    assert wiz5["max_spells"] == 14       # spellbook: 6 + 2 per nivå över 1


def test_limits_for_non_caster():
    f = _lim(**{"class": "Fighter", "level": 3})
    assert (f["max_level"], f["max_cantrips"], f["max_spells"]) == (0, 0, 0)
    # …men en Fighter med Spellcasting-feature (Eldritch Knight) får tredjedels-tak
    ek = _lim(**{"class": "Fighter", "level": 7,
                 "features": [{"name": "Spellcasting", "level": 3, "description": "..."}]})
    assert ek["caster_kind"] == "third" and ek["max_level"] == 2


def test_patch_blocks_spell_level_above_the_class(users_file, campaigns_dir, monkeypatch):
    from fastapi.testclient import TestClient
    token = _seed()
    with TestClient(main.app) as c:
        r = c.patch("/api/campaign/character", json={"spells": [
            {"name": "Cure Wounds", "level": 1},
            {"name": "Meteor Swarm", "level": 9},
        ]}, cookies=_auth(token))
        assert r.status_code == 400, r.text
        assert "out of reach" in r.json()["detail"]
        # …och inget skrevs
        assert _names(main.store.get("hero2")["character"]["spells"]) == ["Cure Wounds"]


def test_patch_blocks_extra_cantrips_and_extra_spells(users_file, campaigns_dir, monkeypatch):
    from fastapi.testclient import TestClient
    token = _seed()
    with TestClient(main.app) as c:
        r = c.patch("/api/campaign/character", json={"spells": [
            {"name": "Cure Wounds", "level": 1},
            {"name": "Druidcraft", "level": 0},
        ]}, cookies=_auth(token))
        assert r.status_code == 400 and "cantrips" in r.json()["detail"], r.text


def test_patch_allows_a_legal_swap(users_file, campaigns_dir, monkeypatch):
    from fastapi.testclient import TestClient
    token = _seed()
    with TestClient(main.app) as c:
        r = c.patch("/api/campaign/character", json={"spells": [
            {"name": "Zephyr Strike", "level": 1, "school": "Transmutation"},
        ]}, cookies=_auth(token))
        assert r.status_code == 200, r.text
        assert _names(r.json()["character"]["spells"]) == ["Zephyr Strike"]


def test_grandfather_baseline_is_sticky_across_a_swap(users_file, campaigns_dir, monkeypatch):
    """Tre leveled spells på en Ranger 2 (5e-tak 2) ska kunna BYTAS, inte bara
    bort. Efter första rättelsen sjunker inte tillåtelsen tillbaka till 2."""
    from fastapi.testclient import TestClient
    token = _seed()
    st = main.store.get("hero2")
    ch = st["character"]
    ch["spells"] = [
        {"name": "Druidcraft", "level": 0, "school": "Transmutation"},
        {"name": "Resistance", "level": 0, "school": "Abjuration"},
        {"name": "Hunter's Mark", "level": 1, "school": "Divination"},
        {"name": "Cure Wounds", "level": 1, "school": "Abjuration"},
        {"name": "Goodberry", "level": 1, "school": "transmutation"},
    ]
    main.store.save(st)
    with TestClient(main.app) as c:
        # 1) ta bort Cure Wounds
        r = c.patch("/api/campaign/character", json={"spells": ch["spells"][:2] + [
            {"name": "Hunter's Mark", "level": 1, "school": "Divination"},
            {"name": "Goodberry", "level": 1, "school": "transmutation"},
        ]}, cookies=_auth(token))
        assert r.status_code == 200, r.text
        # 2) ersättaren MÅSTE fortfarande gå in (baslinjen är kvar på 3)
        r = c.patch("/api/campaign/character", json={"spells": [
            {"name": "Druidcraft", "level": 0, "school": "Transmutation"},
            {"name": "Resistance", "level": 0, "school": "Abjuration"},
            {"name": "Hunter's Mark", "level": 1, "school": "Divination"},
            {"name": "Goodberry", "level": 1, "school": "transmutation"},
            {"name": "Zephyr Strike", "level": 1, "school": "Transmutation"},
        ]}, cookies=_auth(token))
        assert r.status_code == 200, r.text
        assert "Zephyr Strike" in _names(r.json()["character"]["spells"])
        # …och fjärde leveled spell (utöver baslinjen) stoppas
        r = c.patch("/api/campaign/character", json={"spells": [
            {"name": "Zephyr Strike", "level": 1},
            {"name": "Hunter's Mark", "level": 1},
            {"name": "Goodberry", "level": 1},
            {"name": "Cure Wounds", "level": 1},
        ]}, cookies=_auth(token))
        assert r.status_code == 400, r.text


def test_patch_blocks_feature_stacking(users_file, campaigns_dir, monkeypatch):
    from fastapi.testclient import TestClient
    token = _seed()
    with TestClient(main.app) as c:
        feats = [{"name": f"Invented Feat {i}", "level": 1} for i in range(8)]
        r = c.patch("/api/campaign/character", json={"features": feats}, cookies=_auth(token))
        assert r.status_code == 400 and "swap one" in r.json()["detail"], r.text


def test_patch_blocks_foreign_fighting_style(users_file, campaigns_dir, monkeypatch):
    from fastapi.testclient import TestClient
    token = _seed()
    with TestClient(main.app) as c:
        r = c.patch("/api/campaign/character", json={"fighting_style": "Protection"}, cookies=_auth(token))
        assert r.status_code == 400 and "not a Ranger fighting style" in r.json()["detail"], r.text
        r = c.patch("/api/campaign/character", json={"fighting_style": "Archery"}, cookies=_auth(token))
        assert r.status_code == 200, r.text


def test_patch_is_locked_during_combat(users_file, campaigns_dir, monkeypatch):
    from fastapi.testclient import TestClient
    token = _seed()
    st = main.store.get("hero2")
    st.setdefault("world", {})["combat"] = {"active": True, "round": 2}
    main.store.save(st)
    with TestClient(main.app) as c:
        r = c.patch("/api/campaign/character", json={"fighting_style": "Archery"}, cookies=_auth(token))
        assert r.status_code == 409, r.text
        # notes går fortfarande bra mitt i striden
        assert c.patch("/api/campaign/character", json={"notes": "mid-fight"}, cookies=_auth(token)).status_code == 200


def test_sheet_limits_endpoint(client):
    token = _seed()
    r = client.get("/api/campaign/sheet-limits", cookies=_auth(token))
    assert r.status_code == 200, r.text
    lim = r.json()["limits"]
    assert lim["class"] == "Ranger" and lim["level"] == 2
    assert lim["max_level"] == 1 and lim["allow_level"] == 1
    assert lim["combat_active"] is False
    assert "Archery" in lim["fighting_styles"] and "Protection" not in lim["fighting_styles"]