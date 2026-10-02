#!/bin/bash
# Runs every spak.py command on a scratch git repo copy of the board and
# checks the files it leaves; the backlog is branch-backed, so the flush is
# exercised against a scratch bare "origin" (no network). The real board
# and references are never touched.
# Prints "spak smoke: PASS", or the first failure and exits 1.
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$HERE/../../../.." && pwd)
T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT
mkdir -p "$T/r"

# A scratch repo whose "origin" is a bare local repo, so pushes go nowhere.
git init -q --bare "$T/origin"
git init -q -b main "$T/repo"
git -C "$T/repo" remote add origin "$T/origin"
git -C "$T/repo" config user.name spak-test
git -C "$T/repo" config user.email spak-test@scratch
# A clean board: empty columns (never a copy, which would drag
# in whatever the real board currently holds).
mkdir -p "$T/repo/spak"
for d in 1-todo 2-doing 3-review 4-done; do mkdir -p "$T/repo/spak/$d"; touch "$T/repo/spak/$d/.gitkeep"; done
git -C "$T/repo" add -A
git -C "$T/repo" commit -qm board
git -C "$T/repo" push -q origin HEAD

P() { python3 "$HERE/spak.py" --board "$T/repo/spak" --refs "$T/r" "$@"; }
# A todo body with its priority picked (the skeleton's placeholder is refused).
TB() { P skeleton todo | sed 's/^priority: .*/priority: normal/'; }
fail() { echo "spak smoke: FAIL: $1"; exit 1; }
B="spak/0-BACKLOG.md"
btext() { git -C "$T/repo" show "backlog:$B" 2>/dev/null; }
otext() { git --git-dir="$T/origin" show "backlog:$B" 2>/dev/null; }
# has/lacks <file or glob under the board> <text>; gone <glob>
has() { cat "$T/repo/spak"/$1 2>/dev/null | grep -qF -- "$2" || fail "$1 lacks: $2"; }
lacks() { ! cat "$T/repo/spak"/$1 2>/dev/null | grep -qF -- "$2" || fail "$1 still has: $2"; }
gone() { ! ls "$T/repo/spak"/$1 >/dev/null 2>&1 || fail "$1 should be gone"; }
# The backlog lives on the branch; bhas/blacks check it, ohas the pushed
# (origin) copy, olsynced that the local branch and origin agree.
bhas() { btext | grep -qF -- "$1" || fail "backlog branch lacks: $1"; }
blacks() { ! btext | grep -qF -- "$1" || fail "backlog branch still has: $1"; }
ohas() { otext | grep -qF -- "$1" || fail "origin's backlog lacks: $1"; }
olsynced() { [ "$(git -C "$T/repo" rev-parse backlog)" = "$(git --git-dir="$T/origin" rev-parse backlog)" ] \
  || fail "origin's backlog is not synced"; }

# Start empty: no item folders, no backlog branch yet (a fresh clone).
BID=$(P next-id)
[ "$(P backlog | wc -l | tr -d ' ')" = 0 ] || fail "a fresh board should have an empty backlog"

P add "zoom jumps near walls" >/dev/null
P add "plain paragraph second line" >/dev/null
P add "idea to drop" >/dev/null
[ "$(P backlog | wc -l | tr -d ' ')" = 3 ] || fail "backlog should have 3 entries"
bhas "zoom jumps near walls"; ohas "zoom jumps near walls"; olsynced

TB | P todo 1 --title "Zoom A" --keep >/dev/null
TB | P todo 1 --title "Zoom B with a long-hyphenated title" | grep -q "^1\. plain paragraph second line" \
  || fail "todo should print the renumbered backlog"
A=$BID; Z=$((BID + 1))
has "1-todo/$A-zoom.md" "# #$A Zoom A"
has "1-todo/$Z-zoom-b-long-hyphenated.md" "# #$Z Zoom B"
has "1-todo/$A-zoom.md" "> zoom jumps near walls"
blacks "zoom jumps"

