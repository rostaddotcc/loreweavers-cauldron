"""Rörligt faktafönster: FactRegister rank-meta — mentions, kompaktering, rank_score.

Täcker:
  - add_facts räknar omnämnanden (dedup → mentions += 1, last_seen_turn)
  - compact() sänker relevance för LLM-markerade fakta
  - rank_score() normaliserar till 0–1 och straffar kompakterade fakta
  - get_relevant_facts inkluderar mention_boost + relevance-straff

Ingen riktig data rörs: facts.json pekas om till tmp.
"""

import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from extraction import Fact, FactRegister  # noqa: E402


@pytest.fixture(autouse=True)
def tmp_facts(tmp_path):
    """Isolera faktaregistret mot tmp-katalog (via data_dir-parametern)."""
    return tmp_path


def _reg(tmp_path, user="u", campaign="c"):
    return FactRegister(user, campaign, data_dir=tmp_path)


def _fact(text, category="npc", turn=1, confidence=0.9, fid=None):
    return Fact(
        id=fid or ("f" + text[:6].replace(" ", "_") + str(turn)),
        category=category,
        text=text,
        source_turn=turn,
        confidence=confidence,
    )


def test_mentions_increment_on_duplicate(tmp_path):
    reg = _reg(tmp_path)
    f1 = _fact("Borgmästare Hilda litar inte på äventyrare", turn=1)
    reg.add_facts([f1])
    assert reg._facts[0].mentions == 1

    # Samma faktum igen (identisk text) → omnämnande, INTE ny rad
    reg.add_facts([_fact("Borgmästare Hilda litar inte på äventyrare", turn=5)])
    assert len([f for f in reg._facts if not f.superseded_by]) == 1
    assert reg._facts[0].mentions == 2
    assert reg._facts[0].last_seen_turn == 5


def test_compact_lowers_relevance(tmp_path):
    reg = _reg(tmp_path)
    f1 = _fact("Någon sa något oviktigt i krogen", category="event", turn=2)
    reg.add_facts([f1])
    assert f1.relevance == 1.0

    n = reg.compact({f1.id})
    assert n == 1
    assert f1.relevance == 0.2

    # Andra gången (redan 0.2) → ingen ändring
    assert reg.compact({f1.id}) == 0


def test_rank_score_penalizes_compacted(tmp_path):
    reg = _reg(tmp_path)
    hot = _fact("Vasska kräver 200 silver", category="promise", turn=10, fid="hot")
    cold = _fact("Gammal skvaller från krogen", category="event", turn=2, fid="cold")
    reg.add_facts([hot, cold])
    reg.compact({cold.id})

    s_hot = reg.rank_score(hot)
    s_cold = reg.rank_score(cold)
    assert 0.0 <= s_hot <= 1.0
    assert 0.0 <= s_cold <= 1.0
    assert s_hot > s_cold, "Kompakterade fakta ska rankas lägre"


def test_relevant_facts_include_hot_without_keyword(tmp_path):
    """Hett faktum (många omnämnanden) kan komma med även utan nyckelordsträff."""
    reg = _reg(tmp_path)
    hot = _fact("Vasska kräver 200 silver", category="promise", turn=10, fid="hot1")
    reg.add_facts([hot])
    # Nämn 3 extra gånger så det blir hett
    for t in (11, 12, 13):
        reg.add_facts([_fact("Vasska kräver 200 silver", category="promise", turn=t)])

    # Fråga om något helt annat — hett faktum ska ändå kunna plockas in
    relevant = reg.get_relevant_facts("draken sover i bergen", limit=5)
    texts = [f.text for f in relevant]
    assert any("Vasska" in t for t in texts), "Hett faktum ska stanna i fönstret"


def test_compacted_fact_falls_out_of_window(tmp_path):
    reg = _reg(tmp_path)
    cold = _fact("En främling nämnde ett namn en gång", category="npc", turn=1, fid="coldx")
    hot = _fact("Drottningen söker en arvinge", category="world", turn=10, fid="hotx")
    reg.add_facts([hot, cold])
    # 3 omnämnanden gör hot hett
    for t in (11, 12, 13):
        reg.add_facts([_fact("Drottningen söker en arvinge", category="world", turn=t)])
    reg.compact({cold.id})

    relevant = reg.get_relevant_facts("något helt orelaterat", limit=5)
    texts = [f.text for f in relevant]
    assert any("Drottningen" in t for t in texts)
    assert not any("främling" in t for t in texts), "Kompakterat faktum ska glida ut ur fönstret"


# ── Arkivering (archive_old) ──────────────────────────────────────────

