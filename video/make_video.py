"""Record the Cirrus demo video end to end.

1. Pull the numbers for each scene from the running app (so narration always matches the screen).
2. Synthesize narration per scene with a neural voice (edge-tts) and keep word timings.
3. Drive the real app in Chromium with Playwright and record 1080p video, scene by scene.
4. Mix narration at each scene's start, burn styled subtitles, encode H.264 MP4 with ffmpeg.

Run with the app serving locally:  python -m scout serve   then   python video/make_video.py
"""
from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

import edge_tts
import imageio_ffmpeg
from playwright.async_api import Page, async_playwright

BASE = "http://127.0.0.1:8765"
VOICE = "en-US-AvaNeural"
RATE = "+3%"
HERE = Path(__file__).resolve().parent
BUILD = HERE / "build"
OUT = HERE / "out"
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
W, H = 1920, 1080


def api(path: str, **q):
    url = f"{BASE}{path}?{urllib.parse.urlencode(q)}" if q else f"{BASE}{path}"
    with urllib.request.urlopen(url, timeout=120) as r:
        return json.loads(r.read())


def num(x: float) -> str:
    """Speak 47.0 as 47 and 53.8 as 53.8."""
    return str(int(x)) if float(x).is_integer() else str(x)


def team_id(meta, name):
    return next(t["id"] for t in meta["teams"] if t["name"] == name)


def since_for(meta, tid):
    import datetime as dt
    last = next(t["last_played"] for t in meta["teams"] if t["id"] == tid)
    return (dt.date.fromisoformat(last) - dt.timedelta(days=183)).isoformat()


# ---------------------------------------------------------------------------------------
@dataclass
class Scene:
    key: str
    label: str
    text: str
    actions: object  # async callable(page)
    words: list = field(default_factory=list)
    duration: float = 0.0
    start: float = 0.0


async def tts(scene: Scene):
    mp3 = BUILD / f"{scene.key}.mp3"
    meta = BUILD / f"{scene.key}.json"
    if mp3.exists() and meta.exists() and json.loads(meta.read_text())["text"] == scene.text:
        d = json.loads(meta.read_text())
        scene.words, scene.duration = d["words"], d["duration"]
        return
    for attempt in range(5):
        try:
            com = edge_tts.Communicate(scene.text, VOICE, rate=RATE, boundary="WordBoundary")
            audio, words = b"", []
            async for ch in com.stream():
                if ch["type"] == "audio":
                    audio += ch["data"]
                elif ch["type"] == "WordBoundary":
                    words.append({"t": ch["offset"] / 1e7, "d": ch["duration"] / 1e7, "w": ch["text"]})
            break
        except Exception as exc:  # the free endpoint rate-limits; back off and retry
            print(f"  tts retry {attempt + 1}: {str(exc)[:70]}")
            await asyncio.sleep(15 * (attempt + 1))
    else:
        raise SystemExit("TTS failed")
    mp3.write_bytes(audio)
    dur = _probe(mp3)
    scene.words, scene.duration = words, dur
    meta.write_text(json.dumps({"text": scene.text, "words": words, "duration": dur}))


def _probe(path: Path) -> float:
    p = subprocess.run([FFMPEG, "-i", str(path)], capture_output=True, text=True)
    for line in p.stderr.splitlines():
        if "Duration:" in line:
            hh, mm, ss = line.split("Duration:")[1].split(",")[0].strip().split(":")
            return int(hh) * 3600 + int(mm) * 60 + float(ss)
    raise RuntimeError(f"no duration for {path}")


