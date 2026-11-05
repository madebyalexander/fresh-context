#!/usr/bin/env python3
"""fresh-context checks on synthetic data. Prints only failures, then a pass line. Exit 1 on any failure.

Nothing here reads real transcripts or writes outside a temporary folder (HOME is pointed there too).
"""
import json
import os
import py_compile
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(REPO, "skills", "working-lean", "scripts")
HOOKS = os.path.join(SCRIPTS, "lean_hooks.py")
TMP = tempfile.mkdtemp(prefix="fresh-context test ")  # a space on purpose
HOME = os.path.join(TMP, "home dir")
ROOT = os.path.join(TMP, "notes root")
PROJ = os.path.join(TMP, "my project")
for d in (HOME, PROJ):
    os.makedirs(d)

passed, failed = 0, []


def ok(cond, label, detail=""):
    global passed
    if cond:
        passed += 1
    else:
        failed.append(f"FAIL {label}" + (f"\n     {str(detail)[:600]}" if detail != "" else ""))


def env(**kw):
    e = {k: v for k, v in os.environ.items() if not k.startswith(("FRESH_CONTEXT_", "CLAUDE_"))}
    e.update(HOME=HOME, FRESH_CONTEXT_DIR=ROOT, CLAUDE_CONFIG_DIR=os.path.join(HOME, ".claude"))
    e.update({k: str(v) for k, v in kw.items()})
    return {k: v for k, v in e.items() if v != "None"}


def run(args, stdin=None, cwd=None, **kw):
    t = time.time()
    p = subprocess.run(args, input=stdin, capture_output=True, text=True, cwd=cwd or PROJ, env=env(**kw), timeout=60)
    p.secs = time.time() - t
    return p


def hook(event, payload, **kw):
    data = payload if isinstance(payload, str) else json.dumps(payload)
    p = run([sys.executable, HOOKS, event], stdin=data, **kw)
    try:
        p.json = json.loads(p.stdout) if p.stdout.strip() else None
    except ValueError:
        p.json = "not json: " + p.stdout
    return p


