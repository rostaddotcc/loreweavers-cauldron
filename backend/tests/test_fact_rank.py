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
