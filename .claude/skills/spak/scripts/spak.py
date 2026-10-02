#!/usr/bin/env python3
"""spak board tool: every mechanical step of a spak move, so the model only
writes content and asks the user.

The board is spak/: the backlog (below its `---` line, one entry per `- `
line or paragraph) lives only on a `backlog` git branch, pushed to
`origin` as the backup; there is no backlog file on main. Todo, doing,
review and done are folders with one file per item, `N-slug.md`: a short
header the script owns, the `# #N Title` line, then `## ` sections (see
`Item`). A move rewrites the file into the next folder. Dropped entries are
bullets in 4-done/dropped.md.

Never commits to the working branch or merges: those are visible git
commands the model runs, so the project's git guard hook can ask the user.
The git steps it takes are the mechanical ones: creating an item's branch
(`branch`, `start --branch`) and keeping the `backlog` branch current
(`flush_backlog`) — the backlog's own commits and pushes are its autosave,
not project history.

Run `spak.py -h` for the commands; `spak.py skeleton <todo|plan|review>`
prints the body each move reads from stdin.
"""

import argparse
import datetime
import os
import re
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

HERE = Path(__file__).resolve().parent
# The backlog's file name on the `backlog` branch (`spak/0-BACKLOG.md` there,
# never on main). Only a board outside any git repo keeps it as a real file.
BACKLOG = "0-BACKLOG.md"
COLS = {"todo": "1-todo", "doing": "2-doing", "review": "3-review",
        "done": "4-done"}
DROPPED = "4-done/dropped.md"
DROPPED_HEAD = """# Dropped

Backlog entries and items the user chose not to do, so they aren't raised
again. Written by `/spak`.
"""
ITEM = re.compile(r"^# #(\d+) (.*)$")
ITEM_FILE = re.compile(r"^(\d+)-.*\.md$")
DROPPED_ID = re.compile(r"^- #(\d+)\b", re.M)
RANK = {"high": 0, "normal": 1, "low": 2}
STEP = re.compile(r"^(\d+)\. \[[ x]\] ")

# The header's keys, in the order they're written. The script owns them.
HEAD_KEYS = ("status", "type", "priority", "branch", "round", "done")
# Where each known section sits, top to bottom: the newest stage's sections
# first, the history last. A section spak doesn't know (a write-up's extra,
# say) stays under the known one it followed.
ORDER = ("Done",
         "What changed", "How to check it", "Check results",
         "Differs from the plan", "Open questions",
         "Goal", "Decisions", "Plan", "Checks",
         "Why", "Subtasks", "Done when", "Not in scope", "Notes",
         "From the backlog",
         "Review feedback", "Log", "Earlier rounds")
# The sections that last from plan to done. The rest are a review's
# write-up, which `back` replaces with the next one.
LASTING = set(ORDER[ORDER.index("Goal"):])
# What each column's items must have, so a move never builds on a file that
# lost a part (a missing Log once swallowed the user's review feedback).
NEEDS = {"todo": ("Why", "Done when"),
         "doing": ("Goal", "Plan", "Done when", "Log"),
         "review": ("What changed", "How to check it", "Check results",
                    "Plan", "Done when", "Log"),
         "done": ("Done",)}
NEEDS_HEAD = {"todo": "priority", "doing": "status", "review": "status",
              "done": "done"}

SKELETONS = {
    # Body for `todo`: the title and the backlog quote are added for you.
    "todo": """\
---
type: bug | feature | improvement | idea | chore
priority: high | normal | low
---
## Why

What's wrong or wanted, and why it matters.

## Done when

- a concrete, checkable outcome: one claim per point

## Not in scope

What this deliberately leaves out.

## Notes

The user's answers, relevant files (`path/to/file:120`), risks.
""",
    # Body for `plan`: status, the log and everything the todo had are kept.
    "plan": """\
## Goal

One sentence.

## Decisions

- the choice (user) or (project: why) or (AI: why).

## Plan

1. [ ] a step small enough to tick

## Checks

Which checks, renders or screenshots prove it.
""",
    # Body for `review`: sits on top of the plan, which `back` keeps.
    "review": """\
## What changed

The files and what each change does.

## How to check it

- the exact command, and what you should see.

## Check results

Each check's result as it came out; counts as "X of Y", measurements as
printed.

## Differs from the plan

What and why.

## Open questions

Anything to decide while reviewing.
""",
}


def stamp():
    """**Every date spak writes is a timestamp**, `YYYY-MM-DD.HH:MM:SS` (the
    user's rule); dates written before it stay as they are."""
    return datetime.datetime.now().strftime("%Y-%m-%d.%H:%M:%S")


def wrap_bullet(text, indent="  "):
    """A `- ` bullet wrapped to the board's width, continuation indented."""
    return textwrap.fill(" ".join(text.split()), 76, initial_indent="- ",
                         subsequent_indent=indent, break_on_hyphens=False,
                         break_long_words=False)


def die(msg):
    sys.exit("spak: " + msg)


def read_stdin(what):
    if sys.stdin.isatty():
        die(what + " reads its body from stdin (see `skeleton`)")
    body = sys.stdin.read().strip()
    if not body:
        die(what + " got an empty body")
    return body


FILLER = {"a", "an", "the", "of", "to", "for", "and", "or", "in", "on",
          "at", "by", "with", "its", "it", "is", "be", "make", "let"}


def slug(title):
    """The fallback branch/file slug: the title's first four words that
    aren't filler, so names don't end on 'the' or 'a'."""
    words = re.findall(r"[a-z0-9]+", title.lower())
    return "-".join([w for w in words if w not in FILLER][:4] or words[:4])


BRANCH_NAME = re.compile(r"^[a-z0-9]+(-[a-z0-9]+){0,3}$")


def check_branch_name(n, name):
    """A user-approved branch name, as `spak/N-<name>`: 1-4 lowercase
    hyphenated words, at most 40 characters, not an existing branch."""
    name = name.strip()
    prefix = "spak/%s-" % n
    if name.startswith(prefix):
        name = name[len(prefix):]
    if not BRANCH_NAME.match(name):
        die("branch name %r: use 1-4 lowercase words joined by hyphens "
            "(e.g. branch-names)" % name)
    full = prefix + name
    if len(full) > 40:
        die("branch name %s is %d characters; keep it to 40"
            % (full, len(full)))
    if run_git("rev-parse", "--verify", "--quiet", "refs/heads/" + full,
                check=False).returncode == 0:
        die("branch %s already exists" % full)
    return full


