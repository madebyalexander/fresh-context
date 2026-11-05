#!/usr/bin/env python3
"""fresh-context hooks: handoff snapshots, a handoff list at session start, and a big-session nudge.

Usage (Claude Code runs these with the hook's JSON on stdin):
  lean_hooks.py session-start   SessionStart: list this folder's recent handoffs (startup, clear);
                                save the compaction summary (compact); warn on a cold-cache resume (resume, fork)
  lean_hooks.py prompt          UserPromptSubmit: tell you and Claude once the session passes the big-session size
  lean_hooks.py snapshot        PreCompact, SessionEnd: save last-session.md for this folder
  lean_hooks.py where [DIR]     print the handoff folder for DIR (default: the current folder)

Everything stays on this machine: no network, no model calls, nothing is executed from the transcript.
Files are written only under FRESH_CONTEXT_DIR (default: <CLAUDE_CONFIG_DIR or ~/.claude>/handoffs), mode 600.
Any error exits 0 with a one-line note on stderr: a hook never blocks or breaks a session.

Environment (set in your shell or in settings.json "env"):
  FRESH_CONTEXT_DISABLE=1         turn every hook off
  FRESH_CONTEXT_DIR=PATH          where handoffs and snapshots live
  FRESH_CONTEXT_SNAPSHOT=0        don't write last-session.md or compact-summary.md
  FRESH_CONTEXT_LIST=0            don't list handoffs at session start
  FRESH_CONTEXT_BIG_SESSION=N     context size in tokens for the nudge (default 150000; 0 turns it off)
  FRESH_CONTEXT_COLD_RESUME=N     warn when resuming at least N tokens with an expired cache (default 60000; 0 off)
  FRESH_CONTEXT_FRESH_DAYS=N      list handoffs changed in the last N days (default 21)"""
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime

INJECTED = ("<system-reminder", "<command-", "<local-command", "<task-notification", "<user-prompt-submit-hook", "<bash-")


# --- settings -------------------------------------------------------------------------------------------

def env_int(name, default):
    v = os.environ.get(name, "").strip().lower().replace("_", "")
    if not v:
        return default
    try:
        return int(float(v[:-1]) * 1000) if v.endswith("k") else int(v)
    except ValueError:
        return default


def env_on(name, default=True):
    v = os.environ.get(name, "").strip().lower()
    return default if not v else v not in ("0", "false", "no", "off")


def config_dir():
    return os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")


def root():
    return os.path.abspath(os.path.expanduser(os.environ.get("FRESH_CONTEXT_DIR") or os.path.join(config_dir(), "handoffs")))


def slug(cwd):
    s = re.sub(r"[^A-Za-z0-9]", "-", cwd or "unknown")
    return s if len(s) <= 200 else s[:180] + "-" + hashlib.sha1(cwd.encode()).hexdigest()[:12]


def folder(cwd, create=False):
    d = os.path.join(root(), slug(cwd))
    if create:
        os.makedirs(d, mode=0o700, exist_ok=True)
    return d


def write_private(path, text):
    tmp = f"{path}.tmp-{os.getpid()}"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


# --- per-session state (tiny JSON files under <root>/.state) ---------------------------------------------

def state_path(sid):
    return os.path.join(root(), ".state", (re.sub(r"[^A-Za-z0-9-]", "", sid or "") or "none")[:80] + ".json")


