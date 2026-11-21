"""Scouting analytics over the columnar store. Every number shown in the UI comes from here.

Conventions
- Times are seconds since the end of the buy phase (round time 0:00). Negative = buy phase.
- Distances are game units (1 unit = 1 cm). 100 units = 1 m.
- A "round sample" is a round the scouted team played on the chosen map and side.
- A hotspot's share is exactly: rounds with a final cast of that ability by the team within
  HOTSPOT_RADIUS of the hotspot's centre, divided by the rounds sampled.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import pickle
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from .abilities import CATEGORY_LABELS, SPATIAL, info
from .build import to_uv
from .config import DERIVED_DIR, STORE_PATH

HOTSPOT_RADIUS = 450.0        # 4.5 m: casts this close count as "the same spot"
SETUP_END = 20.0              # setup phase: the buy phase plus the first 20 s
MIN_HOTSPOT_ROUNDS = 2
RECURRING_SHARE = 20.0        # a setup spot is "recurring" from one round in five
TIME_WINDOWS = [(0, 20), (20, 40), (40, 100)]
PHASES = ("all", "setup", "mid", "postplant")
SIDE_NAME = {0: "attack", 1: "defense"}
SIDE_ID = {"attack": 0, "attacker": 0, "defense": 1, "defender": 1}
CATS = ["trap", "sentinel", "recon", "smoke", "stall", "flash", "damage", "ult", "mobility", "other"]
CAT = {c: i for i, c in enumerate(CATS)}
WIN_TYPE = {"opponentEliminated": "elimination", "bombExploded": "spike detonated",
            "bombDefused": "spike defused", "timeExpired": "time ran out", "": "no result recorded"}


def cat_codes(names) -> list[int]:
    return [CAT[c] for c in names if c in CAT]


@dataclass
class Store:
    raw: dict

    def __post_init__(self):
        s = self.raw
        self.G, self.R, self.C = s["games"], s["rounds"], s["casts"]
        self.S, self.L, self.K = s["snipe"], s["loadouts"], s["kills"]
        self.maps = s["maps"]
        self.map_id = {m: i for i, m in enumerate(self.maps)}
        self.teams = s["teams"]
        self.team_id = {t: i for i, t in enumerate(self.teams)}
        self.team_names = s["team_names"]
        self.players = s["players"]
        self.player_names = s["player_names"]
        self.abilities = s["abilities"]
        self.ability_id = {a: i for i, a in enumerate(self.abilities)}
        self.weapons = s["weapons"]
        self.weapon_id = {w: i for i, w in enumerate(self.weapons)}
        self.agents = s["agents"]
        self.events = s["events"]
        self.map_info = s["map_info"]
        self.max_charges = s.get("max_charges", {})
        self.excluded_games = s.get("excluded_games", [])
        C, R, G = self.C, self.R, self.G
        # A round whose recorded outcome contradicts its sides (a defuse credited to the attackers,
        # say) has a broken feed. It still counts towards the map score but is never analysed.
        att_won = R["winner"] == R["att"]
        wt = R["win_type"]
        self.round_ok = ~(((wt == "bombDefused") | (wt == "timeExpired")) & att_won) & ~((wt == "bombExploded") & ~att_won)
        # per-round convenience arrays
        self.round_map = G["map"][R["game"]]
        self.round_event = G["event"][R["game"]]
        self.round_date = G["date"][R["game"]].astype(str)
        # per-cast convenience arrays
        self.cast_map = self.round_map[C["round"]]
        self.ability_cat = np.array([CAT.get(info(a)[2], CAT["other"]) for a in self.abilities], dtype=np.int8)
        self.cast_cat = self.ability_cat[C["ability"]]
        placement = [info(a)[3] for a in self.abilities]
        self.ability_spatial = np.array([p in SPATIAL for p in placement])
        self.ability_global = np.array([p == "global" for p in placement])
        self.cast_spatial = self.ability_spatial[C["ability"]]
        self.cast_final = C["final"] == 1 if "final" in C else np.ones(len(C["round"]), bool)
        self.cast_plant_t = R["plant_t"][C["round"]]
        self.snipe_map = self.round_map[self.S["round"]]
        self.kill_map = self.round_map[self.K["round"]]
        self.load_map = self.round_map[self.L["round"]]
        self._spawns = {}
        self._sites = {}

    # ---- helpers ---------------------------------------------------------------
    def team_name(self, ti: int) -> str:
        name = self.team_names.get(self.teams[ti], self.teams[ti])
        return re.sub(r"\s*\(\d+\)$", "", name or "")  # GRID broadcast suffix, e.g. "MIBR (1)"

    def player_name(self, pi: int) -> str:
        return self.player_names.get(self.players[pi], self.players[pi])

    def uv(self, map_name: str, x, y):
        mi = self.map_info[map_name]
        return to_uv(mi.get("transform"), mi["bounds"], x, y)

    def callout(self, map_name: str, x: float, y: float) -> str:
        cos = self.map_info[map_name].get("callouts") or []
        if not cos:
            return f"({x:.0f}, {y:.0f})"
        best = min(cos, key=lambda c: (c["x"] - x) ** 2 + (c["y"] - y) ** 2)
        return best["name"]

    def round_mask(self, team: int, map_name: str, side: int, events: set[int] | None = None,
                   since: str | None = None) -> np.ndarray:
        R = self.R
        m = (self.round_map == self.map_id[map_name]) & self.round_ok
        m &= (R["def"] == team) if side == 1 else (R["att"] == team)
        if events:
            m &= np.isin(self.round_event, list(events))
        if since:
            m &= self.round_date >= since
        return m

    def phase_mask(self, phase: str) -> np.ndarray:
        """Which casts fall in a round phase."""
        t, plant = self.C["t"], self.cast_plant_t
        if phase == "setup":
            return t <= SETUP_END
        if phase == "mid":
            return (t > SETUP_END) & (np.isnan(plant) | (t < plant))
        if phase == "postplant":
            return ~np.isnan(plant) & (t >= plant)
        return np.ones(len(t), bool)

    def spawns(self, map_name: str):
        """Attacker and defender spawn points (named callouts; data fallback)."""
        if map_name in self._spawns:
            return self._spawns[map_name]
        named = {c["name"]: (c["x"], c["y"]) for c in self.map_info[map_name].get("callouts") or []}
        if "Attacker Spawn" in named and "Defender Spawn" in named:
            self._spawns[map_name] = {0: named["Attacker Spawn"], 1: named["Defender Spawn"]}
            return self._spawns[map_name]
        mi = self.map_id[map_name]
        L = self.L
        m = (self.load_map == mi) & np.isfinite(L["x"])
        out = {}
        for side in (0, 1):
            mm = m & (L["side"] == side)
            out[side] = (float(np.median(L["x"][mm])), float(np.median(L["y"][mm]))) if mm.any() else (0.0, 0.0)
        self._spawns[map_name] = out
        return out

    def forwardness(self, map_name: str, x, y):
        """0 = on the defenders' spawn, 1 = on the attackers' spawn."""
        sp = self.spawns(map_name)
        dx = np.hypot(np.asarray(x) - sp[1][0], np.asarray(y) - sp[1][1])
        ax = np.hypot(np.asarray(x) - sp[0][0], np.asarray(y) - sp[0][1])
        return dx / np.maximum(dx + ax, 1.0)

    def site_anchors(self, map_name: str):
        """Plant-site centres from every recorded plant on the map."""
        if map_name in self._sites:
            return self._sites[map_name]
        R = self.R
        m = (self.round_map == self.map_id[map_name]) & np.isfinite(R["plant_x"])
        pts = np.c_[R["plant_x"][m], R["plant_y"][m]].astype(np.float64)
        anchors = []
        if len(pts):
            for idx in cluster(pts, 1500.0):
                if len(idx) < max(5, 0.05 * len(pts)):
                    continue
                cx, cy = pts[idx].mean(0)
                anchors.append({"x": float(cx), "y": float(cy), "n": len(idx)})
            anchors.sort(key=lambda a: -a["n"])
            for a in anchors:
                name = self.callout(map_name, a["x"], a["y"])
                a["site"] = name.split(" ")[0] if name and name[0] in "ABC" else name
                u, v = self.uv(map_name, a["x"], a["y"])
                a["u"], a["v"] = float(u), float(v)
        self._sites[map_name] = anchors
        return anchors


@lru_cache(maxsize=1)
def store() -> Store:
    # The store is written by `scout build` on this machine from the local GRID clone;
    # it is never downloaded or shared, so unpickling it is safe here.
    with open(STORE_PATH, "rb") as fh:
        return Store(pickle.load(fh))


# ---- small pure helpers (unit-tested) ------------------------------------------------------
def cluster(pts: np.ndarray, radius: float) -> list[np.ndarray]:
    """Greedy density clustering: seed at the densest point, absorb neighbours, repeat."""
    n = len(pts)
    if n == 0:
        return []
    remaining = np.ones(n, dtype=bool)
    out = []
    keys = np.floor(pts / radius).astype(np.int64)
    kc = Counter(map(tuple, keys))
    dens = np.array([sum(kc.get((k[0] + dx, k[1] + dy), 0) for dx in (-1, 0, 1) for dy in (-1, 0, 1))
                     for k in keys])
    for i in np.argsort(-dens, kind="stable"):
        if not remaining[i]:
            continue
        center = pts[i]
        for _ in range(3):  # recentre a few times (mean shift)
            d = np.hypot(*(pts - center).T)
            members = np.flatnonzero(remaining & (d <= radius))
            if len(members) == 0:
                break
            center = pts[members].mean(0)
        d = np.hypot(*(pts - center).T)
        members = np.flatnonzero(remaining & (d <= radius))
        if len(members) == 0:
            members = np.array([i])
        remaining[members] = False
        out.append(members)
    return out


def pct_int(k: int, n: int) -> int:
    """The one place a share becomes a whole percentage, so every screen shows the same number."""
    return int(100.0 * k / n + 0.5) if n else 0


def wilson_lower(k: int, n: int, z: float = 1.64) -> float:
    """Lower bound of the Wilson score interval for k successes in n trials."""
    if n <= 0:
        return 0.0
    p = k / n
    return (p + z * z / (2 * n) - z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / (1 + z * z / n)


def strength(k: int, n: int) -> str:
    """Plain-language confidence from sample size (Wilson lower bound on the share)."""
    lb = wilson_lower(k, n)
    if n >= 15 and lb >= 0.4:
        return "strong"
    if n >= 8 and lb >= 0.2:
        return "moderate"
    return "thin"


def two_proportion_z(k1: int, n1: int, k2: int, n2: int) -> float | None:
    """z statistic for the difference between two shares (unpooled standard error)."""
    if n1 <= 0 or n2 <= 0:
        return None
    p1, p2 = k1 / n1, k2 / n2
    se = math.sqrt(max(p1 * (1 - p1), 1e-9) / n1 + max(p2 * (1 - p2), 1e-9) / n2)
    return (p1 - p2) / se if se > 0 else 0.0


def fmt_clock(t: float) -> str:
    t = max(0, int(round(t)))
    return f"{t // 60}:{t % 60:02d}"


def fmt_date(iso: str) -> str:
    try:
        d = dt.date.fromisoformat(iso[:10])
    except ValueError:
        return iso
    return f"{d.day} {d.strftime('%b %Y')}"


def fmt_range(a: str, b: str) -> str:
    try:
        da, db = dt.date.fromisoformat(a[:10]), dt.date.fromisoformat(b[:10])
    except ValueError:
        return f"{a} to {b}"
    if da.year == db.year:
        return f"{da.day} {da.strftime('%b')} – {db.day} {db.strftime('%b %Y')}"
    return f"{da.day} {da.strftime('%b %Y')} – {db.day} {db.strftime('%b %Y')}"


def _when(median_t: float, buy_pct: float) -> str:
    if buy_pct >= 50 or median_t < 0:
        return "buy phase"
    return "around " + fmt_clock(median_t)


HEAT_BINS = 128


def density(u, v, sigma: float = 1.7) -> dict:
    """Smoothed density of points in minimap space (a kernel density estimate on a grid).

    Only the smoothed surface is returned, as sparse cells, never the points themselves.
    """
    from scipy.ndimage import gaussian_filter

    H, _, _ = np.histogram2d(v, u, bins=HEAT_BINS, range=[[0, 1], [0, 1]])
    if H.sum() == 0:
        return {"size": HEAT_BINS, "max": 0.0, "cells": []}
    D = gaussian_filter(H, sigma)
    peak = float(D.max())
    ys, xs = np.nonzero(D >= max(0.06, 0.05 * peak))   # drop the faint tail; keeps payloads small
    return {"size": HEAT_BINS, "max": round(peak, 3),
            "cells": [[int(x), int(y), round(float(D[y, x]), 2)] for y, x in zip(ys, xs)]}


def round_refs(team: int, round_ids) -> list[dict]:
    """Human-readable references for evidence rounds (evidence strip and VOD lookup)."""
    st = store()
    R, G = st.R, st.G
    out = []
    for ri in round_ids:
        ri = int(ri)
        gi = int(R["game"][ri])
        side = 1 if R["def"][ri] == team else 0
        opp = int(R["att"][ri] if side == 1 else R["def"][ri])
        live = dt.datetime.fromtimestamp(float(R["freeze_end"][ri]) / 1000.0, dt.timezone.utc)
        out.append({
            "round": ri, "game_id": G["game_id"][gi], "n": int(R["n"][ri]), "series_id": G["series_id"][gi],
            "map": st.maps[G["map"][gi]], "date": G["date"][gi], "date_label": fmt_date(G["date"][gi]),
            "event": st.events[G["event"][gi]], "opponent": st.team_name(opp),
            "won": bool(R["winner"][ri] == team), "side": SIDE_NAME[side],
            "result": WIN_TYPE.get(R["win_type"][ri], R["win_type"][ri]),
            "live_utc": live.strftime("%H:%M:%S"), "game_number": int(G["game_number"][gi]),
        })
    out.sort(key=lambda r: (r["date"], r["game_number"], r["n"]), reverse=True)
    return out


# ---- sample description ---------------------------------------------------------------------
def sample_info(team: int, map_name: str, side: int, since=None) -> dict:
    st = store()
    rmask = st.round_mask(team, map_name, side, None, since)
    rounds = np.flatnonzero(rmask)
    games = np.unique(st.R["game"][rounds])
    G, C = st.G, st.C
    dates = sorted(G["date"][games].tolist())
    cm = rmask[C["round"]] & (C["team"] == team)
    moved = C["moved"][cm & (C["moved"] >= 0)] if "moved" in C else np.array([])
    setup_moved = C["moved"][cm & (C["moved"] >= 0) & (C["t"] < 0) & (st.cast_cat == CAT["trap"])] if "moved" in C else np.array([])
    return {
        "rounds": int(len(rounds)), "maps": int(len(games)),
        "series": int(len(set(G["series_id"][games].tolist()))),
        "from": dates[0] if dates else None, "to": dates[-1] if dates else None,
        "range_label": fmt_range(dates[0], dates[-1]) if dates else "",
        "low_rate_maps": int(G["low_rate"][games].sum()),
        "median_moved_m": round(float(np.median(moved)) / 100.0, 2) if len(moved) else None,
        "setup_moved_m": round(float(np.median(setup_moved)) / 100.0, 2) if len(setup_moved) else None,
        "superseded": int((cm & ~st.cast_final).sum()),
    }


# ---- utility hotspots ----------------------------------------------------------------
def utility_hotspots(team: int, map_name: str, side: int, *, phase="all", categories=None,
                     events=None, since=None):
    st = store()
    C = st.C
    rmask = st.round_mask(team, map_name, side, events, since)
    n_rounds = int(rmask.sum())
    base = rmask[C["round"]] & (C["team"] == team) & st.cast_final & st.phase_mask(phase)
    base &= st.cast_cat != CAT["mobility"]
    m = base & st.cast_spatial
    if categories:
        m &= np.isin(st.cast_cat, cat_codes(categories))
    idx = np.flatnonzero(m)
    result = {"map": map_name, "side": SIDE_NAME[side], "phase": phase, "rounds": n_rounds,
              "casts": int(len(idx)), "radius_m": HOTSPOT_RADIUS / 100.0, "hotspots": [], "heat": None,
              "global": _global_usage(st, base, n_rounds)}
    if n_rounds == 0 or len(idx) == 0:
        return result

    hotspots = []
    for ab in np.unique(C["ability"][idx]):
        aidx = idx[C["ability"][idx] == ab]
        pts = np.c_[C["x"][aidx], C["y"][aidx]].astype(np.float64)
        agent, name, cat, placement = info(st.abilities[ab])
        for members in cluster(pts, HOTSPOT_RADIUS):
            if len(set(C["round"][aidx[members]].tolist())) < MIN_HOTSPOT_ROUNDS:
                continue
            cx, cy = pts[members].mean(0)
            # The reported share is defined on the centre, so anyone can recount it:
            # rounds with this ability within the radius of (cx, cy).
            near = aidx[np.hypot(pts[:, 0] - cx, pts[:, 1] - cy) <= HOTSPOT_RADIUS]
            rset = sorted(set(C["round"][near].tolist()))
            if len(rset) < MIN_HOTSPOT_ROUNDS:
                continue
            u, v = st.uv(map_name, cx, cy)
            ts = C["t"][near]
            aim, aim_fit = _aim(st, map_name, cx, cy, C["vx"][near], C["vy"][near])
            players = Counter(st.player_name(p) for p in C["player"][near])
            hotspots.append({
                "id": f"{st.abilities[ab]}@{int(round(cx))},{int(round(cy))}",
                "ability": st.abilities[ab], "ability_name": name, "agent": agent, "category": cat,
                "category_label": CATEGORY_LABELS.get(cat, cat), "placement": placement,
                "x": float(cx), "y": float(cy), "u": float(u), "v": float(v),
                "aim": aim, "aim_fit": aim_fit,
                "casts": int(len(near)), "k": len(rset), "n": n_rounds,
                "pct": round(100.0 * len(rset) / n_rounds, 1), "p": pct_int(len(rset), n_rounds),
                "strength": strength(len(rset), n_rounds),
                "median_t": float(np.median(ts)), "buy_phase_pct": round(100.0 * float((ts < 0).mean()), 1),
                "when": _when(float(np.median(ts)), 100.0 * float((ts < 0).mean())),
                "spread_m": round(float(np.median(np.hypot(C["x"][near] - cx, C["y"][near] - cy))) / 100.0, 1),
                "callout": st.callout(map_name, cx, cy),
                "players": [{"name": k, "casts": c} for k, c in players.most_common(3)],
                "evidence": rset,
            })
    priority = {c: i for i, c in enumerate(CATS)}
    hotspots.sort(key=lambda h: (-h["pct"], priority.get(h["category"], 9), h["id"]))
    result["hotspots"] = hotspots[:60]

    u, v = st.uv(map_name, C["x"][idx], C["y"][idx])
    result["heat"] = density(u, v)
    return result


def _global_usage(st: Store, base: np.ndarray, n_rounds: int) -> list[dict]:
    """Map-targeted abilities: where the caster stood says nothing about where it landed."""
    C = st.C
    idx = np.flatnonzero(base & st.ability_global[C["ability"]])
    out = []
    for ab in np.unique(C["ability"][idx]):
        a = idx[C["ability"][idx] == ab]
        rounds = set(C["round"][a].tolist())
        first = defaultdict(lambda: 1e9)
        for r, t in zip(C["round"][a], C["t"][a]):
            first[r] = min(first[r], float(t))
        agent, name, cat, _ = info(st.abilities[ab])
        out.append({"ability": st.abilities[ab], "ability_name": name, "agent": agent, "category": cat,
                    "k": len(rounds), "n": n_rounds, "pct": round(100.0 * len(rounds) / max(1, n_rounds), 1),
                    "p": pct_int(len(rounds), n_rounds),
                    "per_round": round(len(a) / max(1, len(rounds)), 1),
                    "first_t": float(np.median(list(first.values())))})
    out.sort(key=lambda r: -r["pct"])
    return out


def _aim(st: Store, map_name: str, x: float, y: float, vx, vy):
    """Mean aim direction as a unit vector in minimap space, plus how consistent it is (0-1)."""
    n = np.hypot(vx, vy)
    ok = n > 1e-3
    if ok.sum() < 2:
        return None, 0.0
    ux, uy = float(np.mean(vx[ok] / n[ok])), float(np.mean(vy[ok] / n[ok]))
    fit = math.hypot(ux, uy)          # 1 = always the same direction, 0 = all over the place
    if fit < 1e-3:
        return None, 0.0
    u1, v1 = st.uv(map_name, x, y)
    u2, v2 = st.uv(map_name, x + ux / fit * 1000.0, y + uy / fit * 1000.0)
    du, dv = float(u2 - u1), float(v2 - v1)
    length = math.hypot(du, dv) or 1.0
    return [du / length, dv / length], round(fit, 2)


# ---- operator profiler ---------------------------------------------------------------
def operator_profile(team: int, map_name: str, side: int, *, weapon="operator", events=None, since=None):
    st = store()
    rmask = st.round_mask(team, map_name, side, events, since)
    n_rounds = int(rmask.sum())
    out = {"weapon": weapon, "rounds": n_rounds, "map": map_name, "side": SIDE_NAME[side],
           "buy_rounds": 0, "held_rounds": 0, "buy_pct": 0.0, "buy_p": 0, "transfer_pct": 0.0, "transfer_p": 0,
           "holders": [],
           "areas": [], "kills": {"total": 0, "opening": 0, "opening_pct": 0.0, "opening_p": 0, "median_t": None,
                                  "per_op_round": 0.0, "lines": []},
           "heat": None, "windows_heat": [], "buy_round_ids": [], "opening_rounds": 0}
    wid = st.weapon_id.get(weapon)
    if n_rounds == 0 or wid is None:
        return out

    # who starts the round with it (loadouts when the buy phase ends)
    L = st.L
    lm = rmask[L["round"]] & (L["team"] == team) & (L["weapon"] == wid)
    buy_rounds = set(L["round"][lm].tolist())
    holders = Counter(L["player"][lm].tolist())
    agents_by_player = defaultdict(Counter)
    for p, a in zip(L["player"][lm], L["agent"][lm]):
        agents_by_player[p][st.agents[a]] += 1

    # where holders stand once the round is live
    S = st.S
    sm = rmask[S["round"]] & (S["team"] == team) & (S["weapon"] == wid) & (S["t"] >= 0)
    sidx = np.flatnonzero(sm)
    per_round = defaultdict(set)
    for r, p in zip(S["round"][sidx], S["player"][sidx]):
        per_round[r].add(p)
    held_rounds = set(per_round) | buy_rounds
    transfers = sum(1 for ps in per_round.values() if len(ps) > 1)

    total_holder_rounds = sum(holders.values()) or 1
    out["buy_rounds"] = len(buy_rounds)
    out["buy_round_ids"] = sorted(int(r) for r in buy_rounds)
    out["held_rounds"] = len(held_rounds)
    out["buy_pct"] = round(100.0 * len(buy_rounds) / n_rounds, 1)
    out["buy_p"] = pct_int(len(buy_rounds), n_rounds)
    out["transfer_pct"] = round(100.0 * transfers / max(1, len(per_round)), 1)
    out["transfer_p"] = pct_int(transfers, len(per_round))
    out["holders"] = [{
        "player": st.player_name(p), "rounds": c, "share": round(100.0 * c / total_holder_rounds, 1),
        "p": pct_int(c, total_holder_rounds),
        "agents": [a for a, _ in agents_by_player[p].most_common(2)],
    } for p, c in holders.most_common(5)]

    anchors = st.site_anchors(map_name)
    site_fwd = [float(st.forwardness(map_name, a["x"], a["y"])) for a in anchors]

    # recurring holding areas: cluster the positions, then merge clusters that share a callout
    pts = np.c_[S["x"][sidx], S["y"][sidx]].astype(np.float64)
    by_callout: dict[str, list[np.ndarray]] = defaultdict(list)
    for members in cluster(pts, 600.0):
        if len(set(S["round"][sidx[members]].tolist())) < 2:
            continue
        cx, cy = pts[members].mean(0)
        by_callout[st.callout(map_name, cx, cy)].append(members)
    # Opening area: for each Operator round, the one area where the holder spent most of the
    # first 20 seconds. Each round counts once, so these shares add up to at most 100%.
    sample_area = np.full(len(sidx), -1)
    area_index = {}
    for name, groups in by_callout.items():
        area_index[name] = len(area_index)
        sample_area[np.concatenate(groups)] = area_index[name]
    tt, rr = S["t"][sidx], S["round"][sidx]
    early = tt < TIME_WINDOWS[0][1]
    per_open = defaultdict(Counter)
    for j in np.flatnonzero(early & (sample_area >= 0)):
        per_open[int(rr[j])][int(sample_area[j])] += 1
    opening = defaultdict(list)
    for r, c in per_open.items():
        opening[c.most_common(1)[0][0]].append(r)
    n_open = len(set(rr[early].tolist()))
    out["opening_rounds"] = n_open

    areas = []
    for name, groups in by_callout.items():
        groups.sort(key=len, reverse=True)
        members = np.concatenate(groups)
        cidx = sidx[members]
        rset = sorted(set(S["round"][cidx].tolist()))
        cx, cy = pts[groups[0]].mean(0)       # anchor the marker on the densest spot in the area
        ts = S["t"][cidx]
        win_share = [round(100.0 * float(((ts >= a) & (ts < b)).mean()), 1) for a, b in TIME_WINDOWS]
        fwd = float(st.forwardness(map_name, cx, cy))
        site, style = None, "mid-map"
        if anchors:
            j = int(np.argmin([math.hypot(cx - s["x"], cy - s["y"]) for s in anchors]))
            site = anchors[j]["site"]
            delta = fwd - site_fwd[j]
            if side == 1:
                style = "aggressive" if delta > 0.07 else ("passive" if delta < -0.05 else "on-site")
            else:
                style = "lurk or flank" if delta < -0.12 else "default"
        u, v = st.uv(map_name, cx, cy)
        players = Counter(st.player_name(p) for p in S["player"][cidx])
        areas.append({
            "x": float(cx), "y": float(cy), "u": float(u), "v": float(v), "callout": name, "site": site,
            "style": style, "forwardness": round(fwd, 3), "k": len(rset), "n": len(held_rounds),
            "pct": round(100.0 * len(rset) / max(1, len(held_rounds)), 1),
            "window_share": win_share, "median_t": float(np.median(ts)),
            "players": [{"name": k, "samples": c} for k, c in players.most_common(2)],
            "evidence": rset,
            "open_k": len(opening.get(area_index[name], [])), "open_n": n_open,
            "open_pct": round(100.0 * len(opening.get(area_index[name], [])) / max(1, n_open), 1),
            "open_p": pct_int(len(opening.get(area_index[name], [])), n_open),
            "open_evidence": sorted(opening.get(area_index[name], [])),
        })
    areas.sort(key=lambda a: (-a["open_k"], -a["k"], a["callout"]))
    out["areas"] = areas[:10]

    # Operator kills by the team: sightlines and opening picks
    K = st.K
    km = rmask[K["round"]] & (K["kteam"] == team) & (K["weapon"] == wid) & np.isfinite(K["kx"]) & np.isfinite(K["vx"])
    kidx = np.flatnonzero(km)
    lines = []
    for i in kidx[:400]:
        u1, v1 = st.uv(map_name, K["kx"][i], K["ky"][i])
        u2, v2 = st.uv(map_name, K["vx"][i], K["vy"][i])
        lines.append({"from": [float(u1), float(v1)], "to": [float(u2), float(v2)], "t": float(K["t"][i]),
                      "first": bool(K["first"][i]), "round": int(K["round"][i])})
    first = int(K["first"][kidx].sum()) if len(kidx) else 0
    out["kills"] = {
        "total": int(len(kidx)), "opening": first,
        "opening_pct": round(100.0 * first / max(1, len(kidx)), 1), "opening_p": pct_int(first, len(kidx)),
        "median_t": float(np.median(K["t"][kidx])) if len(kidx) else None,
        "per_op_round": round(len(kidx) / max(1, len(held_rounds)), 2),
        "lines": lines,
    }
    u, v = st.uv(map_name, S["x"][sidx], S["y"][sidx])
    out["heat"] = density(u, v)
    for a, b in TIME_WINDOWS:
        w = sidx[(S["t"][sidx] >= a) & (S["t"][sidx] < b)]
        uu, vv = st.uv(map_name, S["x"][w], S["y"][w])
        out["windows_heat"].append({"from": a, "to": b, **density(uu, vv)})
    return out


# ---- setup fingerprint + predictability --------------------------------------------
def setup_fingerprint(team: int, map_name: str, side: int = 1, *, events=None, since=None):
    """How often does the team repeat the same trap and cam setup?"""
    st = store()
    hot = utility_hotspots(team, map_name, side, phase="setup", categories={"trap"}, events=events, since=since)
    n_rounds = hot["rounds"]
    empty = {"rounds": n_rounds, "setup_casts": 0, "predictability": None, "recurring": [], "setups": []}
    if n_rounds == 0:
        return empty
    C = st.C
    rmask = st.round_mask(team, map_name, side, events, since)
    m = rmask[C["round"]] & (C["team"] == team) & st.cast_final & st.cast_spatial
    m &= (st.cast_cat == CAT["trap"]) & (C["t"] <= SETUP_END)
    idx = np.flatnonzero(m)
    recurring = [h for h in hot["hotspots"] if h["pct"] >= RECURRING_SHARE]
    per_round = defaultdict(set)
    in_recurring = 0
    for i in idx:
        ab = st.abilities[C["ability"][i]]
        best, bd = None, 1e18
        for k, h in enumerate(recurring):
            if h["ability"] != ab:
                continue
            d = (C["x"][i] - h["x"]) ** 2 + (C["y"][i] - h["y"]) ** 2
            if d < bd:
                best, bd = k, d
        if best is not None and bd <= HOTSPOT_RADIUS ** 2:
            in_recurring += 1
            per_round[int(C["round"][i])].add(best)
    round_ids = [int(r) for r in np.flatnonzero(rmask)]
    signatures = Counter(frozenset(per_round.get(r, set())) for r in round_ids)
    setups = []
    for sig, cnt in sorted(signatures.items(), key=lambda kv: (-kv[1], sorted(kv[0]))):
        if not sig or len(setups) >= 4:
            continue
        setups.append({
            "k": cnt, "n": n_rounds, "pct": round(100.0 * cnt / n_rounds, 1), "p": pct_int(cnt, n_rounds),
            "strength": strength(cnt, n_rounds),
            "spots": [{"id": recurring[k]["id"], "ability_name": recurring[k]["ability_name"],
                       "agent": recurring[k]["agent"], "callout": recurring[k]["callout"],
                       "u": recurring[k]["u"], "v": recurring[k]["v"]} for k in sorted(sig)],
            "evidence": [r for r in round_ids if frozenset(per_round.get(r, set())) == sig],
        })
    share = pct_int(in_recurring, len(idx)) if len(idx) else None
    return {"rounds": n_rounds, "setup_casts": int(len(idx)), "predictability": share,
            "recurring": [{"id": h["id"], "ability_name": h["ability_name"], "agent": h["agent"],
                           "callout": h["callout"], "u": h["u"], "v": h["v"], "pct": h["pct"],
                           "k": h["k"], "n": h["n"]} for h in recurring],
            "setups": setups}


def league_predictability(map_name: str, side: int = 1) -> list[float]:
    """Predictability of every team with 20+ rounds on this map and side (cached on disk)."""
    cache = DERIVED_DIR / "league_predictability.json"
    stamp = STORE_PATH.stat().st_mtime_ns
    data = {}
    if cache.exists():
        data = json.loads(cache.read_text())
        if data.get("_store") != stamp:
            data = {}
    key = f"{map_name}:{side}"
    if key not in data:
        st = store()
        col = st.R["def"] if side == 1 else st.R["att"]
        counts = Counter(col[st.round_map == st.map_id[map_name]].tolist())
        vals = []
        for team, n in counts.items():
            if n < 20:
                continue
            fp = setup_fingerprint(int(team), map_name, side)
            if fp["setup_casts"] >= 15 and fp["predictability"] is not None:
                vals.append(fp["predictability"])
        data[key] = sorted(vals)
        data["_store"] = stamp
        cache.write_text(json.dumps(data))
    return data[key]


# ---- data-backed counters ----------------------------------------------------------
COUNTER_CATS = ("recon", "damage", "flash", "stall")
CONTEST_BEFORE = 25.0
MIN_ARM = 8


def counter_for_hotspot(map_name: str, x: float, y: float, ability: str):
    """League-wide: when defenders set this spot, did attackers who hit it early win more?"""
    st = store()
    C, R = st.C, st.R
    aid = st.ability_id.get(ability)
    if aid is None:
        return None
    mi = st.map_id[map_name]
    dm = (st.cast_map == mi) & (C["ability"] == aid) & (C["side"] == 1) & st.cast_final & st.round_ok[C["round"]]
    dm &= (C["t"] <= SETUP_END) & (np.hypot(C["x"] - x, C["y"] - y) <= HOTSPOT_RADIUS)
    rounds = np.unique(C["round"][dm])
    out = {"rounds": int(len(rounds)), "contest_before": CONTEST_BEFORE, "enough": False,
           "contested_rounds": 0, "uncontested_rounds": int(len(rounds)), "tools": []}
    if len(rounds) == 0:
        return out
    # attacker utility thrown through or onto the spot early in those rounds
    am = np.isin(C["round"], rounds) & (C["side"] == 0) & (C["t"] >= 0) & (C["t"] <= CONTEST_BEFORE)
    am &= np.isin(st.cast_cat, cat_codes(COUNTER_CATS)) & st.cast_spatial
    aidx = np.flatnonzero(am)
    px, py = C["x"][aidx], C["y"][aidx]
    vx, vy = C["vx"][aidx], C["vy"][aidx]
    nv = np.hypot(vx, vy)
    ok = nv > 1e-3
    safe = np.where(ok, nv, 1)
    along = ((x - px) * vx + (y - py) * vy) / safe
    perp = np.abs((x - px) * vy - (y - py) * vx) / safe
    near = np.hypot(x - px, y - py) <= 700
    hit = (ok & (along > 0) & (along < 3500) & (perp < 550)) | near
    contested = np.isin(rounds, np.unique(C["round"][aidx[hit]]))
    won = R["winner"][rounds] == R["att"][rounds]
    n_c, n_u = int(contested.sum()), int((~contested).sum())
    k_c, k_u = int(won[contested].sum()), int(won[~contested].sum())
    out.update(contested_rounds=n_c, uncontested_rounds=n_u, won_contested=k_c, won_uncontested=k_u)
    by_ability = Counter(st.abilities[a] for a in C["ability"][aidx[hit]])
    for ab, cnt in by_ability.most_common(4):
        agent, name, _, _ = info(ab)
        out["tools"].append({"ability": ab, "ability_name": name, "agent": agent, "uses": cnt})
    if n_c < MIN_ARM or n_u < MIN_ARM:
        return out
    z = two_proportion_z(k_c, n_c, k_u, n_u)
    out.update(
        enough=True,
        win_contested=round(100.0 * k_c / n_c, 1), win_uncontested=round(100.0 * k_u / n_u, 1),
        delta=round(100.0 * k_c / n_c - 100.0 * k_u / n_u, 1), z=round(z, 2),
        signal="clear" if abs(z) >= 1.96 else "some" if abs(z) >= 1.64 else "noise",
    )
    return out


# ---- team listing + overview -----------------------------------------------------------
def teams_index(min_maps=3):
    st = store()
    G = st.G
    counts = Counter(G["team_a"].tolist()) + Counter(G["team_b"].tolist())
    out = []
    for t, n in counts.items():
        if n < min_maps or not st.teams[t]:
            continue
        gm = (G["team_a"] == t) | (G["team_b"] == t)
        evs = Counter(st.events[e] for e in G["event"][gm])
        maps = Counter(st.maps[m] for m in G["map"][gm])
        circuit = "Game Changers" if any("Game Changers" in e for e in evs) else "VCT"
        out.append({"id": st.teams[t], "name": st.team_name(t), "maps_played": n, "circuit": circuit,
                    "last_played": max(G["date"][gm]), "maps": dict(maps.most_common()),
                    "events": [e for e, _ in evs.most_common(3)]})
    names = Counter(r["name"] for r in out)
    for r in out:
        if names[r["name"]] > 1:
            r["name"] = f'{r["name"]} ({r["circuit"]}, {r["last_played"][:4]})'
    out.sort(key=lambda r: (-("Cloud9" in r["name"]), -r["maps_played"], r["name"]))
    return out


def team_overview(team: int):
    st = store()
    R, G = st.R, st.G
    rows = []
    for mi, mname in enumerate(st.maps):
        for side in (0, 1):
            col = R["def"] if side == 1 else R["att"]
            m = (st.round_map == mi) & (col == team)
            n = int(m.sum())
            if n == 0:
                continue
            won = int((R["winner"][m] == team).sum())
            rows.append({"map": mname, "side": SIDE_NAME[side], "rounds": n, "won": won,
                         "win_pct": round(100.0 * won / n, 1)})
    gm = np.flatnonzero((G["team_a"] == team) | (G["team_b"] == team))
    recent = []
    for gi in sorted(gm, key=lambda i: (G["date"][i], G["game_number"][i]), reverse=True)[:12]:
        opp = G["team_b"][gi] if G["team_a"][gi] == team else G["team_a"][gi]
        us = G["score_a"][gi] if G["team_a"][gi] == team else G["score_b"][gi]
        them = G["score_b"][gi] if G["team_a"][gi] == team else G["score_a"][gi]
        recent.append({"date": G["date"][gi], "date_label": fmt_date(G["date"][gi]),
                       "map": st.maps[G["map"][gi]], "opponent": st.team_name(int(opp)),
                       "score": f"{us}–{them}", "won": bool(G["winner"][gi] == team),
                       "event": st.events[G["event"][gi]]})
    return {"team": st.team_name(team), "by_map": rows, "recent": recent}


# ---- headline findings (in the coach's language) -----------------------------------
STYLE_PHRASE = {"aggressive": "an aggressive forward angle", "passive": "a passive, deep position",
                "on-site": "an on-site angle", "mid-map": "a mid-map angle", "default": "a default angle",
                "lurk or flank": "a lurk or flank position"}
VERB = {"placed": "set", "ranged": "placed", "thrown": "threw", "wall": "sent"}


def possessive(name: str) -> str:
    return name + "'" if name.endswith("s") else name + "'s"


def _finding(kind, title, sub, k, n, unit, text, detail, evidence, focus=None, hotspot=None, basis=None):
    """A headline finding. `basis` (k, n) overrides the counts used for evidence strength."""
    bk, bn = basis or (k, n)
    return {"kind": kind, "title": title, "sub": sub, "k": int(k), "n": int(n),
            "pct": pct_int(k, n), "unit": unit, "strength": strength(bk, bn),
            "text": text, "detail": detail, "evidence": evidence, "focus": focus, "hotspot": hotspot}


def insights(team: int, map_name: str, side: int, hot: dict, op: dict, fp: dict | None, league=None):
    st = store()
    name = st.team_name(team)
    mapn = map_name.capitalize()
    side_word = SIDE_NAME[side]
    rounds_word = f"{side_word} rounds"
    out = []

    def spot_finding(h, kind="utility"):
        at = "at" if h["placement"] == "placed" else "from"
        who = h["players"][0]["name"] if h["players"] else "the team"
        by = "placed by" if h["placement"] in ("placed", "ranged") else "by"
        title = f"{h['agent']} {h['ability_name']} {at} {h['callout']}"
        sub = f"{h['k']} of {h['n']} {rounds_word} · {by} {who} · {h['when']}"
        text = (f"{name} {VERB.get(h['placement'], 'used')} {h['agent']} {h['ability_name']} {at} {h['callout']} "
                f"in {h['p']}% of {rounds_word} on {mapn} ({h['k']}/{h['n']}).")
        detail = f"Usually {who}, {h['when']}. Casts sit within {h['spread_m']} m of the marker (median)."
        return _finding(kind, title, sub, h["k"], h["n"], f"of {rounds_word}", text, detail, h["evidence"],
                        {"u": h["u"], "v": h["v"]}, h["id"])

    # On attack the buy phase is spent inside spawn, so only utility used once the round is
    # live says anything about how they take space.
    spots = [h for h in hot["hotspots"] if side == 1 or h["buy_phase_pct"] < 50]
    traps = [h for h in spots if h["category"] in ("trap", "sentinel")]
    if traps:
        out.append(spot_finding(traps[0]))
    others = [h for h in spots if h["category"] in ("recon", "smoke", "flash", "stall") and h["p"] >= 25]
    if others:
        out.append(spot_finding(others[0]))

    if op["rounds"] and op["buy_rounds"] < 6:
        out.append(_finding(
            "operator", "Rarely on the Operator",
            f"{op['buy_rounds']} of {op['rounds']} {rounds_word} start with one", op["buy_rounds"], op["rounds"],
            "of rounds start with an Operator",
            f"{name} start {'an' if side == 0 else 'a'} {side_word} round on {mapn} with the Operator in only "
            f"{op['buy_rounds']} of {op['rounds']} rounds.",
            "Expect rifles on first contact; there is no regular Operator angle to play around. "
            "The evidence lists the rounds where they did buy one.",
            op["buy_round_ids"], basis=(op["rounds"] - op["buy_rounds"], op["rounds"])))
    elif op["holders"] and op["areas"]:
        p, a = op["holders"][0], op["areas"][0]
        if a["open_k"]:
            k, n, ev = a["open_k"], a["open_n"], a["open_evidence"]
            sub, when = f"{k} of {n} Operator rounds · first 20 seconds", "in the first 20 seconds"
        else:
            k, n, ev = a["k"], a["n"], a["evidence"]
            sub, when = f"{k} of {n} Operator rounds", "at some point in the round"
        owner = possessive(name)
        out.append(_finding(
            "operator", f"{p['player']} opens on the Operator at {a['callout']}", sub, k, n, "of Operator rounds",
            f"{p['player']} is {owner} primary Operator ({p['p']}% of their Operator rounds) and holds "
            f"{STYLE_PHRASE.get(a['style'], 'a position')} at {a['callout']} {when} in {k} of {n} Operator rounds.",
            f"{p['player']} carries it in {p['p']}% of their Operator rounds. Bought in {op['buy_p']}% of "
            f"{rounds_word} ({op['buy_rounds']}/{op['rounds']}); {op['kills']['opening_p']}% of its kills are opening picks.",
            ev, {"u": a["u"], "v": a["v"]}))

    if fp and fp["setups"]:
        top = fp["setups"][0]
        spots = " + ".join(f"{s['ability_name']} at {s['callout']}" for s in top["spots"][:3])
        rank = None
        if league and fp["predictability"] is not None:
            rank = round(100.0 * sum(1 for v in league if v < fp["predictability"]) / len(league))
        detail = f"{fp['predictability']}% of their trap and cam placements land on a spot they reuse"
        detail += f", more predictable than {rank}% of teams on {mapn}." if rank is not None else "."
        out.append(_finding(
            "setup", f"Same setup: {spots}", f"{top['k']} of {top['n']} {rounds_word}", top["k"], top["n"],
            f"of {rounds_word}",
            f"{name} ran the same setup ({spots}) in {top['k']} of {top['n']} {rounds_word} on {mapn}.",
            detail, top["evidence"]))
    return out


def scout(team: int, map_name: str, side: int, *, phase="all", events=None, since=None):
    hot = utility_hotspots(team, map_name, side, phase=phase, events=events, since=since)
    op = operator_profile(team, map_name, side, events=events, since=since)
    fp = league = None
    if side == 1:
        fp = setup_fingerprint(team, map_name, side, events=events, since=since)
        league = league_predictability(map_name, side)
        fp["league"] = league
    # headline findings always describe the whole round, whatever phase filter the map shows
    base = hot if phase == "all" else utility_hotspots(team, map_name, side, events=events, since=since)
    return {"sample": sample_info(team, map_name, side, since), "utility": hot, "operator": op, "setup": fp,
            "insights": insights(team, map_name, side, base, op, fp, league)}