# Todo order: priority, then oldest first; --top makes it high.
P add "urgent thing" >/dev/null
TB | sed 's/^priority: normal/priority: low/' | P todo 3 --title "Late" >/dev/null
TB | sed 's/^priority: normal/priority: low/' | P todo 2 --top --title "Urgent" >/dev/null
L=$((BID + 2)); U=$((BID + 3))
has "1-todo/$U-urgent.md" "priority: high"
P status | grep -q "next:    /spak start $U" || fail "a --top todo should be next"
P drop "#$U" "test only" >/dev/null
P status | grep -q "next:    /spak start $A" || fail "a low todo should come last"
P drop "#$L" "test only" >/dev/null

# Several entries merge into one todo, each quoted and removed.
P add "merge one" >/dev/null; P add "merge two" >/dev/null
TB | P todo 3 2 --title "Merged" >/dev/null
M=$((U + 1))
has "1-todo/$M-merged.md" "> merge one"; has "1-todo/$M-merged.md" "> merge two"
has "1-todo/$M-merged.md" "## Subtasks"; has "1-todo/$M-merged.md" "- merge two"
blacks "merge one"; blacks "merge two"
# --into adds an entry to a todo as a subtask: no drop, and the todo's own
# work becomes its first subtask.
P add "merge three" >/dev/null
P todo 2 --into "$M" </dev/null >/dev/null
has "1-todo/$M-merged.md" "- merge three"; has "1-todo/$M-merged.md" "> merge three"
blacks "merge three"; lacks 4-done/dropped.md "merge three"
Ns=$(P next-id); P add "single" >/dev/null; TB | P todo 2 --title "Single" >/dev/null
P add "joins single" >/dev/null; P todo 2 --into "$Ns" </dev/null >/dev/null
awk '/^## Subtasks/{s=1} s&&/^- single$/{a=1} s&&/^- joins single$/{if(!a) exit 1; ok=1} END{exit !ok}' \
  "$T/repo/spak/1-todo/$Ns-single.md" || fail "--into lists the todo's own work first"
! TB | P todo 2 --title x --into "$Ns" 2>/dev/null || fail "--title with --into should fail"
P drop "#$Ns" "test only" >/dev/null
P drop "#$M" "test only" >/dev/null

P drop 1 "not wanted" >/dev/null; P drop "#$A" "duplicate" >/dev/null
has 4-done/dropped.md "- plain paragraph second line"; has 4-done/dropped.md "- #$A Zoom A"
blacks "plain paragraph second line"
gone "1-todo/$A-*"
[ "$(P next-id)" = $((Ns + 1)) ] || fail "next-id ignores a dropped #N"

D="2-doing/$Z-zoom-b-long-hyphenated.md"
P skeleton plan | P start "$Z" --branch-name zoom-b-long-hyphenated --no-git >/dev/null
gone "1-todo/$Z-*"
has "$D" "status: planned"; has "$D" "## Done when"; has "$D" "## Why"
has "$D" "branch: spak/$Z-zoom-b-long-hyphenated"
P status | grep -q "(spak/$Z-zoom-b-long-hyphenated)" || fail "status should show the branch"
# A user-approved branch name: checked, and bad or taken ones refused.
! P branch "$Z" --name "Bad_Name" 2>/dev/null || fail "a bad branch name should fail"
! P branch "$Z" --name "one-two-three-four-five" 2>/dev/null || fail "a 5-word branch name should fail"
Nb=$(P next-id); P add "name me" >/dev/null; TB | P todo 1 --title "Named branch" >/dev/null
[ -n "$(ls "$T/repo/spak/1-todo/$Nb-"* 2>/dev/null)" ] || fail "named todo"
git -C "$T/repo" branch "spak/$Nb-taken"
! P skeleton plan | P start "$Nb" --branch-name taken --no-git 2>/dev/null \
  || fail "a taken branch name should fail"
has "1-todo/$Nb-named-branch.md" "# #$Nb Named branch"
P skeleton plan | P start "$Nb" >/dev/null
P branch "$Nb" --name "spak/$Nb-short-name" --no-git >/dev/null
has "2-doing/$Nb-named-branch.md" "branch: spak/$Nb-short-name"
P drop "#$Nb" "test only" >/dev/null
P step "$Z" "a step added at a re-plan" >/dev/null
has "$D" "2. [ ] a step added at a re-plan"
P set-status "$Z" "in progress" >/dev/null; P tick "$Z" 1 >/dev/null
P note "$Z" "changed a step" >/dev/null
has "$D" "1. [x]"; has "$D" ": changed a step"

