# start: todo → doing

1. `spak show N`, then read the code it touches: the files, the functions,
   the checks that cover them.
2. Find the decisions where reasonable people would differ. Settle what
   the project already answers (`CLAUDE.md`, docs, its patterns) and say
   how; ask the rest. Always: branch or not (yes for bigger or riskier
   work). A bug of unknown cause: ask where the user saw it.
3. Propose the plan in chat: the goal in a sentence, the decisions (tagged
   user, project or AI), steps small enough to tick, and the checks (the
   project's, as its `CLAUDE.md` runs them, plus this item's own check,
   render or screenshot). Where it leans on a safeguard, say what's
   enforced (a hook, a check, the script) and what's only instructed. Ask
   the open decisions and "Is this plan right?" in one batch, the plan
   written assuming the recommended answers. A branch's name is its own
   question: 2-3 names, `spak/N-` plus 1-4 lowercase words saying what it
   touches.
4. On the user's yes:

   ```sh
   spak start N [--branch-name <chosen>] <<'EOF'
   <spak skeleton plan>
   EOF
   ```

   An item already in doing gets its branch with `spak branch N --name
   <chosen>`.

A re-plan after rework: `spak step N "…"`, and edit `## Decisions` in
place (then `spak lint N`). A todo back from `rework --todo` keeps its
branch: no branch question. A follow-up question from the user isn't a
no: answer it, fold it into the plan, and move on their yes.