class Item:
    """One item file, read as a structure rather than hunted with patterns:

        ---
        status: in progress
        priority: normal
        ---
        # #7 Title

        ## Section
        ...

    The header is `key: value` lines (only HEAD_KEYS). A section runs to the
    next `## ` line outside a code fence, so **empty lines mean nothing**
    and a hand edit can't cut a section short. Anything the parser can't
    place stops it with the file and line, before a move changes anything.
    A fragment (a body from stdin) is the same without the title line."""

    def __init__(self, n=None, title="", head=None):
        self.n, self.title = n, title
        self.head = dict(head or {})
        self.sections = []  # [name, body, anchor]: anchor places an unknown one

    @classmethod
    def parse(cls, text, where, fragment=False):
        lines = text.splitlines()
        it, k = cls(), 0
        while k < len(lines) and not lines[k].strip():
            k += 1
        if k < len(lines) and lines[k].strip() == "---":
            start, k = k, k + 1
            while k < len(lines) and lines[k].strip() != "---":
                line = lines[k]
                if line.strip():
                    key, sep, value = line.partition(":")
                    key = key.strip()
                    if not sep or key not in HEAD_KEYS:
                        die("%s:%d: %r isn't a header line (keys: %s)"
                            % (where, k + 1, line, ", ".join(HEAD_KEYS)))
                    if fragment and key not in ("type", "priority"):
                        die("%s:%d: a body sets only type and priority; "
                            "spak writes %s" % (where, k + 1, key))
                    it.head[key] = value.strip()
                k += 1
            if k == len(lines):
                die("%s:%d: the header's --- is never closed"
                    % (where, start + 1))
            k += 1
        if not fragment:
            while k < len(lines) and not lines[k].strip():
                k += 1
            m = ITEM.match(lines[k]) if k < len(lines) else None
            if not m:
                die("%s:%d: expected the `# #N Title` line" % (where, k + 1))
            it.n, it.title = int(m.group(1)), m.group(2).strip()
            k += 1
        fence, cur, anchor = False, None, None
        for i in range(k, len(lines)):
            line = lines[i]
            if line.lstrip().startswith("```"):
                fence = not fence
            if not fence and line.startswith("## "):
                name = line[3:].strip()
                if it.has(name):
                    die("%s:%d: a second ## %s" % (where, i + 1, name))
                cur = [name, [], None if name in ORDER else anchor]
                it.sections.append(cur)
                anchor = name if name in ORDER else anchor
                continue
            if cur is None:
                if line.strip():
                    die("%s:%d: text before the first ## section: %r"
                        % (where, i + 1, line[:60]))
                continue
            cur[1].append(line)
        for s in it.sections:
            s[1] = "\n".join(s[1]).strip("\n")
        return it

    def has(self, name):
        return any(s[0] == name for s in self.sections)

    def get(self, name):
        return next((s[1] for s in self.sections if s[0] == name), "")

    def set(self, name, body):
        for s in self.sections:
            if s[0] == name:
                s[1] = body.strip("\n")
                return
        self.sections.append([name, body.strip("\n"), None])

    def append(self, name, line):
        """A line at the end of a section, made if it's missing."""
        self.set(name, (self.get(name) + "\n" + line).strip("\n"))

    def merge(self, frag, what):
        """A fragment's header and sections, all new: one the item already
        has means the body repeats what an earlier move wrote."""
        self.head.update(frag.head)
        for name, body, anchor in frag.sections:
            if self.has(name):
                die("%s repeats ## %s, which #%s already has"
                    % (what, name, self.n))
            self.sections.append([name, body, anchor])

    def lasting(self, s):
        name, _, anchor = s
        return name in LASTING or (name not in ORDER and anchor in LASTING)

    def ordered(self):
        def key(p):
            pos, (name, _, anchor) = p
            if name in ORDER:
                return (ORDER.index(name), 0, pos)
            return (ORDER.index(anchor) if anchor else -1, 1, pos)
        return [s for _, s in sorted(enumerate(self.sections), key=key)]

    def render(self):
        head = ["%s: %s" % (k, self.head[k]) for k in HEAD_KEYS
                if str(self.head.get(k, "")).strip()]
        out = ["---"] + head + ["---", "# #%s %s" % (self.n, self.title)]
        for name, body, _ in self.ordered():
            out += ["", "## " + name]
            if body.strip():
                out += ["", body]
        return "\n".join(out) + "\n"

    def problems(self, col):
        out = ["no ## %s section" % s for s in NEEDS[col] if not self.has(s)]
        if not self.head.get(NEEDS_HEAD[col]):
            out.append("no `%s:` in its header" % NEEDS_HEAD[col])
        p = self.head.get("priority")
        if p and p not in RANK:
            out.append("priority %r: use high, normal or low" % p)
        r = self.head.get("round")
        if r and not r.isdigit():
            out.append("round %r: a number" % r)
        return out


def list_points(body):
    """A section's `- ` bullets, one string each (continuations joined,
    empty lines between bullets ignored)."""
    out = []
    for l in body.splitlines():
        if l.startswith("- "):
            out.append(l[2:].strip())
        elif out and l.strip():
            out[-1] += " " + l.strip()
    return out