# ---- page helpers ------------------------------------------------------------------------
CURSOR_JS = """
(() => {
  if (window.__cur) return;
  const c = document.createElement('div');
  c.id = '__cur';
  c.style.cssText = 'position:fixed;left:0;top:0;width:22px;height:22px;border-radius:50%;'
    + 'background:rgba(20,33,43,.18);border:2px solid #14212b;pointer-events:none;z-index:99999;'
    + 'transform:translate(-50%,-50%);transition:width .15s,height .15s,background .15s';
  document.body.appendChild(c);
  window.__cur = c;
  addEventListener('mousemove', e => { c.style.left = e.clientX + 'px'; c.style.top = e.clientY + 'px'; }, true);
  addEventListener('mousedown', () => { c.style.width = '14px'; c.style.height = '14px'; c.style.background = 'rgba(226,81,58,.45)'; }, true);
  addEventListener('mouseup', () => { c.style.width = '22px'; c.style.height = '22px'; c.style.background = 'rgba(20,33,43,.18)'; }, true);
})();
"""

LABEL_JS = """
(text) => {
  let el = document.getElementById('__label');
  if (!el) {
    el = document.createElement('div'); el.id = '__label';
    el.style.cssText = 'position:fixed;top:11px;left:66%;transform:translateX(-50%);z-index:99998;pointer-events:none;'
      + 'background:#14212b;color:#fff;font:650 15px "Archivo Variable",system-ui;padding:7px 16px;border-radius:999px;'
      + 'box-shadow:0 8px 24px -12px rgba(0,0,0,.5);transition:opacity .3s';
    document.body.appendChild(el);
  }
  el.textContent = text; el.style.opacity = text ? '1' : '0';
}
"""

CARD_JS = """
([title, sub, foot]) => {
  let el = document.getElementById('__card');
  if (!el) {
    el = document.createElement('div'); el.id = '__card';
    el.style.cssText = 'position:fixed;inset:0;z-index:99997;display:grid;place-items:center;pointer-events:none;'
      + 'background:#edf1f4;transition:opacity .7s ease;opacity:0';
    document.body.appendChild(el);
  }
  el.innerHTML = `<div style="text-align:center;font-family:'Archivo Variable',system-ui;color:#14212b">
    <svg width="92" height="92" viewBox="0 0 32 32" style="margin-bottom:22px"><rect width="32" height="32" rx="7" fill="#14212b"/>
    <path d="M7 20c0-3.3 2.6-6 5.8-6 .8-2.6 3.2-4.4 6-4.4 3.5 0 6.2 2.8 6.2 6.2 0 .2 0 .4-.1.6 1.3.5 2.1 1.7 2.1 3.1 0 1.9-1.5 3.5-3.4 3.5H10.4C8.5 23 7 21.6 7 20z" fill="#1e9bd7"/>
    <circle cx="21" cy="17" r="2.2" fill="#e2513a"/></svg>
    <div style="font-size:120px;font-weight:800;letter-spacing:-0.02em;font-variation-settings:'wdth' 118;line-height:1">${title}</div>
    <div style="font-size:34px;font-weight:500;color:#51616d;margin-top:18px">${sub}</div>
    <div style="font-size:20px;color:#8696a2;margin-top:42px">${foot}</div></div>`;
  requestAnimationFrame(() => { el.style.opacity = '1'; });
  if (window.__cur) window.__cur.style.opacity = '0';
}
"""


async def move_click(page: Page, locator, pause=0.35):
    """Glide the visible cursor to the element, then let Playwright perform a stable click."""
    await locator.first.scroll_into_view_if_needed(timeout=30000)
    box = await locator.first.bounding_box(timeout=30000)
    if box:
        await page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2, steps=28)
        await asyncio.sleep(pause)
    await locator.first.click(timeout=30000)


async def hover(page: Page, locator, pause=0.4):
    await locator.first.scroll_into_view_if_needed(timeout=30000)
    box = await locator.first.bounding_box()
    if box:
        await page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2, steps=28)
    await asyncio.sleep(pause)


async def goto_hash(page: Page, **h):
    await page.evaluate("(h) => { location.hash = h }", urllib.parse.urlencode(h))
    await asyncio.sleep(1.2)
    await page.evaluate(CURSOR_JS)


