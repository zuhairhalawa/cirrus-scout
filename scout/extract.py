"""Stream one GRID series (plus its ability supplement) into compact per-round tables.

The GRID feed is huge once decompressed (up to ~1 GB per series), so everything here is
a single streaming pass. Output goes to the git-ignored ``derived/series`` cache.
"""
from __future__ import annotations

import bisect
import math
import sys
from datetime import datetime
from pathlib import Path

import orjson
import zstandard

from .config import PRIMARY_PRIORITY, SERIES_CACHE, TRACKED_WEAPONS

POS_SAMPLE_MS = 1000     # general position samples (map shape, spawns)
SNIPE_SAMPLE_MS = 500    # sniper / Odin holder samples


def _ms(ts: str) -> int:
    return int(datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp() * 1000)


def _read(path: Path):
    with zstandard.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            yield orjson.loads(line)


def _primary(items) -> str:
    ids = {it.get("id") for it in items or ()}
    for w in PRIMARY_PRIORITY:
        if w in ids:
            return w
    return ""


def _armor(items) -> str:
    ids = {it.get("id") for it in items or ()}
    if "heavyshield" in ids:
        return "heavy"
    if "regenshield" in ids:
        return "regen"
    if "lightshield" in ids:
        return "light"
    return ""


def _xy(state):
    p = (state or {}).get("position") or None
    if not p:
        return None
    return (round(p["x"], 1), round(p["y"], 1))


class _Game:
    __slots__ = ("gid", "map", "bounds", "rounds", "player_team", "teams")

    def __init__(self, gid):
        self.gid = gid
        self.map = None
        self.bounds = None
        self.rounds = {}          # n -> dict
        self.player_team = {}     # player id -> team id
        self.teams = {}           # team id -> name


