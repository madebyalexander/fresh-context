#!/usr/bin/env python3
"""fresh-context status line: model, context size, cache state and plan usage, in one short line.

  Opus · ctx 182k/1M 18% · cache warm · 5h 23% · 7d 41%

Context turns amber at FRESH_CONTEXT_BIG_SESSION tokens (default 150000) and red at 1.5x that: a sign to
/handoff and /clear before new work. Every part is shown only when Claude Code provides it.
Install: add to your settings.json
  "statusLine": {"type": "command", "command": "python3 /absolute/path/to/statusline.py"}
It reads only the JSON Claude Code passes on stdin; it reads no files and writes none."""
import json
import os
import sys

if sys.argv[1:2] in (["-h"], ["--help"]):
    print(__doc__.strip())
    sys.exit(0)

AMB, RED, OFF = "\033[33m", "\033[31m", "\033[0m"


def num(v, default=0):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else default


def k(n):
    return f"{n / 1_000_000:.1f}M".replace(".0M", "M") if n >= 1_000_000 else f"{round(n / 1000)}k"


def main():
    try:
        d = json.load(sys.stdin)
    except ValueError:
        d = {}
    if not isinstance(d, dict):
        d = {}
    try:
        big = int(os.environ.get("FRESH_CONTEXT_BIG_SESSION") or 150_000)
    except ValueError:
        big = 150_000
    parts = []
    name = (d.get("model") or {}).get("display_name")
    if name:
        parts.append(str(name))
    cw = d.get("context_window") or {}
    cu = cw.get("current_usage") or {}
    used = sum(num(cu.get(x)) for x in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
    size = num(cw.get("context_window_size"))
    if used:
        col = RED if big and used >= big * 1.5 else AMB if big and used >= big else ""
        txt = f"ctx {k(used)}" + (f"/{k(size)} {round(100 * used / size)}%" if size else "")
        parts.append(f"{col}{txt}{OFF}" if col else txt)
    pc = d.get("prompt_cache")
    if isinstance(pc, dict) and "warm" in pc:
        parts.append("cache warm" if pc.get("warm") else f"{AMB}cache cold{OFF}")
    rl = d.get("rate_limits") or {}
    for key, label in (("five_hour", "5h"), ("seven_day", "7d")):
        v = (rl.get(key) or {}).get("used_percentage")
        if isinstance(v, (int, float)):
            col = RED if v >= 85 else AMB if v >= 65 else ""
            parts.append(f"{col}{label} {round(v)}%{OFF}" if col else f"{label} {round(v)}%")
    print(" · ".join(parts))


try:
    main()
except Exception:  # a status line must never break the UI
    print("")
