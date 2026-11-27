"""Checks that what Cirrus reports matches the GRID data. Skipped when the data is not present.

Run after `python -m scout all`. These are the checks behind the numbers in the app: official
scores, sides, callout alignment, and independent recounts of headline percentages.
"""
import csv
import datetime as dt
import math
from collections import Counter, defaultdict

import numpy as np
import pytest

from scout.config import DATA_DIR, STORE_PATH

pytestmark = pytest.mark.skipif(not STORE_PATH.exists() or not (DATA_DIR / "meta" / "games.csv").exists(),
                                reason="needs the GRID data and a built store (python -m scout all)")

from scout import analysis as A  # noqa: E402
from scout.abilities import ABILITIES  # noqa: E402


@pytest.fixture(scope="module")
def st():
    return A.store()


def _team(st, grid_name):
    return st.team_id[next(t for t in st.teams if st.team_names.get(t) == grid_name)]


def test_every_map_reproduces_the_official_score(st):
    official = {r["game_id"]: r for r in csv.DictReader(open(DATA_DIR / "meta" / "games.csv", encoding="utf-8"))
                if r["title"] == "val"}
    G, R = st.G, st.R
    for gi, gid in enumerate(G["game_id"]):
        rm = R["game"] == gi
        mine = (int((R["winner"][rm] == G["team_a"][gi]).sum()), int((R["winner"][rm] == G["team_b"][gi]).sum()))
        want = (int(official[gid]["team1_score"] or 0), int(official[gid]["team2_score"] or 0))
        assert mine == want, gid
    assert len(st.excluded_games) <= 3     # maps dropped because their rounds did not add up


def test_round_outcomes_agree_with_sides(st):
    """A detonation is an attacker win; a defuse or time-out is a defender win. Rounds that break
    this have a broken feed: they must be rare and must be kept out of every analysis."""
    R = st.R
    ok = st.round_ok
    att_won = R["winner"] == R["att"]
    assert att_won[ok & (R["win_type"] == "bombExploded")].all()
    assert not att_won[ok & (R["win_type"] == "bombDefused")].any()
    assert not att_won[ok & (R["win_type"] == "timeExpired")].any()
    assert (~ok).sum() <= 0.001 * len(ok)
    for ri in np.flatnonzero(~ok):
        for team, s in ((int(R["def"][ri]), 1), (int(R["att"][ri]), 0)):
            assert not st.round_mask(team, st.maps[st.round_map[ri]], s)[ri]


def test_every_ability_in_the_data_is_catalogued_with_the_right_agent(st):
    C = st.C
    seen = defaultdict(Counter)
    for a, ag in zip(C["ability"], C["agent"]):
        seen[st.abilities[a]][st.agents[ag]] += 1
    norm = lambda s: s.replace("/", "").replace(" ", "").lower()  # noqa: E731
    for ability, agents in seen.items():
        if not ability:
            continue
        assert ability in ABILITIES, ability
        top = agents.most_common(1)[0][0]
        if top:
            assert norm(top) == norm(ABILITIES[ability][0]), (ability, top)


def test_site_callouts_sit_on_real_plant_sites(st):
    for name in st.maps:
        info = st.map_info[name]
        if not info.get("callouts"):
            continue
        sites = {c["name"][0]: c for c in info["callouts"] if c["name"] in ("A Site", "B Site", "C Site")}
        for anchor in st.site_anchors(name):
            if anchor["n"] < 50:
                continue
            c = sites[anchor["site"]]              # the plant cluster resolved to the right letter
            assert math.hypot(c["x"] - anchor["x"], c["y"] - anchor["y"]) < 2500, (name, anchor)


VIEWS = [("MIBR (1)", "icebox", 1), ("Cloud9", "lotus", 1), ("Sentinels", "lotus", 1), ("Cloud9 GC", "lotus", 1),
         ("Cloud9", "lotus", 0)]


@pytest.mark.parametrize("team_name,map_name,side", VIEWS)
def test_hotspot_shares_recount_exactly(st, team_name, map_name, side):
    """Recount every hotspot the slow, obvious way and compare with what the app reports."""
    team = _team(st, team_name)
    hot = A.utility_hotspots(team, map_name, side)
    C, R = st.C, st.R
    rounds = {int(r) for r in np.flatnonzero((st.round_map == st.map_id[map_name]) & st.round_ok
                                             & ((R["def"] if side == 1 else R["att"]) == team))}
    assert hot["rounds"] == len(rounds)
    assert hot["hotspots"], "expected at least one hotspot"
    for h in hot["hotspots"][:25]:
        aid = st.ability_id[h["ability"]]
        hit = set()
        for i in np.flatnonzero((C["ability"] == aid) & (C["team"] == team)):
            if int(C["round"][i]) in rounds and C["final"][i] == 1 \
                    and math.hypot(C["x"][i] - h["x"], C["y"][i] - h["y"]) <= A.HOTSPOT_RADIUS:
                hit.add(int(C["round"][i]))
        assert len(hit) == h["k"], h["id"]
        assert h["pct"] == round(100.0 * h["k"] / h["n"], 1)
        assert h["evidence"] == sorted(hit)