def extract_series(series_id: str, feed: Path, supplement: Path | None) -> dict:
    games: dict[str, _Game] = {}
    rolled_back: set[str] = set()
    cur_game = None
    cur_round = None

    casts_grid = []   # GRID-only ability casts (no precise supplement position)
    grid_cast_ids = set()
    snipe = []
    loadouts = []
    kills = []
    pos = []
    last_pos_ms: dict = {}
    last_snipe_ms: dict = {}
    holding: dict = {}   # player id -> tracked weapon held this round
    dead: set = set()
    charges_after: dict = {}   # GRID cast event id -> charges left after the cast

    def game_state(series_state):
        if not series_state or cur_game is None:
            return None
        for g in series_state.get("games") or ():
            if g.get("id") == cur_game:
                return g
        return None

    for env in _read(feed):
        ts = _ms(env["occurredAt"])
        for e in env["events"]:
            et = e["type"]
            actor = e.get("actor") or {}
            target = e.get("target") or {}

            if et == "series-started-game":
                cur_game = target.get("id")
                games.setdefault(cur_game, _Game(cur_game))
                cur_round = None
            elif et == "series-!started-game":
                rolled_back.add(target.get("id"))
            elif et == "game-started-round":
                segs = (actor.get("stateDelta") or {}).get("segments") or [{}]
                n = segs[0].get("sequenceNumber")
                if cur_game and n:
                    cur_round = n
                    holding.clear()
                    dead.clear()
                    games[cur_game].rounds[n] = {
                        "n": n, "start": ts, "freeze_end": None, "end": None,
                        "winner": None, "win_type": None, "sides": {},
                        "plant": None, "defused": False,
                    }

            g = games.get(cur_game) if cur_game else None
            r = g.rounds.get(cur_round) if (g and cur_round) else None
            ss = e.get("seriesState")
            gs = game_state(ss)

            if gs and g:
                if g.map is None and gs.get("map"):
                    g.map = gs["map"].get("name")
                    b = gs["map"].get("bounds")
                    if b:
                        g.bounds = [b["min"]["x"], b["min"]["y"], b["max"]["x"], b["max"]["y"]]
                for t in gs.get("teams") or ():
                    g.teams[t["id"]] = t.get("name")
                    for p in t.get("players") or ():
                        g.player_team[p["id"]] = t["id"]

            if r is None:
                continue

            if et == "round-ended-freezetime":
                r["freeze_end"] = ts
                if gs:
                    for t in gs.get("teams") or ():
                        r["sides"][t["id"]] = t.get("side")
                        for p in t.get("players") or ():
                            items = (p.get("inventory") or {}).get("items")
                            xy = _xy(p)
                            for it in items or ():
                                if it.get("id") in TRACKED_WEAPONS:
                                    holding[p["id"]] = it["id"]
                                    break
                            loadouts.append([
                                cur_game, cur_round, p["id"], t["id"], t.get("side"),
                                _primary(items), _armor(items),
                                xy[0] if xy else None, xy[1] if xy else None,
                            ])
            elif et == "team-won-round":
                r["winner"] = actor.get("id")
                r["win_type"] = ((actor.get("stateDelta") or {}).get("round") or {}).get("winType")
            elif et == "game-ended-round":
                r["end"] = ts
            elif et == "player-completed-plantBomb":
                xy = _xy((actor.get("state") or {}).get("game"))
                fe = r["freeze_end"] or r["start"]
                r["plant"] = {"x": xy[0] if xy else None, "y": xy[1] if xy else None,
                              "t": ts - fe, "player": actor.get("id")}
            elif et == "player-completed-defuseBomb":
                r["defused"] = True
            elif et in ("player-pickedUp-item", "player-dropped-item"):
                item = target.get("id")
                if item in TRACKED_WEAPONS:
                    if et == "player-pickedUp-item":
                        holding[actor.get("id")] = item
                    elif holding.get(actor.get("id")) == item:
                        holding.pop(actor.get("id"), None)
            elif et == "player-killed-player":
                dead.add(target.get("id"))
                holding.pop(target.get("id"), None)
                ast = actor.get("state") or {}
                tst = target.get("state") or {}
                rd = (actor.get("stateDelta") or {}).get("round") or {}
                wk = rd.get("weaponKills") or {}
                weapon = next(iter(wk), "")
                kxy = _xy(ast.get("game"))
                vxy = _xy(tst.get("game"))
                fe = r["freeze_end"] or r["start"]
                kills.append([
                    cur_game, cur_round, ts - fe, actor.get("id"), ast.get("teamId"),
                    target.get("id"), tst.get("teamId"), weapon,
                    kxy[0] if kxy else None, kxy[1] if kxy else None,
                    vxy[0] if vxy else None, vxy[1] if vxy else None,
                    1 if rd.get("firstKill") else 0,
                ])
            elif et == "player-used-ability":
                ast = actor.get("state") or {}
                xy = _xy(ast.get("game"))
                fe = r["freeze_end"] or r["start"]
                grid_cast_ids.add(e["id"])
                # charges left after this cast; +1 gives the charges held before it
                ch = (target.get("state") or {}).get("charges")
                charges_after[e["id"]] = ch if isinstance(ch, int) else -1
                casts_grid.append([
                    e["id"], cur_game, cur_round, ts - fe, actor.get("id"), ast.get("teamId"),
                    ast.get("side"), target.get("id"),
                    xy[0] if xy else None, xy[1] if xy else None,
                ])

            # Position sampling from the snapshot. Buy-phase positions (t_rel = -1) only feed
            # the map floor plan; weapon-holder samples start when the round goes live.
            if gs and r["end"] is None:
                live = r["freeze_end"] is not None
                t_rel = ts - r["freeze_end"] if live else -1
                for t in gs.get("teams") or ():
                    side = r["sides"].get(t["id"]) or t.get("side")
                    for p in t.get("players") or ():
                        pid = p["id"]
                        if pid in dead or p.get("alive") is False:
                            continue
                        xy = _xy(p)
                        if not xy:
                            continue
                        key = (cur_game, pid)
                        if ts - last_pos_ms.get(key, -10**12) >= POS_SAMPLE_MS:
                            last_pos_ms[key] = ts
                            pos.append([cur_game, cur_round, t_rel, pid, side, xy[0], xy[1]])
                        held = holding.get(pid) if live else None
                        if held and ts - last_snipe_ms.get(key, -10**12) >= SNIPE_SAMPLE_MS:
                            last_snipe_ms[key] = ts
                            snipe.append([cur_game, cur_round, t_rel, pid, t["id"], side, held,
                                          xy[0], xy[1]])

    # ---- Ability supplement: precise caster position + aim for each cast -------------
    casts = []
    supp_ids = set()
    sample_gaps: dict = {}   # game id -> gaps between movement samples (ms)
    if supplement and supplement.exists():
        round_index = {}
        for gid, g in games.items():
            rs = sorted(g.rounds.values(), key=lambda x: x["start"])
            round_index[gid] = ([x["start"] for x in rs], rs)
        for rec in _read(supplement):
            gid = rec.get("game_id")
            if gid not in round_index:
                continue
            ts = _ms(rec["occurred_at"])
            starts, rs = round_index[gid]
            i = bisect.bisect_right(starts, ts) - 1
            if i < 0:
                continue
            r = rs[i]
            if r["end"] is not None and ts > r["end"] + 1000 and i + 1 < len(rs):
                continue
            q = rec.get("quality")
            src = rec.get("interpolated")
            if q == "gap_exceeded":
                fb, fa = rec.get("frame_before"), rec.get("frame_after")
                cands = [f for f in (fb, fa) if f]
                src = min(cands, key=lambda f: abs(f.get("offset_ms") or 0)) if cands else None
            if not src or not src.get("position"):
                continue
            p = src["position"]
            v = src.get("view") or {"x": 0, "y": 0, "z": 0}
            g = games[gid]
            pid = rec.get("player_id")
            tid = g.player_team.get(pid)
            side = r["sides"].get(tid)
            fe = r["freeze_end"] or r["start"]
            if rec.get("grid_event_id"):
                supp_ids.add(rec["grid_event_id"])
            # How far the caster moved between the two movement samples around the cast:
            # an honest bound on how wrong the interpolated position can be.
            fb, fa = rec.get("frame_before"), rec.get("frame_after")
            moved = -1.0
            if fb and fa and fb.get("position") and fa.get("position"):
                moved = round(math.hypot(fa["position"]["x"] - fb["position"]["x"],
                                         fa["position"]["y"] - fb["position"]["y"]), 1)
                gap = (fa.get("offset_ms") or 0) - (fb.get("offset_ms") or 0)
                if 0 < gap < 5000:
                    sample_gaps.setdefault(gid, []).append(gap)
            casts.append([
                gid, r["n"], ts - fe, pid, tid, side, rec.get("ability"), rec.get("slot"),
                round(p["x"], 1), round(p["y"], 1), round(p.get("z", 0.0), 1),
                round(v["x"], 4), round(v["y"], 4), round(v["z"], 4), 1,
                charges_after.get(rec.get("grid_event_id"), -1), moved,
            ])

    # GRID casts with no precise supplement row keep GRID's 2D position.
    for cid, gid, rn, t_rel, pid, tid, side, ability, x, y in casts_grid:
        if cid in supp_ids or x is None:
            continue
        casts.append([gid, rn, t_rel, pid, tid, side, ability, "", x, y, 0.0, 0.0, 0.0, 0.0, 0,
                      charges_after.get(cid, -1), -1.0])

    out_games = []
    for gid, g in games.items():
        if gid in rolled_back or not g.rounds:
            continue
        gaps = sorted(sample_gaps.get(gid) or [])
        out_games.append({
            "game_id": gid, "map": g.map, "bounds": g.bounds, "teams": g.teams,
            "sample_ms": gaps[len(gaps) // 2] if gaps else None,
            "rounds": [g.rounds[k] for k in sorted(g.rounds)],
        })
    keep = {x["game_id"] for x in out_games}
    return {
        "series_id": series_id,
        "games": out_games,
        "casts": [c for c in casts if c[0] in keep],
        "snipe": [c for c in snipe if c[0] in keep],
        "loadouts": [c for c in loadouts if c[0] in keep],
        "kills": [c for c in kills if c[0] in keep],
        "pos": [c for c in pos if c[0] in keep],
    }


def extract_to_cache(args) -> tuple[str, str]:
    series_id, feed, supplement = args
    out = SERIES_CACHE / f"{series_id}.json.zst"
    if out.exists():
        return series_id, "cached"
    try:
        data = extract_series(series_id, Path(feed), Path(supplement) if supplement else None)
    except Exception as exc:  # keep the batch going; report at the end
        return series_id, f"error: {exc!r}"
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    tmp.write_bytes(zstandard.ZstdCompressor(level=6).compress(orjson.dumps(data)))
    tmp.replace(out)
    return series_id, "ok"


if __name__ == "__main__":
    sid, feed, supp = sys.argv[1], sys.argv[2], (sys.argv[3] if len(sys.argv) > 3 else None)
    d = extract_series(sid, Path(feed), Path(supp) if supp else None)
    print({k: (len(v) if isinstance(v, list) else v) for k, v in d.items()})
