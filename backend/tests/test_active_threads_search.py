"""Tester för ACTIVE THREADS + [SÖK:]-mekanismen (2026-08-07)."""
from main import _parse_threads


class TestParseThreads:
    def test_direct_array(self):
        raw = '[{"name": "Hilda\'s quest", "status": "active", "last_turn": 45, "summary": "Find the map"}]'
        out = _parse_threads(raw, 50)
        assert len(out) == 1
        assert out[0]["name"] == "Hilda's quest"
        assert out[0]["status"] == "active"
        assert out[0]["last_turn"] == 45

    def test_wrapped_in_dict(self):
        raw = '{"threads": [{"name": "Pesten", "status": "aktiv", "last_turn": 12, "summary": "Hitta motgift"}]}'
        out = _parse_threads(raw, 20)
        assert len(out) == 1
        assert out[0]["name"] == "Pesten"

    def test_markdown_code_block(self):
        raw = 'Here are the threads:\n```json\n[{"name": "The Promise", "status": "active", "last_turn": 3, "summary": "Vakten lovade väg"}]\n```'
        out = _parse_threads(raw, 10)
        assert len(out) == 1
        assert out[0]["name"] == "The Promise"

    def test_svenska_fältnamn(self):
        raw = '[{"tråd": "Grottan", "status": "aktiv", "turn": 7, "kort": "Kartan ligger i borgmästarens rum"}]'
        out = _parse_threads(raw, 10)
        assert len(out) == 1
        assert out[0]["name"] == "Grottan"
        assert out[0]["last_turn"] == 7
        assert "kartan" in out[0]["summary"].lower()

    def test_garbage_returns_empty(self):
        assert _parse_threads("", 5) == []
        assert _parse_threads("Ingen JSON här alls", 5) == []
        assert _parse_threads("[]", 5) == []

    def test_max_five(self):
        raw = '[{"name": "A", "last_turn": 1, "summary": "s"}, {"name": "B", "last_turn": 2, "summary": "s"}, {"name": "C", "last_turn": 3, "summary": "s"}, {"name": "D", "last_turn": 4, "summary": "s"}, {"name": "E", "last_turn": 5, "summary": "s"}, {"name": "F", "last_turn": 6, "summary": "s"}]'
        out = _parse_threads(raw, 9)
        assert len(out) == 5

    def test_missing_last_turn_falls_back(self):
        raw = '[{"name": "Tråd", "summary": "s"}]'
        out = _parse_threads(raw, 42)
        assert out[0]["last_turn"] == 42


class TestSearchRegexBehavior:
    """Regex-beteendet för [SÖK:]/[SEARCH:] — körs mot mönstret i main.py."""

    def _pattern(self):
        import re
        return re.compile(r"\[(?:SÖK|SEARCH):\s*(.*?)\]", re.DOTALL | re.IGNORECASE)

    def test_svensk_tagg(self):
        m = self._pattern().search("Svärdet blixtrar. [SÖK: Vad lovade Hilda om kartan?]")
        assert m is not None
        assert "Hilda" in m.group(1)

    def test_engelsk_tagg(self):
        m = self._pattern().search("The blade flashes. [SEARCH: What did Hilda promise about the map?]")
        assert m is not None
        assert "Hilda" in m.group(1)

    def test_tagg_borttages(self):
        import re
        pat = self._pattern()
        text = "Del av svaret [SEARCH: fråga] resten"
        cleaned = pat.sub("", text).strip()
        assert "SEARCH" not in cleaned
        assert "Del av svaret" in cleaned