def load_state(sid):
    try:
        with open(state_path(sid), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def save_state(sid, data, tidy=False):
    d = os.path.dirname(state_path(sid))
    os.makedirs(d, mode=0o700, exist_ok=True)
    write_private(state_path(sid), json.dumps(data))
    if tidy:  # forget sessions older than 30 days
        for f in os.listdir(d):
            q = os.path.join(d, f)
            try:
                if f.endswith(".json") and time.time() - os.path.getmtime(q) > 30 * 86400:
                    os.remove(q)
            except OSError:
                pass


# --- transcript reading (JSON parsing only; the format is internal to Claude Code) ----------------------

def tail_lines(path, size):
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            end = f.tell()
            f.seek(max(0, end - size))
            raw = f.read().decode("utf-8", "replace")
    except (OSError, TypeError):
        return []
    lines = raw.split("\n")
    return lines[1:] if end > size else lines


def parse(line):
    try:
        o = json.loads(line)
    except ValueError:
        return None
    return o if isinstance(o, dict) else None


def usage_ctx(o):
    u = (o.get("message") or {}).get("usage") if isinstance(o.get("message"), dict) else None
    if not isinstance(u, dict):
        return None
    return sum(int(u.get(k) or 0) for k in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))


def context_now(path):
    """Context size of the newest model request in the transcript (0 if unknown)."""
    for line in reversed(tail_lines(path, 1_000_000)):
        if '"usage"' in line and '"assistant"' in line:
            o = parse(line)
            if o and o.get("type") == "assistant":
                ctx = usage_ctx(o)
                if ctx is not None:
                    return ctx
    return 0


COMMAND = re.compile(r"<command-name>(.*?)</command-name>(?:.*?<command-args>(.*?)</command-args>)?", re.S)


def text_of(content, prompts_only=False):
    """Plain text of a message. With prompts_only, injected blocks are dropped and slash commands shown as typed."""
    def clean(t):
        if not prompts_only:
            return t
        m = COMMAND.search(t)
        if m:
            return f"{m.group(1).strip()} {(m.group(2) or '').strip()}".strip()
        return "" if t.lstrip().startswith(INJECTED) else t
    if isinstance(content, str):
        return clean(content)
    if isinstance(content, list):
        return "\n".join(clean(c.get("text", "")) for c in content if isinstance(c, dict) and c.get("type") == "text")
    return ""


# --- best-effort redaction of things that look like secrets ---------------------------------------------

