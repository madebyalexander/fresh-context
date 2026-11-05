# Recommended settings

Nothing here is applied automatically. Copy what you want into `~/.claude/settings.json` (every project) or `.claude/settings.json` (one project), then **restart Claude Code**: a running session keeps the settings it started with, and `/clear` does not reload them. Check the effect with `/context`.

## Contents
- The snippet
- What each setting buys and costs
- MCP servers
- Status line (optional)
- fresh-context hook settings
- CLAUDE.md snippets (compact instructions, always-on rules)

## The snippet

```json
{
  "autoCompactWindow": 200000,
  "env": {
    "BASH_MAX_OUTPUT_LENGTH": "12000"
  }
}
```

## What each setting buys and costs

| Setting | Buys | Costs |
|---|---|---|
| `autoCompactWindow: 200000` | Compaction starts at about 200k tokens of context instead of close to the model's window (close to 1M on 1M-token models). Requests late in a long session then carry at most about 200k instead of up to about 1M. | More frequent compactions: older detail is summarized. Keep handoffs and project notes for anything that must survive. Range 100000 to 1000000; values above the model's window are capped. |
| `env.BASH_MAX_OUTPUT_LENGTH: "12000"` | One runaway command can add at most about 12k characters to the context (the default is 30000). | Long output is cut. Use `quiet` or redirect to a log file and `grep` it when you need all of it. |

Precedence, if a value seems ignored: the `CLAUDE_CODE_AUTO_COMPACT_WINDOW` environment variable overrides `autoCompactWindow`; `modelSettings.<model>.autoCompactWindow` overrides it for one model; `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` can only lower the trigger. The `bashOutputMaxChars` setting, if present, wins over `BASH_MAX_OUTPUT_LENGTH`.

## MCP servers

Every connected MCP server adds tool names and instructions to each request. Claude Code defers MCP tool definitions by default (tool search; leave `ENABLE_TOOL_SEARCH` unset), so the bigger cost is servers you never use in a project. Turn those off with `/mcp` in that project and turn them back on when a task needs them. Servers from a project's `.mcp.json` can also be approved or rejected with `enabledMcpjsonServers` / `disabledMcpjsonServers`.

## Status line (optional)

Plugins can't set a status line, so add it yourself. It shows model, context size (amber at the big-session size, red at 1.5x), cache warm/cold when Claude Code reports it, and 5-hour / 7-day plan usage (claude.ai plans only). It reads only the JSON on stdin.

```json
{
  "statusLine": {
    "type": "command",
    "command": "python3 \"/absolute/path/to/working-lean/scripts/statusline.py\""
  }
}
```

An installed plugin lives in a versioned folder under `~/.claude/plugins/` that changes on every update, so copy `statusline.py` somewhere stable (for example `~/.claude/statusline.py`) and point the command there.

## fresh-context hook settings

The hooks read environment variables, which you can set in your shell or in the `env` block of settings.json:

| Variable | Default | Effect |
|---|---|---|
| `FRESH_CONTEXT_DISABLE` | off | `1` turns every fresh-context hook off |
| `FRESH_CONTEXT_BIG_SESSION` | `150000` | context size (tokens) for the big-session nudge and the status-line colour; `0` turns the nudge off |
| `FRESH_CONTEXT_COLD_RESUME` | `60000` | warn when resuming at least this many tokens with an expired cache; `0` off |
| `FRESH_CONTEXT_SNAPSHOT` | on | `0` stops writing `last-session.md` and `compact-summary.md` |
| `FRESH_CONTEXT_LIST` | on | `0` stops listing handoffs at session start |
| `FRESH_CONTEXT_FRESH_DAYS` | `21` | list handoffs changed in the last N days |
| `FRESH_CONTEXT_DIR` | `~/.claude/handoffs` | where handoffs and snapshots live (follows `CLAUDE_CONFIG_DIR`) |

## CLAUDE.md snippets

**Compact instructions.** Compaction reads your CLAUDE.md. This tells it what to keep:

```markdown
# Compact instructions
Keep: the user's requests and decisions (in their words), constraints and preferences, file paths, IDs and versions,
what was built, what was verified and how, what's pending, errors and their fixes.
Drop: raw tool output, superseded attempts, exploration that led nowhere.
```

**Always-on rules.** The skill loads when a task looks like it needs it. If you want the core rules in every session, add this short version to `~/.claude/CLAUDE.md` (about 150 tokens per request):

```markdown
# Working lean
- Cap command output (tail, head -c, grep -n, or quiet); never print raw dumps.
- Read files in ranges: grep -n or outline first, then offset/limit. Don't re-read what you just edited.
- Batch independent tool calls; verify with one script that prints failures and a pass line.
- Screenshots: crop to the element, small JPEG.
- Change what exists in place; say limits before building.
- Big session + new task: /handoff, then /clear and "pick up".
```