R="3-review/$Z-zoom-b-long-hyphenated.md"
P skeleton review | P review "$Z" >/dev/null
has "$R" "## What changed"; has "$R" "## Plan"; gone "$D"
P rework "$Z" "still jumps" >/dev/null
P skeleton review | P review "$Z" >/dev/null
P rework "$Z" "now it stutters" >/dev/null
has "$D" "status: back from review"; has "$D" "round: 2"
has "$D" "- round 1: still jumps"; has "$D" "- round 2: now it stutters"
has "$D" "1. [x]"; lacks "$D" "## What changed"

P skeleton review | P review "$Z" >/dev/null
P approve "$Z" "Zoom holds near walls." | grep -q "spak finish $Z" \
  || fail "approve should print the branch finish"
F="4-done/$Z-zoom-b-long-hyphenated.md"
has "$F" "# #$Z Zoom B with a long-hyphenated title"; has "$F" "## Done"; has "$F" "done: "
has "$F" "branch: spak/$Z-zoom-b-long-hyphenated"; has "$F" "- round 2: now it stutters"
gone "$R"
P show "$Z" | grep -q "^\[done\]" || fail "show should find a done item"

# back --todo: feedback that changes the item sends it to todo with a new
# body, the branch kept and the rounds so far folded; a re-plan keeps both,
# and later edits land above the fold.
Nt=$(P next-id); P add "rework me" >/dev/null; TB | P todo 1 --title "Rework" >/dev/null
P skeleton plan | P start "$Nt" --branch-name rework --no-git >/dev/null
echo "did the thing" | P selfcheck "$Nt" | grep -q '"point_1"' || fail "selfcheck from stdin"
echo "did the thing" | P selfcheck "$Nt" --state-file "$T/sc/state.json" | grep -q '"draft"' \
  && fail "selfcheck --state-file should leave the state out of what it prints"
grep -q '"did the thing"' "$T/sc/state.json" || fail "selfcheck --state-file should write the state"
echo "did the thing" | P selfcheck "$Nt" | grep -q '"point_1"' && \
  ! (echo "did the thing" | P selfcheck "$Nt" | grep -q 'report what came of') \
  || fail "selfcheck should ask about backing, not whether the draft reports a point"
printf 'tyke_check: PASS\ntop 0.440\n' > "$T/ev.txt"
echo "top at 0.440, width 0.158" | P selfcheck "$Nt" --evidence "$T/ev.txt" > "$T/sc.json"
grep -q 'Does `evidence` alone show' "$T/sc.json" || fail "selfcheck --evidence asks the evidence"
grep -q '"all_backed"' "$T/sc.json" || fail "selfcheck --evidence asks about every claim"
grep -q '"0.158"' "$T/sc.json" && ! grep -q '"0.440"' "$T/sc.json" \
  || fail "selfcheck --evidence lists cited numbers the evidence lacks, only those"
Np=$(P next-id); P add "prose point" >/dev/null
printf -- '---\ntype: chore\npriority: low\n---\n## Why\nx\n## Done when\n- the thing works\n- `docs/x.md` describes it\n' \
  | P todo 1 --title "Prose" >/dev/null
P skeleton plan | P start "$Np" --no-git >/dev/null 2>&1 || P skeleton plan | P start "$Np" >/dev/null
echo "done" | P selfcheck "$Np" > "$T/sp.json"
grep -q '"unasked_prose"' "$T/sp.json" && grep -q 'docs/x.md' "$T/sp.json" \
  && ! grep -q '"backed_2"' "$T/sp.json" || fail "selfcheck leaves a docs-only point unasked"
