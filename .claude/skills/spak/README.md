# spak: Sam Palumbo Agentic Kanban

A kanban an AI runs with you: you write the backlog and approve; the AI
refines, plans, does and reviews the work, asking you at every decision.
This page is for people. `SKILL.md` is the AI's instructions and isn't
repeated here.

## The flow

```
backlog ──refine──▶ todo ──start──▶ doing ──work──▶ review ──approve──▶ done
   (AI asks what        (AI asks how       (AI does it,     │   (commits, on
    you want)            you want it)       runs checks)    │    your word)
                                                ▲           │
                                                └──rework───┘

expedite: a backlog entry or item straight to review, the AI answering
its own questions with its best guess (checks still run)
```

Type `/spak <verb>`, or say it in plain words. Also: `status` (the board
and the next move), `add` (to the backlog), `drop`, `retro` (improve spak).

## The columns

| Where | Who writes it | What's in it |
|---|---|---|
| `backlog` git branch | you, via `/spak add` | anything, in any style |
| `spak/1-todo/` | AI, after asking you | what's wanted, what done looks like, scope |
| `spak/2-doing/` | AI, after asking you | the plan you agreed to, then its progress |
| `spak/3-review/` | AI | what changed and how to check it |
| `spak/4-done/` | AI | each finished item whole; `spak/4-done/dropped.md` for what you chose not to do |

## Good to know

- `git log --grep='spak #N'` finds item #N's commit.
- A commit on main, a merge or a push waits for your click (the git guard,
  `.claude/hooks/git_guard.py`); only `git push origin backlog` doesn't.
- Bigger items get a `spak/N-…` branch. Its checkpoints are saved beside
  it, on `refs/spak/N` (`git log refs/spak/27` lists #27's), so the branch
  doesn't move and your editor shows every change. At approve they all go
  on the branch, squash-merged into one commit on main.
- To take a file back to an earlier checkpoint: `git restore
  --source=refs/spak/27~1 -- <path>` (one checkpoint back).
- What spak learns about how you like it to run: `references/preferences.md`.
  What you want of the project: `PREFERENCES.md` at the repo root.