class Board:
    def __init__(self, root):
        self.root = Path(root)
        if not self.root.is_dir():
            die("no board at %s" % self.root)
        self._git_ok = \
            run_git("rev-parse", "--is-inside-work-tree",
                    check=False).returncode == 0
        if self._git_ok:
            self._sync_backlog()
        self._backlog = self._load_backlog()

    def path(self, name):
        return self.root / name

    def text(self, name):
        return self.path(name).read_text()

    def write(self, name, text):
        self.path(name).write_text(text.rstrip("\n") + "\n")

    def _branch_path(self):
        """The backlog's path in the git tree, root-relative (spak/...)."""
        return str(self.root.resolve().relative_to(repo_root()) / BACKLOG)

    def _sync_backlog(self):
        """Bring the local `backlog` branch up to origin's before anything
        reads or writes it: fetch (best-effort, offline is fine), then
        create the local branch from origin's (a fresh clone) or
        fast-forward it. A local branch ahead of origin is an unpushed
        write; one that diverged is left alone with a warning, since
        merging free text is the user's call."""
        if not self._remote():
            return
        run_git("fetch", "--quiet", "origin", "backlog", check=False,
                env={"GIT_TERMINAL_PROMPT": "0"})
        theirs = rev("refs/remotes/origin/backlog")
        if not theirs:
            return
        ours = rev("refs/heads/backlog")
        if ours == theirs or (ours and is_ancestor(theirs, ours)):
            return
        if not ours or is_ancestor(ours, theirs):
            run_git("update-ref", "refs/heads/backlog", theirs)
            return
        print("backlog: the local backlog branch and origin's have "
              "diverged; using the local one, and its push will fail "
              "until they're merged (git log backlog...origin/backlog)")

    def _load_backlog(self):
        """The backlog text: the `backlog` branch, then origin's, then the
        local file (a board outside git), then the default head."""
        if self._git_ok:
            for ref in ("backlog", "origin/backlog"):
                r = run_git("show", "%s:%s" % (ref, self._branch_path()),
                            check=False)
                if r.returncode == 0:
                    return r.stdout.rstrip("\n")
        p = self.root / BACKLOG
        if p.exists():
            return p.read_text().rstrip("\n")
        return BACKLOG_HEAD.rstrip("\n")

    # Item folders: one `N-slug.md` per item. Empty folders aren't in git,
    # so a missing one is just empty.

    def files(self, col):
        d = self.root / COLS[col]
        return [f for f in d.iterdir() if ITEM_FILE.match(f.name)] \
            if d.is_dir() else []

    def where(self, f):
        return str(f.relative_to(self.root))

    def read(self, f, col):
        """(item, its problems for col); parse errors still stop."""
        it = Item.parse(f.read_text(), self.where(f))
        return it, it.problems(col)

    def items(self, col):
        """[(file, #N, item or None, problems)], in the column's order: todo
        by priority then oldest first, done newest first, the rest oldest
        first. A file that won't parse is listed with why, not fatal, so
        `status` can show it."""
        out = []
        for f in self.files(col):
            n = int(ITEM_FILE.match(f.name).group(1))
            try:
                it = Item.parse(f.read_text(), self.where(f))
                out.append((f, n, it, it.problems(col)))
            except SystemExit as e:
                out.append((f, n, None, [str(e).replace("spak: ", "", 1)]))
        if col == "todo":
            return sorted(out, key=lambda r: (
                RANK.get(r[2].head.get("priority"), 1) if r[2] else 1, r[1]))
        return sorted(out, key=lambda r: r[1], reverse=(col == "done"))

    def locate(self, n, cols=("todo", "doing", "review")):
        """(column, file) of #n, by file name alone."""
        for col in cols:
            for f in self.files(col):
                if ITEM_FILE.match(f.name).group(1) == str(n):
                    return col, f
        die("#%s is not in %s" % (n, " / ".join(cols)))

    def find(self, n, cols=("todo", "doing", "review")):
        """(column, file, item) of #n, refusing a file with problems: a move
        builds on every part of it."""
        col, f = self.locate(n, cols)
        it, probs = self.read(f, col)
        if probs:
            die("#%s (%s): %s. Fix the file, then `spak lint %s`"
                % (n, self.where(f), "; ".join(probs), n))
        return col, f, it

    def put(self, col, it, old=None):
        """Write `it` into col, checked first; then remove `old` if it was
        elsewhere. Nothing is removed before the new file is written."""
        probs = it.problems(col)
        if probs:
            die("#%s wouldn't be a valid %s item: %s"
                % (it.n, col, "; ".join(probs)))
        d = self.root / COLS[col]
        d.mkdir(exist_ok=True)
        f = d / ("%s-%s.md" % (it.n, slug(it.title)))
        f.write_text(it.render())
        if old and old.resolve() != f.resolve():
            old.unlink()

    def next_id(self):
        ids = {int(ITEM_FILE.match(f.name).group(1))
               for col in COLS for f in self.files(col)}
        if self.path(DROPPED).exists():
            ids |= {int(m.group(1))
                    for m in DROPPED_ID.finditer(self.text(DROPPED))}
        ids |= self._branch_item_ids()
        return max(ids, default=0) + 1

    def _branch_item_ids(self):
        """Item IDs on any local branch's board or checkpoint ref, so an
        item mid-flight keeps its ID reserved in every checkout (a refine
        can run in a worktree whose tree doesn't hold that item)."""
        if not self._git_ok:
            return set()
        ids = set()
        for ref in git("for-each-ref", "--format=%(refname)",
                       "refs/heads", "refs/spak").split():
            out = run_git("ls-tree", "-r", "--name-only", ref, "--", "spak",
                          check=False)
            if out.returncode == 0:
                for line in out.stdout.splitlines():
                    m = ITEM_FILE.match(Path(line).name)
                    if m:
                        ids.add(int(m.group(1)))
        return ids

    # The backlog: free text below `---`, on the `backlog` branch (or, only
    # when the board isn't in a git repo, in a local file).

    def backlog(self):
        text = self._backlog
        m = re.search(r"^---[ \t]*$", text, re.M)
        if not m:
            die(BACKLOG + " lost its --- line")
        head, body = text[:m.end()], text[m.end():]
        entries, cur = [], None
        for line in body.splitlines():
            if not line.strip():
                cur = None
            elif line.startswith("- ") or cur is None:
                cur = [line]
                entries.append(cur)
            else:
                cur.append(line)
        return head, entries

    def write_backlog(self, head, entries):
        body = "\n\n".join("\n".join(e) for e in entries)
        self.flush_backlog(head + ("" if not body else "\n\n" + body))

    def flush_backlog(self, text):
        """Make `text` the backlog: on the `backlog` branch in a git repo
        (committing and pushing it), else in the local file only."""
        text = text.rstrip("\n")
        self._backlog = text
        if not self._git_ok:
            (self.root / BACKLOG).write_text(text + "\n")
            return
        self._flush_branch(text + "\n")

    def _flush_branch(self, text):
        """Commit `text` onto the backlog branch and push it, plumbing so
        the working tree and checked-out branch are never touched."""
        path = self._branch_path()
        if backlog_ref_exists():
            tip = run_git("show", "backlog:" + path, check=False)
            if tip.returncode == 0 and tip.stdout == text:
                self._push_backlog()  # retry a push that failed earlier
                return
        blob = run_git("hash-object", "-w", "--stdin", input=text)
        blob = blob.stdout.strip()
        with tempfile.NamedTemporaryFile(prefix="spak-index-") as f:
            env = {"GIT_INDEX_FILE": f.name}
            seed = ["read-tree", "--empty"] if not backlog_ref_exists() \
                else ["read-tree", "backlog"]
            run_git(*seed, env=env)
            run_git("update-index", "--add", "--cacheinfo",
                    "100644,%s,%s" % (blob, path), env=env)
            tree = run_git("write-tree", env=env).stdout.strip()
        parents = ["-p", "backlog"] if backlog_ref_exists() else []
        commit = run_git("commit-tree", tree, *parents,
                         "-m", "backlog: %s" % stamp()).stdout.strip()
        run_git("update-ref", "refs/heads/backlog", commit)
        self._push_backlog()

    def _push_backlog(self):
        """Best-effort push of the backlog branch; a failure just means it
        stays local and the next write pushes it."""
        remote = self._remote()
        if not remote:
            print("backlog: saved on the backlog branch; no remote to push "
                  "to")
            return
        r = run_git("push", remote, "backlog", check=False)
        if r.returncode:
            err = r.stderr.strip().splitlines()
            print("backlog: saved locally; the push to %s will retry next "
                  "time: %s" % (remote, err[-1] if err else "unknown error"))

    def _remote(self):
        """`origin` if the repo has it: the backlog's backup is always
        origin, the one remote the docs and the git guard name."""
        return "origin" if "origin" in git("remote").split() else ""

    def take_backlog(self, k):
        head, entries = self.backlog()
        if not 1 <= k <= len(entries):
            die("no backlog entry %d (there are %d)" % (k, len(entries)))
        entry = entries.pop(k - 1)
        return head, entries, entry

    def add_dropped(self, bullet):
        p = self.path(DROPPED)
        p.parent.mkdir(exist_ok=True)
        text = p.read_text().rstrip("\n") if p.exists() else DROPPED_HEAD
        sep = "\n" if text.splitlines()[-1].startswith("  ") or \
            text.splitlines()[-1].startswith("- ") else "\n\n"
        self.write(DROPPED, text.rstrip("\n") + sep + bullet)


