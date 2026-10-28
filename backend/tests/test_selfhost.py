"""Self-host-läge (SELFHOST=1): lokal Ollama som enda provider.

Täcker:
  - selfhost.enabled() — sanningstabell, läses vid anrop (inte import)
  - ollama_base() — default + trailing slash
  - discover_models() — filtrerar bort embedding-only, sorterar, cachar 60 s
  - invalidate_cache() — tvingar ny hämtning
  - default_model_id() — SELFHOST_MODEL vinner, annars första hittade
  - roster() — formen som frontend förväntar sig
  - resolve() — ValueError på allt som inte är "ollama:<namn>"
  - models.get_model("ollama:...") — provider/nyckel/base_url

Inga nätanrop: _fetch_tags monkeypatchas i varje test. Inget behov av levande
Ollama. autouse-fixturen rensar discoveriescachen mellan tester så ordningen
inte spelar roll.
"""
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pytest  # noqa: E402

import models  # noqa: E402
import selfhost  # noqa: E402


@pytest.fixture(autouse=True)
def clean_selfhost(tmp_path, monkeypatch):
    """Rensad cache + känd OLLAMA_URL + SELFHOST av som utgångsläge."""
    selfhost.invalidate_cache()
    monkeypatch.setenv("OLLAMA_URL", "http://test-ollama:11434")
    monkeypatch.delenv("SELFHOST", raising=False)
    monkeypatch.delenv("SELFHOST_MODEL", raising=False)
    yield
    selfhost.invalidate_cache()


def _tag(name, *, family="llama", caps=None):
    m = {"name": name, "model": name, "details": {"family": family}}
    if caps is not None:
        m["capabilities"] = list(caps)
    return m


@pytest.fixture
def fake_tags(monkeypatch):
    """Installerar en räknande _fetch_tags-stubbe; returnerar (calls, set_models)."""
    state = {"calls": 0, "models": []}

    def fake(timeout: float = 4.0):
        state["calls"] += 1
        return list(state["models"])

    monkeypatch.setattr(selfhost, "_fetch_tags", fake)

    def set_models(ms):
        state["models"] = list(ms)
        selfhost.invalidate_cache()

    return state, set_models


# ── enabled() ───────────────────────────────────────────────────────────

def test_enabled_truth_table(monkeypatch):
    for val in ("1", "true", "TRUE", " yes ", "on", "On", "TRUE\n"):
        monkeypatch.setenv("SELFHOST", val)
        assert selfhost.enabled() is True, val
    for val in ("0", "", "false", "no", "off", "2", "  ", "disabled"):
        monkeypatch.setenv("SELFHOST", val)
        assert selfhost.enabled() is False, val


def test_enabled_reads_env_at_call_time_not_import_time(monkeypatch):
    monkeypatch.setenv("SELFHOST", "0")
    assert selfhost.enabled() is False
    monkeypatch.setenv("SELFHOST", "1")
    assert selfhost.enabled() is True
    monkeypatch.delenv("SELFHOST")
    assert selfhost.enabled() is False


# ── ollama_base() ───────────────────────────────────────────────────────

def test_ollama_base_default_and_strip(monkeypatch):
    monkeypatch.delenv("OLLAMA_URL", raising=False)
    assert selfhost.ollama_base() == "http://localhost:11434"
    monkeypatch.setenv("OLLAMA_URL", "http://host.docker.internal:11434/")
    assert selfhost.ollama_base() == "http://host.docker.internal:11434"
    # Inget /v1 här — det hör till OpenAI-vägen i models.ollama_config()
    assert not selfhost.ollama_base().endswith("/v1")


# ── discover_models() ───────────────────────────────────────────────────

def test_discover_models_filters_embeddings_and_sorts(fake_tags):
    _, set_models = fake_tags
    set_models([
        _tag("qwen3:8b", caps=["completion", "vision"]),
        _tag("nomic-embed-text:latest", family="nomic-bert", caps=["embedding"]),
        _tag("mxbai-embed-large", family="bert", caps=["embedding"]),
        _tag("bge-m3", family="bge"),
        _tag("e5-large", family="e5"),
        # embedding-only enligt capabilities, familj säger inget
        _tag("some-embedder:1b", family="unknown", caps=["embedding"]),
        # embedding OCH completion → ändå en chatmodell (multimodal)
        _tag("llama3.2-vision:11b", caps=["completion", "vision", "embedding"]),
        _tag("deepseek-r1:7b"),
    ])
    assert selfhost.discover_models() == [
        "deepseek-r1:7b",
        "llama3.2-vision:11b",
        "qwen3:8b",
    ]


def test_discover_models_returns_empty_on_failure(monkeypatch):
    calls = {"n": 0}

    def boom(timeout: float = 4.0):
        calls["n"] += 1
        raise RuntimeError("connection refused")

    monkeypatch.setattr(selfhost, "_fetch_tags", boom)
    assert selfhost.discover_models() == []
    assert selfhost.roster() == []
    assert selfhost.default_model_id() == ""
    # Felet cachas kort (5 s) — inte en ny hämtning per anrop
    assert calls["n"] == 1


