---
name: working-lean
description: Same quality, fewer tokens in Claude Code. Keeps tool output small, reads files in ranges, batches tool calls, briefs subagents with a budget, and moves long work to a fresh session through a handoff. Use this skill whenever a task will run noisy commands (tests, builds, installs, logs), read large files or JSON, delegate to subagents, or keep a long session going, and whenever the user mentions tokens, context size, usage limits, cost, compaction, /clear, handoffs, or asks to work efficiently, even if they don't name the skill.
---

# Working lean

Every request re-sends the whole conversation. A 30 KB log that enters the context once is paid for again on every later request, until the session compacts or ends. So the cheapest token is the one that never enters the context. These rules keep the result the same and shrink what each request carries. They never override what the user asks for or the project's own rules.

The helper scripts live in `${CLAUDE_SKILL_DIR}/scripts/`; each one has `--help`:
`quiet` (run a command, print exit code + error lines + tail) · `outline` (file landmarks with line numbers) · `jpick` (pick fields from JSON) · `tokens` (what a session cost, ask by ask).

## Keep tool output small

- **Cap command output**: `| tail -n 40`, `| head -c 4000`, `grep -n` for the lines you need, or `quiet <cmd>` (full log kept in a file, path printed). A test run that prints 3,000 lines costs as much as reading a book chapter, and it stays in every later request.
- **Read files in ranges**: find the place first (`grep -n`, `outline <file>`), then read with offset/limit. A 2,000-line file read whole to inspect one function carries 1,900 lines of dead weight.
- **Don't re-read a file you just wrote or edited.** The edit tool would have failed if the change didn't apply, and the content is already in context.
- **Ask APIs, CLIs and MCP tools for the fields and depth you need**, not whole trees: field selectors, `--json` with a filter, `jq`, or `jpick file.json items[*].id meta.total`.
- **Never print raw dumps** (minified files, base64, binary, full stack traces, lockfiles). Print a count, a summary or the first lines, and say where the full thing is.
- **Screenshots**: crop to the element and save a small JPEG; a full-page Retina capture can cost more than the code it shows.

## Fewer round trips

- **Batch independent tool calls** in one message, and put related steps in one script. Each round trip re-sends the context.
- **Verify a change with one check script** that prints only failures and a pass line. Re-run only what failed; do one full pass at the end.
- **Reuse** the project's existing scripts and the helpers above before writing a new one-off harness.
- **If the answer is already in the conversation**, answer without tools.

## Before building

- **Change what exists, in place.** Make a new file, component or copy only when the existing one can't do the job, and say why in one line first. Parallel copies double what later reads have to carry and confuse later sessions.
- **Check the platform's limits first.** If the request can't be met as asked, say so with the options before building, not after.
- **Probe read-only or on throwaway data**; never test a write on the user's real files, accounts or data.
- **When something is replaced, remove the old** once the new one is verified (ask once). Hidden copies get read, edited and shipped by mistake.
- **Measure in the one setup that matters** (the user's environment) and stop once the cause is found. Add setups or prototype alternatives only when the first result is unclear or the user asks.

## Subagents

- Delegate when it keeps bulk out of this context (a broad search across many files, independent parallel work) and you only need the conclusion. Do a lookup with a known target yourself; the brief alone costs more.
- Brief like a peer: the goal, what's already ruled out, the files to read, the measurement setup, what to return, and a **request budget** (about 40 tool calls). Past the budget it reports what it has. A subagent's tokens are billed too, and an unbounded one can cost more than the task.

## Long sessions and handoffs

- A request in a 300k-token session costs about as much as two or three at 120k. When the session is large (the fresh-context hook says so, or `/context` shows well over 150k) and the user starts **new, unrelated work**, suggest: save a handoff (`/handoff`), then `/clear` and say "pick up". Answer questions and make small edits in place.
- At each milestone of long work, update the handoff note, so a compaction, a crash or another account loses nothing.
- When the user says "continue" or "pick up", read the relevant handoff instead of asking them to re-explain.
- Never put secrets (keys, tokens, passwords) in a handoff; say where they live instead.
- Note format, file locations and the automatic snapshots: `references/handoffs.md`.

## Writing

- Patch with small anchored edits; don't rewrite a whole file for a local change. Generate repetitive markup or data from a short script instead of typing it out.
- Status updates: one line. Final reports: what changed, how it was checked, what's left. No recap of what the user already saw.

## When the user asks about cost or setup

- "What did this cost?" / "why is usage high?": run `${CLAUDE_SKILL_DIR}/scripts/tokens` (or `tokens -n 5`), then name the biggest driver and one fix. How to read it: `references/measuring.md`.
- "Set this up" / "tune my settings": `references/settings.md` has the recommended settings with what each one buys and costs. Show the snippet and let the user apply it; don't edit their settings files unasked.
