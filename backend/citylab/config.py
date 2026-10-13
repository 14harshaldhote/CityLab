"""Runtime settings, read once from ``CITYLAB_*`` environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env(name: str, default: str) -> str:
    return os.environ.get(f"CITYLAB_{name}", default)


@dataclass(frozen=True)
class Settings:
    seed: int = field(default_factory=lambda: int(_env("SEED", "1")))
    population: int = field(default_factory=lambda: int(_env("POPULATION", "2000")))
    database_url: str = field(default_factory=lambda: _env("DATABASE_URL", ""))
    start_playing: bool = field(default_factory=lambda: _env("AUTOPLAY", "1") == "1")
    speed: float = field(default_factory=lambda: float(_env("SPEED", "10")))  # sim minutes per real second
    cors_origins: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            o.strip() for o in _env("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o
        )
    )