def test_discovery_caches_for_sixty_seconds(fake_tags):
    state, set_models = fake_tags
    set_models([_tag("qwen3:8b")])
    assert selfhost.discover_models() == ["qwen3:8b"]
    assert selfhost.discover_models() == ["qwen3:8b"]
    assert selfhost.discover_models() == ["qwen3:8b"]
    assert state["calls"] == 1


def test_invalidate_cache_forces_refetch(fake_tags):
    state, set_models = fake_tags
    set_models([_tag("qwen3:8b")])
    assert selfhost.discover_models() == ["qwen3:8b"]
    assert state["calls"] == 1

    # Ny modell dyker upp på servern — utan invalidering syns den inte direkt
    state["models"] = [_tag("qwen3:8b"), _tag("gemma3:4b")]
    assert selfhost.discover_models() == ["qwen3:8b"]
    assert state["calls"] == 1

    selfhost.invalidate_cache()
    assert selfhost.discover_models() == ["gemma3:4b", "qwen3:8b"]
    assert state["calls"] == 2


# ── default_model_id() ──────────────────────────────────────────────────

def test_default_model_id_honors_selfhost_model(fake_tags, monkeypatch):
    state, set_models = fake_tags
    set_models([_tag("qwen3:8b")])
    monkeypatch.setenv("SELFHOST_MODEL", "gemma3:4b")
    assert selfhost.default_model_id() == "ollama:gemma3:4b"
    # Redan prefixat värde accepteras (idempotent)
    monkeypatch.setenv("SELFHOST_MODEL", " ollama:gemma3:4b ")
    assert selfhost.default_model_id() == "ollama:gemma3:4b"
    # SELFHOST_MODEL vinner — ingen hämtning behövs
    assert state["calls"] == 0


def test_default_model_id_falls_back_to_first_discovered(fake_tags, monkeypatch):
    _, set_models = fake_tags
    set_models([_tag("qwen3:8b"), _tag("gemma3:4b")])
    monkeypatch.delenv("SELFHOST_MODEL", raising=False)
    assert selfhost.default_model_id() == "ollama:gemma3:4b"
    # Tomt värde räknas som "inte satt"
    monkeypatch.setenv("SELFHOST_MODEL", "   ")
    assert selfhost.default_model_id() == "ollama:gemma3:4b"


# ── roster() / id-hjälpare ──────────────────────────────────────────────

def test_roster_shape(fake_tags):
    _, set_models = fake_tags
    set_models([_tag("qwen3:8b")])
    assert selfhost.roster() == [
        {
            "id": "ollama:qwen3:8b",
            "name": "qwen3:8b (local)",
            "provider": "ollama",
            "vision": True,
        }
    ]


def test_model_id_and_is_ollama_id_roundtrip():
    assert selfhost.model_id("qwen3:8b") == "ollama:qwen3:8b"
    assert selfhost.model_id(" ollama:qwen3:8b ") == "ollama:qwen3:8b"
    assert selfhost.is_ollama_id("ollama:qwen3:8b")
    assert not selfhost.is_ollama_id("qwen3:8b")
    assert not selfhost.is_ollama_id("orfree:x/y:free")
    assert selfhost.resolve("ollama:qwen3:8b") == "qwen3:8b"


@pytest.mark.parametrize("bad", ["qwen3:8b", "", "   ", "ollama:", "ollama:   ", "orfree:x:free"])
def test_resolve_raises_on_bad_ids(bad):
    with pytest.raises(ValueError):
        selfhost.resolve(bad)


# ── models.py: ollama_config + get_model ────────────────────────────────

def test_ollama_config_fields(monkeypatch):
    monkeypatch.setenv("OLLAMA_URL", "http://host.docker.internal:11434/")
    cfg = models.ollama_config("qwen3:8b")
    assert cfg.model_id == "ollama:qwen3:8b"
    assert cfg.display_name == "qwen3:8b (local)"
    assert cfg.provider == "ollama"
    assert cfg.api_model == "qwen3:8b"
    assert cfg.api_key_env == ""
    assert cfg.supports_vision is True
    assert cfg.base_url == "http://host.docker.internal:11434/v1"
    # Ingen nyckel → main.py utelämnar Authorization-headern
    assert models.get_api_key(cfg) is None


def test_get_model_accepts_ollama_id():
    cfg = models.get_model("ollama:qwen3:8b")
    assert cfg.provider == "ollama"
    assert cfg.api_key_env == ""
    assert cfg.api_model == "qwen3:8b"
    assert cfg.base_url.endswith("/v1")


def test_get_model_still_rejects_unknown_and_empty_ollama_id():
    with pytest.raises(ValueError):
        models.get_model("no-such-model")
    with pytest.raises(ValueError):
        models.get_model("ollama:")
    # Registret är orört — lokala modeller läcker inte in i frontend-listan
    assert "ollama:qwen3:8b" not in models.MODELS
    assert all(not m["id"].startswith("ollama:") for m in models.list_models_for_frontend())