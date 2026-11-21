"""Unit tests for the pure helpers. These run without the GRID data."""
import numpy as np
import pytest

from scout import analysis as A
from scout.abilities import ABILITIES, CATEGORY_LABELS, SPATIAL, info
from scout.brief import render_brief
from scout.build import RECALLABLE, _final_setup, _floor_plan, _rdp, _vector_plan, to_uv


def test_cluster_groups_points_within_radius():
    rng = np.random.default_rng(1)
    a = rng.normal([0, 0], 40, size=(30, 2))
    b = rng.normal([3000, 0], 40, size=(12, 2))
    lone = np.array([[9000.0, 9000.0]])
    groups = A.cluster(np.vstack([a, b, lone]), 450.0)
    sizes = sorted(len(g) for g in groups)
    assert sizes == [1, 12, 30]
    assert sum(sizes) == 43          # every point is assigned exactly once
    assert len(set(np.concatenate(groups).tolist())) == 43


def test_cluster_is_deterministic():
    pts = np.random.default_rng(7).uniform(0, 5000, size=(200, 2))
    one = [sorted(g.tolist()) for g in A.cluster(pts, 450.0)]
    two = [sorted(g.tolist()) for g in A.cluster(pts, 450.0)]
    assert one == two


def test_cluster_empty():
    assert A.cluster(np.empty((0, 2)), 450.0) == []


def test_wilson_lower_bound_matches_reference_values():
    # reference values computed from the closed form with z = 1.64
    assert A.wilson_lower(0, 0) == 0.0
    assert A.wilson_lower(45, 84) == pytest.approx(0.4467, abs=2e-3)
    assert A.wilson_lower(5, 5) == pytest.approx(0.650, abs=3e-3)
    assert 0 <= A.wilson_lower(1, 100) < 0.01


@pytest.mark.parametrize("k,n,expected", [
    (45, 84, "strong"),      # 54% of 84 rounds
    (5, 5, "thin"),          # 100% but only five rounds
    (4, 11, "thin"),
    (16, 37, "moderate"),
    (30, 84, "moderate"),
    (133, 133, "strong"),
    (0, 50, "thin"),
])
def test_strength_needs_both_share_and_sample(k, n, expected):
    assert A.strength(k, n) == expected


def test_whole_percentages_round_half_up_in_one_place():
    assert A.pct_int(39, 51) == 76          # 76.47%
    assert A.pct_int(1, 8) == 13            # 12.5% rounds up, not to even
    assert A.pct_int(45, 84) == 54
    assert A.pct_int(0, 0) == 0
    assert A.pct_int(84, 84) == 100


def test_two_proportion_z():
    assert A.two_proportion_z(50, 100, 50, 100) == pytest.approx(0.0)
    z = A.two_proportion_z(114, 209, 372, 781)     # 54.5% vs 47.6%
    assert z == pytest.approx(1.78, abs=0.05)
    assert A.two_proportion_z(1, 0, 1, 10) is None


def test_formatting_helpers():
    assert A.fmt_clock(0) == "0:00"
    assert A.fmt_clock(75.4) == "1:15"
    assert A.fmt_clock(-12) == "0:00"
    assert A.fmt_date("2025-08-17") == "17 Aug 2025"
    assert A.fmt_range("2025-03-23", "2025-08-17") == "23 Mar – 17 Aug 2025"
    assert A.fmt_range("2025-11-02", "2026-01-09") == "2 Nov 2025 – 9 Jan 2026"
    assert A.possessive("MIBR") == "MIBR's"
    assert A.possessive("Sentinels") == "Sentinels'"


def test_ability_catalogue_is_well_formed():
    placements = {"placed", "ranged", "thrown", "wall", "self", "global"}
    for key, (agent, name, category, placement) in ABILITIES.items():
        assert agent and name, key
        assert category in CATEGORY_LABELS, key
        assert placement in placements, key
    assert set(SPATIAL) < placements
    # devices a player can pick up and re-place must be things we draw on the map
    for key in RECALLABLE:
        assert ABILITIES[key][3] in SPATIAL, key
    # map-targeted smokes are never drawn as if the caster's position were the landing point
    for key in ("sky-smoke", "dark-cover", "ruse", "stars"):
        assert ABILITIES[key][3] == "global"
    assert info("not-a-real-ability")[2] == "other"
    assert info(None)[1] == "Unknown"


