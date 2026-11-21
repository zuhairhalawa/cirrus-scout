"""Full-resolution 2D replay of one round, read straight from the GRID feed + supplement.

Replays are built on demand from the local data clone and cached in derived/replays.
"""
from __future__ import annotations

import bisect
from pathlib import Path

import orjson
import zstandard

from .abilities import info
from .analysis import WIN_TYPE, fmt_date, store
from .config import DATA_DIR, DERIVED_DIR
from .extract import _ms, _read

REPLAY_DIR = DERIVED_DIR / "replays"


def build_replay(game_id: str, round_n: int) -> dict:
    cache = REPLAY_DIR / f"{game_id}_{round_n}.v2.json"
    if cache.exists():
        return orjson.loads(cache.read_bytes())
    st = store()
    gi = list(st.G["game_id"]).index(game_id)
    series_id = st.G["series_id"][gi]
    map_name = st.maps[st.G["map"][gi]]
    feed = DATA_DIR / "val" / f"events_{series_id}_grid.jsonl.zst"
    supp = DATA_DIR / "val-ability-supplements" / f"{series_id}.jsonl.zst"

    in_game = in_round = False
    freeze_end = round_start = round_end = None
    players: dict[str, dict] = {}
    frames = []
    kills = []
    casts_grid = {}
    events = []
    winner = win_type = None
    last_frame_ms = -1
    dead = set()

    for env in _read(feed):
        ts = _ms(env["occurredAt"])
        stop = False
        for e in env["events"]:
            et = e["type"]
            actor, target = e.get("actor") or {}, e.get("target") or {}
            if et == "series-started-game":
                in_game = target.get("id") == game_id
            if not in_game:
                continue
            if et == "game-started-round":
                n = ((actor.get("stateDelta") or {}).get("segments") or [{}])[0].get("sequenceNumber")
                if in_round and n != round_n:
                    stop = True
                    break
                in_round = n == round_n
                if in_round:
                    round_start = ts
            if not in_round:
                continue
            gs = None
            for g in (e.get("seriesState") or {}).get("games") or ():
                if g.get("id") == game_id:
                    gs = g
                    break
            if gs:
                for t in gs.get("teams") or ():
                    for p in t.get("players") or ():
                        pl = players.setdefault(p["id"], {"id": p["id"], "team": t["id"]})
                        pl["team_name"] = t.get("name") or pl.get("team_name")
                        if t.get("side"):
                            pl["side"] = t["side"]
                        if p.get("name"):
                            pl["name"] = p["name"]
                        if p.get("character"):
                            pl["agent"] = p["character"].get("name")
            if et == "round-ended-freezetime":
                freeze_end = ts
            elif et == "team-won-round":
                winner = actor.get("id")
                win_type = ((actor.get("stateDelta") or {}).get("round") or {}).get("winType")
            elif et == "game-ended-round":
                round_end = ts
            elif et == "player-killed-player":
                dead.add(target.get("id"))
                ak = (actor.get("state") or {}).get("game") or {}
                tk = (target.get("state") or {}).get("game") or {}
                wk = (((actor.get("stateDelta") or {}).get("round") or {}).get("weaponKills") or {})
                kills.append({"ts": ts, "killer": actor.get("id"), "victim": target.get("id"),
                              "weapon": next(iter(wk), ""),
                              "from": ak.get("position"), "to": tk.get("position")})
            elif et == "player-used-ability":
                casts_grid[e["id"]] = (ts, actor.get("id"), target.get("id"),
                                       ((actor.get("state") or {}).get("game") or {}).get("position"))
            elif et in ("player-completed-plantBomb", "player-completed-defuseBomb", "player-completed-explodeBomb"):
                pos = ((actor.get("state") or {}).get("game") or {}).get("position")
                events.append({"ts": ts, "type": et.split("-")[-1], "player": actor.get("id"), "pos": pos})
            if gs and ts - last_frame_ms >= 250:
                pts = []
                for t in gs.get("teams") or ():
                    for p in t.get("players") or ():
                        pos = p.get("position")
                        if pos and p["id"] not in dead and p.get("alive") is not False:
                            pts.append((p["id"], pos["x"], pos["y"]))
                if pts:
                    last_frame_ms = ts
                    frames.append((ts, pts))
        if stop or round_end is not None and ts > round_end + 3000:
            break

    if freeze_end is None:
        freeze_end = round_start or 0

    # precise cast positions from the supplement
    casts = []
    precise = {}
    if supp.exists():
        for rec in _read(supp):
            if rec.get("game_id") != game_id:
                continue
            ts = _ms(rec["occurred_at"])
            if round_start and ts < round_start - 1000:
                continue
            if round_end and ts > round_end:
                break
            src = rec.get("interpolated")
            if not src or not src.get("position"):
                continue
            if rec.get("grid_event_id"):
                precise[rec["grid_event_id"]] = True
            casts.append({"ts": ts, "player": rec.get("player_id"), "ability": rec.get("ability"),
                          "pos": src["position"], "view": src.get("view")})
    for cid, (ts, pid, ab, pos) in casts_grid.items():
        if cid not in precise and pos:
            casts.append({"ts": ts, "player": pid, "ability": ab, "pos": pos, "view": None})

    def uv(p):
        if not p:
            return None
        u, v = st.uv(map_name, p["x"], p["y"])
        return [round(float(u), 4), round(float(v), 4)]

    pid_list = list(players)
    pindex = {p: i for i, p in enumerate(pid_list)}
    out_players = []
    for p in pid_list:
        pl = players[p]
        out_players.append({"name": pl.get("name", p), "team": pl.get("team_name", ""), "side": pl.get("side", ""),
                            "agent": pl.get("agent", "")})
    out_frames = []
    for ts, pts in frames:
        row = [round((ts - freeze_end) / 1000.0, 2)]
        for pid, x, y in pts:
            if pid in pindex:
                u, v = st.uv(map_name, x, y)
                row.append([pindex[pid], round(float(u), 4), round(float(v), 4)])
        out_frames.append(row)
    out_casts = []
    for c in sorted(casts, key=lambda c: c["ts"]):
        if c["player"] not in pindex:
            continue
        agent, name, cat, placement = info(c["ability"])
        if cat == "mobility":
            continue
        aim = None
        if c.get("view"):
            vx, vy = c["view"]["x"], c["view"]["y"]
            p2 = {"x": c["pos"]["x"] + vx * 700, "y": c["pos"]["y"] + vy * 700}
            a, b = uv(c["pos"]), uv(p2)
            aim = [round(b[0] - a[0], 4), round(b[1] - a[1], 4)]
        out_casts.append({"t": round((c["ts"] - freeze_end) / 1000.0, 2), "p": pindex[c["player"]],
                          "ability": name, "agent": agent, "cat": cat, "at": uv(c["pos"]), "aim": aim})
    out_kills = [{"t": round((k["ts"] - freeze_end) / 1000.0, 2), "killer": pindex.get(k["killer"]),
                  "victim": pindex.get(k["victim"]), "weapon": k["weapon"], "from": uv(k["from"]), "to": uv(k["to"])}
                 for k in kills]
    out_events = [{"t": round((e["ts"] - freeze_end) / 1000.0, 2), "type": e["type"],
                   "p": pindex.get(e["player"]), "at": uv(e["pos"])} for e in events]
    team_names = {st.teams[t]: st.team_name(t) for t in (st.G["team_a"][gi], st.G["team_b"][gi])}
    result = {
        "game_id": game_id, "round": round_n, "map": map_name, "series_id": series_id,
        "date": st.G["date"][gi], "event": st.events[st.G["event"][gi]],
        "winner": team_names.get(winner, winner), "result": WIN_TYPE.get(win_type or "", win_type or ""),
        "date_label": fmt_date(st.G["date"][gi]),
        "duration": round(((round_end or frames[-1][0] if frames else freeze_end) - freeze_end) / 1000.0, 1),
        "players": out_players, "frames": out_frames, "casts": out_casts, "kills": out_kills, "events": out_events,
    }
    REPLAY_DIR.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(orjson.dumps(result))
    return result