SECRETS = [re.compile(p, f) for p, f in (
    (r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
    (r"\b(?:sk|rk)-[A-Za-z0-9_-]{16,}", 0),
    (r"\bgh[pousr]_[A-Za-z0-9]{20,}", 0),
    (r"\bgithub_pat_[A-Za-z0-9_]{20,}", 0),
    (r"\bglpat-[A-Za-z0-9_-]{20,}", 0),
    (r"\bxox[abprs]-[A-Za-z0-9-]{10,}", 0),
    (r"\bAKIA[0-9A-Z]{16}\b", 0),
    (r"\bAIza[0-9A-Za-z_-]{30,}", 0),
    (r"\bfigd_[A-Za-z0-9_-]{20,}", 0),
    (r"\bnpm_[A-Za-z0-9]{30,}", 0),
    (r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}", 0),
)]
KEY_VALUE = re.compile(r"(?i)(\b(?:api[_-]?key|[a-z]*[_-]?token|secret|password|passwd)\b\s*[:=]\s*[\"']?)([^\s\"']{8,})")
BEARER = re.compile(r"(?i)(\bbearer\s+)[A-Za-z0-9._~+/=-]{16,}")


def redact(s):
    for rx in SECRETS:
        s = rx.sub("[redacted]", s)
    s = KEY_VALUE.sub(lambda m: m.group(1) + "[redacted]", s)
    return BEARER.sub(lambda m: m.group(1) + "[redacted]", s)


# --- the hooks ------------------------------------------------------------------------------------------

def start_cwd(inp):
    return load_state(inp.get("session_id", "")).get("cwd") or inp.get("cwd") or os.getcwd()


def local_time(ts):
    """Transcript timestamps are UTC ISO strings; show them in local time like the rest of the note."""
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00")).astimezone().strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return str(ts)[:16].replace("T", " ")


def snapshot(inp):
    if not env_on("FRESH_CONTEXT_SNAPSHOT") or inp.get("agent_id"):
        return
    path, cwd = inp.get("transcript_path"), start_cwd(inp)
    prompts, files, last_report, ctx, model = [], [], "", 0, ""
    for line in tail_lines(path, 4_000_000) if path else []:
        o = parse(line)
        if not o:
            continue
        m = o.get("message") if isinstance(o.get("message"), dict) else {}
        if o.get("type") == "user" and not o.get("isCompactSummary") and not o.get("isMeta"):
            t = text_of(m.get("content"), prompts_only=True).strip()
            if t:
                prompts.append((str(o.get("timestamp", "")), t))
        elif o.get("type") == "assistant":
            ctx = usage_ctx(o) or ctx
            model = m.get("model") or model
            for c in m.get("content") or []:
                if not isinstance(c, dict):
                    continue
                if c.get("type") == "text" and str(c.get("text", "")).strip():
                    last_report = c["text"].strip()
                elif c.get("type") == "tool_use" and c.get("name") in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
                    fp = (c.get("input") or {}).get("file_path") or (c.get("input") or {}).get("notebook_path")
                    if isinstance(fp, str):
                        files.append(fp)
    if not prompts:  # nothing worth saving; keep the previous snapshot
        return
    event = inp.get("hook_event_name") or "snapshot"
    why = inp.get("trigger") or inp.get("reason")
    out = [f"# Last session here - {datetime.now().strftime('%Y-%m-%d %H:%M')}", "",
           f"- Saved on: {event}{f' ({why})' if why else ''} · context then: ~{ctx // 1000}k tokens · model: {model or 'unknown'}",
           f"- Folder: {cwd}",
           f"- Transcript: {path}", "",
           "## Last requests (newest first)"]
    out += [f"- {local_time(ts)} - {t[:400].replace(chr(10), ' ')}" for ts, t in reversed(prompts[-6:])]
    if files:
        out += ["", "## Files changed"] + [f"- {p}" for p in list(dict.fromkeys(reversed(files)))[:25]]
    if last_report:
        out += ["", "## Last report", last_report[:2500]]
    out += ["", "Handoff notes written with /handoff live next to this file.", ""]
    write_private(os.path.join(folder(cwd, create=True), "last-session.md"), redact("\n".join(out)))


def save_compact_summary(inp):
    if not env_on("FRESH_CONTEXT_SNAPSHOT") or inp.get("agent_id"):
        return
    path, cwd = inp.get("transcript_path"), start_cwd(inp)
    if not path:
        return
    for _ in range(6):  # Claude Code writes the summary a moment after the hook starts
        for line in reversed(tail_lines(path, 3_000_000)):
            if '"isCompactSummary":true' in line.replace(" ", ""):
                o = parse(line)
                if o:
                    text = text_of((o.get("message") or {}).get("content"))
                    if text:
                        ts = local_time(o.get("timestamp", ""))
                        write_private(os.path.join(folder(cwd, create=True), "compact-summary.md"),
                                      redact(f"# Compaction summary - {ts}\n\n{text}\n"))
                        return
        time.sleep(0.4)


def handoff_list(cwd):
    d = folder(cwd)
    if not os.path.isdir(d):
        return ""
    fresh = env_int("FRESH_CONTEXT_FRESH_DAYS", 21) * 86400
    items = []
    for f in os.listdir(d):
        q = os.path.join(d, f)
        try:
            mt = os.path.getmtime(q)
        except OSError:
            continue
        if f.endswith(".md") and time.time() - mt < fresh:
            items.append((mt, f, q))
    if not items:
        return ""
    items.sort(reverse=True)
    lines = [f"Handoffs for this folder (newest first; folder: {d}). Read one only if the user continues earlier work "
             "(\"continue\", \"pick up\", or names it):"]
    for mt, f, q in items[:6]:
        note = ""
        try:
            with open(q, encoding="utf-8", errors="replace") as fh:
                body = fh.read(4000).split("\n")
            if f == "last-session.md":
                req = next((x for x in body if x.startswith("- 20")), "")
                note = "last request: " + req.split(" - ", 1)[-1][:120] if req else "automatic snapshot"
            elif f == "compact-summary.md":
                note = "latest compaction summary"
            else:
                i = next((n for n, x in enumerate(body) if x.strip().lower().startswith("## now")), None)
                rest = body[i + 1:] if i is not None else body[1:]
                note = next((x.strip("#- ").strip() for x in rest if x.strip() and not x.startswith("#")), "")[:120]
        except OSError:
            pass
        lines.append(f"- {q} · {datetime.fromtimestamp(mt).strftime('%m-%d %H:%M')}" + (f" · {note}" if note else ""))
    return "\n".join(lines)


def session_start(inp):
    sid, src = inp.get("session_id", ""), inp.get("source", "")
    st = load_state(sid)
    st.setdefault("cwd", inp.get("cwd") or os.getcwd())
    save_state(sid, st, tidy=True)
    if src == "compact":
        save_compact_summary(inp)
        return None
    if src in ("resume", "fork"):
        limit = env_int("FRESH_CONTEXT_COLD_RESUME", 60_000)
        n = inp.get("context_tokens")
        if limit > 0 and inp.get("prompt_cache_likely_expired") and isinstance(n, (int, float)) and n >= limit:
            usd = inp.get("estimated_cache_write_usd")
            cost = f" (about ${usd:.2f})" if isinstance(usd, (int, float)) else ""
            return {"systemMessage": f"fresh-context: resuming ~{int(n) // 1000}k tokens with a cold cache; your next message "
                                     f"re-caches all of it{cost}. Cheaper: /clear, then say \"pick up\" to continue from the handoff."}
        return None
    if src in ("startup", "clear") and env_on("FRESH_CONTEXT_LIST"):
        text = handoff_list(st["cwd"])
        if text:
            return {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}
    return None


def prompt(inp):
    big = env_int("FRESH_CONTEXT_BIG_SESSION", 150_000)
    if big <= 0 or inp.get("agent_id"):
        return None
    sid = inp.get("session_id", "")
    ctx = context_now(inp.get("transcript_path"))
    st = load_state(sid)
    if ctx < big:
        if st.pop("nudged", None) is not None:  # compacted or cleared: arm the nudge again
            save_state(sid, st)
        return None
    last = st.get("nudged") or 0
    if last and ctx < last + max(big // 3, 10_000):
        return None
    st["nudged"] = ctx
    save_state(sid, st)
    n = ctx // 1000
    return {
        "systemMessage": f"fresh-context: this session is ~{n}k tokens and every request re-sends it. "
                         f"For new work: /handoff, then /clear and \"pick up\".",
        "hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext":
            f"fresh-context: the conversation is ~{n}k tokens and every tool call re-sends all of it. Answer questions and make "
            f"small edits here. If this prompt starts a new, unrelated task, suggest saving a handoff (/handoff) and "
            f"continuing in a fresh session (/clear, then \"pick up\"), or run the task in a subagent with a "
            f"self-contained brief that points at the handoff."},
    }


def main(argv):
    ev = argv[0] if argv else ""
    if ev in ("", "-h", "--help"):
        print(__doc__.strip())
        return
    if ev == "where":
        print(folder(os.path.abspath(argv[1]) if len(argv) > 1 else os.getcwd()))
        return
    if env_on("FRESH_CONTEXT_DISABLE", default=False):
        return
    try:
        inp = json.load(sys.stdin)
    except ValueError:
        inp = {}
    if not isinstance(inp, dict):
        inp = {}
    if ev == "session-start":
        out = session_start(inp)
    elif ev == "prompt":
        out = prompt(inp)
    elif ev == "snapshot":
        out = snapshot(inp)
    else:
        sys.stderr.write(f"fresh-context hook: unknown event {ev!r} (lean_hooks.py --help)\n")
        return
    if out:
        print(json.dumps(out))


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except Exception as e:  # a hook must never break the session
        sys.stderr.write(f"fresh-context hook: {type(e).__name__}: {e}\n")
    sys.exit(0)
