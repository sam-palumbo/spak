# work: doing → review

1. Follow the plan, ticking steps in batches: `spak tick N 1 2 3` (it
   marks the item in progress and, on a branch, saves a checkpoint; `spak
   checkpoint "…"` saves one mid-step).
2. A step turns out wrong: if small, adjust and `spak note N "what and
   why"`; if it changes what the user agreed to, stop and ask. A tool call
   the user rejects with new feedback: fold it into this round (`spak
   note`) and carry on. A side issue: ask fix here, backlog or leave;
   recommend fix-here when it's in code or a screen the item touches, else
   backlog. In shared code, prototype and measure first.
3. Run the plan's checks as the project's `CLAUDE.md` runs them, and look
   at renders and screenshots yourself. A check you can't run here (a
   missing tool, no window): say so in the review. On anything judged by
   feel, the user's eye beats your metric: measure what they describe,
   keep what they liked, change the mechanism.
4. Self-check against the evidence. Put the real results in one file in
   the project's scratch folder, fresh each round, as they came out: the check lines, the
   lines the review quotes, probe and timing numbers, and a line per
   render saying what was seen. In a rework round it still asks every
   Done-when point, so carry the earlier rounds' proof that still holds
   (rerun or re-quote it); left out, the untouched points come back
   unsure. Then

   ```sh
   spak selfcheck N --evidence <file> --state-file <scratch>/scN.json < body.md
   ```

   and pass its questions to Jev's `ask` with the `state_file`. Fix each
   entry in `counts_to_rewrite` and `numbers_not_in_evidence`, and each
   answer that isn't a sure yes; a point in `unasked_prose` gets "reread"
   in the review. `learn` what you checked. A visual claim is backed by its
   render line, not by Jev.
5. Tick the rest, then:

   ```sh
   spak review N <<'EOF'
   <spak skeleton review>
   EOF
   ```

   Say what changed, how the user can see it (exact commands), each
   check's result as it came out, and what differs from the plan. Copy
   each number from its output line and read it back as you write it;
   counts as "X of Y". Don't commit.
