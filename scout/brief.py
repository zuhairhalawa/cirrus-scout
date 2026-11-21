"""Scouting brief: turn a scouting payload into a Markdown document a coach can paste into a prep note.

Every number comes from the payload returned by ``scout.server.scout_payload``.
This module never recomputes a statistic — it only formats what it receives.
"""
from __future__ import annotations

import difflib
import datetime as dt
import sys

from . import analysis as A


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_brief(team: str, map_name: str, side: str, period: str = "recent") -> str:
    """Fetch a scouting payload and render it as a Markdown brief.

    *``team``* may be a team id or a display name (case-insensitive).
    *``period``* is ``"recent"`` (last 6 months) or ``"all"``.
    Raises ``SystemExit`` on invalid input so the CLI can print a clean error.
    """
    st = A.store()

    # --- resolve team (accept id or name, case-insensitive) -----------------
    team_key = team.strip()
    resolved_id: str | None = None

    # exact id match (team_id maps id-string -> int index)
    if team_key in st.team_id:
        resolved_id = team_key
    else:
        # case-insensitive name match
        lower = team_key.lower()
        for tid in st.teams:
            display = st.team_name(st.team_id[tid]).lower()
            if display == lower:
                resolved_id = tid
                break

    if resolved_id is None:
        # Suggest closest team names instead of printing all of them
        all_names = [st.team_name(st.team_id[t]) for t in st.teams]
        close = difflib.get_close_matches(team_key, all_names, n=3, cutoff=0.3)
        if close:
            suggestions = ", ".join(close)
            raise SystemExit(
                f"Unknown team: {team_key!r}. Did you mean: {suggestions}?\n"
                f"Pass one of these names, or a team id, to --team."
            )
        else:
            raise SystemExit(
                f"Unknown team: {team_key!r}. No similar team names found.\n"
                f"Check the team list in the app or run 'python -m scout serve' to browse teams."
            )

    # --- resolve map --------------------------------------------------------
    map_lower = map_name.lower()
    resolved_map: str | None = None
    for m in st.maps:
        if m.lower() == map_lower:
            resolved_map = m
            break
    if resolved_map is None:
        valid_maps = ", ".join(st.maps)
        raise SystemExit(
            f"Unknown map: {map_name!r}. Valid maps: {valid_maps}"
        )

    # --- resolve side -------------------------------------------------------
    side_lower = side.lower()
    if side_lower not in A.SIDE_ID:
        raise SystemExit(
            f"Unknown side: {side!r}. Valid sides: attack, defense"
        )

    # --- since value for "recent" period ------------------------------------
    # Match the app exactly: 183 days before the team's last_played date.
    since: str | None = None
    period_label: str = "All matches"
    if period == "recent":
        period_label = "Last 6 months"
        team_int = st.team_id[resolved_id]
        since = _recent_since(team_int)

    # --- fetch payload ------------------------------------------------------
    from .server import scout_payload
    payload = scout_payload(resolved_id, resolved_map, side_lower, since, phase="all")
    # Keep the original date range, then overlay the period label
    payload["sample"]["date_range"] = payload["sample"].get("range_label", "")
    payload["sample"]["range_label"] = period_label
    return render_brief(payload)