def test_archive_old_hides_old_low_confidence_facts(tmp_path):
    """Arkiveringspasset: gamla + lågkonfidensfakta arkiveras och slutar
    returneras — men raderas aldrig (finns kvar i filen)."""
    reg = _reg(tmp_path)
    old_low = _fact(
        "Ett gammalt rykte från första turen", category="event",
        turn=2, confidence=0.5, fid="oldlow",
    )
    young_low = _fact(
        "Färskt rykte i byn", category="event",
        turn=45, confidence=0.5, fid="younglow",
    )
    old_high = _fact(
        "Gammal men säker sanning om draken", category="world",
        turn=3, confidence=0.9, fid="oldhigh",
    )
    reg.add_facts([old_low, young_low, old_high])

    n = reg.archive_old(max_age_turns=40, min_turn=50)  # tröskel: turn < 10
    assert n == 1
    assert old_low.archived is True
    assert not young_low.archived, "Ny fakta arkiveras inte trots låg konfidens"
    assert not old_high.archived, "Gammal men högtillförlitlig fakta arkiveras inte"

    # Arkiverad fakta är osynlig för get_relevant_facts ...
    relevant = reg.get_relevant_facts("gammalt rykte", limit=10)
    texts = [f.text for f in relevant]
    assert not any("gammalt rykte" in t for t in texts)
    # ... men ligger kvar i registret (aldrig raderad)
    assert len(reg._facts) == 3
    assert reg.stats()["archived"] == 1

    # Återomnämnande väcker en arkiverad fakta
    reg.add_facts([_fact("Ett gammalt rykte från första turen", category="event", turn=50)])
    assert old_low.archived is False, "Återomnämnd arkiverad fakta ska väckas"


def test_superseded_facts_never_returned(tmp_path):
    """Ersatta fakta (superseded_by) returneras aldrig — bara den nya versionen."""
    reg = _reg(tmp_path)
    old = _fact("Borgmästare Hilda litar inte på äventyrare alls", category="npc", turn=3, fid="hilda1")
    new = _fact("Borgmästare Hilda litar nu på äventyrare efter hjälpen", category="npc", turn=10, fid="hilda2")
    reg.add_facts([old])
    reg.add_facts([new])

    assert old.superseded_by == new.id
    assert reg.stats()["superseded"] == 1

    relevant = reg.get_relevant_facts("Borgmästare Hilda", limit=10)
    texts = [f.text for f in relevant]
    assert any("litar nu" in t for t in texts), "Nya versionen ska returneras"
    assert not any("litar inte" in t for t in texts), "Ersatt fakta ska aldrig returneras"


def test_recency_boost_still_works(tmp_path):
    """Nyare fakta rankas före äldre vid samma nyckelordsträff (efter arkivering)."""
    reg = _reg(tmp_path)
    older = _fact("Vasska kräver 200 silver för inträde varje gång", category="promise", turn=5, fid="oldv")
    newer = _fact("Vasska kräver 200 silver för inträde i gillestugan", category="world", turn=40, fid="newv")
    reg.add_facts([older, newer])
    # Olika kategorier + tokenöverlapp 5/6 ≈ 0.83 (≤0.90) → ingen dedup/superseding
    assert older.superseded_by is None and newer.superseded_by is None

    relevant = reg.get_relevant_facts("Vasska silver", limit=5)
    ids = [f.id for f in relevant]
    assert "newv" in ids and "oldv" in ids
    assert ids.index("newv") < ids.index("oldv"), "Nyare fakta ska rankas högre (recency-boost)"


def test_archival_runs_in_post_turn_hook(tmp_path, monkeypatch):
    """Arkiveringspasset körs i post-turn-hooken (gratis, ingen LLM) och arkiverar."""
    import main  # noqa: PLC0415

    reg = _reg(tmp_path)
    old_low = _fact(
        "Gammal skvaller från krogen i turn ett", category="event",
        turn=1, confidence=0.5, fid="hookold",
    )
    reg.add_facts([old_low])

    class _FakeStore:
        """Minimal store: ingen LLM (maybe_summarize/chapter/arc → False)."""

        def __init__(self):
            self.state = {"meta": {"turn_count": 43}}

        def get(self, username, campaign_id=None):
            return self.state

        def save(self, state):
            self.state = state

        def maybe_summarize(self, state):
            return False

        def maybe_chapter(self, state):
            return False

        def maybe_arc(self, state):
            return False

    monkeypatch.setattr(main, "store", _FakeStore())
    monkeypatch.setattr(main, "FactRegister", lambda u, c="": reg)

    # turn 43: udda (ingen faktextraktion), inte %5 (ingen RAG), inte %50
    # (ingen kompaktering) — men arkiveringspasset (1e) körs varje turn.
    # Självhanterad loop (inte pytest-asyncio): teardown-återställning annars
    # sätter set_event_loop(None) och bryter senare sync-tester (spell_slots).
    import asyncio

    _loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_loop)
    try:
        _loop.run_until_complete(
            main._post_turn_tasks_locked("u", "c", "DM-svar", "spelarens drag", 43, "m")
        )
    finally:
        _loop.close()
        asyncio.set_event_loop(asyncio.new_event_loop())  # restore for later tests

    assert old_low.archived is True, "Arkiveringspasset ska ha kört i hooken"
    assert reg.stats()["archived"] == 1
