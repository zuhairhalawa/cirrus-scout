"""Run the extractor over every VALORANT series in the GRID data, in parallel."""
from __future__ import annotations

import csv
import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed

from .config import SERIES_CACHE, check_data_dir
from .extract import extract_to_cache


def series_jobs(only: set[str] | None = None):
    data = check_data_dir()
    with open(data / "val" / "series.csv", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            sid = row["series_id"]
            if only and sid not in only:
                continue
            supp = row.get("ability_supplement") or ""
            yield (sid, str(data / row["file"]), str(data / supp) if supp else "")


def extract_all(workers: int | None = None, only: set[str] | None = None) -> None:
    SERIES_CACHE.mkdir(parents=True, exist_ok=True)
    jobs = list(series_jobs(only))
    workers = workers or max(1, (os.cpu_count() or 4) - 2)
    t0 = time.time()
    done = errors = 0
    print(f"Extracting {len(jobs)} series with {workers} workers -> {SERIES_CACHE}")
    with ProcessPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(extract_to_cache, j) for j in jobs]
        for fut in as_completed(futs):
            sid, status = fut.result()
            done += 1
            if status.startswith("error"):
                errors += 1
                print(f"  {sid}: {status}")
            if done % 50 == 0 or done == len(jobs):
                print(f"  {done}/{len(jobs)} series  ({time.time() - t0:.0f}s)")
    print(f"Done in {time.time() - t0:.0f}s, {errors} errors.")
