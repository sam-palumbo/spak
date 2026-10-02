# retro: improve spak

For `/spak retro ["feedback"]`, or the user saying how spak should work.

1. Gather the feedback (if none, ask, offering what the material
   suggests), `references/preferences.md`, the root `PREFERENCES.md`, and
   `git log --format='%h %s%n%b' -- .claude/skills/spak`. Look for what
   repeats: the same manual fix, correction or answer.
2. Propose one action per `preferences.md` line, each the user's to
   approve (multi-select, grouped by action, four lines a question):
   **delete** (the skill says it, or a one-off), **promote** (into the file
   that owns it, in general words with no project names, then deleted),
   **project** (to `PREFERENCES.md`), or **keep**. Fold lines that say the
   same thing, in both files.
3. Propose the other changes, most useful first, and ask which to apply.
   Script first: a mechanical step or a bulk edit is a script; an agent on
   the cheapest model only when it needs judgement, its output checked in
   code.
4. After an item that leaned on a tool's skill (Jev): an honest verdict,
   by the tool's own docs and data, with the general lessons folded into
   that tool's skill, not this repo.
5. After a script change, `scripts/smoke_test.sh` must print `spak smoke:
   PASS`; a new behaviour gets its test in the same change.

Retro edits the skill, its script and the two preference files, never the
board's items.