def test_a_finding_and_its_marker_show_the_same_percentage(st):
    """The headline, the map marker and the list row for one spot must never disagree."""
    for team_name, map_name, side in VIEWS:
        res = A.scout(_team(st, team_name), map_name, side)
        spots = {h["id"]: h for h in res["utility"]["hotspots"]}
        for h in spots.values():
            assert h["p"] == A.pct_int(h["k"], h["n"])
        for f in res["insights"]:
            assert f["pct"] == A.pct_int(f["k"], f["n"])
            if f["hotspot"]:
                assert f["pct"] == spots[f["hotspot"]]["p"], f["title"]
                assert (f["k"], f["n"]) == (spots[f["hotspot"]]["k"], spots[f["hotspot"]]["n"])


def test_operator_kills_come_from_tracked_holders(st):
    """Possession is rebuilt from buys, drops, pickups and deaths; kills are an independent check."""
    L, S, K = st.L, st.S, st.K
    wid = st.weapon_id["operator"]
    holders = defaultdict(set)
    for r, p in zip(L["round"][L["weapon"] == wid], L["player"][L["weapon"] == wid]):
        holders[int(r)].add(int(p))
    for r, p in zip(S["round"][S["weapon"] == wid], S["player"][S["weapon"] == wid]):
        holders[int(r)].add(int(p))
    km = K["weapon"] == wid
    ok = sum(1 for r, p in zip(K["round"][km], K["killer"][km]) if int(p) in holders.get(int(r), ()))
    assert ok / int(km.sum()) > 0.9


def test_operator_opening_areas_count_each_round_once(st):
    op = A.operator_profile(_team(st, "MIBR (1)"), "icebox", 1)
    assert sum(a["open_k"] for a in op["areas"]) <= op["opening_rounds"] <= op["held_rounds"]
    for a in op["areas"]:
        assert a["open_k"] <= a["k"] <= a["n"]


def test_counter_arms_add_up(st):
    hot = A.utility_hotspots(_team(st, "Sentinels"), "lotus", 1)
    shear = next(h for h in hot["hotspots"] if h["ability"] == "shear")
    c = A.counter_for_hotspot("lotus", shear["x"], shear["y"], "shear")
    assert c["contested_rounds"] + c["uncontested_rounds"] == c["rounds"]
    if c["enough"]:
        assert c["win_contested"] == round(100.0 * c["won_contested"] / c["contested_rounds"], 1)
        assert c["signal"] in ("clear", "some", "noise")


def test_game_plan_counter_matches_counter_for_hotspot(st):
    """For one real defense view, every plan item's counter matches counter_for_hotspot and advice is correct."""
    team = _team(st, "Sentinels")
    res = A.scout(team, "lotus", 1)
    plan = res.get("plan", [])
    assert isinstance(plan, list)
    for item in plan:
        ability = item["id"].split("@")[0]
        counter = A.counter_for_hotspot("lotus", item["x"], item["y"], ability)
        # The advice must follow the classification rules
        if counter is None or not counter.get("enough"):
            assert item["advice"] == "untested"
        elif counter.get("signal") in ("clear", "some"):
            expected = "hit" if counter.get("delta", 0) > 0 else "leave"
            assert item["advice"] == expected
        else:
            assert item["advice"] == "no_edge"


def test_attack_view_has_empty_plan(st):
    """Attack views must have an empty plan list."""
    team = _team(st, "Cloud9")
    res = A.scout(team, "lotus", 0)
    assert res.get("plan") == []


def test_scout_payload_keys_unchanged(st):
    """The existing keys of the payload must still be present."""
    team = _team(st, "MIBR (1)")
    res = A.scout(team, "icebox", 1)
    for key in ("sample", "utility", "operator", "setup", "insights"):
        assert key in res, f"Missing key: {key}"
    # New key should also be present
    assert "plan" in res


def test_weapon_summary_rows_equal_their_profiles(st):
    """Every summary row is the matching `operator_profile` fields."""
    from scout.config import TRACKED_WEAPONS
    others = set(TRACKED_WEAPONS) - {"operator"}
    team = _team(st, "Cloud9")
    for map_name, side in (("lotus", 1), ("lotus", 0)):
        rows = A.weapon_summary(team, map_name, side)
        assert [r["buy_rounds"] for r in rows] == sorted((r["buy_rounds"] for r in rows), reverse=True)
        assert {r["weapon"] for r in rows} <= others
        for row in rows:
            p = A.operator_profile(team, map_name, side, weapon=row["weapon"])
            assert row["buy_rounds"] > 0
            assert (row["rounds"], row["buy_rounds"], row["buy_p"], row["held_rounds"]) == \
                (p["rounds"], p["buy_rounds"], p["buy_p"], p["held_rounds"])
            assert row["strength"] == A.strength(p["buy_rounds"], p["rounds"])
            if p["holders"]:
                assert row["holder"] == {k: p["holders"][0][k] for k in ("player", "rounds", "p")}
            else:
                assert row["holder"] is None
            opening = [a for a in p["areas"] if a["open_k"] > 0]
            if opening:
                assert row["area"]["open_k"] == max(a["open_k"] for a in opening)
                a = next(a for a in opening if a["callout"] == row["area"]["callout"])
                for k in ("open_k", "open_n", "open_p", "u", "v"):
                    assert row["area"][k] == a[k]
            else:
                assert row["area"] is None
        for w in others - {r["weapon"] for r in rows}:     # a weapon that is not listed was never bought
            assert A.operator_profile(team, map_name, side, weapon=w)["buy_rounds"] == 0


