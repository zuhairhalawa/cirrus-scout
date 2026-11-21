"""Write the aggregate-only static demo (a hosted link judges can open in a browser).

What goes out, per the organizers' guidance on section 4(b) of the data license
(https://cloud9.devpost.com/forum_topics/45930): results, statistics and charts derived from
the data, plus small excerpts needed to demonstrate the project.

- per team, map and side: hotspot clusters (centre, counts, percentages), smoothed density
  grids, Operator profile aggregates, setup fingerprints, round references
- at most MAX_LINES Operator kill sightlines per view
- a handful of showcase round replays
No raw events, no per-cast rows, no decompressed feeds.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import shutil
from pathlib import Path

from . import analysis as A
from .config import PROJECT_ROOT
from .server import dumps, meta_payload, scout_payload

OUT = PROJECT_ROOT / "web" / "public" / "data"
MAX_LINES = 25
MIN_MAPS = 3
# Views whose evidence rounds get full replays in the hosted demo (a small excerpt).
FEATURED = [("MIBR", "icebox"), ("Cloud9", "icebox"), ("Cloud9", "lotus"), ("Cloud9 GC", "lotus"),
            ("Sentinels", "lotus")]


def slug(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "_", s)


def _round_floats(o, nd=4):
    if isinstance(o, float):
        return round(o, nd)
    if isinstance(o, dict):
        return {k: _round_floats(v, nd) for k, v in o.items()}
    if isinstance(o, list):
        return [_round_floats(v, nd) for v in o]
    return o


def _dump(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_round_floats(json.loads(dumps(data))), separators=(",", ":")), encoding="utf-8")


def recent_since(last_played: str) -> str:
    return (dt.date.fromisoformat(last_played) - dt.timedelta(days=183)).isoformat()


def default_teams(st) -> set[str]:
    """Team ids: Cloud9's teams, everyone they played, and the most-played Game Changers teams."""
    idx = A.teams_index()
    c9 = [st.team_id[t["id"]] for t in idx if t["name"] in ("Cloud9", "Cloud9 GC")]
    G = st.G
    ids = {st.teams[t] for t in c9}
    for gi in range(len(G["game_id"])):
        a, b = int(G["team_a"][gi]), int(G["team_b"][gi])
        if a in c9:
            ids.add(st.teams[b])
        if b in c9:
            ids.add(st.teams[a])
    for t in idx[:12]:
        ids.add(t["id"])
    return ids


def export_static(team_names: list[str] | None = None, showcase: list[tuple[str, int]] | None = None):
    st = A.store()
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    idx = A.teams_index()
    wanted = {t["id"] for t in idx if t["name"] in team_names} if team_names else default_teams(st)
    teams = [t for t in idx if t["id"] in wanted]
    print(f"Exporting {len(teams)} teams -> {OUT}")

    exported, counters_done = [], set()
    for t in teams:
        ti = st.team_id[t["id"]]
        _dump(OUT / "overview" / f"{slug(t['id'])}.json", A.team_overview(ti))
        since = recent_since(t["last_played"])
        for m, n in t["maps"].items():
            if n < MIN_MAPS or not st.map_info.get(m, {}).get("samples"):
                continue
            for side in ("defense", "attack"):
                for suffix, s in (("", since), ("-all", None)):
                    res = scout_payload(t["id"], m, side, s)
                    if res["sample"]["rounds"] < 8:
                        continue
                    res["operator"]["kills"]["lines"] = res["operator"]["kills"]["lines"][:MAX_LINES]
                    _dump(OUT / "scout" / slug(t["id"]) / f"{m}-{side}{suffix}.json", res)
                    if suffix == "":
                        exported.append({"team": t["id"], "map": m, "side": side})
                    if side == "defense":
                        for h in res["utility"]["hotspots"][:14]:
                            if h["category"] not in ("trap", "sentinel") or h["id"] in counters_done:
                                continue
                            counters_done.add(h["id"])
                            c = A.counter_for_hotspot(m, h["x"], h["y"], h["ability"])
                            if c:
                                _dump(OUT / "counter" / m / f"{slug(h['id'])}.json", c)
        print(f"  {t['name']}")

    if showcase is None:
        showcase = []
        for name, m in FEATURED:
            t = next((x for x in teams if x["name"] == name), None)
            if not t:
                continue
            res = scout_payload(t["id"], m, "defense", recent_since(t["last_played"]))
            for ins in res["insights"]:
                for ri in ins["evidence"][-2:]:
                    ref = res["rounds"].get(ri)
                    if ref:
                        showcase.append((ref["game_id"], ref["n"]))
        showcase = list(dict.fromkeys(showcase))
    replays = []
    if showcase:
        from .replay import build_replay
        for gid, n in showcase:
            _dump(OUT / "replays" / f"{gid}_{n}.json", build_replay(gid, n))
            replays.append(f"{gid}_{n}")

    meta = meta_payload("static")
    meta["teams"] = [t for t in meta["teams"] if t["id"] in wanted]
    meta["exported"] = exported
    meta["replays"] = replays
    _dump(OUT / "meta.json", meta)
    size = sum(f.stat().st_size for f in OUT.rglob("*") if f.is_file())
    print(f"Static demo: {len(exported)} views, {len(counters_done)} counters, {len(replays)} replays, {size / 1e6:.1f} MB")