def entry_text(lines):
    first = lines[0][2:] if lines[0].startswith("- ") else lines[0]
    return " ".join([first.strip()] + [l.strip() for l in lines[1:]])


def read_fragment(what):
    return Item.parse(read_stdin(what), what + " body", fragment=True)


# Commands.

def cmd_status(b, a):
    _, entries = b.backlog()
    print("backlog  %d" % len(entries))
    for k, e in enumerate(entries, 1):
        t = entry_text(e)
        print("  %d. %s" % (k, t if len(t) <= 90 else t[:87] + "..."))
    for col in ("todo", "doing", "review"):
        rows = b.items(col)
        print("%-8s %d" % (col, len(rows)))
        for f, n, it, probs in rows:
            if it is None:
                print("  #%s %s" % (n, f.name))
            else:
                tag = ""
                if col != "todo":
                    tag = "  [%s%s]" % (it.head.get("status", "?"),
                                        ", round " + it.head["round"]
                                        if it.head.get("round") else "")
                if it.head.get("branch"):
                    tag += "  (%s)" % it.head["branch"]
                print("  #%s %s%s" % (n, it.title, tag))
            for p in probs:
                print("    ! " + p)
    dropped = b.text(DROPPED) if b.path(DROPPED).exists() else ""
    print("done     %d  (dropped %d)" % (
        len(b.files("done")), len(re.findall(r"^- ", dropped, re.M))))
    print("next id  #%d" % b.next_id())
    print("next:    " + next_move(b, entries))


def next_move(b, entries):
    first = {c: b.items(c) for c in ("review", "doing", "todo")}
    n = {c: v[0][1] for c, v in first.items() if v}
    if "review" in n:
        return "review #%s: /spak approve #%s, or /spak rework %s \"why\"" % (
            (n["review"],) * 3)
    if "doing" in n:
        return "/spak work %s" % n["doing"]
    if "todo" in n:
        return "/spak start %s" % n["todo"]
    if entries:
        return "/spak refine"
    return "board is empty: add to the backlog or /spak add \"...\""


def cmd_lint(b, a):
    """Every item file (or #N) parses and has what its column needs: run it
    after editing an item file by hand."""
    total, bad = 0, 0
    for col in COLS:
        for f, n, it, probs in b.items(col):
            if a.n and str(n) != a.n:
                continue
            total += 1
            bad += bool(probs)
            for p in probs:
                print("%s: %s" % (b.where(f), p))
    if a.n and not total:
        die("#%s is on no column" % a.n)
    print("lint: %d of %d items ok" % (total - bad, total))
    docs = [] if a.n else doc_problems(b, Path(a.refs))
    for p in docs:
        print(p)
    if docs:
        print("lint: %d doc problem(s)" % len(docs))
    sys.exit(1 if bad or docs else 0)


# A backticked token that names a file or folder; a placeholder (`N`,
# `<x>`, `…`) or a command (it has spaces) isn't checked.
DOC_TOKEN = re.compile(r"`([^`\s]+)`")
PLACEHOLDER = re.compile(r"[<>…*$|{}=]|(?<![A-Za-z])N(?![a-z])")


def doc_problems(b, refs):
    """**The stale sweep's mechanical half**: a path the docs name that
    doesn't exist, and a skill file nothing names. The docs are the skill's
    own and the project's `CLAUDE.md` and `PREFERENCES.md`."""
    skill, root = refs.parent, repo_root()
    docs = [skill / "SKILL.md", skill / "README.md",
            *sorted(refs.glob("*.md")), root / "CLAUDE.md",
            root / PROJECT_PREFS]
    docs = [d for d in dict.fromkeys(docs) if d.exists()]
    bases = [root, HERE.parents[3], skill, refs, b.root]
    out = []
    for d in docs:
        for i, line in enumerate(d.read_text().splitlines(), 1):
            for tok in DOC_TOKEN.findall(line):
                path = re.sub(r":\d+$", "", tok)
                if not ("/" in path or path.endswith(".md")) or \
                        path.startswith(("http", "-", "/", "#")) or \
                        PLACEHOLDER.search(path):
                    continue
                if not any((base / path).exists()
                           for base in bases + [d.parent]):
                    out.append("%s:%d: `%s` doesn't exist" % (d.name, i, tok))
    if (skill / "SKILL.md").exists():
        for f in [*refs.glob("*.md"), *(skill / "scripts").glob("*")]:
            if not any(f.name in d.read_text() for d in docs if d != f):
                out.append("%s: no doc names it" % f.relative_to(skill))
    return out


def cmd_next_id(b, a):
    print(b.next_id())


def cmd_backlog(b, a):
    _, entries = b.backlog()
    for k, e in enumerate(entries, 1):
        print("%d. %s" % (k, entry_text(e)))


def cmd_add(b, a):
    head, entries = b.backlog()
    entries.append(wrap_bullet(a.text).splitlines())
    b.write_backlog(head, entries)
    print("added as backlog entry %d" % len(entries))


def cmd_show(b, a):
    col, f = b.locate(a.n, tuple(COLS))
    print("[%s] %s\n%s" % (col, b.where(f), f.read_text()))


def cmd_skeleton(b, a):
    print(SKELETONS[a.kind], end="")


def quote(entries):
    return "\n>\n".join(
        "\n".join("> " + l.strip() for l in
                  [e[0][2:] if e[0].startswith("- ") else e[0]] + e[1:])
        for e in entries)