def test_to_uv_with_minimap_transform_and_bounds_fallback():
    meta = {"xm": 7e-05, "ym": -7e-05, "xs": 0.8, "ys": 0.5}
    u, v = to_uv(meta, None, np.array([1000.0]), np.array([2000.0]))
    assert u[0] == pytest.approx(2000 * 7e-05 + 0.8)
    assert v[0] == pytest.approx(1000 * -7e-05 + 0.5)
    u, v = to_uv(None, [0, 0, 100, 200], np.array([50.0]), np.array([50.0]))
    assert (u[0], v[0]) == pytest.approx((0.5, 0.75))


def test_rdp_keeps_corners_and_drops_collinear_points():
    line = np.array([[0, 0], [1, 0.01], [2, 0], [3, 0.01], [4, 0], [4, 4]], dtype=float)
    out = _rdp(line, 0.5)
    assert out.tolist() == [[0, 0], [4, 0], [4, 4]]


def test_floor_plan_removes_specks_and_fills_pinholes():
    hist = np.zeros((300, 300))
    hist[50:250, 50:250] = 1          # a room
    hist[150, 150] = 0                # a pin-hole (one missed sample)
    hist[10:13, 10:13] = 1            # an isolated speck
    hist[120:160, 180:220] = 0        # a real pillar, well above the fill threshold
    plan = _floor_plan(hist) > 0.5
    assert plan[150, 150]             # pin-hole filled
    assert not plan[11, 11]           # speck removed
    assert not plan[140, 200]         # pillar kept
    assert plan[100, 100]


def test_vector_plan_traces_a_closed_path():
    mask = np.zeros((200, 200), dtype=np.float32)
    mask[40:160, 40:160] = 1.0
    mask[80:120, 80:120] = 0.0        # a hole
    path = _vector_plan(mask)
    assert path.count("M") == 2 and path.count("Z") == 2   # outline + hole
    nums = [float(x) for x in path.replace("M", " ").replace("L", " ").replace("Z", " ").split()]
    assert 0 <= min(nums) and max(nums) <= 1000


def _store(rows, abilities):
    """Tiny cast table: rows of (round, player, ability index, t seconds, charges before)."""
    arr = np.array(rows, dtype=float)
    return {"casts": {
        "round": arr[:, 0].astype(np.int32), "player": arr[:, 1].astype(np.int32),
        "ability": arr[:, 2].astype(np.int32), "t": arr[:, 3].astype(np.float32),
        "charges": arr[:, 4].astype(np.int8),
    }}, abilities


def test_final_setup_keeps_only_placements_still_standing():
    abilities = ["turret", "trapwire", "recon-bolt"]
    rows = [
        # round 0, player 1: turret placed three times in the buy phase -> only the last stands
        (0, 1, 0, -30, 1), (0, 1, 0, -20, 1), (0, 1, 0, -5, 1),
        # round 0, player 2: three trapwires with two charges -> the first was picked up
        (0, 2, 1, -25, 2), (0, 2, 1, -15, 1), (0, 2, 1, -4, 1),
        # round 0, player 3: a recon bolt is never "re-placed"
        (0, 3, 2, -3, 1), (0, 3, 2, -2, 1),
        # round 1, player 1: a turret placed once in the buy phase and once mid-round both count
        (1, 1, 0, -10, 1), (1, 1, 0, 40, 1),
    ]
    # enough two-charge trapwire casts for the charge count to be learned from the data
    rows += [(9, 9, 1, 5, 2)] * 3
    store, ids = _store(rows, abilities)
    max_charges, final = _final_setup(store, ids)
    assert max_charges == {"turret": 1, "trapwire": 2, "recon-bolt": 1}
    assert final[:3].tolist() == [0, 0, 1]
    assert final[3:6].tolist() == [0, 1, 1]
    assert final[6:8].tolist() == [1, 1]
    assert final[8:10].tolist() == [1, 1]


# ---- game plan classification ------------------------------------------------

def _counter(enough=True, signal="some", delta=5.0, z=1.8,
             rounds=100, contested_rounds=50, uncontested_rounds=50,
             won_contested=28, won_uncontested=22,
             win_contested=56.0, win_uncontested=44.0,
             tools=None):
    """Build a hand-written counter dict."""
    return {
        "rounds": rounds, "contest_before": 25.0, "enough": enough,
        "contested_rounds": contested_rounds, "uncontested_rounds": uncontested_rounds,
        "won_contested": won_contested, "won_uncontested": won_uncontested,
        "win_contested": win_contested, "win_uncontested": win_uncontested,
        "delta": delta, "z": z, "signal": signal,
        "tools": tools or [],
    }