def render_brief(payload: dict) -> str:
    """Pure function: payload dict → Markdown string.

    The payload has the shape returned by ``scout.server.scout_payload``:
    ``sample``, ``utility``, ``operator``, ``setup``, ``insights``, ``team``.
    """
    lines: list[str] = []
    sample = payload.get("sample", {})
    team = payload.get("team", {})
    utility = payload.get("utility", {})
    operator = payload.get("operator", {})
    setup = payload.get("setup")
    insights = payload.get("insights") or []

    team_name = team.get("name", "Unknown")
    map_name = utility.get("map", "").capitalize()
    side_word = utility.get("side", "defense")
    n_rounds = sample.get("rounds", 0)
    n_maps = sample.get("maps", 0)
    range_label = sample.get("range_label", "")
    date_range = sample.get("date_range", "")

    # 1. Title
    lines.append(f"# {team_name} — {map_name} ({side_word})")
    lines.append("")
    if date_range:
        lines.append(f"**Sample:** {n_rounds} rounds across {n_maps} maps ({range_label}, {date_range})")
    else:
        lines.append(f"**Sample:** {n_rounds} rounds across {n_maps} maps ({range_label})")
    lines.append("")

    # 2. Key findings — always label evidence strength
    if insights:
        lines.append("## Key findings")
        lines.append("")
        for f in insights:
            strength_label = f.get("strength", "thin")
            k = f["k"]
            n = f["n"]
            unit = f.get("unit", "rounds")
            # the app's unit reads "of defense rounds"; the count already supplies the "of"
            if unit.startswith("of "):
                unit = unit[3:]
            bullet = f"- **{f['title']}** — {k} of {n} {unit}, {strength_label} evidence"
            lines.append(bullet)
        lines.append("")

    # 3. Utility hotspots — filtered and ranked
    hotspots = utility.get("hotspots", [])
    global_abilities = utility.get("global", [])
    if hotspots or global_abilities:
        lines.append("## Utility")
        lines.append("")

        # Separate strong/moderate from thin
        strong_mod = [h for h in hotspots if h.get("strength") in ("strong", "moderate")]
        thin = [h for h in hotspots if h.get("strength") not in ("strong", "moderate")]

        if strong_mod:
            # Sort by usage (k descending), limit to 12
            strong_mod.sort(key=lambda h: -h["k"])
            shown = strong_mod[:12]
            omitted = len(strong_mod) + len(thin) - len(shown)
            for h in shown:
                _append_hotspot_line(lines, h)
            if omitted > 0:
                lines.append(f"- *{omitted} less frequent spots omitted*")
        else:
            # No strong/moderate spots — show top 5 thin ones
            thin.sort(key=lambda h: -h["k"])
            top5 = thin[:5]
            omitted = len(thin) - len(top5)
            for h in top5:
                line = _hotspot_base(h) + " *(thin evidence)*"
                lines.append(line)
            if omitted > 0:
                lines.append(f"- *{omitted} less frequent spots omitted*")

        # Global abilities (smokes placed from tactical map)
        for g in global_abilities:
            ability_name = g.get("ability_name", "?")
            agent = g.get("agent", "")
            gk = g["k"]
            gn = g["n"]
            lines.append(f"- **{agent} {ability_name}** (map-targeted) — {gk} of {gn} rounds")

        lines.append("")

    # 3a. Game plan — directly after key findings
    plan = payload.get("plan") or []
    if plan:
        lines.append("## Game plan")
        lines.append("")
        _append_game_plan(lines, plan)
        lines.append("")

    # 4. Operator
    op_rounds = operator.get("rounds", 0)
    if op_rounds > 0:
        lines.append("## Operator")
        lines.append("")
        buy_rounds = operator.get("buy_rounds", 0)
        buy_p = operator.get("buy_p", 0)
        lines.append(f"- **Buy rate:** {buy_p}% ({buy_rounds} of {op_rounds} rounds)")

        if buy_rounds == 0:
            lines.append(f"- No Operator was bought in {op_rounds} rounds.")
            lines.append("")
        else:
            holders = operator.get("holders", [])
            if holders:
                primary = holders[0]
                primary_rounds = primary.get("rounds", 0)
                lines.append(
                    f"- **Primary holder:** {primary['player']} "
                    f"({primary['p']}% of Operator rounds, {primary_rounds} rounds)"
                )

            areas = operator.get("areas", [])
            # Only list areas with open_k > 0, ordered by open_k, include style
            open_areas = [a for a in areas if a.get("open_k", 0) > 0]
            if open_areas:
                open_areas.sort(key=lambda a: -a["open_k"])
                lines.append("- **Opening areas:**")
                for a in open_areas[:3]:
                    open_k = a["open_k"]
                    open_n = a["open_n"]
                    callout = a.get("callout", "?")
                    style = a.get("style", "")
                    style_text = f" ({style})" if style else ""
                    lines.append(f"  - {callout}{style_text}: {open_k} of {open_n} Operator rounds")

            kills = operator.get("kills", {})
            total_kills = kills.get("total", 0)
            opening_kills = kills.get("opening", 0)
            if total_kills > 0:
                lines.append(
                    f"- **Opening picks:** {opening_kills} of {total_kills} Operator kills"
                )

            lines.append("")

    # 5. Setup fingerprint
    if setup and setup.get("setups"):
        lines.append("## Setup")
        lines.append("")
        top = setup["setups"][0]
        # Name the agent with each ability
        spots_desc = " + ".join(
            f"{s['agent']} {s['ability_name']} at {s['callout']}" for s in top.get("spots", [])[:3]
        )
        k = top["k"]
        n = top["n"]
        lines.append(f"- **Recurring setup:** {spots_desc} — {k} of {n} rounds")

        predictability = setup.get("predictability")
        if predictability is not None:
            lines.append(
                f"- **Predictability:** {predictability}% of trap and cam placements "
                f"land on a reused spot"
            )
        lines.append("")

    # 6. Methodology note — plain filename, not a Markdown link
    lines.append("---")
    lines.append("")
    lines.append(
        "_Numbers are defined in docs/METHODOLOGY.md. "
        "Spot shares use a 4.5 m radius around the cluster centre. "
        "Evidence strength uses a Wilson interval (z=1.64)._"
    )

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def _recent_since(team: int) -> str | None:
    """Return the date string 183 days before the team's last_played date.

    Matches the app's ``sinceFor`` function exactly.
    Returns ``None`` if last_played cannot be resolved.
    """
    idx = A.teams_index()
    st = A.store()
    team_id_str = st.teams[team]
    for row in idx:
        if row["id"] == team_id_str:
            last_played = row["last_played"]
            try:
                from_date = dt.date.fromisoformat(last_played[:10])
            except ValueError:
                return None
            cutoff = (from_date - dt.timedelta(days=183)).isoformat()
            return cutoff
    return None


