# Measuring what a session costs

`${CLAUDE_SKILL_DIR}/scripts/tokens` reads the session transcripts Claude Code keeps on this machine (`~/.claude/projects/<folder>/<session>.jsonl`, or under `CLAUDE_CONFIG_DIR`). It sends nothing anywhere.

```text
tokens            # the newest session in this folder, one line per prompt
tokens -n 10      # the 10 newest sessions, one line each, plus the average
tokens FILE.jsonl # one transcript
tokens --cwd /path/to/project -n 5
```

## Reading it

- **req**: model requests. Every tool call is at least one more request.
- **ctx**: the context sent with a request (fresh input + cache read + cache write). This is what grows.
- **re-read**: the sum of ctx over the requests: what the conversation re-sent. Cached tokens are cheaper than fresh ones, but on subscription plans they still count toward usage limits, and a cold cache re-sends them at full price.
- **out**: output tokens.

Cost is roughly *requests x average context*. So the two levers are fewer requests (batching, one check script, answering from context) and a smaller context per request (small tool output, ranges, earlier compaction, fresh sessions for new work).

## Typical drivers and the fix

| What you see | Likely cause | Fix |
|---|---|---|
| ctx jumps by 20k+ inside one prompt | a big tool result (log, file, JSON, screenshot) | cap output, read ranges, `jpick`, crop images |
| many req for a small change | one tool call per step | batch calls; one script for related steps |
| avg ctx 300k+ | a long session that never compacts | `autoCompactWindow`, handoff + `/clear` for new work |
| a short prompt with a huge re-read | the prompt landed in a big session | start new work in a fresh session |

## Before and after

Run `tokens -n 10` before changing anything and again after a week of normal work. Compare the "average context per request" line, and the number of requests for similar tasks. Expect the average to depend on the work: a session of small edits looks cheaper than a refactor no matter what.

## Caveats

- The transcript format is internal to Claude Code and can change. `tokens` skips lines it can't read; if its numbers look wrong after an update, compare with `/context` and `/usage`.
- Subagent runs may be stored apart from the main transcript and are not included.
- Transcripts are kept for 30 days by default (`cleanupPeriodDays`).
