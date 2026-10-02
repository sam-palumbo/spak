# refine: backlog → todo

1. `spak backlog`; refine the entries named, else all. `spak status` shows
   todo and done: an entry may be a duplicate, or dropped before.
2. Find the code and docs each entry touches. An entry that names an
   inspiration source: research it online first.
3. Propose its shape: one todo, several (unrelated things mixed), merged
   with another, or dropped (only on the user's yes: `spak drop n
   "reason"`). Offer merging two entries that touch the same thing; merged
   entries become subtasks, never drops, and the user asking to merge is
   the yes. A related side issue nearby: recommend including it when it's
   the same kind of fix, and still offer backlog.
4. Ask at least one round, even when the entry looks clear, until the todo
   could go to someone who never met the user: what's wanted, why, what
   done looks like (concrete, checkable, **one claim per point**), what's
   out of scope. Your reading of the entry is the first option; keep each
   option's description to its own question. One round for several
   entries.
5. Write each todo once its answers are in:

   ```sh
   spak todo <n…> --title "Plain title" [--top] [--keep] <<'EOF'
   <spak skeleton todo>
   EOF
   ```

   `--keep` leaves the entry for another todo (a split); `--top` makes it
   high priority. Several entries make one todo with `## Subtasks`: give
   each its own Done-when points. Into an existing todo: `spak todo n
   --into M`.
