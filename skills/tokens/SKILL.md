---
name: tokens
description: Show what recent Claude Code sessions in this folder cost, prompt by prompt, and name the biggest driver.
argument-hint: "[-n N | --cwd PATH | session.jsonl]"
disable-model-invocation: true
---

# Tokens

Run this and read its output (it only reads local transcripts and prints a short table):

```sh
python3 "${CLAUDE_SKILL_DIR}/../working-lean/scripts/tokens" $ARGUMENTS
```

Then answer in at most five lines:

1. The headline: requests, average context per request, and what was re-sent in total.
2. The single biggest driver, pointing at the prompt or session where it shows.
3. One concrete fix for it:

| What the numbers show | Likely cause | Fix |
|---|---|---|
| ctx jumps by 20k+ inside one prompt | a big tool result (log, file, JSON, screenshot) | cap output, read ranges, pick JSON fields, crop images |
| many requests for a small change | one tool call per step | batch independent calls; one script for related steps |
| average ctx of 300k+ | a long session that never compacts | `autoCompactWindow`, or `/handoff` + `/clear` for new work |
| a short prompt with a huge re-read | the prompt landed in a big session | start new work in a fresh session |

Don't paste the whole table back. If the script finds no transcripts, say so and suggest `--cwd` with the project's folder. More on reading the numbers: `${CLAUDE_SKILL_DIR}/../working-lean/references/measuring.md`.
