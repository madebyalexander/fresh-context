# fresh-context

Work in a fresh context with a short handoff, instead of one session that keeps growing.

A Claude Code plugin: a skill that keeps every request small, plus `/handoff`, `/tokens` and a few local hooks, so long work moves to a new session without losing anything. Same quality, fewer tokens.

Unofficial; not affiliated with or endorsed by Anthropic.

## Why

Every request re-sends the whole conversation. A 30 KB log, a full-page screenshot or a 2,000-line file read once is paid for again on every later request until the session compacts or ends. fresh-context keeps that from piling up: small tool output, reads in ranges, batched calls, budgets for subagents, and a handoff note so the next task starts in a clean session instead of an endless one.

**Before and after, on the author's machine** (measured with the bundled `tokens -n 10`, same kind of work, same quality bar):

| | Sessions | Requests | Average context per request | Peak context |
|---|---|---|---|---|
| Before | 5 | about 5,800 | about 450k tokens | about 960k |
| After | 3 | about 2,400 | about 120k tokens | about 170k |

Be fair about the cause: a good part of the drop comes from compacting at 200k tokens instead of close to 1M (the `autoCompactWindow` setting below), not from the rules alone. Your numbers will depend on your work; measure your own with `/fresh-context:tokens -n 10` before and after.

## Install

### As a plugin (skill + commands + hooks)

With Node 18 or later:

```sh
npx fresh-context
```

It checks that the `claude` CLI is on your PATH, copies the plugin from the npm package to `~/.local/share/fresh-context` (or `$XDG_DATA_HOME/fresh-context`), then runs `claude plugin marketplace add` on that folder and `claude plugin install fresh-context@fresh-context`. Running it again (`npx fresh-context@latest`) replaces the copy and updates the marketplace. `--dry-run` prints the steps without doing anything; `npx fresh-context uninstall` reverses them and deletes the copy.

Or by hand, from GitHub (works once the repository is public):

```sh
claude plugin marketplace add madebyalexander/fresh-context
claude plugin install fresh-context@fresh-context
```

or from a local clone:

```sh
git clone https://github.com/madebyalexander/fresh-context
claude plugin marketplace add ./fresh-context
claude plugin install fresh-context@fresh-context
```

Inside Claude Code the same commands work as `/plugin marketplace add …` and `/plugin install …`.

Restart Claude Code. Plugin skills are prefixed with the plugin name: `/fresh-context:handoff`, `/fresh-context:tokens`.

### As skills only (no hooks)

```sh
git clone https://github.com/madebyalexander/fresh-context
mkdir -p ~/.claude/skills
cp -R fresh-context/skills/working-lean fresh-context/skills/handoff fresh-context/skills/tokens ~/.claude/skills/
```

