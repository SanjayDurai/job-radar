"""Paths, environment and YAML config loading."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

# fetcher/src/radar/settings.py -> repo root is 3 levels above the package dir
REPO_ROOT = Path(os.environ.get("RADAR_ROOT", Path(__file__).resolve().parents[3]))
CONFIG_DIR = REPO_ROOT / "config"
COMPANIES_YAML = CONFIG_DIR / "companies.yaml"
DEFAULT_XLSX = REPO_ROOT / "Job_Switch_Top100_Companies.xlsx"

load_dotenv(REPO_ROOT / ".env")


def database_url() -> str:
    """Return a SQLAlchemy URL using the psycopg3 driver.

    Accepts plain `postgres://` / `postgresql://` URLs (as Neon gives them) and rewrites the scheme.
    """
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError("DATABASE_URL is not set. Copy .env.example to .env and fill it in.")
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix) :]
    return url


def _load_yaml(name: str) -> dict[str, Any]:
    with open(CONFIG_DIR / name, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


@lru_cache
def profile() -> dict[str, Any]:
    return _load_yaml("profile.yaml")


@lru_cache
def scoring() -> dict[str, Any]:
    return _load_yaml("scoring.yaml")
