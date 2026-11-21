"""Combine the per-series cache into one columnar store, draw map shapes, attach callouts.

Map art: we don't ship any Riot minimap image. Each map's floor plan is drawn from where
players actually stood (millions of GRID position samples), so the background is original
and lines up with the data by construction. Callout names and the game-to-minimap
transform come from the community valorant-api.com map metadata.
"""
from __future__ import annotations

import csv
import json
import pickle
import time
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import orjson
import zstandard
from PIL import Image

from .config import DATA_DIR, DERIVED_DIR, MAPS_DIR, SERIES_CACHE, STORE_PATH, check_data_dir

RASTER = 1024
SIDE = {"attacker": 0, "defender": 1}


class Interner:
    def __init__(self):
        self.ids: list = []
        self.index: dict = {}

    def __call__(self, key) -> int:
        if key is None:
            key = ""
        i = self.index.get(key)
        if i is None:
            i = self.index[key] = len(self.ids)
            self.ids.append(key)
        return i


def _csv(path: Path):
    with open(path, newline="", encoding="utf-8") as f:
        return [r for r in csv.DictReader(f)]


def _fetch_map_meta() -> dict:
    """valorant-api.com map metadata: minimap transform + callouts, cached locally."""
    cache = DERIVED_DIR / "valorant-api-maps.json"
    if not cache.exists():
        try:
            req = urllib.request.Request("https://valorant-api.com/v1/maps", headers={"User-Agent": "c9-valorant-scout"})
            cache.write_bytes(urllib.request.urlopen(req, timeout=30).read())
        except Exception as exc:  # offline: fall back to map bounds
            print(f"  map metadata unavailable ({exc}); using bounds-based layout")
            return {}
    data = orjson.loads(cache.read_bytes()).get("data") or []
    out = {}
    for m in data:
        if not m.get("xMultiplier"):
            continue
        out[m["displayName"].lower()] = {
            "xm": m["xMultiplier"], "ym": m["yMultiplier"], "xs": m["xScalarToAdd"], "ys": m["yScalarToAdd"],
            "callouts": [
                {"name": f'{c["superRegionName"]} {c["regionName"]}'.replace("Attacker Side ", "Attacker ")
                 .replace("Defender Side ", "Defender "),
                 "region": c["superRegionName"], "x": c["location"]["x"], "y": c["location"]["y"]}
                for c in (m.get("callouts") or [])
            ],
        }
    return out


def to_uv(meta: dict | None, bounds, x, y):
    """Game units -> [0,1] minimap space (u right, v down)."""
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    if meta:
        return y * meta["xm"] + meta["xs"], x * meta["ym"] + meta["ys"]
    x0, y0, x1, y1 = bounds
    return (x - x0) / (x1 - x0), 1.0 - (y - y0) / (y1 - y0)


# Sentinel devices a player can pick up and place again before the round goes live.
RECALLABLE = {"trapwire", "spycam", "alarmbot", "turret", "trademark", "shear", "arc-rose", "razorvine",
              "nanoswarm", "sonic-sensor", "chokehold", "interceptor"}


def _final_setup(store: dict, ability_ids: list) -> tuple[dict, np.ndarray]:
    """Work out each ability's charge count from the data, then flag buy-phase placements that
    were picked up and placed again. Only the placements still standing when the round goes
    live count as the setup (final = 1); earlier ones are kept for the replay but not counted.
    """
    C = store["casts"]
    n = len(C["round"])
    final = np.ones(n, dtype=np.int8)
    max_charges = {}
    for ai, ab in enumerate(ability_ids):
        ch = C["charges"][(C["ability"] == ai) & (C["charges"] > 0)]
        if len(ch) == 0:
            continue
        vals, counts = np.unique(ch, return_counts=True)
        share = counts / counts.sum()
        # largest charge count that at least 2% of casts started from (ignores rare glitches)
        max_charges[ab] = int(vals[share >= 0.02].max())
    rec = np.array([ab in RECALLABLE for ab in ability_ids])
    idx = np.flatnonzero(rec[C["ability"]] & (C["t"] < 0))
    order = idx[np.lexsort((C["t"][idx], C["ability"][idx], C["player"][idx], C["round"][idx]))]
    key = np.c_[C["round"][order], C["player"][order], C["ability"][order]]
    starts = np.flatnonzero(np.r_[True, (key[1:] != key[:-1]).any(axis=1)])
    ends = np.r_[starts[1:], len(order)]
    for a, b in zip(starts, ends):
        cap = max_charges.get(ability_ids[int(C["ability"][order[a]])], 1)
        if b - a > cap:
            final[order[a:b - cap]] = 0
    return max_charges, final


