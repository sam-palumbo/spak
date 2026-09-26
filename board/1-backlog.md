# Backlog

Anything that comes to mind, one line each.

- ~~SPAK board: work flows through files in the repo, which humans and agents both read and edit. Backlog: anything that comes to mind, one line each. Todo: backlog items, bundled with similar ones, refined through questions into specs an agent can execute without guessing. Doing: one task at a time on its own branch, worked in a loop (spec kept current, commits, findings, dead ends, tests and edge cases) until the acceptance criteria are met. Review: finished work checked by a fresh reviewer for hallucinations, standards, readability and docs, then approved by a human. Done: merged work, each with a short summary.~~ → 001
- ~~Agent tooling for each transition~~ → 002
- ~~Board rules: log a move to review or done in the last branch commit before it~~ → 002
- ~~Board rules: editors and whitespace checks keep the blank line in empty column files~~ → 002
- ~~Board rules: say what a move back to todo resets (Definition of Ready, Review, Done summary)~~ → 002
- ~~Self-improvement: end every move by fixing what did not hold up, recording what the human prefers and logging the run, as the ttbb implementation does — SPAK has no way to learn from a run today~~ → 002
- ~~Board layout: replace the five column files with one folder per column and one file per card, so a move is a rename and column files can never conflict — needs an answer for todo's order, which folders lose~~ → 002
- ~~Tooling: build a safe, tool-agnostic SPAK CLI here from the strongest parts of the ttbb implementation while preserving the canonical board workflow~~ → 002
- ~~Tooling: ship an optional enforced commit guard that makes commits on main, merges and pushes wait for the human however the command is written, with its own self-test, leaving the board core tool-agnostic~~ → 002
- ~~Backlog: move the backlog off main onto its own branch that the tooling commits and pushes, so capturing an idea costs no click~~ → 002
- ~~Board rules: bound what a Log line may hold, so a card's log stays readable — 001's Log ran to 130 lines, its Handoff entries pages long~~ → 002
- ~~Commits: put the card id in the commit body so a card's history is one `git log --grep` away~~ → 002
- ~~Principle: whenever a step can be mechanical it becomes a script, not a rule in prose or an instruction to an agent — state it in the board docs and hold every card to it~~ → 002
- ~~Tooling: 001 ran four shell checks pasted into its own task file by hand (deliverables exist, link resolution, template section order, line budget) — make them one script every card's Verification can call~~ → 002