def transcript(name, prompts=(), ctxs=(), extra=()):
    """A synthetic transcript: one user prompt, then one assistant request per ctx value."""
    path = os.path.join(TMP, "transcripts", name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    lines, n = [], 0
    for i, pr in enumerate(prompts):
        lines.append({"type": "user", "timestamp": f"2026-01-0{i + 1}T10:00:00Z", "message": {"role": "user", "content": pr}})
        lines.append({"type": "user", "message": {"role": "user", "content": [{"type": "text", "text": "<system-reminder>injected</system-reminder>"}]}})
        for c in (ctxs[i] if i < len(ctxs) else []):
            n += 1
            lines.append({"type": "assistant", "timestamp": f"2026-01-0{i + 1}T10:0{n % 10}:00Z", "message": {
                "id": f"msg_{n}", "model": "test-model",
                "usage": {"input_tokens": 1000, "cache_read_input_tokens": c - 1000, "cache_creation_input_tokens": 0, "output_tokens": 50},
                "content": [{"type": "text", "text": f"reply {n}"}]}})
    lines += list(extra)
    with open(path, "w") as f:
        f.write("\n".join(json.dumps(x) for x in lines) + "\n")
        f.write("{this line is not json\n")
    return path


def base(sid="s1", **kw):
    d = {"session_id": sid, "cwd": PROJ}
    d.update(kw)
    if "transcript_path" not in d:
        d["transcript_path"] = transcript(f"{sid}.jsonl", ["hello"], [[20_000]])
    return d


NOTES = os.path.join(ROOT, re.sub(r"[^A-Za-z0-9]", "-", PROJ))

# ---------------------------------------------------------------- syntax and layout
for f in ("jpick", "outline", "tokens", "statusline.py", "lean_hooks.py"):
    try:
        py_compile.compile(os.path.join(SCRIPTS, f), cfile=os.path.join(TMP, "pyc", f + ".pyc"), doraise=True)
        ok(True, f)
    except py_compile.PyCompileError as e:
        ok(False, f"python syntax: {f}", e)
p = run(["bash", "-n", os.path.join(SCRIPTS, "quiet")])
ok(p.returncode == 0, "bash syntax: quiet", p.stderr)
for f in ("quiet", "jpick", "outline", "tokens", "statusline.py", "lean_hooks.py"):
    path = os.path.join(SCRIPTS, f)
    ok(os.stat(path).st_mode & stat.S_IXUSR, f"executable bit: {f}")
    p = run([path, "--help"])
    ok(p.returncode == 0 and len(p.stdout) > 40, f"--help works: {f}", p.stderr or p.stdout)

# ---------------------------------------------------------------- manifests and skills
def load(rel):
    with open(os.path.join(REPO, rel)) as fh:
        return json.load(fh)


plugin, market, hooks = load(".claude-plugin/plugin.json"), load(".claude-plugin/marketplace.json"), load("hooks/hooks.json")
ok(plugin.get("name") == "fresh-context" and re.fullmatch(r"\d+\.\d+\.\d+", plugin.get("version", "")), "plugin.json name and version")
ok(market["plugins"][0]["name"] == plugin["name"], "marketplace lists the plugin by the same name")
events = set(hooks["hooks"])
ok(events == {"SessionStart", "UserPromptSubmit", "PreCompact", "SessionEnd"}, "hooks.json events", events)
for ev, groups in hooks["hooks"].items():
    for h in (x for g in groups for x in g["hooks"]):
        m = re.search(r'"\$\{CLAUDE_PLUGIN_ROOT\}/([^"]+)" (\S+)$', h["command"])
        ok(m and os.path.isfile(os.path.join(REPO, m.group(1))), f"{ev} hook script exists", h["command"])
        ok(m and m.group(2) in ("session-start", "prompt", "snapshot"), f"{ev} hook subcommand", h["command"])
        ok(0 < h.get("timeout", 0) <= 10, f"{ev} hook timeout set and short")
for name in os.listdir(os.path.join(REPO, "skills")):
    with open(os.path.join(REPO, "skills", name, "SKILL.md")) as fh:
        text = fh.read()
    fm = re.match(r"---\n(.*?)\n---\n", text, re.S)
    ok(fm, f"{name}: frontmatter")
    meta = dict(re.findall(r"^(\w[\w-]*): (.*)$", fm.group(1) if fm else "", re.M))
    ok(meta.get("name") == name, f"{name}: name matches folder", meta.get("name"))
    ok(40 < len(meta.get("description", "")) <= 1024, f"{name}: description length", len(meta.get("description", "")))
    for up, ref in re.findall(r"(\.\./working-lean/)?((?:scripts|references)/[\w./-]*\w)", text):
        ok(os.path.exists(os.path.join(REPO, "skills", "working-lean" if up else name, ref)), f"{name}: {up}{ref} exists")

# ---------------------------------------------------------------- quiet, jpick, outline, statusline
p = run([os.path.join(SCRIPTS, "quiet"), "bash", "-c", 'for i in $(seq 1 500); do echo "line $i"; done; echo "Error: boom" >&2; exit 3'])
ok(p.returncode == 3, "quiet keeps the exit code", p.returncode)
ok(p.stdout.count("\n") < 45 and "exit 3" in p.stdout and "Error: boom" in p.stdout and "line 500" in p.stdout, "quiet output is short and keeps errors + tail", p.stdout)
log = re.search(r"full log: (.+)$", p.stdout.splitlines()[0]) if p.stdout else None
ok(log and os.path.isfile(log.group(1)) and "line 250" in open(log.group(1)).read(), "quiet keeps the full log", p.stdout[:200])
if log:
    os.remove(log.group(1))
jf = os.path.join(TMP, "data file.json")
with open(jf, "w") as fh:
    json.dump({"items": [{"name": "a", "big": "x" * 5000}, {"name": "b"}], "meta": {"x": 1}}, fh)
p = run([os.path.join(SCRIPTS, "jpick"), jf, "items[*].name", "meta.x"])
ok(p.returncode == 0 and p.stdout.splitlines() == ['items[*].name = ["a","b"]', "meta.x = 1"], "jpick picks paths", p.stdout + p.stderr)
p = run([os.path.join(SCRIPTS, "jpick"), jf])
ok(p.returncode == 0 and "items" in p.stdout and "xxxx" not in p.stdout, "jpick with no path lists top-level keys", p.stdout)
p = run([os.path.join(SCRIPTS, "jpick"), "-"], stdin="{broken")
ok(p.returncode == 1 and p.stderr, "jpick rejects bad JSON clearly", p.stderr)
pyf = os.path.join(TMP, "big module.py")
with open(pyf, "w") as fh:
    fh.write("\n".join(f"x{i} = {i}" for i in range(300)) + "\nclass Ledger:\n    def normalize_amount(self, v):\n        return max(v, 0)\n")
p = run([os.path.join(SCRIPTS, "outline"), pyf, "--grep", "normalize"])
ok(p.returncode == 0 and re.search(r"\b302\b.*normalize_amount", p.stdout) and p.stdout.count("\n") <= 3, "outline finds a method with its line", p.stdout)
p = run([os.path.join(SCRIPTS, "outline"), os.path.join(TMP, "missing.py")])
ok(p.returncode == 1, "outline: missing file exits 1", p.returncode)
sl = {"model": {"display_name": "Opus"}, "context_window": {"context_window_size": 1_000_000, "used_percentage": 18,
      "current_usage": {"input_tokens": 1000, "cache_read_input_tokens": 181_000, "cache_creation_input_tokens": 0}},
      "rate_limits": {"five_hour": {"used_percentage": 23}, "seven_day": {"used_percentage": 41}}}
p = run([sys.executable, os.path.join(SCRIPTS, "statusline.py")], stdin=json.dumps(sl))
plain = re.sub(r"\x1b\[[0-9;]*m", "", p.stdout)
ok(p.returncode == 0 and "Opus" in plain and "182k" in plain and "5h 23%" in plain, "statusline shows model, context and limits", plain)
p = run([sys.executable, os.path.join(SCRIPTS, "statusline.py")], stdin="garbage")
ok(p.returncode == 0 and p.stdout.strip() == "", "statusline: bad input prints an empty line", p.stdout + p.stderr)

# ---------------------------------------------------------------- tokens
proj_dir = os.path.join(TMP, "transcripts for tokens")
os.makedirs(proj_dir)
a = transcript("a.jsonl", ["first ask", "second ask"], [[100_000, 120_000], [140_000]])
with open(a) as fh:
    dup = [ln for ln in fh if '"msg_2"' in ln]
with open(a, "a") as fh:
    fh.write(dup[0])  # the same request logged twice must count once
shutil.copy(a, os.path.join(proj_dir, "a.jsonl"))
time.sleep(0.01)
shutil.copy(transcript("b.jsonl", ["only ask"], [[10_000, 30_000]]), os.path.join(proj_dir, "b.jsonl"))
tok = os.path.join(SCRIPTS, "tokens")
p = run([sys.executable, tok, "-n", "2", "--dir", proj_dir])
ok(p.returncode == 0 and re.search(r"3 req\s+avg ctx\s+120k", p.stdout) and re.search(r"2 req\s+avg ctx\s+20k", p.stdout), "tokens -n: per-session lines, duplicates counted once", p.stdout + p.stderr)
ok(re.search(r"average context per request over these sessions: 80k \(5 requests\)", p.stdout), "tokens -n: average line", p.stdout)
p = run([sys.executable, tok, os.path.join(proj_dir, "a.jsonl")])
ok(p.returncode == 0 and "first ask" in p.stdout and "second ask" in p.stdout and "injected" not in p.stdout, "tokens FILE: one line per prompt, injected text skipped", p.stdout)
p = run([sys.executable, tok, "--dir", os.path.join(TMP, "nothing here")])
ok(p.returncode == 1 and p.stderr.strip(), "tokens: no transcripts exits 1 with a message", p.stdout + p.stderr)

# ---------------------------------------------------------------- hooks: list, compact, resume
p = run([sys.executable, HOOKS, "where", "/tmp/a b"])
ok(p.stdout.strip() == os.path.join(ROOT, "-tmp-a-b"), "where: slug of a path with spaces", p.stdout)
p = run([sys.executable, HOOKS, "where", "/x" * 150])
ok(len(os.path.basename(p.stdout.strip())) <= 200, "where: long paths are shortened", p.stdout)
p = run([sys.executable, HOOKS, "where", "/tmp/a b"], FRESH_CONTEXT_DIR=None)
ok(p.stdout.strip() == os.path.join(HOME, ".claude", "handoffs", "-tmp-a-b"), "where: default root follows CLAUDE_CONFIG_DIR", p.stdout)
p = hook("session-start", base(source="startup"))
ok(p.returncode == 0 and p.json is None and not p.stderr, "session-start: nothing to list, no output", p.stdout + p.stderr)
os.makedirs(NOTES)
with open(os.path.join(NOTES, "parser.md"), "w") as fh:
    fh.write("# Parser - handoff\n## Now\nShip the date parser; next: fix rounding\n## Open\n- x\n")
old = os.path.join(NOTES, "ancient.md")
with open(old, "w") as fh:
    fh.write("# Old\n## Now\nlong done\n")
os.utime(old, (time.time() - 40 * 86400,) * 2)
p = hook("session-start", base(source="startup"))
ctx = (p.json or {}).get("hookSpecificOutput", {}).get("additionalContext", "") if isinstance(p.json, dict) else ""
ok("parser.md" in ctx and "Ship the date parser" in ctx and "ancient" not in ctx and NOTES in ctx, "session-start: lists fresh notes with their Now line", p.stdout)
p = hook("session-start", base(source="startup"), FRESH_CONTEXT_LIST=0)
ok(p.json is None, "session-start: FRESH_CONTEXT_LIST=0 lists nothing", p.stdout)
p = hook("session-start", base(source="startup"), FRESH_CONTEXT_FRESH_DAYS=60)
ok("ancient.md" in p.stdout, "session-start: FRESH_CONTEXT_FRESH_DAYS widens the list", p.stdout)
summary = {"type": "user", "isCompactSummary": True, "timestamp": "2026-01-02T11:00:00Z",
           "message": {"role": "user", "content": "This session is being continued. Summary: parser work, token=" + "q7" * 8}}
p = hook("session-start", base("s2", source="compact", transcript_path=transcript("s2.jsonl", ["go"], [[5000]], [summary])))
cs = os.path.join(NOTES, "compact-summary.md")
ok(os.path.isfile(cs) and "parser work" in open(cs).read() and p.secs < 1.5, "session-start (compact): saves the summary quickly", p.secs)
ok(os.path.isfile(cs) and "q7q7q7q7" not in open(cs).read(), "compact summary is redacted")
cold = base("s3", source="resume", context_tokens=200_000, prompt_cache_likely_expired=True, estimated_cache_write_usd=1.5)
p = hook("session-start", cold)
ok(isinstance(p.json, dict) and "200k" in p.json.get("systemMessage", "") and "$1.50" in p.json["systemMessage"], "resume: cold cache warning", p.stdout)
p = hook("session-start", dict(cold, prompt_cache_likely_expired=False))
ok(p.json is None, "resume: warm cache, no warning", p.stdout)
p = hook("session-start", dict(cold, context_tokens=30_000))
ok(p.json is None, "resume: small session, no warning", p.stdout)
p = hook("session-start", cold, FRESH_CONTEXT_COLD_RESUME=0)
ok(p.json is None, "resume: FRESH_CONTEXT_COLD_RESUME=0 turns it off", p.stdout)

# ---------------------------------------------------------------- hooks: the big-session nudge
def nudge(ctx_k, **kw):
    return hook("prompt", {"session_id": "n1", "cwd": PROJ, "transcript_path": transcript("n1.jsonl", ["p"], [[ctx_k * 1000]]), "prompt": "next"}, **kw)


seq = [(100, False), (160, True), (170, False), (209, False), (215, True), (20, False), (160, True)]
got = []
for k, want in seq:
    p = nudge(k)
    got.append((k, isinstance(p.json, dict)))
    ok(isinstance(p.json, dict) == want, f"nudge at {k}k: {'shown' if want else 'quiet'}", got)
p = nudge(160)
ok(p.json is None, "nudge: not repeated without growth")
ok(isinstance(nudge(400).json, dict) and "~500k" in nudge(500).json["systemMessage"], "nudge: repeats as the session grows")
p = hook("prompt", {"session_id": "n2", "cwd": PROJ, "transcript_path": transcript("n2.jsonl", ["p"], [[120_000]])}, FRESH_CONTEXT_BIG_SESSION="100k")
ok(isinstance(p.json, dict) and "additionalContext" in p.json.get("hookSpecificOutput", {}), "nudge: threshold accepts 100k and adds context for Claude", p.stdout)
ok("decision" not in p.stdout, "nudge never blocks")
p = hook("prompt", {"session_id": "n3", "cwd": PROJ, "transcript_path": transcript("n3.jsonl", ["p"], [[900_000]])}, FRESH_CONTEXT_BIG_SESSION=0)
ok(p.json is None, "nudge: FRESH_CONTEXT_BIG_SESSION=0 turns it off", p.stdout)
p = hook("prompt", {"session_id": "n4", "agent_id": "sub", "transcript_path": transcript("n4.jsonl", ["p"], [[900_000]])})
ok(p.json is None, "nudge: skipped for subagents", p.stdout)

# ---------------------------------------------------------------- hooks: snapshot
secrets = ["".join(("gh", "p_")) + "Ab3" * 10, "".join(("sk", "-")) + "live" * 6, "AKIA" + "Q" * 16, "hunter2" * 3]
edit = {"type": "assistant", "message": {"id": "msg_e", "model": "test-model", "usage": {"input_tokens": 9000}, "content": [
    {"type": "tool_use", "name": "Edit", "input": {"file_path": "/work/my app/a b.py"}},
    {"type": "text", "text": f"Done. Fixed rounding. Left a key {secrets[0]} in the reply by mistake."}]}}
prompts = [f"ask number {i}" for i in range(1, 8)] + ["<command-message>x</command-message>\n<command-name>/fresh-context:handoff</command-name>\n<command-args>billing</command-args>"] + [f"use {secrets[1]} and AWS {secrets[2]} with password={secrets[3]}"]
tp = transcript("s5.jsonl", prompts, [[5000]] * 9, [edit])
p = hook("snapshot", {"session_id": "s5", "cwd": PROJ, "transcript_path": tp, "hook_event_name": "SessionEnd", "reason": "clear"})
ls = os.path.join(NOTES, "last-session.md")
body = open(ls).read() if os.path.isfile(ls) else ""
ok(p.returncode == 0 and body.startswith("# Last session here"), "snapshot: writes last-session.md", p.stderr)
ok("SessionEnd (clear)" in body and "~9k tokens" in body and "test-model" in body, "snapshot: event, context and model", body[:400])
ok("/fresh-context:handoff billing" in body and body.index("ask number 7") < body.index("ask number 4") and "ask number 3" not in body and "injected" not in body, "snapshot: last 6 prompts, newest first, injected text skipped", body)
ok("/work/my app/a b.py" in body and "Fixed rounding" in body, "snapshot: files changed and last report", body)
ok(not any(s in body for s in secrets) and body.count("[redacted]") >= 4, "snapshot: secrets redacted", [s[:6] for s in secrets if s in body])
other = os.path.join(TMP, "other project")
hook("snapshot", {"session_id": "s5b", "cwd": other, "transcript_path": tp})
made = os.path.join(ROOT, re.sub(r"[^A-Za-z0-9]", "-", other))
ok(stat.S_IMODE(os.stat(ls).st_mode) == 0o600 and stat.S_IMODE(os.stat(made).st_mode) == 0o700, "snapshot: file 600, new folder 700")
st = os.path.join(ROOT, ".state")
ok(all(stat.S_IMODE(os.stat(os.path.join(st, f)).st_mode) == 0o600 for f in os.listdir(st)), "state files are 600")
before = open(ls).read()
hook("snapshot", {"session_id": "s6", "cwd": PROJ, "transcript_path": transcript("s6.jsonl", [], [])})
ok(open(ls).read() == before, "snapshot: a session with no prompts keeps the previous snapshot")
hook("snapshot", {"session_id": "s7", "agent_id": "sub", "cwd": PROJ, "transcript_path": transcript("s7.jsonl", ["sub ask"], [[1]])})
ok("sub ask" not in open(ls).read(), "snapshot: skipped for subagents")
hook("snapshot", {"session_id": "s8", "cwd": PROJ, "transcript_path": transcript("s8.jsonl", ["off ask"], [[1]])}, FRESH_CONTEXT_SNAPSHOT=0)
ok("off ask" not in open(ls).read(), "snapshot: FRESH_CONTEXT_SNAPSHOT=0 writes nothing")
# the snapshot goes to the folder the session started in, even after a cd
hook("session-start", {"session_id": "s9", "cwd": PROJ, "source": "startup"})
hook("snapshot", {"session_id": "s9", "cwd": os.path.join(PROJ, "sub dir"), "transcript_path": transcript("s9.jsonl", ["after cd"], [[1]])})
ok("after cd" in open(ls).read(), "snapshot: uses the session's starting folder")

# ---------------------------------------------------------------- hooks: safety
for ev in ("session-start", "prompt", "snapshot"):
    for bad in ("", "not json", "[1, 2]", json.dumps({"transcript_path": os.path.join(TMP, "missing.jsonl"), "source": "startup"}),
                json.dumps({"transcript_path": "$(touch pwned)", "cwd": "`touch pwned`", "session_id": "../../evil"})):
        p = hook(ev, bad)
        ok(p.returncode == 0 and p.json in (None,) or isinstance(p.json, dict), f"{ev}: bad input exits 0 quietly", (bad[:40], p.stdout, p.stderr))
ok(not os.path.exists(os.path.join(PROJ, "pwned")) and not os.path.exists(os.path.join(TMP, "evil.json")), "nothing from the input is executed or used as a path outside the root")
p = hook("session-start", base(source="startup"), FRESH_CONTEXT_DISABLE=1)
ok(p.json is None and p.returncode == 0, "FRESH_CONTEXT_DISABLE=1 turns hooks off", p.stdout)
p = hook("bogus", "{}")
ok(p.returncode == 0 and "unknown event" in p.stderr, "unknown event exits 0 with a note", p.stderr)
slow = max(hook(ev, base(source="startup")).secs for ev in ("session-start", "prompt", "snapshot"))
ok(slow < 1.0, "every hook runs in under a second", f"{slow:.2f}s")
allowed = (ROOT, os.path.join(TMP, "transcripts"), os.path.join(TMP, "pyc"), proj_dir, jf, pyf)
stray = [os.path.join(dp, f) for dp, _, fs in os.walk(TMP) for f in fs if not os.path.join(dp, f).startswith(allowed)]
ok(not stray, "hooks wrote only under FRESH_CONTEXT_DIR", stray)

shutil.rmtree(TMP, ignore_errors=True)
if failed:
    print("\n".join(failed))
# ---------------------------------------------------------------- npx installer (bin/fresh-context.js)
NODE = shutil.which("node")
if not NODE:
    print("skip: node not found (installer tests)")
else:
    BIN = os.path.join(REPO, "bin", "fresh-context.js")
    pkg = load("package.json")
    ok(pkg.get("name") == plugin["name"] and pkg.get("version") == plugin["version"], "package.json name and version match plugin.json")
    ok(pkg.get("bin", {}).get("fresh-context") == "bin/fresh-context.js" and os.stat(BIN).st_mode & stat.S_IXUSR, "package.json bin")
    shipped = {f.rstrip("/") for f in pkg.get("files", [])}
    ok({".claude-plugin", "hooks", "skills", "bin", "README.md", "LICENSE", "CHANGELOG.md"} <= shipped, "package.json files", shipped)
    FAKE = os.path.join(TMP, "fake bin")
    os.makedirs(FAKE)
    with open(os.path.join(FAKE, "claude"), "w") as fh:
        fh.write('#!/bin/sh\necho "$*" >> "$FAKE_LOG"\n'
                 'case "$*" in "plugin marketplace list --json") printf "%s\\n" "${FAKE_LIST:-[]}";; esac\nexit 0\n')
    os.chmod(os.path.join(FAKE, "claude"), 0o755)
    LOG, XDG = os.path.join(TMP, "claude.log"), os.path.join(TMP, "xdg data")
    DATA = os.path.join(XDG, "fresh-context")

    def npx(*args, **kw):
        if os.path.exists(LOG):
            os.remove(LOG)
        kw.setdefault("PATH", FAKE)
        p = run([NODE, BIN, *args], cwd=TMP, XDG_DATA_HOME=XDG, FAKE_LOG=LOG, **kw)
        p.calls = open(LOG).read().splitlines() if os.path.exists(LOG) else []
        return p

    p = npx("--help")
    ok(p.returncode == 0 and "Usage: npx fresh-context" in p.stdout and not p.calls, "installer: --help", p.stdout + p.stderr)
    p = npx("bogus")
    ok(p.returncode == 2 and "Usage" in p.stderr, "installer: unknown argument exits 2", p.returncode)
    p = npx("--dry-run")
    ok(p.returncode == 0 and "marketplace add " + DATA in p.stdout and "plugin install fresh-context@fresh-context" in p.stdout
       and not p.calls and not os.path.exists(DATA), "installer: --dry-run only prints", p.stdout + str(p.calls))
    p = npx("uninstall", "--dry-run")
    ok(p.returncode == 0 and "marketplace remove fresh-context" in p.stdout and not p.calls, "installer: uninstall --dry-run", p.stdout)
    p = npx(PATH=os.path.join(TMP, "empty"))
    ok(p.returncode == 1 and "claude plugin marketplace add madebyalexander/fresh-context" in p.stderr
       and "claude plugin install fresh-context@fresh-context" in p.stderr and not os.path.exists(DATA),
       "installer: no claude CLI prints the manual commands and exits 1", p.stderr)
    p = npx()
    want = ["--version", "plugin marketplace list --json", "plugin marketplace add " + DATA, "plugin install fresh-context@fresh-context"]
    ok(p.returncode == 0 and p.calls == want, "installer: install runs add then install", p.calls)
    ok(os.path.isfile(os.path.join(DATA, ".claude-plugin", "marketplace.json"))
       and os.stat(os.path.join(DATA, "skills", "working-lean", "scripts", "lean_hooks.py")).st_mode & stat.S_IXUSR
       and not os.path.exists(os.path.join(DATA, "tests")), "installer: plugin copied with exec bits, no tests", os.listdir(DATA))
    open(os.path.join(DATA, "stale.txt"), "w").close()
    p = npx(FAKE_LIST=json.dumps([{"name": "fresh-context", "source": "directory", "path": DATA}]))
    ok(p.returncode == 0 and "plugin marketplace update fresh-context" in p.calls and not any("marketplace add" in c for c in p.calls)
       and not os.path.exists(os.path.join(DATA, "stale.txt")), "installer: re-run replaces the copy and updates", p.calls)
    p = npx("uninstall")
    ok(p.returncode == 0 and p.calls[1:] == ["plugin uninstall fresh-context@fresh-context", "plugin marketplace remove fresh-context"]
       and not os.path.exists(DATA), "installer: uninstall reverses both steps and deletes the copy", p.calls)
    os.makedirs(DATA)
    open(os.path.join(DATA, "mine.txt"), "w").close()
    p = npx()
    ok(p.returncode == 1 and os.path.exists(os.path.join(DATA, "mine.txt")) and "plugin install fresh-context@fresh-context" not in p.calls,
       "installer: refuses to replace a folder that isn't its own", p.stderr)

print(f"all {passed} passed" if not failed else f"{len(failed)} failed, {passed} passed")
sys.exit(1 if failed else 0)
