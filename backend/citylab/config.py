"""Runtime settings, read once from ``CITYLAB_*`` environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env(name: str, default: str) -> str:
    return os.environ.get(f"CITYLAB_{name}", default)


@dataclass(frozen=True)
class Settings:
    seed: int = field(default_factory=lambda: int(_env("SEED", "1")))
    population: int = field(default_factory=lambda: int(_env("POPULATION", "5000")))  # people acted out on the map
    town: int = field(default_factory=lambda: int(_env("TOWN", "200000")))  # everyone in Kamalnagar, map included
    database_url: str = field(default_factory=lambda: _env("DATABASE_URL", ""))
    start_playing: bool = field(default_factory=lambda: _env("AUTOPLAY", "1") == "1")
    speed: float = field(default_factory=lambda: float(_env("SPEED", "10")))  # sim minutes per real second
    # the free local AI (Ollama). Leave the URL empty to switch it off completely.
    ollama_url: str = field(default_factory=lambda: _env("OLLAMA_URL", "http://localhost:11434"))
    chat_model: str = field(default_factory=lambda: _env("OLLAMA_MODEL", "llama3.2:3b"))
    embed_model: str = field(default_factory=lambda: _env("EMBED_MODEL", "nomic-embed-text"))
    # set this to require the token for the actions that wipe or rewrite the city (new city, changing a rule)
    admin_token: str = field(default_factory=lambda: _env("ADMIN_TOKEN", ""))
    cors_origins: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            o.strip() for o in _env("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o
        )
    )
