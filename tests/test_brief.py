"""Tests for scout/brief.py.

Unit tests for ``render_brief`` use hand-written payloads with invented names
and numbers so no licensed data is copied into the repository.
One data-integrity test needs the built store and is skipped when it is missing.
"""
import datetime as dt
import re

import pytest

from scout.config import STORE_PATH

pytestmark_data = pytest.mark.skipif(
    not STORE_PATH.exists(),
    reason="needs a built store (python -m scout build)",
)

from scout.brief import render_brief, _recent_since  # noqa: E402


# ---------------------------------------------------------------------------
# Helper: build a minimal payload dict
# ---------------------------------------------------------------------------

def _payload(
    team_name="Echo",
    map_name="icebox",
    side="defense",
    rounds=50,
    maps=8,
    range_label="Last 6 months",
    insights=None,
    hotspots=None,
    operator=None,
    setup=None,
    global_abilities=None,
):
    return {
        "team": {"id": "echo-1", "name": team_name},
        "sample": {
            "rounds": rounds,
            "maps": maps,
            "range_label": range_label,
        },
        "utility": {
            "map": map_name,
            "side": side,
            "rounds": rounds,
            "hotspots": hotspots or [],
            "global": global_abilities or [],
        },
        "operator": operator or {
            "weapon": "operator",
            "rounds": 0,
            "buy_rounds": 0,
            "buy_pct": 0.0,
            "buy_p": 0,
            "holders": [],
            "areas": [],
            "kills": {"total": 0, "opening": 0, "opening_pct": 0.0, "opening_p": 0, "median_t": None, "per_op_round": 0.0, "lines": []},
        },
        "setup": setup,
        "insights": insights or [],
    }


# ---------------------------------------------------------------------------
# Unit tests — render_brief (pure, no data)
# ---------------------------------------------------------------------------