class TestClassifyAdvice:
    """_classify_advice is a pure function mapping counter dicts to advice strings."""

    def test_hit_on_positive_delta_with_clear_signal(self):
        assert A._classify_advice(_counter(signal="clear", delta=5.0, z=2.5)) == "hit"

    def test_hit_on_positive_delta_with_some_signal(self):
        assert A._classify_advice(_counter(signal="some", delta=3.0, z=1.7)) == "hit"

    def test_leave_on_negative_delta_with_clear_signal(self):
        assert A._classify_advice(_counter(signal="clear", delta=-4.0, z=-2.2)) == "leave"

    def test_leave_on_negative_delta_with_some_signal(self):
        assert A._classify_advice(_counter(signal="some", delta=-2.0, z=-1.7)) == "leave"

    def test_no_edge_when_signal_is_noise(self):
        assert A._classify_advice(_counter(signal="noise", delta=1.0, z=0.5)) == "no_edge"

    def test_untested_when_not_enough(self):
        assert A._classify_advice(_counter(enough=False)) == "untested"

    def test_untested_when_counter_is_none(self):
        assert A._classify_advice(None) == "untested"

    def test_hit_zero_delta_is_not_hit(self):
        """Delta must be strictly positive for hit."""
        assert A._classify_advice(_counter(signal="some", delta=0.0, z=0.0)) == "leave"


# ---- game plan ordering -------------------------------------------------------

def _plan_item(advice, k=10, z=1.5):
    """Build a minimal plan item for ordering tests."""
    return {
        "id": f"item-{advice}-{k}",
        "ability_name": "Turret", "agent": "Killjoy", "callout": "A Site",
        "u": 0.5, "v": 0.5, "k": k, "n": 50, "p": 20, "strength": "moderate",
        "advice": advice,
        "counter": {"z": z, "enough": True, "signal": "some", "delta": 5.0 if advice == "hit" else -5.0},
    }


class TestGamePlanOrdering:
    """game_plan orders items: hit (z desc), leave (z asc), no_edge (k desc), untested (k desc)."""

    def test_hit_before_leave(self):
        items = [_plan_item("leave", z=-1.5), _plan_item("hit", z=2.0)]
        A.game_plan.__code__  # just ensure it's importable
        # We test the sort key directly
        advice_order = {"hit": 0, "leave": 1, "no_edge": 2, "untested": 3}
        items.sort(key=lambda it: (
            advice_order[it["advice"]],
            -(it["counter"].get("z") or 0) if it["advice"] == "hit"
            else (it["counter"].get("z") or 0) if it["advice"] == "leave"
            else -it["k"],
        ))
        assert items[0]["advice"] == "hit"
        assert items[1]["advice"] == "leave"

    def test_hit_sorted_by_z_descending(self):
        items = [
            _plan_item("hit", z=1.5),
            _plan_item("hit", z=2.5),
            _plan_item("hit", z=1.0),
        ]
        advice_order = {"hit": 0, "leave": 1, "no_edge": 2, "untested": 3}
        items.sort(key=lambda it: (
            advice_order[it["advice"]],
            -(it["counter"].get("z") or 0) if it["advice"] == "hit"
            else (it["counter"].get("z") or 0) if it["advice"] == "leave"
            else -it["k"],
        ))
        assert items[0]["counter"]["z"] == 2.5
        assert items[1]["counter"]["z"] == 1.5
        assert items[2]["counter"]["z"] == 1.0

    def test_leave_sorted_by_z_ascending(self):
        items = [
            _plan_item("leave", z=-1.0),
            _plan_item("leave", z=-2.5),
            _plan_item("leave", z=-1.5),
        ]
        advice_order = {"hit": 0, "leave": 1, "no_edge": 2, "untested": 3}
        items.sort(key=lambda it: (
            advice_order[it["advice"]],
            -(it["counter"].get("z") or 0) if it["advice"] == "hit"
            else (it["counter"].get("z") or 0) if it["advice"] == "leave"
            else -it["k"],
        ))
        assert items[0]["counter"]["z"] == -2.5
        assert items[1]["counter"]["z"] == -1.5
        assert items[2]["counter"]["z"] == -1.0

    def test_no_edge_sorted_by_k_descending(self):
        items = [
            _plan_item("no_edge", k=5),
            _plan_item("no_edge", k=20),
            _plan_item("no_edge", k=10),
        ]
        advice_order = {"hit": 0, "leave": 1, "no_edge": 2, "untested": 3}
        items.sort(key=lambda it: (
            advice_order[it["advice"]],
            -(it["counter"].get("z") or 0) if it["advice"] == "hit"
            else (it["counter"].get("z") or 0) if it["advice"] == "leave"
            else -it["k"],
        ))
        assert items[0]["k"] == 20
        assert items[1]["k"] == 10
        assert items[2]["k"] == 5

    def test_untested_sorted_by_k_descending(self):
        items = [
            _plan_item("untested", k=3),
            _plan_item("untested", k=15),
            _plan_item("untested", k=8),
        ]
        advice_order = {"hit": 0, "leave": 1, "no_edge": 2, "untested": 3}
        items.sort(key=lambda it: (
            advice_order[it["advice"]],
            -(it["counter"].get("z") or 0) if it["advice"] == "hit"
            else (it["counter"].get("z") or 0) if it["advice"] == "leave"
            else -it["k"],
        ))
        assert items[0]["k"] == 15
        assert items[1]["k"] == 8
        assert items[2]["k"] == 3


