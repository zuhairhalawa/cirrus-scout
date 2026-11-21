"""Local scouting server: JSON API + the built web app. Standard library only."""
from __future__ import annotations

import datetime as dt
import json
import mimetypes
import time
import traceback
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import numpy as np

from . import analysis as A
from .config import MAPS_DIR, STORE_PATH, WEB_DIST


class _Enc(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, (np.floating,)):
            return None if np.isnan(o) else float(o)
        if isinstance(o, np.ndarray):
            return o.tolist()
        if isinstance(o, (set, frozenset)):
            return sorted(o)
        return super().default(o)


def dumps(data) -> str:
    return json.dumps(data, cls=_Enc, separators=(",", ":"))


def _q(qs, key, default=None):
    v = qs.get(key)
    return v[0] if v else default


def map_meta(map_name: str) -> dict:
    """Everything the front end needs to draw a map: vector floor plan, callouts, sites."""
    st = A.store()
    info = st.map_info[map_name]
    plan = MAPS_DIR / f"{map_name}.json"
    path = json.loads(plan.read_text(encoding="utf-8"))["path"] if plan.exists() else ""
    b = info.get("bbox", [0, 0, 1, 1])
    pad = 0.03
    bbox = [max(0.0, b[0] - pad), max(0.0, b[1] - pad), min(1.0, b[2] + pad), min(1.0, b[3] + pad)]
    return {"callouts": info.get("callouts", []), "sites": st.site_anchors(map_name) if info.get("samples") else [],
            "samples": info.get("samples", 0), "bbox": bbox, "path": path}


def dataset_info() -> dict:
    st = A.store()
    G = st.G
    return {
        "series": len(set(G["series_id"].tolist())), "maps": len(G["game_id"]), "rounds": len(st.R["n"]),
        "casts": len(st.C["round"]), "kills": len(st.K["round"]), "teams": len(A.teams_index()),
        "from": min(G["date"]), "to": max(G["date"]),
        "range_label": A.fmt_range(min(G["date"]), max(G["date"])),
        "excluded_maps": len(st.excluded_games), "excluded_rounds": int((~st.round_ok).sum()),
        "built": dt.datetime.fromtimestamp(STORE_PATH.stat().st_mtime).strftime("%Y-%m-%d"),
    }


def meta_payload(mode: str = "live") -> dict:
    st = A.store()
    return {"teams": A.teams_index(), "maps": {m: map_meta(m) for m in st.maps}, "dataset": dataset_info(),
            "mode": mode}


def scout_payload(team: str, map_name: str, side: str, since: str | None, phase: str = "all") -> dict:
    """One scouting view, with a readable reference for every round in the sample."""
    st = A.store()
    ti = st.team_id[team]
    sd = A.SIDE_ID[side]
    res = A.scout(ti, map_name, sd, phase=phase if phase in A.PHASES else "all", since=since or None)
    rmask = st.round_mask(ti, map_name, sd, None, since or None)
    res["rounds"] = {r["round"]: r for r in A.round_refs(ti, np.flatnonzero(rmask))}
    res["team"] = {"id": team, "name": st.team_name(ti)}
    return res


@lru_cache(maxsize=256)
def _scout_cached(team: str, map_name: str, side: str, since: str, phase: str) -> str:
    return dumps(scout_payload(team, map_name, side, since, phase))


def api(path: str, qs: dict) -> str:
    st = A.store()
    if path == "/api/meta":
        return dumps(meta_payload())
    if path == "/api/overview":
        return dumps(A.team_overview(st.team_id[_q(qs, "team")]))
    if path == "/api/scout":
        return _scout_cached(_q(qs, "team"), _q(qs, "map"), _q(qs, "side", "defense"), _q(qs, "since", ""),
                             _q(qs, "phase", "all"))
    if path == "/api/counter":
        return dumps(A.counter_for_hotspot(_q(qs, "map"), float(_q(qs, "x")), float(_q(qs, "y")), _q(qs, "ability")))
    if path == "/api/replay":
        from .replay import build_replay
        return dumps(build_replay(_q(qs, "game"), int(_q(qs, "round"))))
    raise KeyError(path)


class Handler(BaseHTTPRequestHandler):
    server_version = "CirrusScout/1.1"

    def log_message(self, fmt, *args):  # only log API calls
        if args and "/api/" in str(args[0]):
            super().log_message(fmt, *args)

    def _send(self, code, body: bytes, ctype="application/json", cache=False):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "max-age=86400" if cache else "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urlparse(self.path)
        path = url.path
        try:
            if path.startswith("/api/"):
                self._send(200, api(path, parse_qs(url.query)).encode())
                return
            f = (WEB_DIST / path.lstrip("/")).resolve()
            if not str(f).startswith(str(WEB_DIST.resolve())) or not f.is_file():
                f = WEB_DIST / "index.html"
            if not f.exists():
                self._send(503, b"Web app not built. Run: cd web && npm install && npm run build", "text/plain")
                return
            ctype = mimetypes.guess_type(str(f))[0] or "application/octet-stream"
            self._send(200, f.read_bytes(), ctype, cache=f.suffix in (".js", ".css", ".woff2", ".png"))
        except KeyError as exc:
            self._send(404, json.dumps({"error": f"unknown {exc}"}).encode())
        except Exception as exc:
            traceback.print_exc()
            self._send(500, json.dumps({"error": repr(exc)}).encode())


def serve(port: int = 8765, host: str = "127.0.0.1"):
    print("Loading store...")
    t0 = time.time()
    A.store()
    print(f"Ready in {time.time() - t0:.1f}s -> http://{host}:{port}")
    ThreadingHTTPServer((host, port), Handler).serve_forever()