class TestRenderBrief:
    """render_brief with hand-written payloads."""

    def test_normal_payload_contains_all_sections(self):
        payload = _payload(
            insights=[
                {
                    "kind": "utility",
                    "title": "Killjoy Turret at B Kitchen",
                    "sub": "30 of 50 defense rounds",
                    "k": 30,
                    "n": 50,
                    "unit": "of defense rounds",
                    "strength": "strong",
                    "text": "...",
                    "detail": "...",
                    "evidence": [1, 2, 3],
                }
            ],
            hotspots=[
                {
                    "ability_name": "Turret",
                    "agent": "Killjoy",
                    "callout": "B Kitchen",
                    "k": 30,
                    "n": 50,
                    "strength": "strong",
                    "players": [{"name": "Vexa", "casts": 28}],
                    "when": "buy phase",
                }
            ],
            operator={
                "weapon": "operator",
                "rounds": 50,
                "buy_rounds": 20,
                "buy_pct": 40.0,
                "buy_p": 40,
                "holders": [{"player": "Orin", "rounds": 18, "share": 90.0, "p": 90}],
                "areas": [
                    {
                        "callout": "A Site",
                        "k": 15,
                        "n": 20,
                        "open_k": 12,
                        "open_n": 18,
                        "style": "aggressive",
                    }
                ],
                "kills": {
                    "total": 10,
                    "opening": 4,
                    "opening_pct": 40.0,
                    "opening_p": 40,
                    "median_t": 8.5,
                    "per_op_round": 0.5,
                    "lines": [],
                },
            },
            setup={
                "rounds": 50,
                "setup_casts": 40,
                "predictability": 65,
                "recurring": [],
                "setups": [
                    {
                        "k": 18,
                        "n": 50,
                        "pct": 36.0,
                        "p": 36,
                        "strength": "moderate",
                        "spots": [
                            {"ability_name": "Turret", "agent": "Killjoy", "callout": "B Kitchen"},
                            {"ability_name": "FRAG/ment", "agent": "KAY/O", "callout": "A Main"},
                        ],
                        "evidence": [1, 2, 3],
                    }
                ],
            },
        )
        md = render_brief(payload)

        # Title
        assert "# Echo — Icebox (defense)" in md
        assert "**Sample:** 50 rounds across 8 maps (Last 6 months)" in md

        # Key findings — k of n format, strength at end
        assert "## Key findings" in md
        assert "**Killjoy Turret at B Kitchen** — 30 of 50 defense rounds, strong evidence" in md

        # Utility
        assert "## Utility" in md
        assert "**Killjoy Turret** at B Kitchen — 30 of 50 rounds" in md
        assert "placed by Vexa" in md
        assert "buy phase" in md

        # Operator
        assert "## Operator" in md
        assert "**Buy rate:** 40% (20 of 50 rounds)" in md
        assert "**Primary holder:** Orin (90% of Operator rounds, 18 rounds)" in md
        assert "A Site (aggressive): 12 of 18 Operator rounds" in md
        assert "**Opening picks:** 4 of 10 Operator kills" in md

        # Setup — agent names included
        assert "## Setup" in md
        assert "Killjoy Turret at B Kitchen + KAY/O FRAG/ment at A Main" in md
        assert "18 of 50 rounds" in md
        assert "65% of trap and cam placements" in md

        # Methodology — plain text, not a Markdown link
        assert "docs/METHODOLOGY.md" in md
        assert "[docs/METHODOLOGY.md](docs/METHODOLOGY.md)" not in md

    def test_no_operator_rounds_skips_operator_section(self):
        payload = _payload(
            operator={
                "weapon": "operator",
                "rounds": 0,
                "buy_rounds": 0,
                "buy_pct": 0.0,
                "buy_p": 0,
                "holders": [],
                "areas": [],
                "kills": {"total": 0, "opening": 0, "opening_pct": 0.0, "opening_p": 0, "median_t": None, "per_op_round": 0.0, "lines": []},
            }
        )
        md = render_brief(payload)
        assert "## Operator" not in md

    def test_operator_no_buy_rounds_shows_message(self):
        """When buy_rounds is 0 but rounds > 0, show a useful message."""
        payload = _payload(
            rounds=30,
            operator={
                "weapon": "operator",
                "rounds": 30,
                "buy_rounds": 0,
                "buy_pct": 0.0,
                "buy_p": 0,
                "holders": [],
                "areas": [],
                "kills": {"total": 0, "opening": 0, "opening_pct": 0.0, "opening_p": 0, "median_t": None, "per_op_round": 0.0, "lines": []},
            }
        )
        md = render_brief(payload)
        assert "## Operator" in md
        assert "No Operator was bought in 30 rounds" in md

    def test_all_findings_labelled_with_strength(self):
        """Every finding must end with plain strength words: *strong evidence*, etc."""
        payload = _payload(
            insights=[
                {
                    "kind": "utility",
                    "title": "Strong Finding",
                    "k": 30,
                    "n": 50,
                    "unit": "of defense rounds",
                    "strength": "strong",
                    "text": "...",
                    "detail": "...",
                    "evidence": [],
                },
                {
                    "kind": "utility",
                    "title": "Moderate Finding",
                    "k": 12,
                    "n": 50,
                    "unit": "of defense rounds",
                    "strength": "moderate",
                    "text": "...",
                    "detail": "...",
                    "evidence": [],
                },
                {
                    "kind": "utility",
                    "title": "Thin Finding",
                    "k": 3,
                    "n": 10,
                    "unit": "of defense rounds",
                    "strength": "thin",
                    "text": "...",
                    "detail": "...",
                    "evidence": [],
                },
            ]
        )
        md = render_brief(payload)
        assert ", strong evidence" in md
        assert ", moderate evidence" in md
        assert ", thin evidence" in md
        # Old format must not appear
        assert "(strength:" not in md

    def test_key_findings_include_k_and_n(self):
        """Each Key findings bullet must contain both k and n: 'k of n <unit>'."""
        payload = _payload(
            insights=[
                {
                    "kind": "utility",
                    "title": "Test",
                    "k": 7,
                    "n": 23,
                    "unit": "of defense rounds",
                    "strength": "thin",
                    "text": "...",
                    "detail": "...",
                    "evidence": [],
                }
            ]
        )
        md = render_brief(payload)
        # Reads "7 of 23 defense rounds" — unit starts with "of" but we still include n
        assert "7 of 23 defense rounds" in md

    def test_key_findings_bullets_parse_k_of_n(self):
        """Every Key findings bullet must contain 'k of n' matching the finding fields."""
        payload = _payload(
            insights=[
                {
                    "kind": "utility",
                    "title": "First Finding",
                    "k": 30,
                    "n": 50,
                    "unit": "of defense rounds",
                    "strength": "strong",
                    "text": "...",
                    "detail": "...",
                    "evidence": [],
                },
                {
                    "kind": "utility",
                    "title": "Second Finding",
                    "k": 12,
                    "n": 50,
                    "unit": "of defense rounds",
                    "strength": "moderate",
                    "text": "...",
                    "detail": "...",
                    "evidence": [],
                },
                {
                    "kind": "utility",
                    "title": "Third Finding",
                    "k": 5,
                    "n": 10,
                    "unit": "of attack rounds",
                    "strength": "thin",
                    "text": "...",
                    "detail": "...",
                    "evidence": [],
                },
            ]
        )
        md = render_brief(payload)
        # Each bullet must contain "k of n"
        assert "30 of 50" in md
        assert "12 of 50" in md
        assert "5 of 10" in md
        # Verify by parsing: extract all "k of n" pairs from Key findings bullets
        findings_section = md.split("## Key findings")[1].split("## ")[0] if "## Key findings" in md else ""
        pairs = re.findall(r"(\d+) of (\d+)", findings_section)
        assert len(pairs) >= 3
        assert ("30", "50") in pairs
        assert ("12", "50") in pairs
        assert ("5", "10") in pairs

    def test_title_includes_date_range(self):
        """Title block must show both period label and date range."""
        payload = _payload(
            range_label="Last 6 months",
            insights=[],
        )
        # Simulate what build_brief does: add date_range
        payload["sample"]["date_range"] = "15 May – 20 Nov 2026"
        md = render_brief(payload)
        assert "Last 6 months" in md
        assert "15 May – 20 Nov 2026" in md
        assert "(Last 6 months, 15 May – 20 Nov 2026)" in md

    def test_utility_filters_to_strong_moderate(self):
        """Only strong/moderate spots are listed, up to 12, with omission count."""
        hotspots = [
            {"ability_name": "Turret", "agent": "Killjoy", "callout": f"Spot{i}", "k": 30 - i, "n": 50, "strength": "strong", "players": [], "when": ""}
            for i in range(15)
        ] + [
            {"ability_name": "FRAG/ment", "agent": "KAY/O", "callout": f"Thin{i}", "k": 3, "n": 50, "strength": "thin", "players": [], "when": ""}
            for i in range(5)
        ]
        payload = _payload(hotspots=hotspots)
        md = render_brief(payload)
        # Should show 12 strong spots
        assert "Spot0" in md
        assert "Spot11" in md
        # Spot12, Spot13 should be omitted (beyond 12)
        assert "Spot12" not in md
        # Omission line: 3 strong + 5 thin = 8 omitted
        assert "8 less frequent spots omitted" in md

    def test_utility_thin_only_shows_top5(self):
        """When no strong/moderate spots, show top 5 thin ones."""
        hotspots = [
            {"ability_name": "FRAG/ment", "agent": "KAY/O", "callout": f"Thin{i}", "k": 10 - i, "n": 50, "strength": "thin", "players": [], "when": ""}
            for i in range(8)
        ]
        payload = _payload(hotspots=hotspots)
        md = render_brief(payload)
        assert "Thin0" in md
        assert "Thin4" in md
        assert "Thin5" not in md
        assert "3 less frequent spots omitted" in md
        # Thin spots should be labelled
        assert "*(thin evidence)*" in md

    def test_global_abilities_shown(self):
        """Global abilities (map-targeted smokes) should appear in Utility."""
        payload = _payload(
            hotspots=[],
            global_abilities=[
                {"ability_name": "Smoke", "agent": "Brimstone", "k": 15, "n": 50, "pct": 30.0, "p": 30, "per_round": 1.2, "first_t": -5.0}
            ]
        )
        md = render_brief(payload)
        assert "## Utility" in md
        assert "**Brimstone Smoke** (map-targeted) — 15 of 50 rounds" in md

    def test_operator_opening_areas_only(self):
        """Only areas with open_k > 0 are listed; areas with open_k=0 are skipped."""
        payload = _payload(
            operator={
                "weapon": "operator",
                "rounds": 30,
                "buy_rounds": 10,
                "buy_pct": 33.3,
                "buy_p": 33,
                "holders": [{"player": "X", "rounds": 8, "share": 80.0, "p": 80}],
                "areas": [
                    {"callout": "A Site", "k": 6, "n": 10, "open_k": 5, "open_n": 8, "style": "aggressive"},
                    {"callout": "Mid", "k": 4, "n": 10, "open_k": 0, "open_n": 5, "style": "passive"},
                ],
                "kills": {"total": 3, "opening": 1, "opening_pct": 33.3, "opening_p": 33, "median_t": None, "per_op_round": 0.3, "lines": []},
            }
        )
        md = render_brief(payload)
        assert "A Site (aggressive): 5 of 8 Operator rounds" in md
        # Mid should NOT appear (open_k = 0)
        assert "Mid" not in md

    def test_operator_opening_picks(self):
        """Opening picks should use the payload's opening/total, not 'median kill'."""
        payload = _payload(
            operator={
                "weapon": "operator",
                "rounds": 30,
                "buy_rounds": 10,
                "buy_pct": 33.3,
                "buy_p": 33,
                "holders": [{"player": "X", "rounds": 8, "share": 80.0, "p": 80}],
                "areas": [],
                "kills": {"total": 5, "opening": 2, "opening_pct": 40.0, "opening_p": 40, "median_t": 12.0, "per_op_round": 0.5, "lines": []},
            }
        )
        md = render_brief(payload)
        assert "**Opening picks:** 2 of 5 Operator kills" in md
        # Should NOT contain "median kill"
        assert "median kill" not in md

    def test_setup_includes_agent_names(self):
        """Setup spots should include agent names."""
        payload = _payload(
            setup={
                "rounds": 50,
                "setup_casts": 40,
                "predictability": 65,
                "recurring": [],
                "setups": [
                    {
                        "k": 18,
                        "n": 50,
                        "pct": 36.0,
                        "p": 36,
                        "strength": "moderate",
                        "spots": [
                            {"ability_name": "Turret", "agent": "Killjoy", "callout": "B Kitchen"},
                        ],
                        "evidence": [1, 2, 3],
                    }
                ],
            }
        )
        md = render_brief(payload)
        assert "Killjoy Turret at B Kitchen" in md

    def test_k_of_n_matches_payload(self):
        """Every 'k of n' in the output must match the payload numbers."""
        payload = _payload(
            insights=[
                {
                    "kind": "utility",
                    "title": "Test Finding",
                    "sub": "7 of 23 rounds",
                    "k": 7,
                    "n": 23,
                    "unit": "of defense rounds",
                    "strength": "thin",
                    "text": "...",
                    "detail": "...",
                    "evidence": [],
                }
            ],
            hotspots=[
                {
                    "ability_name": "FRAG/ment",
                    "agent": "KAY/O",
                    "callout": "A Main",
                    "k": 7,
                    "n": 23,
                    "strength": "thin",
                    "players": [{"name": "player1", "casts": 5}],
                    "when": "buy phase",
                }
            ],
            operator={
                "weapon": "operator",
                "rounds": 23,
                "buy_rounds": 9,
                "buy_pct": 39.1,
                "buy_p": 39,
                "holders": [{"player": "player1", "rounds": 7, "share": 77.8, "p": 78}],
                "areas": [
                    {"callout": "A Site", "k": 5, "n": 9, "open_k": 4, "open_n": 7, "style": "on-site"}
                ],
                "kills": {"total": 3, "opening": 1, "opening_pct": 33.3, "opening_p": 33, "median_t": 12.0, "per_op_round": 0.33, "lines": []},
            },
            setup={
                "rounds": 23,
                "setup_casts": 20,
                "predictability": 52,
                "recurring": [],
                "setups": [
                    {
                        "k": 6,
                        "n": 23,
                        "pct": 26.1,
                        "p": 26,
                        "strength": "thin",
                        "spots": [{"ability_name": "Turret", "agent": "Killjoy", "callout": "B Kitchen"}],
                        "evidence": [],
                    }
                ],
            },
        )
        md = render_brief(payload)

        # Key findings bullet now includes k of n
        assert "7 of 23 defense rounds" in md
        assert "**KAY/O FRAG/ment** at A Main — 7 of 23 rounds" in md
        assert "9 of 23 rounds" in md
        assert "4 of 7 Operator rounds" in md
        assert "6 of 23 rounds" in md

    def test_empty_payload_produces_title_and_methodology(self):
        payload = _payload(
            team_name="NoData",
            map_name="bind",
            side="attack",
            rounds=0,
            maps=0,
            range_label="",
        )
        md = render_brief(payload)
        assert "# NoData — Bind (attack)" in md
        assert "0 rounds" in md
        assert "docs/METHODOLOGY.md" in md
        # No optional sections
        assert "## Key findings" not in md
        assert "## Utility" not in md
        assert "## Operator" not in md
        assert "## Setup" not in md

    def test_setup_without_setups_list_is_skipped(self):
        payload = _payload(
            setup={
                "rounds": 50,
                "setup_casts": 10,
                "predictability": None,
                "recurring": [],
                "setups": [],
            }
        )
        md = render_brief(payload)
        assert "## Setup" not in md