def _floor_plan(hist: np.ndarray) -> np.ndarray:
    """Occupancy histogram -> clean floor mask in [0, 1].

    Walkable = any cell a player stood in. Close pin-holes between neighbouring samples, drop
    isolated specks, fill small enclosed gaps, then smooth the outline so walls read as lines.
    """
    from scipy import ndimage as ndi

    occ = hist > 0
    occ = ndi.binary_closing(occ, structure=np.ones((5, 5), bool), iterations=1)
    # remove islands smaller than ~2 m x 2 m
    lab, n = ndi.label(occ)
    if n:
        sizes = ndi.sum(occ, lab, index=np.arange(1, n + 1))
        keep = np.r_[False, sizes >= 220]
        occ = keep[lab]
    # fill enclosed holes smaller than ~1.5 m x 1.5 m (pillars and boxes are larger and stay)
    holes, n = ndi.label(~occ)
    if n:
        sizes = ndi.sum(~occ, holes, index=np.arange(1, n + 1))
        small = np.r_[False, sizes < 120]
        occ = occ | small[holes]
    soft = ndi.gaussian_filter(occ.astype(np.float32), 1.6)
    return np.clip((soft - 0.38) * 4.2, 0, 1)


def _rdp(points: np.ndarray, tol: float) -> np.ndarray:
    """Douglas-Peucker simplification of a polyline (iterative)."""
    n = len(points)
    if n < 3:
        return points
    keep = np.zeros(n, bool)
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        a, b = stack.pop()
        if b <= a + 1:
            continue
        seg = points[b] - points[a]
        length = float(np.hypot(*seg))
        rel = points[a + 1:b] - points[a]
        if length < 1e-9:
            dist = np.hypot(rel[:, 0], rel[:, 1])
        else:
            dist = np.abs(rel[:, 0] * seg[1] - rel[:, 1] * seg[0]) / length
        i = int(np.argmax(dist))
        if dist[i] > tol:
            mid = a + 1 + i
            keep[mid] = True
            stack.append((a, mid))
            stack.append((mid, b))
    return points[keep]


def _vector_plan(mask: np.ndarray, tol: float = 1.3) -> str:
    """Trace the floor mask into one SVG path (even-odd fill) in a 0-1000 coordinate box."""
    from contourpy import contour_generator

    scale = 1000.0 / mask.shape[0]
    parts = []
    for loop in contour_generator(z=mask).lines(0.5):
        if len(loop) < 8:
            continue
        x, y = loop[:, 0], loop[:, 1]
        area = 0.5 * abs(float(np.dot(x[:-1], y[1:]) - np.dot(x[1:], y[:-1])))
        if area < 80:      # specks and pin-holes below ~1.2 m x 1.2 m
            continue
        # split the closed loop at its farthest point so both halves simplify cleanly
        far = int(np.argmax(np.hypot(x - x[0], y - y[0])))
        pts = np.vstack([_rdp(loop[:far + 1], tol), _rdp(loop[far:], tol)[1:]])
        if len(pts) < 4:
            continue
        pts = (pts + 0.5) * scale
        parts.append("M" + "L".join(f"{px:.1f} {py:.1f}" for px, py in pts[:-1]) + "Z")
    return "".join(parts)


