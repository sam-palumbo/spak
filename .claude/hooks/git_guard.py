#!/usr/bin/env python3
"""PreToolUse hook on Bash: makes the user click for every commit, push and
merge, whatever form the command takes (`git -C dir commit`, `env … git
push`, `sh -c "git commit"`, chains, `gh pr merge`).

Push and merge always ask, except `git push <remote> backlog`: that's the
backlog branch's backup, a push of a non-project branch. spak.py's own
autosave pushes it from inside Python, which this hook never sees; the
exemption is for pushing it by hand. A commit asks too, except a plain commit on
a `spak/` branch, which reaches main only through approve's squash merge
(spak's rule, `.claude/skills/spak/SKILL.md`). Anything unclear asks.

It can't see git run from inside another program; the spak skill runs git
only as visible commands so this hook sees them.

`git_guard.py --test` checks it against the cases below.
"""

import json
import re
import subprocess
import sys

GIT = re.compile(
    r"(?<![\w-])git"
    r"((?:\s+(?:-C\s+\S+|-c\s+\S+|--git-dir(?:=|\s+)\S+"
    r"|--work-tree(?:=|\s+)\S+|--[\w-]+|-[a-zA-Z]))*)"
    r"\s+(commit|push|merge)(?![\w-])")
GH_MERGE = re.compile(r"(?<![\w-])gh\s+pr\s+merge(?![\w-])")
BACKLOG_PUSH = re.compile(
    r"(?<![\w-])git\s+push\s+[^\s;&|]+\s+backlog(?:\s*(?:&&|;|\||$))")
ELSEWHERE = re.compile(
    r"(?<![\w-])(cd|pushd|switch|checkout|GIT_DIR|GIT_WORK_TREE)(?![\w-])")


def verdict(command, branch):
    """None to pass (normal permissions apply), else the reason to ask."""
    flat = re.sub(r"[\"'`\\]", " ", command)
    if GH_MERGE.search(flat):
        return "a merge of a pull request"
    found = [(m.group(2), m.group(1)) for m in GIT.finditer(flat)]
    if not found:
        return None
    kinds = {k for k, _ in found}
    if kinds & {"push", "merge"}:
        n_push = sum(1 for k, _ in found if k == "push")
        if n_push == 1 and kinds == {"push"} and BACKLOG_PUSH.search(flat):
            return None
        return "a git " + " and ".join(sorted(kinds & {"push", "merge"}))
    if not branch.startswith("spak/"):
        return "a commit on %s" % (branch or "a detached HEAD")
    if any(opts.strip() for _, opts in found) or ELSEWHERE.search(flat):
        return "a commit that may not land on %s" % branch
    return None


def branch_of(cwd):
    try:
        return subprocess.run(["git", "-C", cwd or ".", "branch",
                               "--show-current"], capture_output=True,
                              text=True, timeout=5).stdout.strip()
    except Exception:
        return ""


CASES = [
    # (command, current branch, asks?)
    ("git status", "main", False),
    ("git log --grep='spak #1'", "main", False),
    ("git merge-base main HEAD", "main", False),
    ("git commit -m x", "main", True),
    ("git commit -m x", "spak/1-verbs", False),
    ("git add a && git commit -m 'checkpoint: x'", "spak/1-verbs", False),
    ("git -C /tmp/other commit -m x", "spak/1-verbs", True),
    ("cd /tmp/other && git commit -m x", "spak/1-verbs", True),
    ("git switch main && git commit -m x", "spak/1-verbs", True),
    ("git -c user.name=x commit -m y", "main", True),
    ("env GIT_DIR=x git commit", "main", True),
    ("GIT_DIR=/tmp/x git commit -m y", "spak/1-verbs", True),
    ("sh -c \"git commit -m x\"", "main", True),
    ("bash -c 'git push'", "spak/1-verbs", True),
    ("/usr/bin/git commit", "main", True),
    ("git --no-pager commit", "main", True),
    ("git push origin main", "spak/1-verbs", True),
    ("git push origin backlog", "main", False),
    ("git push otherremote backlog", "main", False),
    ("git add a && git push origin backlog", "spak/6-x", False),
    ("git push origin backlog main", "main", True),
    ("git push origin backlog --force", "main", True),
    ("git push --force origin backlog", "main", True),
    ("git push -u origin backlog", "main", True),
    ("git push origin backedup-log", "main", True),
    ("git push origin main && git push origin backlog", "main", True),
    ("git merge --squash spak/1-verbs", "main", True),
    ("git status; git merge x", "spak/1-verbs", True),
    ("gh pr merge 3 --squash", "main", True),
    ("git commit-tree abc", "main", False),
    ("git commit -m x", "", True),
]


def test():
    bad = [(c, b, want) for c, b, want in CASES
           if (verdict(c, b) is not None) != want]
    for c, b, want in bad:
        print("git_guard: FAIL: %r on %r should %s" % (
            c, b, "ask" if want else "pass"))
    print("git_guard: " + ("FAIL" if bad else "PASS"))
    sys.exit(1 if bad else 0)


def main():
    if sys.argv[1:] == ["--test"]:
        test()
    data = json.load(sys.stdin)
    if data.get("tool_name") != "Bash":
        return
    command = data.get("tool_input", {}).get("command", "")
    reason = verdict(command, branch_of(data.get("cwd")))
    if reason:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": "git guard: %s needs your OK" % reason,
        }}))


if __name__ == "__main__":
    main()
