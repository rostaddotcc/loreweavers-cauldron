"""Global test fixtures (2026-08-08).

Turn-ledgern (strikt per-anrops-modell) skrivs till main._TURN_LEDGERS_DIR.
Utan autouse-fixture här skriver ALLA tester som rör chat/bilder riktiga
ledger-filer i backend/data/turn_ledgers/ — exakt samma läckage-klass som
users.json-läckan 2026-08-04. Denna fixture gäller för VARJE test i sviten.
"""
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import main  # noqa: E402


@pytest.fixture(autouse=True)
def turn_ledgers_dir(tmp_path, monkeypatch):
    d = tmp_path / "turn_ledgers"
    monkeypatch.setattr(main, "_TURN_LEDGERS_DIR", d)
    return d
