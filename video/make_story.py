"""A short vertical story (1080x1920) about how the JetBrains tools were used on Cirrus.

Everything shown is real: the brief's own wording, the two round counts that disagreed, the task
file names, the test counts, and screenshots of the JetBrains Air session (kept locally in
video/build/story, not in the repository).

    python video/make_story.py        ->  video/out/cirrus-junie-story.mp4

Needs the extras in requirements-video.txt.
"""
from __future__ import annotations

import asyncio
import base64
import json
import subprocess
import time
from pathlib import Path

import edge_tts
import imageio_ffmpeg
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "video" / "build" / "story"
OUT = ROOT / "video" / "out" / "cirrus-junie-story.mp4"
FONT = ROOT / "web" / "node_modules" / "@fontsource-variable" / "archivo" / "files" / "archivo-latin-wdth-normal.woff2"
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
VOICE, RATE = "en-US-AvaNeural", "+4%"
W, H = 1080, 1920
TAIL = 0.55          # quiet beat after each line
TASKS = sorted(p.name for p in (ROOT / "docs" / "junie-tasks").glob("*.md"))

# (key, narration, html)
SCENES = [
    ("hook", "The agent's tests all passed. It was still wrong.",
     '<p class="huge a1">Its tests<br>passed.</p><p class="huge coral a2">It was<br>still wrong.</p>'),
    ("briefs", "For Cirrus, a VALORANT scouting tool, JetBrains' coding agent Junie got seven written briefs.",
     '<p class="kicker a1">Cirrus · VALORANT scouting</p><p class="big a1">Seven written briefs<br>for <span class="sky">Junie</span></p>'
     '<ol class="files">' + "".join(f'<li style="--i:{i}">{n}</li>' for i, n in enumerate(TASKS)) + "</ol>"),
    ("green", "Brief two was a text scouting report. Nine tests. All green.",
     '<p class="kicker a1">Brief 02</p><p class="big a1">A text scouting report</p>'
     '<div class="tests">' + "".join(f'<i style="--i:{i}"></i>' for i in range(9)) + '</div>'
     '<p class="mid good a3">9 passed</p>'),
    ("mismatch", "Then one check against the app. The app said eighty-four rounds. Junie's report said twenty-three.",
     '<p class="kicker a1">One check against the app</p>'
     '<div class="versus"><div class="a2"><span class="label">The app</span><span class="num">84</span><span class="unit">rounds</span></div>'
     '<div class="a3"><span class="label">Junie\'s report</span><span class="num coral">23</span><span class="unit">rounds</span></div></div>'),
    ("cause", "The brief said: work out the period the way the server does. That logic was not on the server. "
              "So Junie guessed thirty days, and wrote tests that agreed with the guess.",
     '<p class="kicker a1">What the brief said</p>'
     '<p class="quote a1">works out the <code>since</code> value <mark>the way the server does</mark></p>'
     '<p class="mid a2">That logic was not on the server.</p>'
     '<p class="mid coral a3">Junie guessed: 30 days.<br>Its tests agreed with the guess.</p>'),
    ("fixes", "Three fixes. Name the exact function. Send the review back as a written brief. "
              "And ask for the test that would have caught it.",
     '<p class="kicker a1">Three fixes</p><ol class="fixes">'
     '<li class="a1">Name the exact function.</li><li class="a2">Send the review back as a written brief.</li>'
     '<li class="a3">Ask for the test that would have caught it.</li></ol>'),
    ("air", "Brief seven ran in JetBrains Air. Every command was approved before it ran.",
     '<p class="kicker a1">Brief 07 · JetBrains Air</p><p class="big a1">Every command approved<br>before it ran</p>'
     '<div class="shot a2"><img src="{air1}"></div>'),
    ("match", "Fifty-one results checked against the app. Fifty-one matched. No review round.",
     '<div class="shot small a1"><img src="{air2}"></div>'
     '<div class="versus one"><div class="a2"><span class="label">Checked against the app</span>'
     '<span class="num good">51 of 51</span><span class="unit">matched · no review round</span></div></div>'),
    ("tests", "Thirty-eight tests became ninety-seven. Brief it like a teammate. Check it like a stranger.",
     '<p class="kicker a1">Automated tests</p><p class="counter a1"><span id="count">38</span></p>'
     '<p class="big a3">Brief it like a teammate.<br><span class="sky">Check it like a stranger.</span></p>'),
    ("end", "Cirrus. Built with Junie and JetBrains Air.",
     '<div class="logo a1"><svg viewBox="0 0 64 64"><rect width="64" height="64" rx="14" fill="#151f27"/>'
     '<path d="M20 43a9 9 0 0 1 1.6-17.9A12 12 0 0 1 44.5 27 8 8 0 0 1 44 43z" fill="#3aaee6"/><circle cx="41" cy="33" r="4" fill="#ff7059"/></svg></div>'
     '<p class="huge a1">Cirrus</p><p class="mid a2">Built with Junie and JetBrains Air</p>'
     '<p class="small a3">github.com/zuhairhalawa/cirrus-scout</p>'),
]