P drop "#$Np" "test only" >/dev/null
P skeleton review | P review "$Nt" >/dev/null
P selfcheck "$Nt" </dev/null | grep -q '"draft"' || fail "selfcheck of an item in review"
! P rework "$Nt" "rethink it" --todo </dev/null 2>/dev/null || fail "rework --todo needs a body"
[ -n "$(ls "$T/repo/spak/3-review/$Nt-"* 2>/dev/null)" ] || fail "a refused back --todo should leave the item in review"
TB | P rework "$Nt" "rethink it" --todo >/dev/null
Tt="1-todo/$Nt-rework.md"
has "$Tt" "branch: spak/$Nt-rework"; has "$Tt" "## Done when"
has "$Tt" "## Earlier rounds"; has "$Tt" "- round 1: rethink it"
has "$Tt" "sent back to todo (round 1)"
! P skeleton plan | P start "$Nt" --branch-name other --no-git 2>/dev/null || fail "a kept branch refuses a new one"
P skeleton plan | P start "$Nt" >/dev/null
Dt="2-doing/$Nt-rework.md"
has "$Dt" "branch: spak/$Nt-rework"; has "$Dt" "round: 1"
P step "$Nt" "second pass step" >/dev/null; P note "$Nt" "above the fold" >/dev/null
awk '/^## Earlier rounds/{h=1} /second pass step|above the fold/{if(h) exit 1}' "$T/repo/spak/$Dt" \
  || fail "step and note should land above the earlier rounds"
echo "did the thing" | P selfcheck "$Nt" | grep -q '"point_1"' || fail "selfcheck from stdin"
P skeleton review | P review "$Nt" >/dev/null
P selfcheck "$Nt" </dev/null | grep -q '"draft"' || fail "selfcheck of an item in review"
P rework "$Nt" "still off" >/dev/null
has "$Dt" "- round 2: still off"
echo "did the thing" | P selfcheck "$Nt" | grep -q "review feedback, round 2: still off" \
  || fail "selfcheck should ask about the review feedback too"
awk '/^## Earlier rounds/{h=1} /round 2: still off/{if(h) exit 1}' "$T/repo/spak/$Dt" \
  || fail "round 2 feedback should land in the live plan"
P drop "#$Nt" "test only" >/dev/null

# Hand edits: empty lines mean nothing, and a file that lost a part is
# refused before anything moves (each once lost data and said it worked).
Nh=$(P next-id); P add "hand edits" >/dev/null
printf -- '---\npriority: normal\n---\n## Why\n\nx\n\n## Done when\n\n- point one\n\n- point two\n' \
  | P todo 1 --title "Hand" >/dev/null
P skeleton plan | P start "$Nh" >/dev/null
Dh="2-doing/$Nh-hand.md"
has "$Dh" "- point two"
echo "x" | P selfcheck "$Nh" | grep -q '"point_2": "point two"' \
  || fail "an empty line between Done-when points should keep both"
P skeleton review | P review "$Nh" >/dev/null; P rework "$Nh" "first" >/dev/null
perl -0pi -e 's/## Review feedback\n\n/## Review feedback\n\n\n\n/' "$T/repo/spak/$Dh"
P skeleton review | P review "$Nh" >/dev/null; P rework "$Nh" "second feedback" >/dev/null
has "$Dh" "- round 2: second feedback"
echo "x" | P selfcheck "$Nh" | grep -q "round 2: second feedback" \
  || fail "extra empty lines under Review feedback should keep the feedback"
perl -pi -e 's/^## Log$/## Progress/' "$T/repo/spak/$Dh"
! P set-status "$Nh" "in progress" 2>/dev/null || fail "a doing item without a Log should be refused"
! P lint "$Nh" >/dev/null || fail "lint should report the missing Log"
P lint "$Nh" | grep -q "no ## Log section" || fail "lint names what's missing"
P status | grep -q "! no ## Log section" || fail "status flags a broken item"
perl -pi -e 's/^## Progress$/## Log/; s/^status: .*\n//' "$T/repo/spak/$Dh"
! P branch "$Nh" --name x --no-git 2>/dev/null || fail "a doing item without a status should be refused"
lacks "$Dh" "branch:"
perl -0pi -e 's/^---\n/---\nstatus: in progress\n/' "$T/repo/spak/$Dh"
P lint "$Nh" >/dev/null || fail "a repaired file should lint clean"
# A section spak doesn't know stays under the one it followed, and a `## `
# inside a code fence is text, not a section.
perl -0pi -e 's/(## Checks\n)/## Findings\n\n```sh\n## not a section\n```\n\n$1/' "$T/repo/spak/$Dh"
P note "$Nh" "kept" >/dev/null
awk '/^## Decisions/{d=1} /^## Findings/{if(!d) exit 1; f=1} /^## Checks/{if(!f) exit 1}' "$T/repo/spak/$Dh" \
  || fail "an unknown section should stay where it was"
has "$Dh" "## not a section"
P drop "#$Nh" "test only" >/dev/null

