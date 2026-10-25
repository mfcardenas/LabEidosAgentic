from __future__ import annotations

import shutil
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
APPS = ["usuarios", "reservas"]


@pytest.fixture(autouse=True)
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Cada prueba trabaja con una copia de las aplicaciones y un almacén vacío, con el perfil determinista."""
    apps = tmp_path / "apps"
    shutil.copytree(REPO / "apps", apps)
    monkeypatch.setenv("EIDOS_APPS_DIR", str(apps))
    monkeypatch.setenv("EIDOS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("EIDOS_PROFILE", "fake")
    monkeypatch.setenv("EIDOS_CLIENT_DIR", str(tmp_path / "no-client"))
    return apps