CSS = """
@font-face{font-family:Archivo;src:url(data:font/woff2;base64,__FONT__) format('woff2');font-weight:100 900;font-stretch:62% 125%}
*{box-sizing:border-box;margin:0}
body{width:1080px;height:1920px;background:#0e161c;color:#e9eff3;font-family:Archivo,system-ui,sans-serif;overflow:hidden}
section{position:absolute;inset:0;padding:230px 84px 300px;display:none;flex-direction:column;justify-content:center;gap:44px}
section.on{display:flex}
.kicker{font-size:40px;font-weight:600;color:#91a0ab}
.huge{font-size:164px;line-height:.95;font-weight:800;font-stretch:88%;letter-spacing:-.02em}
.big{font-size:86px;line-height:1.04;font-weight:750;font-stretch:92%;letter-spacing:-.015em}
.mid{font-size:58px;line-height:1.18;font-weight:600}
.small{font-size:38px;color:#91a0ab;font-weight:500}
.sky{color:#6cc6f2}.coral{color:#ff7059}.good{color:#52c692}
.files{list-style:none;padding:0;display:grid;gap:14px;margin-top:10px}
.files li{font-size:36px;font-weight:550;color:#b6c3cc;padding:18px 26px;background:#151f27;border-radius:10px;opacity:0;
  animation:rise .45s ease-out forwards;animation-delay:calc(.9s + var(--i) * .32s)}
.tests{display:grid;grid-template-columns:repeat(9,1fr);gap:16px;margin-top:20px}
.tests i{height:86px;border-radius:10px;background:#273640;animation:green .25s ease-out forwards;animation-delay:calc(1.6s + var(--i) * .16s)}
.versus{display:grid;gap:40px}
.versus>div{background:#151f27;border-radius:18px;padding:44px 52px;display:grid;gap:4px}
.label{font-size:42px;font-weight:600;color:#91a0ab}
.num{font-size:250px;line-height:1;font-weight:800;font-stretch:88%;letter-spacing:-.03em;font-variant-numeric:tabular-nums}
.versus.one .num{font-size:168px}
.unit{font-size:44px;font-weight:550;color:#b6c3cc}
.quote{font-size:66px;line-height:1.2;font-weight:600;border-left:8px solid #273640;padding-left:36px}
code{font-family:ui-monospace,Menlo,monospace;font-size:.86em;color:#6cc6f2}
mark{background:linear-gradient(#ff705955,#ff705955) no-repeat 0 100%/0 46%;color:inherit;animation:mark .7s 2.4s ease-out forwards}
.fixes{padding:0;list-style:none;counter-reset:n;display:grid;gap:40px}
.fixes li{counter-increment:n;font-size:68px;line-height:1.12;font-weight:700;display:grid;grid-template-columns:96px 1fr;align-items:start}
.fixes li::before{content:counter(n);color:#6cc6f2;font-weight:800}
.shot{border-radius:16px;overflow:hidden;border:2px solid #273640;background:#151f27}
.shot img{display:block;width:100%}
.shot.small{max-height:640px}
.counter{font-size:330px;line-height:.9;font-weight:800;font-stretch:88%;letter-spacing:-.03em;color:#52c692;font-variant-numeric:tabular-nums}
.logo svg{width:150px;height:150px}
.a1,.a2,.a3{opacity:0;animation:rise .5s ease-out forwards}
.a1{animation-delay:.1s}.a2{animation-delay:var(--d2,1.5s)}.a3{animation-delay:var(--d3,3s)}
@keyframes rise{from{opacity:0;transform:translateY(26px)}to{opacity:1;transform:none}}
@keyframes green{to{background:#52c692}}
@keyframes mark{to{background-size:100% 46%}}
"""