# ---------------------------------------------------------------------------
# Test _recent_since — needs the built store
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    not STORE_PATH.exists(),
    reason="needs a built store (python -m scout build)",
)
class TestRecentSince:
    """Check that _recent_since computes 183 days before last_played."""

    def test_since_is_183_days_before_last_played(self):
        from scout import analysis as A

        st = A.store()
        idx = A.teams_index()
        # Pick the first team
        row = idx[0]
        team_int = st.team_id[row["id"]]
        since = _recent_since(team_int)
        assert since is not None
        expected = (dt.date.fromisoformat(row["last_played"][:10]) - dt.timedelta(days=183)).isoformat()
        assert since == expected


# ---------------------------------------------------------------------------
# Data integrity test — needs the built store
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    not STORE_PATH.exists(),
    reason="needs a built store (python -m scout build)",
)
class TestBriefDataIntegrity:
    """Checks that the brief counts match the payload counts."""

    def test_key_findings_counts_match_payload(self):
        """Build a brief for a real view and verify every Key findings count
        equals the corresponding finding in scout_payload for the same view."""
        from scout import analysis as A
        from scout.server import scout_payload

        st = A.store()

        # Pick a team that exists in the store
        team_id_str = st.teams[0]
        # Pick a map that exists
        map_name = st.maps[0]

        payload = scout_payload(team_id_str, map_name, "defense", None, phase="all")
        md = render_brief(payload)

        # For every insight in the payload, check the title appears
        for f in payload.get("insights", []):
            assert f["title"] in md, (
                f"Finding title '{f['title']}' not found in brief"
            )

    def test_key_findings_kn_pairs_match_payload(self):
        """Parse (k, n) pairs from Key findings bullets and compare with
        scout_payload['insights'] in order."""
        from scout import analysis as A
        from scout.server import scout_payload

        st = A.store()
        team_id_str = st.teams[0]
        map_name = st.maps[0]

        payload = scout_payload(team_id_str, map_name, "defense", None, phase="all")
        md = render_brief(payload)

        # Extract the Key findings section
        if "## Key findings" not in md:
            # No findings — nothing to check
            assert len(payload.get("insights", [])) == 0
            return

        findings_section = md.split("## Key findings")[1].split("## ")[0]
        # Parse all "k of n" pairs from the findings bullets
        pairs = re.findall(r"(\d+) of (\d+)", findings_section)
        # Compare with payload insights in order
        expected_pairs = [(str(f["k"]), str(f["n"])) for f in payload.get("insights", [])]
        # The first len(expected) pairs from the section should match
        assert pairs[:len(expected_pairs)] == expected_pairs, (
            f"Key findings (k, n) pairs {pairs[:len(expected_pairs)]} "
            f"do not match payload insights {expected_pairs}"
        )

    def test_brief_round_count_matches_payload(self):
        """The round count in the brief title must equal sample.rounds of scout_payload."""
        from scout import analysis as A
        from scout.server import scout_payload

        st = A.store()
        team_id_str = st.teams[0]
        map_name = st.maps[0]

        # With since=None (all matches)
        payload = scout_payload(team_id_str, map_name, "defense", None, phase="all")
        md = render_brief(payload)
        n_rounds = payload["sample"]["rounds"]
        assert f"{n_rounds} rounds" in md
