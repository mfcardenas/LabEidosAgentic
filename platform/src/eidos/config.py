"""Configuración de la plataforma desde variables de entorno (y .env si existe)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        val = val.strip().strip('"').strip("'")
        os.environ.setdefault(key.strip(), val)


_load_dotenv(REPO_ROOT / ".env")


def env(key: str, default: str = "") -> str:
    val = os.environ.get(key, "")
    return val if val != "" else default


@dataclass(frozen=True)
class Settings:
    apps_dir: Path = field(default_factory=lambda: Path(env("EIDOS_APPS_DIR", str(REPO_ROOT / "apps"))))
    data_dir: Path = field(default_factory=lambda: Path(env("EIDOS_DATA_DIR", str(REPO_ROOT / "data" / "platform"))))
    client_dir: Path = field(default_factory=lambda: Path(env("EIDOS_CLIENT_DIR", str(REPO_ROOT / "client" / "dist"))))
    contracts_dir: Path = field(default_factory=lambda: Path(env("EIDOS_CONTRACTS_DIR", str(REPO_ROOT / "contracts"))))
    profile: str = field(default_factory=lambda: env("EIDOS_PROFILE", "fake"))
    host: str = field(default_factory=lambda: env("EIDOS_HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: int(env("EIDOS_PORT", "8000")))
    timeout_s: float = field(default_factory=lambda: float(env("LLM_TIMEOUT_MS", "600000")) / 1000)


def settings() -> Settings:
    return Settings()