def _hotspot_base(h: dict) -> str:
    """Build one Utility bullet line for a hotspot."""
    ability_name = h.get("ability_name", h.get("ability", "?"))
    agent = h.get("agent", "")
    callout = h.get("callout", "?")
    k = h["k"]
    n = h["n"]
    players = h.get("players", [])
    who = players[0]["name"] if players else ""
    when = h.get("when", "")
    line = f"- **{agent} {ability_name}** at {callout} — {k} of {n} rounds"
    if who:
        line += f", placed by {who}"
    if when:
        line += f", {when}"
    return line


def _append_hotspot_line(lines: list[str], h: dict) -> None:
    """Append a hotspot line with strength label."""
    strength_label = h.get("strength", "thin")
    line = _hotspot_base(h)
    if strength_label == "thin":
        line += " *(thin evidence)*"
    lines.append(line)


def _signal_word(signal: str | None) -> str:
    """Plain-language signal label."""
    if signal == "clear":
        return "Clear signal"
    if signal == "some":
        return "Some signal"
    return "Within noise"


def _fmt_n(n: int | None) -> str:
    """Format an integer with thousands separators."""
    if n is None:
        return ""
    return f"{n:,}"


def _append_game_plan(lines: list[str], plan: list[dict]) -> None:
    """Append the Game plan section, one line per item."""
    hit_items = [p for p in plan if p["advice"] == "hit"]
    leave_items = [p for p in plan if p["advice"] == "leave"]
    no_edge_items = [p for p in plan if p["advice"] == "no_edge"]
    untested_items = [p for p in plan if p["advice"] == "untested"]

    for item in hit_items:
        c = item["counter"]
        ability_name = item["ability_name"]
        agent = item["agent"]
        callout = item["callout"]
        k = item["k"]
        n = item["n"]
        won_c = c.get("won_contested")
        n_c = c.get("contested_rounds")
        won_u = c.get("won_uncontested")
        n_u = c.get("uncontested_rounds")
        win_c = c.get("win_contested")
        win_u = c.get("win_uncontested")
        signal = c.get("signal")
        tools = c.get("tools")
        line = (f"- Hit the {agent} {ability_name} at {callout} early "
                f"(set in {_fmt_n(k)} of {_fmt_n(n)} rounds): "
                f"attackers won {win_c}% ({won_c} of {_fmt_n(n_c)}) when they did, "
                f"{win_u}% ({won_u} of {_fmt_n(n_u)}) when they left it. "
                f"{_signal_word(signal)}.")
        if tools:
            tool_names = ", ".join(f"{t['agent']} {t['ability_name']}" for t in tools[:3])
            line += f" Common tools: {tool_names}."
        lines.append(line)

    for item in leave_items:
        c = item["counter"]
        ability_name = item["ability_name"]
        agent = item["agent"]
        callout = item["callout"]
        k = item["k"]
        n = item["n"]
        won_c = c.get("won_contested")
        n_c = c.get("contested_rounds")
        won_u = c.get("won_uncontested")
        n_u = c.get("uncontested_rounds")
        win_c = c.get("win_contested")
        win_u = c.get("win_uncontested")
        signal = c.get("signal")
        line = (f"- Leave the {agent} {ability_name} at {callout} alone "
                f"(set in {_fmt_n(k)} of {_fmt_n(n)} rounds): "
                f"attackers won {win_c}% ({won_c} of {_fmt_n(n_c)}) when they hit it early, "
                f"{win_u}% ({won_u} of {_fmt_n(n_u)}) when they didn't. "
                f"{_signal_word(signal)}.")
        lines.append(line)

    for item in no_edge_items:
        c = item["counter"]
        ability_name = item["ability_name"]
        agent = item["agent"]
        callout = item["callout"]
        k = item["k"]
        n = item["n"]
        rounds = c.get("rounds")
        lines.append(
            f"- {agent} {ability_name} at {callout} (set in {_fmt_n(k)} of {_fmt_n(n)} rounds): "
            f"no reliable edge either way ({_fmt_n(rounds)} league rounds)."
        )

    if untested_items:
        spots = ", ".join(
            f"{it['agent']} {it['ability_name']} at {it['callout']}" for it in untested_items
        )
        lines.append(f"- {spots}: too few league rounds to tell.")

    # Blank line before the closing disclaimer so Markdown does not glue it to the last bullet
    lines.append("")
    lines.append(
        "_This is an association across the league, not proof of cause._"
    )