# Counts: "X of Y" is the one way a review writes one, checked like any number.
printf 'check.sh: 7 of 8 PASS\n' > "$T/ev2.txt"
Nc=$(P next-id); P add "counts" >/dev/null; TB | P todo 1 --title "Counts" >/dev/null
P skeleton plan | P start "$Nc" >/dev/null
printf '7 of 8 pass; 8 of 8 later; 95%% faster; all 12 pass; 3/4 checks\n' \
  | P selfcheck "$Nc" --evidence "$T/ev2.txt" > "$T/cc.json"
grep -q '"8 of 8"' "$T/cc.json" && ! grep -q '"7 of 8"' "$T/cc.json" && grep -q '"95%"' "$T/cc.json" \
  || fail "selfcheck checks X-of-Y counts and shares against the evidence"
grep -q '"all 12"' "$T/cc.json" && grep -q '"3/4"' "$T/cc.json" \
  || fail "selfcheck lists counts not written as X of Y"
P drop "#$Nc" "test only" >/dev/null
P lint >/dev/null || fail "the scratch board should lint clean"
printf -- '- see `nowhere/gone.md`\n' > "$T/r/dead.md"
P lint | grep -q "nowhere/gone.md. doesn't exist" || fail "lint should flag a dead path in the docs"
rm "$T/r/dead.md"

# Preferences: a file named each time, bullets only, standing rules only.
: > "$T/r/preferences.md"
! P preference "smoke" 2>/dev/null || fail "a preference needs --skill or --project"
P preference "smoke" --skill >/dev/null
P preference "likes it lively" --project >/dev/null
[ "$(cat "$T/repo/PREFERENCES.md")" = "- likes it lively" ] || fail "preference --project: one bare bullet at the root"
! grep -q "lively" "$T/r/preferences.md" || fail "a project preference stays out of spak's own"
[ "$(head -1 "$T/r/preferences.md")" = "- smoke" ] || fail "preference --skill: a bare bullet, no header"
! P preference "since 2026-01-01" --skill 2>/dev/null || fail "a dated preference should be refused"
! P preference "as in #23" --skill 2>/dev/null || fail "an item number should be refused"
P preference "a changed mind" --skill --replace "smoke" >/dev/null
grep -q -- "a changed mind" "$T/r/preferences.md" || fail "preference --replace"
! grep -q -- "- smoke" "$T/r/preferences.md" || fail "preference --replace leaves the old line"
! P preference "x" --skill --replace "no such line" 2>/dev/null || fail "--replace of nothing should fail"
P status | grep -q "next:    board is empty" || fail "status next move"
P add "one more" >/dev/null
P status | grep -q "next:    /spak refine" || fail "status next move: refine"
bhas "one more"; ohas "one more"; olsynced

! P show 999 2>/dev/null || fail "show of a missing item should fail"
! P tick 999 1 2>/dev/null || fail "tick of a missing item should fail"
! P todo 99 --title x </dev/null 2>/dev/null || fail "todo of a missing entry should fail"

# A fresh clone has only origin/backlog: it must read it, and its first
# write must build on origin's history so the push fast-forwards.
git clone -q -b "$(git -C "$T/repo" branch --show-current)" "$T/origin" "$T/clone"
git -C "$T/clone" config user.name spak-test
git -C "$T/clone" config user.email spak-test@scratch
P2() { python3 "$HERE/spak.py" --board "$T/clone/spak" --refs "$T/r" "$@"; }
P2 backlog | grep -qF -- "one more" || fail "a fresh clone should read origin's backlog"
P2 add "from the clone" >/dev/null
otext | grep -qF -- "from the clone" || fail "a fresh clone's add should push"
otext | grep -qF -- "one more" || fail "a fresh clone's add lost origin's entries"

# The first repo is now behind origin: its next write must fetch and
# fast-forward first, keeping the clone's entry.
P add "back in the first repo" >/dev/null
bhas "from the clone"; ohas "back in the first repo"; olsynced

# A board outside any git repo falls back to a real backlog file.
mkdir -p "$T/plain/spak"
P3() { python3 "$HERE/spak.py" --board "$T/plain/spak" --refs "$T/r" "$@"; }
P3 add "offline board" >/dev/null
grep -qF -- "offline board" "$T/plain/spak/0-BACKLOG.md" \
  || fail "a non-repo board should keep its backlog as a file"

