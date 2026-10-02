# rework and approve

## rework N "why"

Plain-text feedback on an item in review is a rework: `spak rework N
"<feedback, verbatim>"`. A fix within the plan: go on with work. A change
to the plan: re-plan with the user first (start's questions), then `spak
step N "…"` and edit decisions in place (`spak lint N`). Feedback on the
whole approach: recommend changing the method over tuning it.

## rework N "why" --todo

When the feedback changes what the item is: checkpoint, run the checks
and render what's visual to see what the branch holds, ask a refine round
on the new direction, then

```sh
spak rework N "<feedback, verbatim>" --todo <<'EOF'
<spak skeleton todo>
EOF
```

Next: `/spak start N`.

## approve #N

Only `/spak approve #N` authorizes it; else ask "approve #N and commit?".
Sent while the item is in doing: finish its checks and self-check, then
review and approve in one go, stopping only if a check fails.

1. `spak approve N "<one sentence: what it does now, and the key
   decision>"`.
2. Improve (SKILL.md), so its edits land in the item's commit.
3. On a branch: `spak finish N`, then what it prints, one visible command
   at a time: the squash merge, the commit, `git branch -D`. Without a
   branch: `git status`, `git add` the item's paths (not `-A` blindly),
   then the commit. The message:

   ```
   Imperative plain subject

   Body wrapped at 72, saying why.

   spak #N
   ```