def cmd_todo(b, a):
    """Backlog entries -> one todo. **Merged entries are subtasks, not
    drops** (the user's call): several entries, or `--into M`, list each in
    `## Subtasks` in the user's words, and each is quoted and removed from
    the backlog; nothing goes to dropped.md."""
    if a.keep and (len(a.entry) > 1 or a.into):
        die("--keep splits one entry; it can't go with a merge")
    if bool(a.into) == bool(a.title):
        die("give --title for a new todo, or --into M to add to #M")
    head, entries = b.backlog()
    for k in a.entry:
        if not 1 <= k <= len(entries):
            die("no backlog entry %d (there are %d)" % (k, len(entries)))
    if len(set(a.entry)) < len(a.entry):
        die("an entry is named twice")
    taken = [entries[k - 1] for k in a.entry]
    if a.into:
        _, f, it = b.find(a.into, ("todo",))
        if not it.has("Subtasks"):
            # The todo's own work is its first subtask.
            first = [p.replace("\n", " ") for p in re.split(
                r"\n>\n", re.sub(r"^> ?", "", it.get("From the backlog"),
                                 flags=re.M)) if p.strip()]
            it.set("Subtasks", "\n".join(wrap_bullet(t)
                                         for t in first or [it.title]))
        for e in taken:
            it.append("Subtasks", wrap_bullet(entry_text(e)))
        it.append("From the backlog", (">\n" if it.get("From the backlog")
                                       else "") + quote(taken))
        b.put("todo", it, old=f)
    else:
        frag = read_fragment("todo")
        it = Item(b.next_id(), a.title.strip(), {"status": "todo"})
        it.merge(frag, "the todo body")
        if a.top:
            it.head["priority"] = "high"
        if len(taken) > 1:
            it.set("Subtasks", "\n".join(wrap_bullet(entry_text(e))
                                         for e in taken))
        it.set("From the backlog", quote(taken))
        b.put("todo", it)
    if not a.keep:
        for k in sorted(a.entry, reverse=True):
            entries.pop(k - 1)
    b.write_backlog(head, entries)
    print("#%d in todo%s" % (it.n, "; backlog entry kept" if a.keep else
                             "; %d subtasks" % len(list_points(
                                 it.get("Subtasks")))
                             if it.has("Subtasks") else ""))
    if entries:  # numbers shift once an entry goes: show the new ones
        print("backlog now:")
        cmd_backlog(b, a)


def cmd_start(b, a):
    _, f, it = b.find(a.n, ("todo",))
    kept = it.head.get("branch")
    if kept and a.name:
        die("#%s is already on %s; start it without --branch-name"
            % (a.n, kept))
    if a.name:  # refuse a bad name before the item moves
        check_branch_name(a.n, a.name)
    it.merge(read_fragment("start"), "the plan body")
    it.head["status"] = "planned"
    it.append("Log", "- %s: planned." % stamp())
    b.put("doing", it, old=f)
    print("#%s in doing, planned%s" % (a.n, " on " + kept if kept else ""))
    if a.name:
        cmd_branch(b, a)


def run_git(*args, input=None, check=True, env=None):
    """Run git in the repo root; die on failure unless check=False."""
    full = dict(os.environ)
    full.update(env or {})
    r = subprocess.run(("git",) + args, cwd=str(repo_root()), env=full,
                       capture_output=True, text=True, input=input)
    if check and r.returncode:
        die("git %s: %s" % (" ".join(args), r.stderr.strip()))
    return r


def git(*args):
    return run_git(*args).stdout.strip()


BACKLOG_HEAD = ("# Backlog\n\n"
                "Write anything below the line, in any style: bugs, mistakes, "
                "ideas, things that feel off. Separate entries with a blank "
                "line or a `-`. The spak skill turns them into todos and "
                "asks you what you meant.\n\n---\n")


def rev(ref):
    """The commit `ref` names, or "" if it doesn't exist."""
    r = run_git("rev-parse", "--verify", "--quiet", ref + "^{commit}",
                check=False)
    return r.stdout.strip() if r.returncode == 0 else ""


def is_ancestor(a, b):
    return run_git("merge-base", "--is-ancestor", a, b,
                   check=False).returncode == 0


def backlog_ref_exists():
    return run_git("rev-parse", "--verify", "--quiet",
                   "refs/heads/backlog", check=False).returncode == 0


def repo_root():
    return Path(ARGS.board).resolve().parent


def current_branch():
    return run_git("branch", "--show-current", check=False).stdout.strip()


def checkpoint_ref(branch):
    m = re.match(r"spak/(\d+)-", branch)
    return "refs/spak/%s" % m.group(1) if m else ""


def checkpoint(message):
    """**A checkpoint never moves the branch you're on** (the user's rule):
    an editor shows the changes not yet committed to it, so the whole item
    stays in view. It snapshots the working tree (what git doesn't ignore)
    as a commit on a side ref, `refs/spak/N`, chained on the last one;
    `spak finish` puts them all on the branch at approve."""
    ref = checkpoint_ref(current_branch())
    if not ref:
        return
    parent = rev(ref) or rev("HEAD")
    with tempfile.NamedTemporaryFile(prefix="spak-index-") as f:
        env = {"GIT_INDEX_FILE": f.name}
        run_git("read-tree", parent, env=env)
        run_git("add", "-A", ".", env=env)
        tree = run_git("write-tree", env=env).stdout.strip()
    if tree == git("rev-parse", parent + "^{tree}"):
        return
    commit = git("commit-tree", tree, "-p", parent,
                 "-m", "checkpoint: " + message)
    run_git("update-ref", ref, commit)
    print("checkpoint %s on %s (%s so far)" % (
        commit[:7], ref, git("rev-list", "--count", "HEAD.." + ref)))


def cmd_checkpoint(b, a):
    if not checkpoint_ref(current_branch()):
        die("checkpoints are for a spak/N-… branch; this is %s"
            % (current_branch() or "detached"))
    checkpoint(a.message)