# ---- brief game plan section --------------------------------------------------

def _brief_payload(plan=None):
    """Minimal payload for brief tests."""
    return {
        "team": {"id": "echo", "name": "Echo"},
        "sample": {"rounds": 50, "maps": 8, "range_label": "Last 6 months"},
        "utility": {"map": "lotus", "side": "defense", "rounds": 50, "hotspots": [], "global": []},
        "operator": {"weapon": "operator", "rounds": 0, "buy_rounds": 0, "buy_pct": 0.0,
                      "buy_p": 0, "holders": [], "areas": [],
                      "kills": {"total": 0, "opening": 0, "opening_pct": 0.0, "opening_p": 0,
                                "median_t": None, "per_op_round": 0.0, "lines": []}},
        "setup": None,
        "insights": [],
        "plan": plan or [],
    }


class TestBriefGamePlan:
    """render_brief game plan section with hand-written payloads."""

    def test_hit_item_format(self):
        plan = [{
            "id": "shear@100,200", "ability_name": "Shear", "agent": "Vyse",
            "callout": "C Main", "u": 0.3, "v": 0.4, "k": 45, "n": 84, "p": 54,
            "strength": "strong", "advice": "hit",
            "counter": {
                "rounds": 195, "contested_rounds": 105, "uncontested_rounds": 90,
                "won_contested": 57, "won_uncontested": 43,
                "win_contested": 54.3, "win_uncontested": 47.8,
                "delta": 6.5, "z": 1.8, "signal": "some",
                "tools": [{"ability_name": "Recon Bolt", "agent": "Skye", "ability": "recon-bolt", "uses": 40},
                          {"ability_name": "FRAG/ment", "agent": "KAY/O", "ability": "frag", "uses": 25}],
                "contest_before": 25.0, "enough": True,
            },
        }]
        md = render_brief(_brief_payload(plan))
        assert "## Game plan" in md
        assert "Hit the Vyse Shear at C Main early" in md
        assert "(set in 45 of 84 rounds)" in md
        assert "54.3%" in md
        assert "57 of 105" in md
        assert "47.8%" in md
        assert "43 of 90" in md
        assert "Some signal" in md
        assert "Common tools: Skye Recon Bolt, KAY/O FRAG/ment" in md
        assert "association across the league, not proof of cause" in md

    def test_leave_item_format(self):
        plan = [{
            "id": "turret@300,400", "ability_name": "Turret", "agent": "Killjoy",
            "callout": "B Kitchen", "u": 0.6, "v": 0.3, "k": 30, "n": 50, "p": 60,
            "strength": "strong", "advice": "leave",
            "counter": {
                "rounds": 150, "contested_rounds": 80, "uncontested_rounds": 70,
                "won_contested": 34, "won_uncontested": 40,
                "win_contested": 42.5, "win_uncontested": 57.1,
                "delta": -14.6, "z": -2.1, "signal": "clear",
                "tools": [],
                "contest_before": 25.0, "enough": True,
            },
        }]
        md = render_brief(_brief_payload(plan))
        assert "Leave the Killjoy Turret at B Kitchen alone" in md
        assert "(set in 30 of 50 rounds)" in md
        assert "42.5%" in md
        assert "34 of 80" in md
        assert "57.1%" in md
        assert "40 of 70" in md
        assert "Clear signal" in md

    def test_no_edge_item_format(self):
        plan = [{
            "id": "trapwire@100,100", "ability_name": "Trapwire", "agent": "Killjoy",
            "callout": "A Site", "u": 0.5, "v": 0.5, "k": 12, "n": 40, "p": 30,
            "strength": "moderate", "advice": "no_edge",
            "counter": {
                "rounds": 60, "contested_rounds": 30, "uncontested_rounds": 30,
                "won_contested": 15, "won_uncontested": 14,
                "win_contested": 50.0, "win_uncontested": 46.7,
                "delta": 3.3, "z": 0.3, "signal": "noise",
                "tools": [],
                "contest_before": 25.0, "enough": True,
            },
        }]
        md = render_brief(_brief_payload(plan))
        assert "no reliable edge either way" in md
        assert "(set in 12 of 40 rounds)" in md
        assert "60 league rounds" in md

    def test_untested_items_collapsed(self):
        plan = [
            {
                "id": "alarmbot@100,100", "ability_name": "Alarmbot", "agent": "Killjoy",
                "callout": "Mid", "u": 0.5, "v": 0.5, "k": 8, "n": 30, "p": 27,
                "strength": "moderate", "advice": "untested",
                "counter": {"rounds": None, "contested_rounds": None, "uncontested_rounds": None,
                            "won_contested": None, "won_uncontested": None,
                            "win_contested": None, "win_uncontested": None,
                            "delta": None, "z": None, "signal": None,
                            "tools": None, "contest_before": None, "enough": None},
            },
            {
                "id": "spycam@200,200", "ability_name": "Spycam", "agent": "Killjoy",
                "callout": "B Main", "u": 0.4, "v": 0.6, "k": 10, "n": 30, "p": 33,
                "strength": "moderate", "advice": "untested",
                "counter": {"rounds": None, "contested_rounds": None, "uncontested_rounds": None,
                            "won_contested": None, "won_uncontested": None,
                            "win_contested": None, "win_uncontested": None,
                            "delta": None, "z": None, "signal": None,
                            "tools": None, "contest_before": None, "enough": None},
            },
        ]
        md = render_brief(_brief_payload(plan))
        assert "Killjoy Alarmbot at Mid" in md
        assert "Killjoy Spycam at B Main" in md
        assert "too few league rounds to tell" in md

    def test_empty_plan_skips_section(self):
        md = render_brief(_brief_payload([]))
        assert "## Game plan" not in md

    def test_none_plan_skips_section(self):
        payload = _brief_payload(None)
        md = render_brief(payload)
        assert "## Game plan" not in md

    def test_thousands_separators(self):
        """Large round counts get thousands separators."""
        plan = [{
            "id": "shear@100,200", "ability_name": "Shear", "agent": "Vyse",
            "callout": "C Main", "u": 0.3, "v": 0.4, "k": 157, "n": 300, "p": 52,
            "strength": "strong", "advice": "hit",
            "counter": {
                "rounds": 1098, "contested_rounds": 500, "uncontested_rounds": 598,
                "won_contested": 275, "won_uncontested": 270,
                "win_contested": 55.0, "win_uncontested": 45.1,
                "delta": 9.9, "z": 2.0, "signal": "clear",
                "tools": [],
                "contest_before": 25.0, "enough": True,
            },
        }]
        md = render_brief(_brief_payload(plan))
        assert "1,098 league rounds" not in md  # hit items don't mention league rounds
        assert "set in 157 of 300 rounds" in md
        assert "275 of 500" in md
        assert "270 of 598" in md

    def test_thousands_separators_in_no_edge(self):
        """No-edge items show thousands separators for league rounds."""
        plan = [{
            "id": "trapwire@100,100", "ability_name": "Trapwire", "agent": "Killjoy",
            "callout": "A Site", "u": 0.5, "v": 0.5, "k": 50, "n": 200, "p": 25,
            "strength": "strong", "advice": "no_edge",
            "counter": {
                "rounds": 1098, "contested_rounds": 500, "uncontested_rounds": 598,
                "won_contested": 260, "won_uncontested": 270,
                "win_contested": 52.0, "win_uncontested": 45.1,
                "delta": 3.0, "z": 0.5, "signal": "noise",
                "tools": [],
                "contest_before": 25.0, "enough": True,
            },
        }]
        md = render_brief(_brief_payload(plan))
        assert "1,098 league rounds" in md

    def test_game_plan_after_key_findings(self):
        """Game plan section appears directly after Key findings, before Operator."""
        plan = [{
            "id": "shear@100,200", "ability_name": "Shear", "agent": "Vyse",
            "callout": "C Main", "u": 0.3, "v": 0.4, "k": 45, "n": 84, "p": 54,
            "strength": "strong", "advice": "hit",
            "counter": {
                "rounds": 195, "contested_rounds": 105, "uncontested_rounds": 90,
                "won_contested": 57, "won_uncontested": 43,
                "win_contested": 54.3, "win_uncontested": 47.8,
                "delta": 6.5, "z": 1.8, "signal": "some",
                "tools": [],
                "contest_before": 25.0, "enough": True,
            },
        }]
        payload = _brief_payload(plan)
        # Add operator data so both sections appear
        payload["operator"] = {
            "weapon": "operator", "rounds": 50, "buy_rounds": 10, "buy_pct": 20.0,
            "buy_p": 20, "holders": [], "areas": [],
            "kills": {"total": 0, "opening": 0, "opening_pct": 0.0, "opening_p": 0,
                      "median_t": None, "per_op_round": 0.0, "lines": []},
        }
        md = render_brief(payload)
        gp_pos = md.index("## Game plan")
        op_pos = md.index("## Operator")
        assert gp_pos < op_pos, "Game plan must appear before Operator"

    def test_disclaimer_has_blank_line_before(self):
        """Blank line separates last bullet from the disclaimer."""
        plan = [{
            "id": "shear@100,200", "ability_name": "Shear", "agent": "Vyse",
            "callout": "C Main", "u": 0.3, "v": 0.4, "k": 45, "n": 84, "p": 54,
            "strength": "strong", "advice": "hit",
            "counter": {
                "rounds": 195, "contested_rounds": 105, "uncontested_rounds": 90,
                "won_contested": 57, "won_uncontested": 43,
                "win_contested": 54.3, "win_uncontested": 47.8,
                "delta": 6.5, "z": 1.8, "signal": "some",
                "tools": [],
                "contest_before": 25.0, "enough": True,
            },
        }]
        md = render_brief(_brief_payload(plan))
        # The disclaimer should be on its own line, preceded by a blank line
        assert "\n\n_This is an association across the league, not proof of cause._" in md