async def wait_view(page: Page, team: str, map_name: str):
    """Wait until the findings column shows this team and map, fully loaded."""
    await page.wait_for_function(
        """([t, m]) => {
            const h = document.querySelector('.findings h1');
            const s = document.querySelector('.sample');
            return h && h.innerText.startsWith(t) && h.innerText.toLowerCase().includes(m)
                && s && !s.innerText.startsWith('Loading') && document.querySelectorAll('.finding').length > 0;
        }""", arg=[team, map_name], timeout=60000)
    await asyncio.sleep(0.4)


async def label(page: Page, text: str):
    await page.evaluate(LABEL_JS, text)


async def card(page: Page, title: str, sub: str, foot: str = ""):
    await page.evaluate(CARD_JS, [title, sub, foot])


async def hide_card(page: Page):
    await page.evaluate("() => { const el = document.getElementById('__card'); if (el) el.style.opacity = '0';"
                        " if (window.__cur) window.__cur.style.opacity = '1'; }")


# ---- subtitles ---------------------------------------------------------------------------
def ass_time(t: float) -> str:
    t = max(0.0, t)
    h = int(t // 3600); m = int(t % 3600 // 60); s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


MAX_CUE_CHARS = 54      # one comfortable line at 1080p
MIN_BREAK_CHARS = 26    # don't break on a comma before this many characters


def align_words(text: str, words: list[dict]) -> list[dict]:
    """Attach each spoken word to its place in the script, walking forwards only.

    The voice engine reports words without punctuation and in order. Searching from a moving
    cursor keeps repeated words ("in", "the", "every") pointing at the right occurrence.
    """
    out, pos = [], 0
    for w in words:
        token = w["w"].strip()
        if not token:
            continue
        j = text.find(token, pos)
        if j < 0:                       # e.g. the engine spoke "percent" for "%": keep the timing only
            j = text.lower().find(token.lower(), pos)
        if j < 0:
            if out:
                out[-1]["end_t"] = w["t"] + w["d"]
            continue
        end = j + len(token)
        while end < len(text) and text[end] in ".,:;?!":
            end += 1
        out.append({"start": j, "end": end, "t": w["t"], "end_t": w["t"] + w["d"]})
        pos = j + len(token)
    return out


def cues_for(text: str, words: list[dict]) -> list[tuple[float, float, str]]:
    """Split the script into subtitle cues at sentence ends, then commas, then length."""
    aligned = align_words(text, words)
    groups, first = [], 0
    for i, w in enumerate(aligned):
        chunk = text[aligned[first]["start"]:w["end"]]
        last_char = text[w["end"] - 1]
        nxt = aligned[i + 1] if i + 1 < len(aligned) else None
        too_long = nxt is not None and len(text[aligned[first]["start"]:nxt["end"]]) > MAX_CUE_CHARS
        if nxt is None or last_char in ".?!:" or (last_char in ",;" and len(chunk) >= MIN_BREAK_CHARS):
            groups.append((first, i))
            first = i + 1
        elif too_long:
            # never strand a one- or two-letter word ("B", "of", "at") at the end of a line
            cut = i - 1 if (w["end"] - w["start"] <= 2 and i > first) else i
            groups.append((first, cut))
            first = cut + 1
    # fold a stranded tail ("map.") back into the line before it
    merged = []
    for g in groups:
        tail = text[aligned[g[0]]["start"]:aligned[g[1]]["end"]]
        if merged and len(tail) < 12:
            prev = merged[-1]
            if len(text[aligned[prev[0]]["start"]:aligned[g[1]]["end"]]) <= MAX_CUE_CHARS + 10:
                merged[-1] = (prev[0], g[1])
                continue
        merged.append(g)
    return [(aligned[a]["t"], aligned[b]["end_t"], text[aligned[a]["start"]:aligned[b]["end"]].strip()) for a, b in merged]


def build_ass(scenes: list[Scene], path: Path):
    cues = []
    for sc in scenes:
        for a, b, text in cues_for(sc.text, sc.words):
            cues.append((sc.start + a, sc.start + b + 0.3, text))
    for i in range(len(cues) - 1):          # a cue ends when the next one starts
        a, b, t = cues[i]
        if b > cues[i + 1][0] - 0.04:
            cues[i] = (a, cues[i + 1][0] - 0.04, t)
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sub,Segoe UI Semibold,44,&H00FFFFFF,&H00FFFFFF,&H1E2B2114,&H1E2B2114,0,0,0,0,100,100,0.3,0,3,16,0,2,160,160,70,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    body = "".join(f"Dialogue: 0,{ass_time(a)},{ass_time(b)},Sub,,0,0,0,,{t}\n" for a, b, t in cues)
    path.write_text(header + body, encoding="utf-8")
    return cues


# ---- the storyboard -------------------------------------------------------------------------
def storyboard(meta) -> list[Scene]:
    """Problem in the first ten seconds, in the product by 0:12, both hero features before 1:30.

    Every number spoken is read from the running app, so narration and screen cannot disagree.
    """
    ds = meta["dataset"]
    mibr, sen, c9 = team_id(meta, "MIBR"), team_id(meta, "Sentinels"), team_id(meta, "Cloud9")
    mib = api("/api/scout", team=mibr, map="icebox", side="defense", since=since_for(meta, mibr), phase="all")
    turret = next(h for h in mib["utility"]["hotspots"] if h["category"] == "trap")
    wall = next(h for h in mib["utility"]["hotspots"] if h["ability"] == "toxic-screen")
    op = mib["operator"]
    holder, area = op["holders"][0], op["areas"][0]
    op_index = next(i for i, f in enumerate(mib["insights"]) if f["kind"] == "operator")
    sen_s = api("/api/scout", team=sen, map="lotus", side="defense", since=since_for(meta, sen), phase="all")
    shear = next(h for h in sen_s["utility"]["hotspots"] if h["ability"] == "shear" and h["callout"] == "C Main")
    ctr = api("/api/counter", map="lotus", x=shear["x"], y=shear["y"], ability="shear")
    assert ctr["enough"], "the counter scene needs a spot with enough league rounds"
    c9s = api("/api/scout", team=c9, map="icebox", side="defense", since=since_for(meta, c9), phase="all")
    c9t = next(h for h in c9s["utility"]["hotspots"] if h["category"] == "trap")
    fp = c9s["setup"]
    signal = {"clear": "That is a clear signal.", "some": "That is a real signal, though not a certainty.",
              "noise": "That difference is within the noise, and Cirrus says so."}[ctr["signal"]]

    async def s_problem(page):
        await card(page, "Cirrus", "Scouting for Cloud9's VALORANT coaches", "Sky's The Limit 2026, Category 1")

    async def s_findings(page):
        await hide_card(page)
        await label(page, "MIBR, Icebox defense")
        await asyncio.sleep(2.5)
        await hover(page, page.locator(".finding").nth(0), 2.6)
        await hover(page, page.locator(".finding").nth(1), 2.6)
        await page.mouse.move(W * 0.5, H * 0.45, steps=30)

    async def s_operator(page):
        await label(page, "Operator profiler")
        await move_click(page, page.locator(".finding").nth(op_index))
        await page.locator(".area-list").wait_for(timeout=30000)
        await asyncio.sleep(4.5)
        tools = page.locator(".stage-tools")
        for name, pause in (("0–20s", 2.2), ("20–40s", 2.0), ("40s+", 2.2), ("Opening area", 1.0)):
            await move_click(page, tools.get_by_role("button", name=name, exact=True))
            await asyncio.sleep(pause)

    async def s_replay(page):
        await label(page, "Every finding has its rounds")
        await hover(page, page.locator(".evidence-head"), 1.6)
        await move_click(page, page.locator(".round:not([disabled])").first)
        await page.locator(".replay-bar").wait_for(timeout=90000)
        await page.mouse.move(W * 0.86, H * 0.4, steps=30)

    async def s_counter(page):
        await label(page, "Counters, tested league-wide")
        await hover(page, page.locator(".select"))
        await page.select_option(".select", sen)
        await asyncio.sleep(1.0)
        await move_click(page, page.locator(".map-tab", has_text="Lotus"))
        await wait_view(page, "Sentinels", "lotus")
        await move_click(page, page.locator(".tab", has_text="Utility"))
        await asyncio.sleep(1.2)
        row = page.locator(".spot-list button").filter(has_text="Shear").filter(has_text="C Main").first
        await row.wait_for(timeout=30000)
        await move_click(page, row)
        await page.locator(".counter-figure").wait_for(timeout=60000)
        await hover(page, page.locator(".counter-figure"), 1.0)

    async def s_mirror(page):
        await label(page, "Self-scout Cloud9")
        await hover(page, page.locator(".select"))
        await page.select_option(".select", c9)
        await asyncio.sleep(1.0)
        await move_click(page, page.locator(".map-tab", has_text="Icebox"))
        await wait_view(page, "Cloud9", "icebox")
        await asyncio.sleep(2.0)
        await move_click(page, page.locator(".tab", has_text="Setups"))
        await asyncio.sleep(1.6)
        await hover(page, page.locator(".strip"), 1.0)

    async def s_trust(page):
        await label(page, "Honest about its limits")
        await move_click(page, page.locator(".tab", has_text="Utility"))
        await asyncio.sleep(0.8)
        await move_click(page, page.locator(".stage-tools").get_by_role("button", name="Heatmap", exact=True))
        await asyncio.sleep(2.2)
        await hover(page, page.locator(".quality"), 2.0)

    async def s_close(page):
        await label(page, "")
        await card(page, "Cirrus", "Less VOD scrubbing. Sharper prep.", "Built on official GRID esports data")

    return [
        Scene("s0", "", "Before every match, Cloud9's coaches spend hours in VODs answering two questions. "
              "Where does the opponent put their utility? And who holds the Operator? Cirrus answers both in seconds.",
              s_problem),
        Scene("s1", "", f"This is MIBR defending Icebox, read straight from the official GRID data. Their Killjoy turret sits at "
              f"{turret['callout']} in {turret['p']} percent of defense rounds, {turret['k']} of {turret['n']}. "
              f"Their Viper wall starts from {wall['callout']} in {wall['p']} percent. "
              "Every finding shows its sample size, and how strong the evidence is.", s_findings),
        Scene("s2", "", f"Who holds the Operator? {holder['player']}, in {holder['p']} percent of MIBR's Operator rounds. "
              f"In the first twenty seconds the Operator sets up at {area['callout']} in {area['open_k']} of {area['open_n']} of them. "
              "Step through the round clock, and you can see where the angle moves. The red lines are opening picks.",
              s_operator),
        Scene("s3", "", "A coach should never have to trust a number blindly. Every finding lists the rounds behind it. "
              "Pick one, and it replays in 2D, straight from the feed: every player, every ability, every kill.", s_replay),
        Scene("s4", "", f"Cirrus also tests counters against the whole league. Sentinels set a Vyse Shear at C Main. "
              f"Across {ctr['rounds']} league rounds with that setup, attackers who hit it with utility in the first "
              f"{int(ctr['contest_before'])} seconds won {num(ctr['win_contested'])} percent. When they left it alone, they won "
              f"{num(ctr['win_uncontested'])} percent. {signal}", s_counter),
        Scene("s5", "", f"And it works as a mirror. Cloud9's own turret sits at {c9t['callout']} in {c9t['p']} percent of "
              f"Icebox defense rounds. {fp['predictability']} percent of their trap placements land on a spot they reuse, "
              "shown here against every other team on the map.", s_mirror),
        Scene("s6", "", f"Cirrus is honest about its limits. It tells you when tracking is coarse, and when evidence is thin. "
              f"And its percentages are checked by automated tests, including a recount from the raw GRID files, "
              f"across {ds['series']} series and {ds['rounds'] // 1000} thousand rounds.", s_trust),
        Scene("s7", "", "Cirrus. Less VOD scrubbing, sharper prep, for Cloud9's VALORANT and Game Changers coaches.", s_close),
    ]


async def record(scenes: list[Scene]) -> Path:
    vdir = BUILD / "raw"
    if vdir.exists():
        for f in vdir.glob("*"):
            f.unlink()
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        ctx = await browser.new_context(viewport={"width": W, "height": H}, device_scale_factor=1,
                                        record_video_dir=str(vdir), record_video_size={"width": W, "height": H})
        page = await ctx.new_page()
        t0 = time.monotonic()
        await page.goto(f"{BASE}/#team={team_id(api('/api/meta'), 'MIBR')}&map=icebox&side=defense&mode=utility&period=recent")
        await page.wait_for_selector(".finding", timeout=60000)
        await page.evaluate(CURSOR_JS)
        await page.mouse.move(W * 0.5, H * 0.5)
        lead = 0.6
        for sc in scenes:
            sc.start = time.monotonic() - t0 + lead
            print(f"  scene {sc.key} at {sc.start:.1f}s ({sc.duration:.1f}s)")
            await asyncio.sleep(lead)
            t_s = time.monotonic()
            await sc.actions(page)
            rest = sc.duration + 0.5 - (time.monotonic() - t_s)
            if rest > 0:
                await asyncio.sleep(rest)
            lead = 0.4
        await asyncio.sleep(1.5)
        total = time.monotonic() - t0
        await ctx.close()
        await browser.close()
    webm = next(vdir.glob("*.webm"))
    print(f"  recorded {total:.1f}s -> {webm.name}")
    return webm


def mux(webm: Path, scenes: list[Scene], out: Path):
    ass = BUILD / "subs.ass"
    cues = build_ass(scenes, ass)
    longest = max(len(t) for _, _, t in cues)
    print(f"  {len(cues)} subtitle cues, longest {longest} characters")
    inputs, filters, labels = ["-i", str(webm)], [], []
    for i, sc in enumerate(scenes, start=1):
        inputs += ["-i", str(BUILD / f"{sc.key}.mp3")]
        ms = int(sc.start * 1000)
        filters.append(f"[{i}:a]adelay={ms}|{ms},volume=1.0[a{i}]")
        labels.append(f"[a{i}]")
    filters.append(f"{''.join(labels)}amix=inputs={len(scenes)}:normalize=0,loudnorm=I=-16:TP=-1.5:LRA=11[aout]")
    filters.append("[0:v]ass=build/subs.ass,format=yuv420p[vout]")
    cmd = [FFMPEG, "-y", *inputs, "-filter_complex", ";".join(filters), "-map", "[vout]", "-map", "[aout]",
           "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-r", "30", "-c:a", "aac", "-b:a", "192k",
           "-movflags", "+faststart", "-shortest", str(out)]
    subprocess.run(cmd, check=True, cwd=str(HERE), capture_output=True)


async def main():
    BUILD.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    meta = api("/api/meta")
    scenes = storyboard(meta)
    print("Narration:")
    for sc in scenes:
        await tts(sc)
        print(f"  {sc.key}: {sc.duration:.1f}s  {sc.text[:70]}…")
    total = sum(s.duration for s in scenes) + 0.4 * len(scenes) + 2
    print(f"Estimated length {total:.0f}s")
    (BUILD / "script.txt").write_text("\n\n".join(s.text for s in scenes), encoding="utf-8")
    if "--remux" in sys.argv:
        timeline = json.loads((BUILD / "timeline.json").read_text())
        for sc in scenes:
            sc.start = timeline["starts"][sc.key]
        webm = Path(timeline["webm"])
    else:
        print("Recording…")
        webm = await record(scenes)
        (BUILD / "timeline.json").write_text(json.dumps({"webm": str(webm), "starts": {sc.key: sc.start for sc in scenes}}))
    out = OUT / "cirrus-demo.mp4"
    print("Mixing…")
    mux(webm, scenes, out)
    print(f"Done: {out} ({_probe(out):.1f}s)")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(main())