def cmd_finish(b, a):
    """Approve's mechanical half on a branch: a last checkpoint, every
    checkpoint onto the branch, then main checked out, or, from a worktree
    while another tree has main, the merge printed for that tree. The squash
    merge and the commit stay visible commands, for the git guard."""
    _, _, it = b.find(a.n, ("done",))
    br = it.head.get("branch")
    if not br:
        die("#%s has no branch: commit it on main" % a.n)
    if current_branch() != br:
        die("finish runs on %s; this is %s" % (br, current_branch()))
    checkpoint("#%s approved" % a.n)
    ref = checkpoint_ref(br)
    tip = rev(ref)
    if not tip:
        die("#%s has no checkpoint: nothing to merge" % a.n)
    run_git("update-ref", "refs/heads/" + br, tip)
    run_git("reset", "--quiet")  # the index follows; the files already match
    left = git("status", "--porcelain")
    if left:
        die("changes the last checkpoint didn't take:\n" + left)
    run_git("update-ref", "-d", ref)
    count = git("rev-list", "--count", "main.." + br)
    elsewhere = main_elsewhere()
    if elsewhere:
        # A worktree can't check out main while another tree has it: the
        # merge happens there, and this worktree goes once it's in.
        print("""main is checked out in %s, so this tree stays on %s; %s checkpoint(s) of #%s are on it. Now, one visible command at a time:
  git -C %s merge --squash %s
  git -C %s commit      # the item's message, ending: spak #%s (check nothing else was staged there)
  git worktree remove %s
  git -C %s branch -D %s""" % (elsewhere, br, count, a.n, elsewhere, br, elsewhere,
                               a.n, git("rev-parse", "--show-toplevel"), elsewhere, br))
        return
    git("switch", "--quiet", "main")
    print("""on main; %s checkpoint(s) of #%s are on %s. Now, one visible command at a time:
  git merge --squash %s
  git commit            # the item's message, ending: spak #%s
  git branch -D %s""" % (count, a.n, br, br, a.n, br))


def main_elsewhere():
    """Another worktree that has main checked out, or "" if none does."""
    here = Path(git("rev-parse", "--show-toplevel")).resolve()
    path = None
    for line in git("worktree", "list", "--porcelain").splitlines():
        if line.startswith("worktree "):
            path = Path(line[len("worktree "):]).resolve()
        elif line == "branch refs/heads/main" and path is not None and path != here:
            return str(path)
    return ""


def cmd_branch(b, a):
    """Put a doing item on its own branch, made from main."""
    _, f, it = b.find(a.n, ("doing",))
    if it.head.get("branch"):
        die("#%s is already on %s" % (a.n, it.head["branch"]))
    name = check_branch_name(a.n, a.name)
    it.head["branch"] = name
    if not a.no_git:
        current = git("branch", "--show-current")
        if current != "main":
            die("branches start from main; this is %s" % (current or "detached"))
        git("switch", "-c", name)
    b.put("doing", it, old=f)
    print("#%s on branch %s (uncommitted changes came along)" % (a.n, name))


def cmd_step(b, a):
    """Add a step to a doing item's plan, numbered after the last one."""
    _, f, it = b.find(a.n, ("doing",))
    lines = it.get("Plan").splitlines()
    last = max((k for k, l in enumerate(lines) if STEP.match(l)), default=None)
    if last is None:
        die("#%s has no plan steps to add to" % a.n)
    n = int(STEP.match(lines[last]).group(1)) + 1
    end = last + 1
    while end < len(lines) and lines[end].startswith("   "):
        end += 1
    new = textwrap.fill(" ".join(a.text.split()), 76,
                        initial_indent="%d. [ ] " % n,
                        subsequent_indent="   ").splitlines()
    it.set("Plan", "\n".join(lines[:end] + new + lines[end:]))
    b.put("doing", it, old=f)
    print("#%s: added step %d" % (a.n, n))


def cmd_set_status(b, a):
    _, f, it = b.find(a.n, ("doing",))
    it.head["status"] = a.status
    b.put("doing", it, old=f)
    print("#%s: %s" % (a.n, a.status))


def cmd_tick(b, a):
    _, f, it = b.find(a.n, ("doing",))
    plan = it.get("Plan")
    for step in a.steps:
        new = re.sub(r"^(\s*%d\. )\[ \]" % step, r"\1[x]", plan,
                     count=1, flags=re.M)
        if new == plan:
            die("#%s has no open step %d" % (a.n, step))
        plan = new
    it.set("Plan", plan)
    it.head["status"] = "in progress"
    b.put("doing", it, old=f)
    print("#%s: ticked %s" % (a.n, ", ".join(map(str, a.steps))))
    checkpoint("#%s steps %s" % (a.n, ", ".join(map(str, a.steps))))


def cmd_note(b, a):
    """Doing, and review or done too: a review answer is worth keeping."""
    col, f, it = b.find(a.n, ("doing", "review", "done"))
    it.append("Log", wrap_bullet("%s: %s" % (stamp(), a.text)))
    b.put(col, it, old=f)
    print("#%s: logged" % a.n)


def cmd_review(b, a):
    _, f, it = b.find(a.n, ("doing",))
    it.merge(read_fragment("review"), "the review body")
    it.head["status"] = "in review"
    b.put("review", it, old=f)
    print("#%s in review" % a.n)
    checkpoint("#%s in review" % a.n)


def cmd_rework(b, a):
    _, f, it = b.find(a.n, ("review",))
    frag = read_fragment("rework --todo") if a.todo else None
    rnd = int(it.head.get("round") or 0) + 1
    it.head["round"] = str(rnd)
    it.append("Review feedback", wrap_bullet("round %d: %s" % (rnd, a.feedback)))
    if a.todo:
        back_to_todo(b, f, it, frag, rnd)
        return
    it.sections = [s for s in it.sections if it.lasting(s)]
    it.head["status"] = "back from review"
    it.append("Log", "- %s: sent back from review (round %d)." % (stamp(), rnd))
    b.put("doing", it, old=f)
    print("#%s back in doing, round %d" % (a.n, rnd))


def back_to_todo(b, f, it, frag, rnd):
    """Review -> todo, for feedback that changes what the item is: a new
    todo body (stdin) on top, the branch and round kept, and everything so
    far (the write-up, the plan, its feedback and log) folded under Earlier
    rounds, so plan rereads it and the user's words aren't lost."""
    it.append("Log", "- %s: sent back to todo (round %d)." % (stamp(), rnd))
    fold = ["### Up to round %d" % rnd]
    for name, body, _ in it.ordered():
        if name != "Earlier rounds":
            fold += ["", "#### " + name, "", body]
    new = Item(it.n, it.title, {k: it.head[k] for k in ("branch", "round")
                                if it.head.get(k)})
    new.head["status"] = "todo"
    new.merge(frag, "the todo body")
    new.set("Earlier rounds", "\n\n".join(
        x for x in (it.get("Earlier rounds"), "\n".join(fold)) if x))
    b.put("todo", new, old=f)
    print("#%s back in todo, round %d%s" % (
        it.n, rnd, "; still on " + it.head["branch"]
        if it.head.get("branch") else ""))


def cmd_approve(b, a):
    _, f, it = b.find(a.n, ("review",))
    it.head["status"] = "done"
    it.head["done"] = stamp()
    it.set("Done", textwrap.fill(" ".join(a.summary.split()), 76,
                                 break_on_hyphens=False))
    br = it.head.get("branch")
    b.put("done", it, old=f)
    if not br:
        print("#%s in done. Improve step first, then commit on main; end "
              "the body with: spak #%s" % (a.n, a.n))
        return
    print("#%s in done. Improve step first, then `spak finish %s`."
          % (a.n, a.n))


