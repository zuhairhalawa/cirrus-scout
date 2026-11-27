# Methodology

Cirrus turns the official GRID VALORANT feeds into opponent scouting that a coach can read at a glance, and backs every claim with the rounds it came from. This page explains how each number is produced, how it was checked, and how far it can be trusted.

Every figure on this page was produced by the code in this repository on the data processed on 2026-11-21. `python -m pytest` re-runs the checks described in section 12.

## 1. The data

The source is the official Sky's The Limit 2026 GRID starter data: VCT Americas, Masters Toronto and Game Changers matches from 16 January 2025 to 3 September 2026, plus Cloud9's ability supplement.

| What | Count |
|---|---|
| Series with match data | 856 (of 857 files; GRID invalidated one) |
| Maps analysed | 2,077 |
| Rounds | 42,520 |
| Ability casts | 1,441,804 (99.5% with the supplement's precise position and aim) |
| Kills | 297,105 |
| Position samples of players carrying an Operator, Outlaw, Marshal or Odin | 565,444 |

Everything is read in a single streaming pass per series (`scout/extract.py`). Decompressed, the feeds are about 160 GB, so nothing is ever unpacked to disk. The license forbids redistributing the data, so the GRID clone lives next to the project and is never committed; a pre-commit guard enforces that.

## 2. Turning a feed into rounds

GRID events are replayed in order to rebuild each round:

- **Round timing:** each round's start, the end of the buy phase (round time 0:00), its end, the winner and win type, and the plant position.
- **Sides:** which team attacked and which defended.
- **Loadouts:** each player's primary weapon and armor when the buy phase ends.
- **Utility casts:** ability ids come from GRID. Positions and aim come from the supplement. If a cast has no supplement row, GRID's 2D position is used.
- **Weapon possession:** GRID only sends inventories in occasional full snapshots. So who holds an Operator is tracked as a small state machine: who bought it, drops, pickups and deaths. Holders' positions are then sampled at most every 0.5 s.
- **Rolled-back games:** maps that were abandoned and restarted are removed, as the data README recommends.

Two integrity gates decide what is analysed:

- **Score gate:** a map is used only if the rounds rebuilt from its feed add up to the official score in `meta/games.csv`. One map fails and is left out.
- **Outcome gate:** a round is used only if its result agrees with its sides (a detonation is an attacker win; a defuse or time-out is a defender win). Three rounds fail and are left out.

## 3. The whole buy phase counts, and a re-placed device counts once

Pro rounds often have long buy phases: timeouts, pistol rounds and technical pauses. Setup utility is placed during that time, so every cast from the start of the round is kept. An earlier version cut off casts more than 50 seconds before the round went live, which dropped 28,465 casts and understated setups; an independent recount from the raw files caught it (section 12).

A sentinel can pick a device up and place it again before the round starts. Counting both placements would describe a setup that never existed. So:

1. Each ability's charge count is learned from the data: GRID reports the charges left after every cast.
2. For devices that can be recalled (Trapwire, Spycam, Alarmbot, Turret, Trademark, Shear, Arc Rose, Razorvine, Nanoswarm, Sonic Sensor, Chokehold, Interceptor), only a player's last placements in the buy phase count, up to the charge count.

This marks 9,242 of 128,097 buy-phase placements (7.2%) as superseded. They still appear in round replays, but not in any percentage. The rule is an approximation when a player with two charges recalls only the first; it keeps the last two.

## 4. Map geometry without Riot art

No minimap images are shipped.

- **Floor plans:** each map's floor plan is traced from where players actually stood, including the buy phase so spawns are filled in. Positions are rasterised, pin-holes closed, specks removed, and the outline traced into a vector path.
- **Alignment:** the drawing therefore matches the data by construction, and the walls are the walls players could not walk through.
- **Callouts:** names like "B Kitchen" come from the community valorant-api.com map metadata, which uses the same world coordinates as GRID. This is checked: on every map, each cluster of real plants resolves to the correct site letter and sits within 25 m of that site's callout.
- **Sites:** A, B and C are found by clustering every recorded plant on the map.

## 5. Utility spots

For a team, map and side, casts of the same ability are grouped by greedy density clustering. A spot's share is then defined on its centre, so anyone can recount it:

> rounds in which the team used that ability within 4.5 m of the spot's centre, divided by the rounds sampled.

Each spot also reports when it is used (buy phase or a median round time), who uses it, and how tight it is (the median distance of its casts from the centre).

**What a marker means depends on the ability.** The data has where the player stood and where they aimed. It has no landing points. Abilities are therefore sorted into kinds (`scout/abilities.py`, checked against the public valorant-api.com ability descriptions):

| Kind | Examples | What the marker shows |
|---|---|---|
| Placed | Turret, Alarmbot, Trapwire, Shear | Where the device sits, to within a couple of metres |
| Placed at range | Spycam, Trademark, Arc Rose, Sonic Sensor | Where the player stood, with the aim; the device is further along it |
| Thrown | Recon Bolt, Nanoswarm, flashes | Where it was thrown from, with the aim |
| Wall | Viper's Toxic Screen, Fault Line | Where it starts and its direction |
| Aimed on a tactical map | Brimstone, Omen, Astra and Clove smokes | Not drawn. The caster's position says nothing about where it lands, so these are listed as usage only |

The aim vectors were checked to be in the same frame as positions: among 2,377 casts by fast-moving players, the aim is within 30° of the direction of travel in 56.5% and within 60° in 74%.

**Round phase.** The map can be limited to the setup (buy phase and first 20 seconds), mid-round (after 20 seconds, before the plant) or post-plant.

**Heatmap.** The heat view is a kernel density estimate of cast positions on a 128 × 128 grid. Only the smoothed surface is sent to the browser.

## 6. Operator profiler

- **Buy rate:** rounds that start with an Operator, divided by rounds sampled.
- **Primary holder:** each player's share of the team's Operator rounds.
- **Opening area:** for each Operator round, the one area where its holder spent most of the first 20 seconds. Each round counts once, so these shares never add up to more than 100%. An earlier version counted every area a holder passed through, which overstated all of them.
- **Round time:** for each area, the share of sightings in 0–20 s, 20–40 s and 40 s+.
- **Aggressive or passive:** each position gets a "forwardness" score, from 0 at the defender spawn to 1 at the attacker spawn, and is compared with its nearest plant site. More than 7 points closer to the attackers is called aggressive; more than 5 points deeper is called passive. These thresholds are a judgement, not a measurement.
- **Sightlines:** each Operator kill is drawn from shooter to victim, with opening picks highlighted.

Possession tracking is checked against an independent signal: 94.2% of all Operator kills in the data (8,162 of 8,663) were made by a player the tracker says held it that round.

**Other tracked weapons.** The same profile is run for the Outlaw, Marshal and Odin, and each is reduced to one summary row: rounds that start with it (and the share, with the same evidence strength as any other share), its primary holder, and the area where it opens most often. Only weapons bought in at least one round are listed, most bought first. Every number is read from that weapon's profile; the summary adds no threshold and recomputes nothing.

## 7. Setup fingerprint and predictability

- **Setup:** trap and cam placements still standing when the round goes live, plus any placed in the first 20 seconds.
- **Recurring spot:** a spot the team uses in at least one round in five.
- **Signature:** the set of recurring spots a round used. The most common signatures are the team's setups ("Turret at Mid Boiler: 26 of 51 rounds").
- **Predictability:** the share of setup placements that land on a recurring spot, shown against every team with 15 or more setup placements on the same map.

## 8. Counters tested league-wide

For a defensive spot, Cirrus finds every round in the data, from any team, where a defense used the same ability within 4.5 m during the setup. It then asks whether attackers who contested the spot early won more.

- **Contested:** in the first 25 seconds, an attacker used recon, damage, flash or stall utility whose aim passes within 5.5 m of the spot (within 35 m of range), or used it from within 7 m.
- **Result:** the attack win rate with and without early contact, each with its counts, and the utility used most often.
- **Significance:** a two-proportion z-test, labelled clear (|z| ≥ 1.96), some (|z| ≥ 1.64) or within noise. Fewer than 8 rounds on either side and no comparison is shown.

This is an association across the league, not proof of cause, and the app says so next to every result.

## 9. Game plan

The game plan summarises counters for a team's defense on a map. It considers only trap and sentinel spots with strong or moderate evidence, because those are the setups a team can be expected to repeat. Each spot is classified into exactly one advice value:

| Advice | Condition |
|---|---|
| Hit | The counter has enough rounds in both arms, its signal is "clear" or "some", and the delta (attack win rate when contested minus when left) is positive. |
| Leave | The counter has enough rounds in both arms, its signal is "clear" or "some", and the delta is negative. |
| No edge | The counter has enough rounds in both arms, but its signal is "noise". |
| Untested | The counter does not have enough (fewer than 8 rounds in one arm), or it is `None`. |

Items are ordered: "hit" first by z descending, then "leave" by z ascending, then "no_edge", then "untested"; inside the last two groups, the most-used spot comes first. The game plan is only computed for defense views; attack views return an empty list.

## 10. Evidence strength

Every finding carries a plain-language strength, from the lower bound of a 90% Wilson interval on its share and from its sample size:

| Strength | Rule |
|---|---|
| Strong | 15 or more rounds, and a lower bound of at least 40% |
| Moderate | 8 or more rounds, and a lower bound of at least 20% |
| Thin | Anything else |

Every finding lists its rounds: opponent, date, round number, result, and the UTC time the round went live, to find it in the VOD.

## 11. Position accuracy

Movement is sampled every 0.2 s in 1,762 maps, every 0.1 s in 82, and only once per second in 233 (mostly VCT Americas 2025). The rate is measured per map from the supplement, not assumed from the event name.

Where a view includes once-per-second maps, the app says so and shows how far players moved between samples while placing setup utility, which bounds how far a marker can be off. Spots stay tight in practice: MIBR's turret at B Kitchen has a median spread of 0.5 m across 45 rounds.

## 12. How the numbers were checked

`python -m pytest` runs 97 tests. The ones that need the data are skipped without it.

- **Official scores:** every analysed map reproduces its official score.
- **Outcomes and sides:** detonations are attacker wins; defuses and time-outs are defender wins.
- **Ability catalogue:** all 111 ability ids in the data are catalogued, each with the agent that actually uses it.
- **Callouts:** plant clusters resolve to the right site on every map.
- **Spot shares:** for five team views, every reported spot is recounted cast by cast and must match exactly.
- **Raw recount:** one headline number (MIBR's turret at B Kitchen on Icebox) is rebuilt from the raw GRID feed and supplement by separate code that does not use the extractor, and must match exactly.
- **Operator:** possession agrees with kills; opening areas count each round once; every row of the other-weapons summary equals the fields of that weapon's profile.
- **Counters:** the two arms add up to the total.
- **Rounding:** a finding, its map marker and its list row always show the same whole percentage.
- **Subtitles:** the demo video's captions reproduce the narration exactly, in order.
- **Game plan:** every plan item's counter matches `counter_for_hotspot` for that spot, and every advice value follows the classification rules. Attack views have an empty plan.

## 13. Known limits

- **No landing points.** Thrown utility shows origin and aim only.
- **Recall rule.** With two charges, a player who recalls only their first placement is treated as keeping the last two.
- **Style thresholds.** "Aggressive" and "passive" rest on chosen thresholds.
- **Counters are observational.** Teams that contest a spot early may differ in other ways.
- **Replay resolution.** Replays use the positions GRID sends with each game event. In a sample of rounds a player's position updated a median 1.2 s apart, with gaps of several seconds in quiet stretches. Movement in between is interpolated (held still across gaps over 6 s). Replays show the shape of a round, not exact footsteps.
- **Name changes.** Team names change between events. Cirrus follows GRID team IDs, drops broadcast suffixes such as "MIBR (1)", and labels teams that share a name with their circuit and year.
- **Recent period.** "Last 6 months" counts back from each team's own most recent match in the data, not from today.