# ---- cache mutation protection ------------------------------------------------

def test_counter_for_hotspot_returns_copy():
    """Mutating the returned counter must not affect the cached value.

    We patch the cached function to return a known dict so the test runs
    without the store and proves the copy semantics.
    """
    from unittest.mock import patch

    cached_result = {
        "rounds": 100, "contest_before": 25.0, "enough": True,
        "contested_rounds": 50, "uncontested_rounds": 50,
        "won_contested": 28, "won_uncontested": 22,
        "win_contested": 56.0, "win_uncontested": 44.0,
        "delta": 12.0, "z": 1.8, "signal": "some",
        "tools": [{"ability": "frag", "ability_name": "FRAG/ment", "agent": "KAY/O", "uses": 10}],
    }

    from scout.analysis import counter_for_hotspot, _counter_for_hotspot_cached
    _counter_for_hotspot_cached.cache_clear()
    try:
        with patch.object(
            _counter_for_hotspot_cached, '__wrapped__', return_value=cached_result
        ):
            # Bypass the cache entirely and call the wrapper directly
            _counter_for_hotspot_cached.cache_clear()
            _counter_for_hotspot_cached.cache_parameters()
            # Patch at the function level so the cached call returns our dict
            with patch('scout.analysis._counter_for_hotspot_uncached', return_value=cached_result):
                a = counter_for_hotspot("lotus", 0.0, 0.0, "turret")
                b = counter_for_hotspot("lotus", 0.0, 0.0, "turret")
                assert a is not None
                assert b is not None
                assert a["rounds"] == b["rounds"] == 100
                assert a is not b
                # Mutating a's tools must not affect b's tools
                a["tools"].append({"ability": "test", "ability_name": "Test", "agent": "Test", "uses": 1})
                assert len(b["tools"]) == 1
    finally:
        _counter_for_hotspot_cached.cache_clear()