def cmd_drop(b, a):
    if a.what.startswith("#"):
        n = a.what[1:]
        _, f, it = b.find(n)
        f.unlink()
        what = "#%s %s" % (n, it.title)
        if it.head.get("branch"):
            print("its branch %s is left; switch to main and delete it with "
                  "git branch -D %s" % (it.head["branch"], it.head["branch"]))
    else:
        head, entries, entry = b.take_backlog(int(a.what))
        b.write_backlog(head, entries)
        what = entry_text(entry)
    b.add_dropped(wrap_bullet("%s (%s): %s" % (what, stamp(), a.reason)))
    print("dropped: " + what)


# **Two preference files, bullets only** (the user's rule): a lean standing
# rule per line, written for an AI to read, with no title or header. How
# spak runs goes to the skill's own file; what's being built goes to the
# project root. The model asks the user before either, and which one.
PROJECT_PREFS = "PREFERENCES.md"
# A preference is a standing rule, not a record: no dates, no item numbers.
NOT_STANDING = re.compile(r"\b\d{4}-\d{2}-\d{2}\b|#\d+")


def cmd_preference(b, a):
    if a.skill == a.project:
        die("say which: --skill (how spak runs) or --project (what's being "
            "built); ask the user")
    line = " ".join(a.text.split())
    if NOT_STANDING.search(line):
        die("a preference is a standing rule: drop the date or item number "
            "(%s)" % NOT_STANDING.search(line).group(0))
    if a.project:
        refs, name = str(repo_root()), PROJECT_PREFS
    else:
        refs, name = a.refs, "preferences.md"
    (Path(refs) / name).touch()
    if a.replace:
        replace_ref(refs, name, a.replace, line)
    else:
        append_ref(refs, name, line)


def replace_ref(refs, name, old, line):
    """Swap the one bullet containing `old` (whitespace-insensitive) for `line`,
    in place: a preference the user changed their mind on is replaced, not
    appended beside the one it contradicts."""
    p = Path(refs) / name
    head, bullets = [], []
    for l in p.read_text().splitlines():
        if l.startswith("- "):
            bullets.append([l])
        elif bullets and l.startswith("  "):
            bullets[-1].append(l)
        elif bullets:
            bullets.append([l])
        else:
            head.append(l)
    want = " ".join(old.split())
    hits = [i for i, bl in enumerate(bullets)
            if bl[0].startswith("- ") and want in " ".join(" ".join(bl).split())]
    if len(hits) != 1:
        die("%d lines of %s contain %r; name one exactly" % (len(hits), name, old))
    bullets[hits[0]] = [wrap_bullet(line)]
    p.write_text("\n".join(head + ["\n".join(bl) for bl in bullets]).strip("\n") + "\n")
    print("%s: replaced" % name)


# A "Done when" point that only prose can meet (the docs say so): nothing but
# a reread backs it, and asked, Jev lands unsure every time.
PROSE_POINT = re.compile(r"(`[^`]*\.md`|\bdocs?\b|\bREADME\b|\bCLAUDE\.md\b"
                         r"|\bcomments?\b)", re.I)
# **The one way a review writes a number**, shared with `skeleton review`: a
# count is "X of Y", a measurement is
# written as the output printed it. These are what selfcheck looks for in the
# evidence, in code, since Jev can't tell 0.441 from 0.414. Small bare
# integers ("round 2", "step 4") aren't cited results, so they're left out.
CITED_NUMBER = re.compile(
    r"(?<![\w.#])\d+ of \d+(?![\w.])"          # a count: 7 of 8
    r"|(?<![\w.#])\d+(?:\.\d+)?%"              # a share: 95%
    r"|(?<![\w.#])\d[\d,]*\.\d+"               # a measurement: 0.441
    r"|(?<![\w.#])\d{1,3}(?:,\d{3})+"          # a big count: 1,200
    r"|(?<![\w.#])\d{3,}")                     # or 1200
# A count written any other way, which the check above would miss: rewrite
# it as "X of Y".
OTHER_COUNT = re.compile(
    r"(?<![\w.#/])\d+/\d+(?=\s+(?:checks?|tests?|pass(?:ed|es)?|PASS|ok|"
    r"fail(?:ed|s)?|FAIL))"
    r"|\ball \d+\b|\b\d+ out of \d+\b", re.I)


def cmd_selfcheck(b, a):
    """Jev's self-check, built: whether each "Done when" point (and each
    round of review feedback) is backed, about the review body (from stdin,
    before `review`; or the item's own write-up, after).

    **Against the evidence, not only the draft.** With `--evidence`, a file
    of the real results (check output, probe numbers, what a render showed),
    the state carries it and each question asks whether it supports what the
    draft says; without it, Jev can only say the draft names a result. The
    old "does the draft report point N?" is gone: a review written from the
    points reports every one, and it came back yes 137 times in 139."""
    import json
    col, _, it = b.find(a.n, ("doing", "review"))
    draft = "" if sys.stdin.isatty() else sys.stdin.read().strip()
    if not draft:
        if col != "review":
            die("selfcheck reads the review body from stdin (see `skeleton review`)")
        draft = "\n\n".join("## %s\n\n%s" % (name, body)
                            for name, body, anchor in it.ordered()
                            if not it.lasting((name, body, anchor)))
    points = list_points(it.get("Done when"))
    if not points:
        die("#%s has no \"Done when\" to check against" % a.n)
    prose = [p for p in points if PROSE_POINT.search(p)]
    points = [p for p in points if p not in prose] + [
        "The user's review feedback, " + p
        for p in list_points(it.get("Review feedback"))]
    evidence = Path(a.evidence).read_text().strip() if a.evidence else ""
    # The points ride in the state, not the question: a point quoting code in
    # backticks reads to Jev as a field of the state that isn't there.
    questions = {}
    for k in range(1, len(points) + 1):
        if evidence:
            # About the point, not the draft: asked whether the evidence
            # "supports what the draft says", Jev let the draft's own claim
            # stand in for evidence and was sure of an export no line showed.
            ask = "Does `evidence` alone show that `points.point_%d` holds?" % k
        else:
            ask = ("Does `draft` back `points.point_%d` with a result (a check "
                   "line, a number, a screenshot or render looked at), rather "
                   "than only saying it is done?" % k)
        questions["backed_%d" % k] = {"type": "boolean", "instructions": ask}
    if evidence:
        questions["all_backed"] = {
            "type": "boolean",
            "instructions": "Is every claim in `draft` that something works "
                            "supported by `evidence`?"}
    state = {"draft": draft,
             "points": {"point_%d" % k: p for k, p in enumerate(points, 1)}}
    if evidence:
        state["evidence"] = evidence
    extra = {"unasked_prose": prose,
             "counts_to_rewrite": sorted(set(OTHER_COUNT.findall(draft)))}
    if evidence:
        # Numbers are checked here, not by Jev: every number the draft cites
        # should be in the evidence as written.
        flat = " ".join(evidence.replace(",", "").split())
        extra["numbers_not_in_evidence"] = sorted(
            {n for n in CITED_NUMBER.findall(draft)
             if n.replace(",", "") not in flat})
    else:
        extra["note"] = ("no --evidence: Jev can only judge what the draft "
                         "says, not what happened")
    if a.state_file:
        # Jev's `state_file` wants the state alone, and a path under the
        # project: split here rather than by hand.
        out = Path(a.state_file)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(state, indent=1, ensure_ascii=False))
        print(json.dumps({"state_file": a.state_file, "questions": questions,
                          **extra}, indent=1, ensure_ascii=False))
        return
    print(json.dumps({"state": state, "questions": questions, **extra},
                     indent=1, ensure_ascii=False))


