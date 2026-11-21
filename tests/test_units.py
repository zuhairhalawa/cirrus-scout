"""Unit tests for the pure helpers. These run without the GRID data."""
import numpy as np
import pytest

from scout import analysis as A
from scout.abilities import ABILITIES, CATEGORY_LABELS, SPATIAL, info
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
