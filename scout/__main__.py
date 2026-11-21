"""Command line: python -m scout {extract,build,serve,export,all}"""
from __future__ import annotations

import argparse


def main():
    ap = argparse.ArgumentParser(prog="scout", description="Cloud9 VALORANT tactical scouting")
    sub = ap.add_subparsers(dest="cmd", required=True)
    ex = sub.add_parser("extract", help="stream every GRID series into the local cache")
    ex.add_argument("--workers", type=int, default=None)
    ex.add_argument("--series", nargs="*", help="only these series ids")
    sub.add_parser("build", help="combine the cache into the analysis store + map plans")
    sv = sub.add_parser("serve", help="run the scouting app locally")
    sv.add_argument("--port", type=int, default=8765)
    sv.add_argument("--host", default="127.0.0.1")
    exp = sub.add_parser("export", help="write the aggregate-only static demo into web/public/data")
    exp.add_argument("--teams", nargs="*", help="team names to export (default: Cloud9 teams + most-played)")
    sub.add_parser("all", help="extract + build")
    a = ap.parse_args()

    if a.cmd in ("extract", "all"):
        from .pipeline import extract_all
        extract_all(getattr(a, "workers", None), set(a.series) if getattr(a, "series", None) else None)
    if a.cmd in ("build", "all"):
        from .build import build_store
        build_store()
    if a.cmd == "serve":
        from .server import serve
        serve(a.port, a.host)
    if a.cmd == "export":
        from .export import export_static
        export_static(a.teams)


if __name__ == "__main__":
    main()