def append_ref(refs, name, line):
    p = Path(refs) / name
    old = p.read_text().rstrip("\n")
    p.write_text((old + "\n" if old else "") + wrap_bullet(line) + "\n")
    print("%s: added" % name)


def find_board():
    for d in [Path.cwd(), *Path.cwd().parents]:
        # A board is its column folders (each kept by a .gitkeep), or the
        # backlog file of a board outside git.
        if (d / "spak" / COLS["todo"]).is_dir() or \
                (d / "spak" / BACKLOG).exists():
            return d / "spak"
    return HERE.parents[3] / "spak"


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--board", help="the board folder (default: spak/)")
    p.add_argument("--refs", default=str(HERE.parent / "references"),
                   help="the skill's references folder, for preference --skill")
    sub = p.add_subparsers(dest="cmd", required=True)

    def cmd(name, fn, help, *args):
        s = sub.add_parser(name, help=help)
        for flags, kw in args:
            s.add_argument(*flags, **kw)
        s.set_defaults(fn=fn)

    num = (("n",), dict(help="item number, without #"))
    cmd("status", cmd_status, "the board and the next move")
    cmd("lint", cmd_lint, "check every item file (or #N) after a hand edit",
        (("n",), dict(nargs="?", help="item number, without #")))
    cmd("next-id", cmd_next_id, "the number the next todo gets")
    cmd("backlog", cmd_backlog, "the backlog entries in full, numbered")
    cmd("add", cmd_add, "append an entry to the backlog",
        (("text",), {}))
    cmd("show", cmd_show, "one item and its column", num)
    cmd("skeleton", cmd_skeleton, "the stdin body a move expects",
        (("kind",), dict(choices=sorted(SKELETONS))))
    cmd("todo", cmd_todo, "refine: backlog entry -> todo (body on stdin)",
        (("entry",), dict(type=int, nargs="+", help="backlog entry "
                          "number; several merge into one todo")),
        (("--title",), dict(help="the new todo's title")),
        (("--into",), dict(metavar="M", help="add the entries to todo #M "
                           "as subtasks, instead of a new todo")),
        (("--top",), dict(action="store_true", help="make it high priority")),
        (("--keep",), dict(action="store_true",
                           help="keep the entry (it splits into more todos)")))
    nogit = (("--no-git",), dict(action="store_true",
                                 help="record the branch, don't create it"))
    bname = (("--branch-name", "--name"), dict(
        dest="name", help="the user-approved name, spak/N-<this> "
        "(1-4 lowercase hyphenated words)"))
    cmd("start", cmd_start, "todo -> doing, planned (plan on stdin)", num,
        nogit, bname)
    cmd("branch", cmd_branch, "put a doing item on its own branch", num, nogit,
        (("--branch-name", "--name"), dict(dest="name", required=True,
         help="the user-approved name, spak/N-<this>")))
    cmd("checkpoint", cmd_checkpoint, "save the working tree on the branch's "
        "side ref (tick and review do it too); the branch doesn't move",
        (("message",), {}))
    cmd("finish", cmd_finish, "after approve on a branch: every checkpoint "
        "onto it, then main; prints the squash merge", num)
    cmd("step", cmd_step, "add a step to a doing item's plan", num,
        (("text",), {}))
    cmd("set-status", cmd_set_status, "set a doing item's status", num,
        (("status",), {}))
    cmd("tick", cmd_tick, "tick plan steps of a doing item", num,
        (("steps",), dict(type=int, nargs="+")))
    cmd("note", cmd_note, "add a line to an item's log (doing, "
        "review or done)", num,
        (("text",), {}))
    cmd("review", cmd_review, "doing -> review (write-up on stdin)", num)
    cmd("selfcheck", cmd_selfcheck, "a Jev ask: is each Done-when point "
        "backed, about the review body (stdin, or the item's once in review)",
        num,
        (("--evidence",), dict(help="a file of the real results (check "
                               "output, probe numbers, render notes): Jev "
                               "then asks whether it supports each point, "
                               "and cited numbers are looked for in it")),
        (("--state-file",), dict(help="write the state here (under the "
                                 "project, e.g. a gitignored scratch dir) and "
                                 "print only the questions, for Jev's "
                                 "state_file")))
    cmd("rework", cmd_rework, "review -> doing, with the user's feedback", num,
        (("feedback",), {}),
        (("--todo",), dict(action="store_true",
                           help="back to todo instead, for feedback that "
                           "changes the item (new todo body on stdin)")))
    cmd("approve", cmd_approve, "review -> done (does not commit)", num,
        (("summary",), dict(help="one sentence: what it does now")))
    cmd("drop", cmd_drop, "backlog entry or #N -> Dropped",
        (("what",), dict(help="backlog entry number, or #N")),
        (("reason",), {}))
    cmd("preference", cmd_preference, "a line in a preference file, once "
        "the user said yes (and which file)",
        (("text",), {}),
        (("--skill",), dict(action="store_true", help="how spak runs: the "
                            "skill's references/preferences.md")),
        (("--project",), dict(action="store_true", help="what's being "
                              "built: " + PROJECT_PREFS + " at the root")),
        (("--replace",), dict(metavar="OLD", help="replace the one line "
                               "containing OLD instead of adding")))

    global ARGS
    a = ARGS = p.parse_args()
    a.board = a.board or str(find_board())
    a.fn(Board(a.board), a)


if __name__ == "__main__":
    main()