JS = """
window.show = (i, d2, d3) => {
  document.querySelectorAll('section').forEach((s, k) => {
    s.classList.toggle('on', k === i);
    if (k === i) { s.style.setProperty('--d2', d2 + 's'); s.style.setProperty('--d3', d3 + 's'); }
  });
  const c = document.querySelector('section.on #count');
  if (c) { const t0 = performance.now() + 600; const step = (t) => { const p = Math.min(1, Math.max(0, (t - t0) / 2200));
    c.textContent = Math.round(38 + (97 - 38) * (1 - Math.pow(1 - p, 3))); if (p < 1) requestAnimationFrame(step) }; requestAnimationFrame(step) }
};
"""


def data_uri(path: Path) -> str:
    mime = "image/png" if path.suffix == ".png" else "image/jpeg"
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()


def probe(path: Path) -> float:
    err = subprocess.run([FFMPEG, "-i", str(path)], capture_output=True, text=True).stderr
    h, m, s = err.split("Duration: ")[1].split(",")[0].split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


async def main():
    BUILD.mkdir(parents=True, exist_ok=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    air1, air2 = BUILD / "air-approval.png", BUILD / "air-result.png"
    assert air1.exists() and air2.exists(), f"put the two JetBrains Air screenshots in {BUILD}"
    durs = []
    for key, text, _ in SCENES:
        mp3 = BUILD / f"{key}.mp3"
        await edge_tts.Communicate(text, VOICE, rate=RATE).save(str(mp3))
        durs.append(probe(mp3))
    body = "".join(f"<section>{html}</section>" for _, _, html in SCENES)
    body = body.replace("{air1}", data_uri(air1)).replace("{air2}", data_uri(air2))
    page_html = (f"<!doctype html><meta charset=utf-8><style>{CSS}</style>{body}<script>{JS}</script>"
                 .replace("__FONT__", base64.b64encode(FONT.read_bytes()).decode()))
    (BUILD / "story.html").write_text(page_html, encoding="utf-8")

    raw = BUILD / "raw"
    for f in raw.glob("*") if raw.exists() else []:
        f.unlink()
    starts = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        ctx = await browser.new_context(viewport={"width": W, "height": H}, record_video_dir=str(raw),
                                        record_video_size={"width": W, "height": H})
        page = await ctx.new_page()
        t0 = time.monotonic()
        await page.goto((BUILD / "story.html").as_uri())
        await page.evaluate("document.fonts.ready")
        await asyncio.sleep(0.4)
        for i, d in enumerate(durs):
            starts.append(time.monotonic() - t0)
            await page.evaluate("([i, a, b]) => window.show(i, a, b)", [i, round(d * 0.36, 2), round(d * 0.66, 2)])
            await asyncio.sleep(d + TAIL)
        await asyncio.sleep(0.9)
        total = time.monotonic() - t0
        await ctx.close()
        await browser.close()
    webm = next(raw.glob("*.webm"))
    cmd = [FFMPEG, "-y", "-loglevel", "error", "-i", str(webm)]
    for key, _, _ in SCENES:
        cmd += ["-i", str(BUILD / f"{key}.mp3")]
    lead = starts[0]                       # cut the blank lead-in before the first scene
    mix = "".join(f"[{i + 1}:a]adelay={int((s + 0.12) * 1000)}:all=1[a{i}];" for i, s in enumerate(starts))
    mix += "".join(f"[a{i}]" for i in range(len(starts))) + f"amix=inputs={len(starts)}:normalize=0[a]"
    cmd += ["-filter_complex", mix, "-ss", f"{lead:.2f}", "-map", "0:v", "-map", "[a]", "-t", f"{total - lead:.2f}",
            "-c:v", "libx264", "-preset", "slow", "-crf", "20", "-pix_fmt", "yuv420p", "-r", "30",
            "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(OUT)]
    subprocess.run(cmd, check=True)
    (BUILD / "timeline.json").write_text(json.dumps({"starts": [round(s - lead, 2) for s in starts], "durations": durs}))
    print(f"Done: {OUT} ({probe(OUT):.1f}s)")


if __name__ == "__main__":
    asyncio.run(main())
