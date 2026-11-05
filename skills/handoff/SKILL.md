---
name: handoff
description: Save the current work as a short handoff note so a fresh session can continue without the old conversation, or pick up from one. Use on /handoff, before /clear or switching accounts, at milestones of long work, when a session has grown large and the next task is unrelated, and whenever the user says "continue", "pick up", "where were we" or names earlier work.
argument-hint: "[topic]"
---

# Handoff

A handoff replaces a long conversation with one short file. The next session reads a page instead of re-sending hundreds of thousands of tokens, and nothing that matters is lost to compaction.

## Find the folder

Notes live in one folder per project. Use the folder named in the session-start list if there is one. Otherwise get it with:

```sh
python3 "${CLAUDE_SKILL_DIR}/../working-lean/scripts/lean_hooks.py" where
```

If that script isn't there (this skill was copied alone), use `~/.claude/handoffs/<folder>/`, where `<folder>` is the session's starting directory with every character other than a letter or digit replaced by `-` (`/home/sam/my app` becomes `-home-sam-my-app`). Create it if needed.

## Write or update

Name the file after the piece of work in short kebab case (`$ARGUMENTS` if given, e.g. `billing-refactor.md`). If a note for this work exists, update it in place rather than starting another: stale notes are worse than none.

```markdown
# <Topic> - handoff, <YYYY-MM-DD HH:MM>
## Now
<3-8 lines: the goal, where it stands, the very next step>
## Decisions and preferences
<the user's choices and constraints, in their words where it matters>
## Where things are
<paths, branches, commits, IDs, URLs, commands to run, test scripts>
## Verified
<what was checked and how>
## Open
<pending work, questions waiting on the user, known risks>
## Gotchas
<things that bit us, so they don't again>
```

- Keep it under about 1,200 words. The reader is a capable engineer with none of this conversation: give them what they can't rediscover cheaply, and point to files instead of copying them.
- The first line under `## Now` is what the session-start list shows, so make it say where things stand.
- Never write secrets, tokens, passwords or private keys into a note, even if they appeared in the conversation. Write where the secret lives (`.env`, the keychain) instead.
- After writing, tell the user in one line where the note is and that they can `/clear` and say "pick up <topic>".

## Pick up

When the user says "continue", "pick up" or names earlier work:

1. Read the relevant note (the newest one if they didn't say which).
2. Read `last-session.md` (an automatic snapshot of the last prompts, files changed and the last reply) only if the note is missing or older than it.
3. Read `compact-summary.md` only if both leave a gap.

Then carry on with the next step from `## Now`. Don't recap the note back to the user; one line saying what you're picking up is enough.