# Found from inside the repo with no --board: the column folders mark it.
(cd "$T/repo" && python3 "$HERE/spak.py" --refs "$T/r" status) | grep -q "^next:" \
  || fail "the board should be found by its columns"
# Checkpoints go to a side ref and never move the branch, so every change
# stays pending; finish puts them all on the branch for the squash merge.
Nf=$(P next-id); P add "finish me" >/dev/null; TB | P todo 1 --title "Finish" >/dev/null
P skeleton plan | P start "$Nf" --branch-name finish >/dev/null
base=$(git -C "$T/repo" rev-parse HEAD)
echo "feature" > "$T/repo/feature.txt"
P tick "$Nf" 1 | grep -q "checkpoint .* on refs/spak/$Nf" || fail "tick should save a checkpoint on a branch"
has "2-doing/$Nf-finish.md" "status: in progress"
[ "$(git -C "$T/repo" rev-parse HEAD)" = "$base" ] || fail "a checkpoint must not move the branch"
git -C "$T/repo" status --short | grep -q "feature.txt" || fail "the change should stay pending"
P checkpoint "nothing new" | grep -q "checkpoint" && fail "a checkpoint with no change should save nothing"
echo "more" >> "$T/repo/feature.txt"
P skeleton review | P review "$Nf" | grep -q "checkpoint" || fail "review should save a checkpoint"
P approve "$Nf" "Finished." | grep -q "spak finish $Nf" || fail "approve should point to finish"
P finish "$Nf" | grep -q "git merge --squash spak/$Nf-finish" || fail "finish should print the squash merge"
[ "$(git -C "$T/repo" branch --show-current)" = main ] || fail "finish should end on main"
[ "$(git -C "$T/repo" rev-list --count "main..spak/$Nf-finish")" = 3 ] || fail "every checkpoint should be on the branch"
git -C "$T/repo" rev-parse -q --verify "refs/spak/$Nf" >/dev/null && fail "finish should drop the side ref"
git -C "$T/repo" merge --squash -q "spak/$Nf-finish" >/dev/null
git -C "$T/repo" diff --cached --name-only | grep -q "feature.txt" || fail "the squash should bring the item"
git -C "$T/repo" commit -qm "finish"; git -C "$T/repo" branch -qD "spak/$Nf-finish"
# From a worktree while another tree has main: finish stays on the branch and
# prints the merge for the tree that has main, and that flow lands it.
Nw=$(P next-id); P add "finish from a worktree" >/dev/null; TB | P todo 1 --title "Worktree" >/dev/null
P skeleton plan | P start "$Nw" --branch-name wt >/dev/null
git -C "$T/repo" switch -q main
git -C "$T/repo" worktree add -q "$T/wt" "spak/$Nw-wt"
mkdir -p "$T/wt/spak/2-doing"; mv "$T/repo/spak/2-doing/$Nw-"*.md "$T/wt/spak/2-doing/"
W() { python3 "$HERE/spak.py" --board "$T/wt/spak" --refs "$T/r" "$@"; }
echo "worktree" > "$T/wt/wt.txt"
W skeleton review | W review "$Nw" >/dev/null
W approve "$Nw" "From a worktree." >/dev/null
W finish "$Nw" > "$T/finish.txt" || fail "finish should run in a worktree"
grep -q -- "-C .*repo merge --squash spak/$Nw-wt" "$T/finish.txt" || fail "finish should print the merge for the tree that has main"
[ "$(git -C "$T/wt" branch --show-current)" = "spak/$Nw-wt" ] || fail "finish should leave the worktree on its branch"
git -C "$T/repo" merge --squash -q "spak/$Nw-wt" >/dev/null
git -C "$T/repo" diff --cached --name-only | grep -q "wt.txt" || fail "the squash from a worktree should bring the item"
git -C "$T/repo" commit -qm "worktree"; git -C "$T/repo" worktree remove "$T/wt"
git -C "$T/repo" branch -qD "spak/$Nw-wt" || fail "the branch should go once the worktree has"
python3 "$REPO/.claude/hooks/git_guard.py" --test >/dev/null || fail "git guard self-test"

echo "spak smoke: PASS"