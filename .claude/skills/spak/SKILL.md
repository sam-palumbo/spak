---
name: spak
description: This project's kanban board in spak/ (backlog → todo → doing → review → done, one file per item). Use for /spak, and whenever the user mentions the backlog or board, asks what's next, adds an idea in passing, gives feedback on how spak works, or asks to refine (groom), start (plan), work on, expedite (fast-track), rework (send back), approve or drop an item (#N).
---

# spak

The backlog lives on the `backlog` git branch (the script commits and
pushes it); each other column is a folder of `N-slug.md` item files;
dropped entries go in `4-done/dropped.md`. The user writes the backlog and
reviews. **Every decision is theirs**: refine asks what, start asks how, and
nothing reaches done or a commit without their approval.

`spak` means `python3 .claude/skills/spak/scripts/spak.py`, run from the
repo root. It does every mechanical step (the board, IDs, moves, formats,
checkpoints); you write content and talk to the user. A step it lacks: do
it once by hand, then add it to the script (Improve).

**Item files**: a header the script owns, the `# #N Title` line, then `## `
sections. After editing one by hand: `spak lint N`.

**Preferences**: read `references/preferences.md` (how spak runs; it beats
this file) before every verb, and the root `PREFERENCES.md` (what's being
built) for refine, start and work.

## Verbs

| Verb | Move | Read |
|---|---|---|
| `status` (or none) | the board and its `next:` | `spak status` |
| `add "text"` | → backlog, in the user's words | `spak add` |
| `refine [n…]` | backlog → todo, asking the user | `references/refine.md` |
| `start N` | todo → doing, the plan agreed with the user | `references/start.md` |
| `work N` | do the plan, doing → review | `references/work.md` |
| `expedite n` or `#N` | → review on your best guesses; checks still run | `references/expedite.md` |
| `rework N "why"` | review → doing (`--todo`: → todo) with the feedback | `references/review.md` |
| `approve #N` | review → done, **and commit** | `references/review.md` |
| `drop n` or `#N` | → dropped, **only on the user's yes** | `spak drop` |
| `retro ["feedback"]` | improve this skill | `references/retro.md` |

Plain phrases map by meaning ("send #4 back: it jumps" is rework; "take
hold of the current task" continues the doing item). **Only `/spak approve
#N` authorizes a commit**; anything else ("approve 13", "looks good",
"continue") gets "approve #N and commit?" asked first.

## Rules for every move

- **Ask only what the user can answer**, always with AskUserQuestion,
  recommendation first, up to four questions a batch; offer your best
  guesses for an open one. **Offer only what you've tested.**
- **Jev where its skill says it fits, unasked**: a `map` for one judgement
  over many files or items, and `spak selfcheck` before review. Not for
  finding a name, checking text against code, or anything visual. `learn`
  what you checked; the review says what Jev caught and missed.
- **Keep the user's words** in decisions and feedback, and quote them in
  chat.
- **The skill names nothing of the project**: how to run it goes in its
  `CLAUDE.md`, the user's taste in `PREFERENCES.md`.
- **One item in doing** unless the user starts a second.
- **Branches**: the plan decides (bigger or riskier work gets one),
  `spak/N-short-title`, made as the item enters doing. Checkpoints are the
  script's (`spak tick`, `spak review`, `spak checkpoint "…"`), on a side
  ref, so the branch never moves and the user's editor shows the whole
  item. Approve squash-merges them into one commit: **done means merged
  into main.**
- **Commits on main, merges and pushes are visible commands** (the git
  guard asks the user). A commit on main follows `CLAUDE.md`, ends its
  body with `spak #N`, and has no attribution line. Never push unless
  asked.

## Improve: the last step of every move

At approve, before the commit, so its edits land in it.

1. **Fix what didn't hold up**: a correction, a pointless question, a
   manual step the script should do. Edit this file, the verb's reference
   or the script (then `scripts/smoke_test.sh` must pass).
2. **Preferences: always ask first.** Propose any preference, the user's or
   your own idea, with AskUserQuestion, which also asks where it goes:
   skill (how spak runs), project (what's being built) or nowhere. Then
   `spak preference --skill|--project "…"`, with `--replace "<phrase>"`
   for a line it changes. Only `/spak retro` moves one into the skill, on
   the user's yes.

Nothing else is logged: the history is the commits. Don't add rules that
only mattered once.
