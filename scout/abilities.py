"""VALORANT ability catalogue keyed by GRID ability id.

Agent names and what each ability does were checked against the public valorant-api.com agent
data (ability descriptions) on 2026-11-21; ids follow GRID's naming.

category   what the utility does, ordered by the coaching brief's priority:
           trap (placeable sentinel), sentinel, recon, smoke, stall, flash, damage, mobility, ult
placement  what the caster's position tells a coach:
           'placed'  - the device sits at or right next to the caster (turret, alarmbot, trapwire,
                       shear): the cast position is the placement to within a couple of metres
           'ranged'  - placed at the point the caster aims at, which can be several metres away
                       (spycam, trademark, arc rose, sonic sensor): we show origin and aim
           'thrown'  - a projectile; we show where it was thrown from and the aim
           'wall'    - a line sent along the aim from the caster (Viper wall, Fault Line): origin
                       and direction define it
           'self'    - affects the caster (dashes, buffs)
           'global'  - targeted on a tactical map or from anywhere (Brimstone, Omen, Astra, Clove
                       smokes): the caster's position says nothing about where it lands, so these
                       are never drawn on the map; they are reported as usage only
"""
from __future__ import annotations

# id: (agent, display name, category, placement)
ABILITIES: dict[str, tuple[str, str, str, str]] = {
    # Cypher
    "trapwire": ("Cypher", "Trapwire", "trap", "placed"),
    "spycam": ("Cypher", "Spycam", "trap", "ranged"),
    "cyber-cage": ("Cypher", "Cyber Cage", "smoke", "thrown"),
    "neural-theft": ("Cypher", "Neural Theft", "ult", "self"),
    # Killjoy
    "alarmbot": ("Killjoy", "Alarmbot", "trap", "placed"),
    "turret": ("Killjoy", "Turret", "trap", "placed"),
    "nanoswarm": ("Killjoy", "Nanoswarm", "sentinel", "thrown"),
    "lockdown": ("Killjoy", "Lockdown", "ult", "placed"),
    # Chamber
    "trademark": ("Chamber", "Trademark", "trap", "ranged"),
    "rendezvous": ("Chamber", "Rendezvous", "mobility", "placed"),
    "headhunter": ("Chamber", "Headhunter", "mobility", "self"),
    "tour-de-force": ("Chamber", "Tour De Force", "ult", "self"),
    # Vyse
    "shear": ("Vyse", "Shear", "trap", "placed"),
    "razorvine": ("Vyse", "Razorvine", "sentinel", "thrown"),
    "arc-rose": ("Vyse", "Arc Rose", "flash", "ranged"),
    "steel-garden": ("Vyse", "Steel Garden", "ult", "self"),
    # Deadlock
    "sonic-sensor": ("Deadlock", "Sonic Sensor", "trap", "ranged"),
    "barrier-mesh": ("Deadlock", "Barrier Mesh", "stall", "thrown"),
    "gravnet": ("Deadlock", "GravNet", "stall", "thrown"),
    "annihilation": ("Deadlock", "Annihilation", "ult", "wall"),
    # Sage
    "barrier-orb": ("Sage", "Barrier Orb", "stall", "placed"),
    "slow-orb": ("Sage", "Slow Orb", "stall", "thrown"),
    "healing-orb": ("Sage", "Healing Orb", "mobility", "self"),
    "resurrection": ("Sage", "Resurrection", "ult", "self"),
    # Veto
    "chokehold": ("Veto", "Chokehold", "trap", "thrown"),
    "interceptor": ("Veto", "Interceptor", "trap", "placed"),
    "crosscut": ("Veto", "Crosscut", "mobility", "placed"),
    # Sova
    "recon-bolt": ("Sova", "Recon Bolt", "recon", "thrown"),
    "owl-drone": ("Sova", "Owl Drone", "recon", "thrown"),
    "shock-bolt": ("Sova", "Shock Bolt", "damage", "thrown"),
    "hunter's-fury": ("Sova", "Hunter's Fury", "ult", "wall"),
    # Fade
    "haunt": ("Fade", "Haunt", "recon", "thrown"),
    "prowler": ("Fade", "Prowler", "recon", "thrown"),
    "seize": ("Fade", "Seize", "stall", "thrown"),
    "nightfall": ("Fade", "Nightfall", "ult", "wall"),
    # Skye
    "trailblazer": ("Skye", "Trailblazer", "recon", "thrown"),
    "guiding-light": ("Skye", "Guiding Light", "flash", "thrown"),
    "regrowth": ("Skye", "Regrowth", "mobility", "self"),
    "seekers": ("Skye", "Seekers", "ult", "thrown"),
    # KAY/O
    "zero-point": ("KAY/O", "ZERO/point", "recon", "thrown"),
    "flash-drive": ("KAY/O", "FLASH/drive", "flash", "thrown"),
    "frag-ment": ("KAY/O", "FRAG/ment", "damage", "thrown"),
    "null-cmd": ("KAY/O", "NULL/cmd", "ult", "self"),
    # Breach
    "flashpoint": ("Breach", "Flashpoint", "flash", "thrown"),
    "fault-line": ("Breach", "Fault Line", "stall", "wall"),
    "aftershock": ("Breach", "Aftershock", "damage", "thrown"),
    "rolling-thunder": ("Breach", "Rolling Thunder", "ult", "wall"),
    # Gekko
    "wingman": ("Gekko", "Wingman", "recon", "thrown"),
    "dizzy": ("Gekko", "Dizzy", "flash", "thrown"),
    "mosh-pit": ("Gekko", "Mosh Pit", "damage", "thrown"),
    "thrash": ("Gekko", "Thrash", "ult", "thrown"),
    # Tejo
    "stealth-drone": ("Tejo", "Stealth Drone", "recon", "thrown"),
    "special-delivery": ("Tejo", "Special Delivery", "stall", "thrown"),
    "guided-salvo": ("Tejo", "Guided Salvo", "damage", "global"),
    "armageddon": ("Tejo", "Armageddon", "ult", "global"),
    # Omen
    "dark-cover": ("Omen", "Dark Cover", "smoke", "global"),
    "paranoia": ("Omen", "Paranoia", "flash", "thrown"),
    "shrouded-step": ("Omen", "Shrouded Step", "mobility", "self"),
    "from-the-shadows": ("Omen", "From the Shadows", "ult", "self"),
    # Brimstone
    "sky-smoke": ("Brimstone", "Sky Smoke", "smoke", "global"),
    "incendiary": ("Brimstone", "Incendiary", "damage", "thrown"),
    "stim-beacon": ("Brimstone", "Stim Beacon", "mobility", "thrown"),
    "orbital-strike": ("Brimstone", "Orbital Strike", "ult", "global"),
    # Viper
    "toxic-screen": ("Viper", "Toxic Screen", "smoke", "wall"),
    "poison-cloud": ("Viper", "Poison Cloud", "smoke", "thrown"),
    "snake-bite": ("Viper", "Snake Bite", "damage", "thrown"),
    "viper's-pit": ("Viper", "Viper's Pit", "ult", "self"),
    # Astra
    "stars": ("Astra", "Star placement", "smoke", "global"),
    "nebula-dissipate": ("Astra", "Nebula", "smoke", "global"),
    "gravity-well": ("Astra", "Gravity Well", "stall", "global"),
    "nova-pulse": ("Astra", "Nova Pulse", "stall", "global"),
    "cosmic-divide": ("Astra", "Cosmic Divide", "ult", "global"),
    # Harbor
    "cove": ("Harbor", "Cove", "smoke", "global"),
    "high-tide": ("Harbor", "High Tide", "smoke", "wall"),
    "cascade": ("Harbor", "Cascade", "smoke", "wall"),
    "storm-surge": ("Harbor", "Storm Surge", "stall", "thrown"),
    "reckoning": ("Harbor", "Reckoning", "ult", "thrown"),
    # Clove
    "ruse": ("Clove", "Ruse", "smoke", "global"),
    "meddle": ("Clove", "Meddle", "stall", "thrown"),
    "pick-me-up": ("Clove", "Pick-Me-Up", "mobility", "self"),
    "not-dead-yet": ("Clove", "Not Dead Yet", "ult", "self"),
    # Jett
    "cloudburst": ("Jett", "Cloudburst", "smoke", "thrown"),
    "updraft": ("Jett", "Updraft", "mobility", "self"),
    "tailwind": ("Jett", "Tailwind", "mobility", "self"),
    "blade-storm": ("Jett", "Blade Storm", "ult", "self"),
    # Phoenix
    "curveball": ("Phoenix", "Curveball", "flash", "thrown"),
    "blaze": ("Phoenix", "Blaze", "smoke", "wall"),
    "hot-hands": ("Phoenix", "Hot Hands", "damage", "thrown"),
    "run-it-back": ("Phoenix", "Run It Back", "ult", "self"),
    # Reyna
    "leer": ("Reyna", "Leer", "flash", "thrown"),
    "devour": ("Reyna", "Devour", "mobility", "self"),
    "dismiss": ("Reyna", "Dismiss", "mobility", "self"),
    "empress": ("Reyna", "Empress", "ult", "self"),
    # Raze
    "paint-shells": ("Raze", "Paint Shells", "damage", "thrown"),
    "boom-bot": ("Raze", "Boom Bot", "recon", "thrown"),
    "blast-pack": ("Raze", "Blast Pack", "mobility", "thrown"),
    "showstopper": ("Raze", "Showstopper", "ult", "thrown"),
    # Neon
    "relay-bolt": ("Neon", "Relay Bolt", "stall", "thrown"),
    "fast-lane": ("Neon", "Fast Lane", "smoke", "wall"),
    "high-gear": ("Neon", "High Gear", "mobility", "self"),
    "overdrive": ("Neon", "Overdrive", "ult", "self"),
    # Yoru
    "blindside": ("Yoru", "Blindside", "flash", "thrown"),
    "fakeout": ("Yoru", "Fakeout", "recon", "thrown"),
    "gatecrash": ("Yoru", "Gatecrash", "mobility", "thrown"),
    "dimensional-drift": ("Yoru", "Dimensional Drift", "ult", "self"),
    # Iso
    "undercut": ("Iso", "Undercut", "stall", "thrown"),
    "double-tap": ("Iso", "Double Tap", "mobility", "self"),
    "contingency": ("Iso", "Contingency", "smoke", "wall"),
    "kill-contract": ("Iso", "Kill Contract", "ult", "thrown"),
    # Waylay
    "saturate": ("Waylay", "Saturate", "stall", "thrown"),
    "refract": ("Waylay", "Refract", "mobility", "self"),
    "light-speed": ("Waylay", "Lightspeed", "mobility", "self"),
    "convergent-paths": ("Waylay", "Convergent Paths", "ult", "thrown"),
    # Miks
    "harmonize": ("Miks", "Harmonize", "mobility", "self"),
    "waveform": ("Miks", "Waveform", "smoke", "global"),
    "m-pulse": ("Miks", "M-Pulse", "stall", "thrown"),
    "bassquake": ("Miks", "Bassquake", "ult", "wall"),
}

CATEGORY_LABELS = {
    "trap": "Traps and cams",
    "sentinel": "Sentinel lockdown",
    "recon": "Recon",
    "smoke": "Smokes and walls",
    "stall": "Reactive stall",
    "flash": "Flashes",
    "damage": "Damage utility",
    "mobility": "Movement and support",
    "ult": "Ultimates",
}

# The brief asks for placeable utility first, then recon, smokes, stall and flashes.
CATEGORY_ORDER = ["trap", "sentinel", "recon", "smoke", "stall", "flash", "damage", "ult", "mobility"]

# Placements whose cast position can be drawn on the map.
SPATIAL = ("placed", "ranged", "thrown", "wall")


def info(ability_id: str | None) -> tuple[str, str, str, str]:
    if not ability_id:
        return ("?", "Unknown", "other", "thrown")
    return ABILITIES.get(ability_id, ("?", ability_id.replace("-", " ").title(), "other", "thrown"))
