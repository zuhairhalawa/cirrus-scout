"""Pre-commit guard: refuse to commit anything from (or derived from) the licensed GRID data.

Install:  python scripts/check_no_data.py --install
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

BLOCK = re.compile(
    r"(\.(zst|jsonl|parquet|sqlite|duckdb|pkl)$)|(^|/)(derived|cache)/|stl-hackathon-2026-grid-starter|"
    r"^web/public/data/|^web/dist/|^video/build/",
    re.IGNORECASE,
)
MAX_BYTES = 5_000_000


def staged() -> list[str]:
    out = subprocess.run(["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
                         capture_output=True, text=True, check=True).stdout
    return [p for p in out.splitlines() if p]


def main() -> int:
    if "--install" in sys.argv:
        # Always the repository's own .git/hooks, never a global core.hooksPath folder
        # (a global hooks folder can chain to it).
        common = subprocess.run(["git", "rev-parse", "--git-common-dir"], capture_output=True, text=True,
                                check=True).stdout.strip()
        hook = Path(common) / "hooks" / "pre-commit"
        hook.parent.mkdir(parents=True, exist_ok=True)
        hook.write_text("#!/bin/sh\npython scripts/check_no_data.py\n", encoding="utf-8")
        print(f"installed {hook}")
        return 0
    bad = [p for p in staged() if BLOCK.search(p.replace("\\", "/"))]
    big = [p for p in staged() if Path(p).exists() and Path(p).stat().st_size > MAX_BYTES]
    if bad or big:
        print("Refusing to commit licensed GRID data or large derived files:")
        for p in bad + big:
            print("  ", p)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