Commands are then `/handoff` and `/tokens`. Copy all three folders side by side: `handoff` and `tokens` use scripts inside `working-lean`. `working-lean` also works on its own. To add the hooks by hand, see [references/handoffs.md](skills/working-lean/references/handoffs.md#hooks-without-the-plugin). For one project instead of all, copy into `<project>/.claude/skills/`.

### Recommended settings (optional, never applied for you)

```json
{
  "autoCompactWindow": 200000,
  "env": { "BASH_MAX_OUTPUT_LENGTH": "12000" }
}
```

Add to `~/.claude/settings.json` if you want them. What each buys and costs, plus an optional status line: [references/settings.md](skills/working-lean/references/settings.md).

## What's inside and what it costs

| Piece | What it does | Context cost |
|---|---|---|
| `working-lean` skill | Rules with reasons: cap tool output, read in ranges, batch calls, brief subagents with a budget, hand off long work. Loads by itself when a task fits. | about 130 tokens for the description, always; about 1.5k when it loads |
| `/handoff` | Writes or updates a short note (Now / Decisions / Where things are / Verified / Open / Gotchas) so `/clear` loses nothing; reads it back on "pick up". | about 60 tokens for the description; the note when read |
| `/tokens` | Reads local transcripts and prints what each prompt or session re-sent, then names the biggest driver. User-invoked only. | none until you run it |
| Session-start hook | Lists this folder's recent handoffs (a few lines). After a compaction, saves the summary to a file. On resuming a large session with an expired cache, warns you once. | about 50-250 tokens per session (none when there are no notes) |
| Prompt hook | Past 150k tokens of context (then every 50k more), shows you one line and asks Claude to suggest `/handoff` + `/clear` before unrelated new work. Never blocks. | a few lines, a few times per long session |
| Snapshot hook (before compaction, at session end) | Writes `last-session.md`: the last prompts, files changed, the last reply. | none |
| Scripts in `skills/working-lean/scripts/` | `quiet`, `outline`, `jpick`, `tokens`, `statusline.py`. Each has `--help`. | only their (small) output |

## Configuration

The hooks read `FRESH_CONTEXT_*` environment variables, set in your shell or in the `env` block of `settings.json`: `FRESH_CONTEXT_DISABLE=1` turns every hook off, `FRESH_CONTEXT_BIG_SESSION=0` turns the nudge off, `FRESH_CONTEXT_SNAPSHOT=0` stops snapshots. All of them with their defaults: [references/settings.md](skills/working-lean/references/settings.md#fresh-context-hook-settings). To turn the whole plugin off, disable it in `/plugin`.

## Requirements

- Claude Code with plugin support (any recent version).
- Python 3.8+ for the hooks and `tokens`, `jpick`, `outline`, `statusline.py`. Standard library only.
- Bash for `quiet`.
- Node 18+ only for the `npx` installer. It has no dependencies.
- macOS and Linux. Windows works under WSL; native Windows is untested.

## Privacy and security

- **Everything stays on your machine.** No network calls, no telemetry, no model calls from the hooks or scripts.
- **What is read:** the hook's JSON from Claude Code, and the session transcript it points to (`~/.claude/projects/...`) to find the context size, the last prompts and the last reply. `/tokens` reads the same transcripts. Transcript content is only parsed as JSON, never executed or passed to a shell.
- **What is written:** only under `FRESH_CONTEXT_DIR` (default `~/.claude/handoffs/<project folder>/`): your handoff notes, `last-session.md`, `compact-summary.md`, and small state files in `.state/` (removed after 30 days). Files are mode 600, folders 700.
- **Snapshots contain your prompt text** (the last 6 prompts, up to 400 characters each) and the start of Claude's last reply. Things that look like API keys, tokens, private keys and `password=` values are redacted, but that is best effort. If you paste secrets into prompts, set `FRESH_CONTEXT_SNAPSHOT=0`.
- **Hooks fail open:** any error exits 0 with a note on stderr; a hook never blocks a prompt or a session. Subagent events are skipped. Each hook has a 5-10 second limit and normally takes well under one.
- **Nothing changes your settings.** The settings snippet and the status line are documented, never applied. The `npx` installer only writes its own folder (`~/.local/share/fresh-context`) and calls `claude plugin`, which records the marketplace and the plugin in your user settings.

## Uninstall

```sh
npx fresh-context uninstall
```

or by hand: `claude plugin uninstall fresh-context@fresh-context`, then `claude plugin marketplace remove fresh-context` (and delete `~/.local/share/fresh-context` if you used npx).

For the skills-only install, delete the three folders from `~/.claude/skills/` (and any hooks you added by hand). Your notes stay in `~/.claude/handoffs/`; delete that folder if you don't want them.

## FAQ

**Does it make answers worse?** It shouldn't: the rules cut what enters the context (log noise, unread file bodies, oversized images), not the thinking or the checks. Every rule says why, so Claude can tell when the user's request needs the full output.

**Why not just compact more often?** Compaction helps (it's the setting above), but a summary loses detail you didn't plan to lose. A handoff is a summary you choose, written while the details are still in front of Claude.

**Will the nudge interrupt me?** No. It shows one line, adds a short note for Claude, and never blocks. Set `FRESH_CONTEXT_BIG_SESSION=0` to turn it off.

**`/tokens` numbers look different from `/usage`.** `/tokens` reads transcripts, whose format is internal to Claude Code and can change, and leaves out subagent runs stored elsewhere. Use it to compare sessions, not as a bill.

**Can I use it in a team?** Install the plugin per user. Handoff notes are personal by default; point `FRESH_CONTEXT_DIR` into a project folder if you want to share them, and review them before committing.

## Development

```sh
tests/run.sh
```

Runs the script and hook tests on synthetic data, checks the manifests and skills, and runs `claude plugin validate` if the CLI is installed. It prints only failures, then a pass line.

## License

MIT, see [LICENSE](LICENSE).
