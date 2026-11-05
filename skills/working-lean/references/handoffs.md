# Handoffs

A handoff replaces hundreds of thousands of tokens of conversation with one short file, so a fresh session (or another account, or a teammate) can continue cheaply.

## Where they live

`<handoff root>/<folder>/`, where:
- `<handoff root>` is `$FRESH_CONTEXT_DIR`, else `$CLAUDE_CONFIG_DIR/handoffs`, else `~/.claude/handoffs`;
- `<folder>` is the session's starting folder with every character other than a letter or digit replaced by `-` (`/home/sam/my app` becomes `-home-sam-my-app`; very long paths are shortened with a hash).

`python3 "${CLAUDE_SKILL_DIR}/scripts/lean_hooks.py" where` prints the exact folder for the current directory. With the plugin, the session-start list also names it.

| File | Written by | Contents |
|---|---|---|
| `<topic>.md` | Claude, on `/handoff` | the note below |
| `last-session.md` | the snapshot hook (before compaction, at session end) | the last 6 prompts (first 400 characters each), files changed, the last reply (first 2,500 characters), context size, transcript path |
| `compact-summary.md` | the session-start hook after a compaction | the compaction summary Claude Code wrote |
| `.state/<session>.json` | the hooks | starting folder and the last nudge level; removed after 30 days |

Snapshots pass through a best-effort redaction of things that look like secrets (API keys, tokens, private keys, `password=...`). It is not a guarantee: don't paste secrets into prompts you want snapshotted, or turn snapshots off with `FRESH_CONTEXT_SNAPSHOT=0`. Files are created with mode 600 in folders with mode 700. Nothing is deleted automatically except `.state` files older than 30 days.

## The note

Update the existing note for a topic rather than adding a new one. Keep it under about 1,200 words. Point to files instead of copying them.

```markdown
# <Topic> - handoff, <YYYY-MM-DD HH:MM>
## Now
<3-8 lines: the goal, where it stands, the very next step>
## Decisions and preferences
<the user's choices and constraints, in their words where it matters>
## Where things are
<paths, IDs, branches, commits, URLs, commands to run, test scripts>
## Verified
<what was checked and how>
## Open
<pending work, questions waiting on the user, known risks>
## Gotchas
<things that bit us, so they don't again>
```

## Picking up

When the user says "continue", "pick up" or names earlier work: read the relevant note; read `last-session.md` only if the note is older than it or missing; read `compact-summary.md` only if both leave a gap. Then continue the work without a recap.

## The hooks (plugin)

| Event | What it does | Limit |
|---|---|---|
| SessionStart (startup, clear) | adds a few lines to Claude's context: this folder's handoffs changed in the last 21 days, newest first, with each note's first "Now" line. The files themselves are not loaded. | 10 s |
| SessionStart (compact) | saves the compaction summary to `compact-summary.md` | 10 s |
| SessionStart (resume, fork) | if Claude Code reports an expired cache and at least 60k tokens, shows you a one-line warning: the next message re-caches all of it | 10 s |
| UserPromptSubmit | once the context passes 150k tokens (again every further 50k), shows you one line and tells Claude to suggest `/handoff` + `/clear` before new, unrelated work. It never blocks a prompt. | 5 s |
| PreCompact, SessionEnd | writes `last-session.md` | 10 s |

Each hook is a short Python script with no network access and no model calls. It only parses JSON (never executes anything from a transcript), exits 0 on any error, and skips subagent events. Thresholds and switches: `references/settings.md`.

## Hooks without the plugin

If you copied only the skill, add this to `~/.claude/settings.json` (replace the path; keep the quotes if it contains spaces):

```json
{
  "hooks": {
    "SessionStart": [{"hooks": [{"type": "command", "command": "python3 \"/path/to/working-lean/scripts/lean_hooks.py\" session-start", "timeout": 10}]}],
    "UserPromptSubmit": [{"hooks": [{"type": "command", "command": "python3 \"/path/to/working-lean/scripts/lean_hooks.py\" prompt", "timeout": 5}]}],
    "PreCompact": [{"hooks": [{"type": "command", "command": "python3 \"/path/to/working-lean/scripts/lean_hooks.py\" snapshot", "timeout": 10}]}],
    "SessionEnd": [{"hooks": [{"type": "command", "command": "python3 \"/path/to/working-lean/scripts/lean_hooks.py\" snapshot", "timeout": 10}]}]
  }
}
```

Don't do this as well as installing the plugin, or each hook runs twice.