def test_weapons_key_is_added_for_both_sides_and_nothing_else_changes(st):
    team = _team(st, "Cloud9")
    for side in (1, 0):
        res = A.scout(team, "lotus", side)
        assert res["weapons"] == A.weapon_summary(team, "lotus", side)
        assert set(res) == {"sample", "utility", "operator", "setup", "insights", "plan", "weapons"}
        assert res["operator"]["weapon"] == "operator"


def test_recount_from_the_raw_grid_files(st):
    """Rebuild one headline number from the raw feed and supplement, without the extractor."""
    import orjson
    import zstandard

    grid_name, map_name = "MIBR (1)", "icebox"
    team_id = next(t for t in st.teams if st.team_names.get(t) == grid_name)
    turret = next(h for h in A.utility_hotspots(st.team_id[team_id], map_name, 1)["hotspots"] if h["ability"] == "turret")

    def read(path):
        with zstandard.open(path, "rt", encoding="utf-8") as f:
            for line in f:
                yield orjson.loads(line)

    def secs(s):
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()

    included = set(st.G["game_id"].tolist())
    games = [g for g in csv.DictReader(open(DATA_DIR / "meta" / "games.csv", encoding="utf-8"))
             if g["title"] == "val" and g["map"] == map_name and team_id in (g["team1_id"], g["team2_id"])
             and g["game_id"] in included]
    roster = defaultdict(dict)
    for r in csv.DictReader(open(DATA_DIR / "meta" / "rosters.csv", encoding="utf-8")):
        if r["title"] == "val":
            roster[r["game_id"]][r["player_id"]] = r["team_id"]

    total = with_spot = 0
    for g in games:
        sid, gid = g["series_id"], g["game_id"]
        rounds, cur, in_game = [], None, False
        for env in read(DATA_DIR / "val" / f"events_{sid}_grid.jsonl.zst"):
            t = secs(env["occurredAt"])
            for e in env["events"]:
                kind = e["type"]
                if kind == "series-started-game":
                    in_game = e["target"]["id"] == gid
                if not in_game:
                    continue
                if kind == "game-started-round":
                    cur = {"start": t, "live": None, "end": None, "defending": None}
                    rounds.append(cur)
                elif kind == "round-ended-freezetime" and cur:
                    cur["live"] = t
                    for gs in e["seriesState"]["games"]:
                        if gs["id"] == gid:
                            for tm in gs["teams"]:
                                if tm["id"] == team_id:
                                    cur["defending"] = tm["side"] == "defender"
                elif kind == "game-ended-round" and cur:
                    cur["end"] = t
        casts = [c for c in read(DATA_DIR / "val-ability-supplements" / f"{sid}.jsonl.zst")
                 if c["game_id"] == gid and c["ability"] == "turret" and roster[gid].get(c["player_id"]) == team_id]
        for i, r in enumerate(rounds):
            if not r["defending"] or r["live"] is None:
                continue
            total += 1
            nxt = rounds[i + 1]["start"] if i + 1 < len(rounds) else float("inf")
            mine = [c for c in casts if r["start"] <= secs(c["occurred_at"]) < nxt
                    and secs(c["occurred_at"]) <= (r["end"] or nxt) + 1 and c.get("interpolated")]
            # A turret has one charge: of several buy-phase placements by a player, only the last stands.
            last_buy = {}
            live = []
            for c in sorted(mine, key=lambda c: c["occurred_at"]):
                if secs(c["occurred_at"]) < r["live"]:
                    last_buy[c["player_id"]] = c
                else:
                    live.append(c)
            hit = False
            for c in list(last_buy.values()) + live:
                src = c["interpolated"]
                if c["quality"] == "gap_exceeded":
                    frames = [f for f in (c.get("frame_before"), c.get("frame_after")) if f]
                    src = min(frames, key=lambda f: abs(f.get("offset_ms") or 0))
                p = src["position"]
                if math.hypot(round(p["x"], 1) - turret["x"], round(p["y"], 1) - turret["y"]) <= A.HOTSPOT_RADIUS:
                    hit = True
            with_spot += hit
    assert (with_spot, total) == (turret["k"], turret["n"])