def build_store() -> None:
    check_data_dir()
    t0 = time.time()
    files = sorted(SERIES_CACHE.glob("*.json.zst"))
    if not files:
        raise SystemExit("No extracted series. Run `python -m scout extract` first.")
    print(f"Building store from {len(files)} series")

    meta_games = {r["game_id"]: r for r in _csv(DATA_DIR / "meta" / "games.csv") if r["title"] == "val"}
    series_rows = {r["series_id"]: r for r in _csv(DATA_DIR / "val" / "series.csv")}
    team_names = {r["team_id"]: r["name"] for r in _csv(DATA_DIR / "meta" / "teams.csv") if r["title"] == "val"}
    player_names = {r["player_id"]: r["name"] for r in _csv(DATA_DIR / "meta" / "players.csv") if r["title"] == "val"}
    roster_agent = {}
    for r in _csv(DATA_DIR / "meta" / "rosters.csv"):
        if r["title"] == "val":
            roster_agent[(r["game_id"], r["player_id"])] = r["character_name"]

    maps, teams, players, abilities, weapons, agents, events = (Interner() for _ in range(7))
    weapons("")
    G = defaultdict(list)    # games
    R = defaultdict(list)    # rounds
    C = defaultdict(list)    # casts
    S = defaultdict(list)    # sniper/odin samples
    L = defaultdict(list)    # loadouts at round start
    K = defaultdict(list)    # kills
    hist_by_map: dict = {}
    samples_by_map: dict = {}
    excluded = []
    api = _fetch_map_meta()
    game_index = {}
    round_index = {}
    dctx = zstandard.ZstdDecompressor()

    for f in files:
        d = orjson.loads(dctx.decompress(f.read_bytes()))
        sid = d["series_id"]
        srow = series_rows.get(sid, {})
        for g in d["games"]:
            mg = meta_games.get(g["game_id"])
            if not mg or not g.get("map"):
                continue  # abandoned / rolled-back or unmatched game
            wins = Counter(r.get("winner") for r in g["rounds"])
            mine = (wins.get(mg["team1_id"], 0), wins.get(mg["team2_id"], 0))
            official = (int(mg.get("team1_score") or 0), int(mg.get("team2_score") or 0))
            if mine != official:
                # the rounds we rebuilt don't add up to the official result: don't analyse this map
                excluded.append({"game_id": g["game_id"], "series_id": sid, "map": g["map"],
                                 "rebuilt": list(mine), "official": list(official)})
                continue
            gi = len(G["game_id"])
            game_index[g["game_id"]] = gi
            G["game_id"].append(g["game_id"])
            G["series_id"].append(sid)
            G["map"].append(maps(g["map"]))
            G["patch"].append(mg["patch"])
            G["event"].append(events(srow.get("event", "")))
            G["stage"].append(srow.get("stage", ""))
            G["date"].append((mg.get("started_at") or srow.get("scheduled_start") or "")[:10])
            G["game_number"].append(int(mg.get("game_number") or 0))
            G["team_a"].append(teams(mg["team1_id"]))
            G["team_b"].append(teams(mg["team2_id"]))
            G["score_a"].append(int(mg.get("team1_score") or 0))
            G["score_b"].append(int(mg.get("team2_score") or 0))
            G["winner"].append(teams(mg.get("winner_team_id") or ""))
            sm = g.get("sample_ms") or 0
            G["sample_ms"].append(sm)
            G["low_rate"].append(sm > 500)
            G["bounds"].append(g.get("bounds") or [0, 0, 1, 1])
            for r in g["rounds"]:
                sides = r.get("sides") or {}
                att = next((t for t, s in sides.items() if s == "attacker"), None)
                de = next((t for t, s in sides.items() if s == "defender"), None)
                if att is None or de is None or r.get("freeze_end") is None:
                    continue
                round_index[(g["game_id"], r["n"])] = len(R["game"])
                plant = r.get("plant") or {}
                R["game"].append(gi)
                R["n"].append(r["n"])
                R["att"].append(teams(att))
                R["def"].append(teams(de))
                R["winner"].append(teams(r.get("winner")))
                R["win_type"].append(r.get("win_type") or "")
                R["plant_x"].append(plant.get("x") if plant.get("x") is not None else np.nan)
                R["plant_y"].append(plant.get("y") if plant.get("y") is not None else np.nan)
                R["plant_t"].append((plant.get("t") or 0) / 1000.0 if plant else np.nan)
                R["freeze_end"].append(r["freeze_end"])
                R["dur"].append(((r.get("end") or r["freeze_end"]) - r["freeze_end"]) / 1000.0)

        def ridx(gid, n):
            return round_index.get((gid, n))

        for c in d["casts"]:
            gid, n, t_ms, pid, tid, side, ab, slot, x, y, z, vx, vy, vz, precise, ch_after, moved = c
            ri = ridx(gid, n)
            if ri is None or side not in SIDE:
                continue
            C["charges"].append(ch_after + 1 if ch_after >= 0 else -1)
            C["moved"].append(moved)
            C["round"].append(ri)
            C["t"].append(t_ms / 1000.0)
            C["player"].append(players(pid))
            C["team"].append(teams(tid))
            C["side"].append(SIDE[side])
            C["ability"].append(abilities(ab))
            C["agent"].append(agents(roster_agent.get((gid, pid), "")))
            C["x"].append(x); C["y"].append(y); C["z"].append(z)
            C["vx"].append(vx); C["vy"].append(vy); C["vz"].append(vz)
            C["precise"].append(precise)
        for s in d["snipe"]:
            gid, n, t_ms, pid, tid, side, w, x, y = s
            ri = ridx(gid, n)
            if ri is None:
                continue
            ti = teams(tid)
            sd = 0 if R["att"][ri] == ti else (1 if R["def"][ri] == ti else SIDE.get(side))
            if sd is None:
                continue
            S["round"].append(ri); S["t"].append(t_ms / 1000.0); S["player"].append(players(pid))
            S["team"].append(ti); S["side"].append(sd); S["weapon"].append(weapons(w))
            S["x"].append(x); S["y"].append(y)
        for lo in d["loadouts"]:
            gid, n, pid, tid, side, prim, armor, x, y = lo
            ri = ridx(gid, n)
            if ri is None or side not in SIDE:
                continue
            L["round"].append(ri); L["player"].append(players(pid)); L["team"].append(teams(tid))
            L["side"].append(SIDE[side]); L["weapon"].append(weapons(prim))
            L["agent"].append(agents(roster_agent.get((gid, pid), "")))
            L["x"].append(x if x is not None else np.nan); L["y"].append(y if y is not None else np.nan)
        for k in d["kills"]:
            gid, n, t_ms, kid, kt, vid, vt, w, kx, ky, vx_, vy_, first = k
            ri = ridx(gid, n)
            if ri is None:
                continue
            K["round"].append(ri); K["t"].append(t_ms / 1000.0)
            K["killer"].append(players(kid)); K["kteam"].append(teams(kt))
            K["victim"].append(players(vid)); K["vteam"].append(teams(vt))
            K["weapon"].append(weapons(w)); K["first"].append(first)
            K["kx"].append(kx if kx is not None else np.nan); K["ky"].append(ky if ky is not None else np.nan)
            K["vx"].append(vx_ if vx_ is not None else np.nan); K["vy"].append(vy_ if vy_ is not None else np.nan)
        by_game = defaultdict(list)
        for p in d["pos"]:
            by_game[p[0]].append((p[5], p[6]))
        for gid, pts in by_game.items():
            gi = game_index.get(gid)
            if gi is None:
                continue
            mi = G["map"][gi]
            arr = np.asarray(pts, dtype=np.float64)
            u, v = to_uv(api.get(maps.ids[mi]), G["bounds"][gi], arr[:, 0], arr[:, 1])
            ok = (u >= 0) & (u < 1) & (v >= 0) & (v < 1)
            h, _, _ = np.histogram2d(v[ok], u[ok], bins=RASTER, range=[[0, 1], [0, 1]])
            if mi not in hist_by_map:
                hist_by_map[mi] = np.zeros((RASTER, RASTER))
                samples_by_map[mi] = 0
            hist_by_map[mi] += h
            samples_by_map[mi] += len(arr)

    def cols(table, spec):
        out = {}
        for k, v in table.items():
            dt = spec.get(k)
            out[k] = np.asarray(v, dtype=dt) if dt else np.asarray(v, dtype=object)
        return out

    i32, f32, f64, i8 = np.int32, np.float32, np.float64, np.int8
    store = {
        "games": cols(G, {"map": i32, "event": i32, "game_number": i32, "team_a": i32, "team_b": i32,
                          "score_a": i32, "score_b": i32, "winner": i32, "low_rate": bool, "sample_ms": i32}),
        "rounds": cols(R, {"game": i32, "n": i32, "att": i32, "def": i32, "winner": i32, "plant_x": f32,
                           "plant_y": f32, "plant_t": f32, "freeze_end": f64, "dur": f32}),
        "casts": cols(C, {"round": i32, "t": f32, "player": i32, "team": i32, "side": i8, "ability": i32,
                          "agent": i32, "x": f32, "y": f32, "z": f32, "vx": f32, "vy": f32, "vz": f32,
                          "precise": i8, "charges": i8, "moved": f32}),
        "snipe": cols(S, {"round": i32, "t": f32, "player": i32, "team": i32, "side": i8, "weapon": i32,
                          "x": f32, "y": f32}),
        "loadouts": cols(L, {"round": i32, "player": i32, "team": i32, "side": i8, "weapon": i32,
                             "agent": i32, "x": f32, "y": f32}),
        "kills": cols(K, {"round": i32, "t": f32, "killer": i32, "kteam": i32, "victim": i32, "vteam": i32,
                          "weapon": i32, "first": i8, "kx": f32, "ky": f32, "vx": f32, "vy": f32}),
        "maps": maps.ids, "teams": teams.ids, "players": players.ids, "abilities": abilities.ids,
        "weapons": weapons.ids, "agents": agents.ids, "events": events.ids,
        "team_names": {t: team_names.get(t, t) for t in teams.ids},
        "player_names": {p: player_names.get(p, p) for p in players.ids},
    }

    store["excluded_games"] = excluded
    store["max_charges"], store["casts"]["final"] = _final_setup(store, abilities.ids)

    # ---- map rasters + callouts ----------------------------------------------------
    MAPS_DIR.mkdir(parents=True, exist_ok=True)
    map_info = {}
    for mi, mname in enumerate(maps.ids):
        gi = int(np.flatnonzero(store["games"]["map"] == mi)[0])
        bounds = store["games"]["bounds"][gi]
        meta = api.get(mname)
        info = {"name": mname, "bounds": bounds, "transform": meta and {k: meta[k] for k in ("xm", "ym", "xs", "ys")},
                "callouts": [], "samples": int(samples_by_map.get(mi, 0))}
        if mi in hist_by_map:
            arr = _floor_plan(hist_by_map[mi])
            Image.fromarray((arr * 255).astype(np.uint8), "L").save(MAPS_DIR / f"{mname}.png", optimize=True)
            info["coverage"] = float((arr > 0.5).mean())
            ys, xs = np.nonzero(arr > 0.5)
            pad = 0.02
            info["bbox"] = [max(0.0, xs.min() / RASTER - pad), max(0.0, ys.min() / RASTER - pad),
                            min(1.0, xs.max() / RASTER + pad), min(1.0, ys.max() / RASTER + pad)]
            (MAPS_DIR / f"{mname}.json").write_text(json.dumps({"path": _vector_plan(arr)}), encoding="utf-8")
        if meta:
            for c in meta["callouts"]:
                cu, cv = to_uv(meta, bounds, c["x"], c["y"])
                info["callouts"].append({"name": c["name"], "region": c["region"], "x": c["x"], "y": c["y"],
                                         "u": float(cu), "v": float(cv)})
        map_info[mname] = info
    store["map_info"] = map_info

    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(STORE_PATH, "wb") as fh:
        pickle.dump(store, fh, protocol=pickle.HIGHEST_PROTOCOL)
    n = {k: len(store[k]["round"]) if "round" in store[k] else len(store[k]["game"]) for k in ("casts", "snipe", "loadouts", "kills")}
    if excluded:
        print(f"  excluded {len(excluded)} map(s) whose rebuilt score differs from the official one")
    print(f"Store: {len(store['games']['game_id'])} maps played, {len(store['rounds']['n'])} rounds, "
          f"{n['casts']:,} casts, {n['snipe']:,} sniper samples, {n['kills']:,} kills "
          f"-> {STORE_PATH} ({time.time() - t0:.0f}s)")
