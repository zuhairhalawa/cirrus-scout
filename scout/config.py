"""Paths and constants shared by the pipeline and the server."""
from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# The licensed GRID data lives in its own clone next to this project, never inside it.
DATA_DIR = Path(
    os.environ.get("STL_DATA_DIR", PROJECT_ROOT.parent / "stl-hackathon-2026-grid-starter")
).resolve()

# Everything derived from the data goes here. It is git-ignored on purpose:
# the data license forbids committing or publishing the data or extracts of it.
DERIVED_DIR = Path(os.environ.get("SCOUT_DERIVED_DIR", PROJECT_ROOT / "derived")).resolve()
SERIES_CACHE = DERIVED_DIR / "series"
STORE_PATH = DERIVED_DIR / "store.pkl"
MAPS_DIR = DERIVED_DIR / "maps"

WEB_DIST = PROJECT_ROOT / "web" / "dist"

# Weapons we profile as "high-impact snipers".
SNIPERS = ("operator", "outlaw", "marshal")
HEAVY = ("odin",)
TRACKED_WEAPONS = SNIPERS + HEAVY

# Primary weapon priority when a player carries more than one gun.
PRIMARY_PRIORITY = (
    "operator", "outlaw", "marshal", "odin", "ares", "vandal", "phantom", "guardian",
    "bulldog", "spectre", "stinger", "judge", "bucky", "ghost", "sheriff", "frenzy",
    "shorty", "classic",
)


def check_data_dir() -> Path:
    if not (DATA_DIR / "val" / "series.csv").exists():
        raise SystemExit(
            f"GRID data not found at {DATA_DIR}.\n"
            "Clone it next to this project:\n"
            "  git clone https://github.com/cloud9esports/stl-hackathon-2026-grid-starter.git ../stl-hackathon-2026-grid-starter\n"
            "or set STL_DATA_DIR to its location."
        )
    return DATA_DIR
