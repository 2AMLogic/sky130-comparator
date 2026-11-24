#!/usr/bin/env python3
"""WORK_LOG.md forge-truthfulness gate (issue #418).

WORK_LOG.md is this repo's chronological record of merged PRs and closed
issues, and the Guide's presence-check reads it to decide what is "not yet
recorded". PR #415's first commit (`0dc2fb4`) appended 161 entries that
belonged to a different repository; CI was green (nothing checked the file)
and the Docs-Only Fast Path certified it (it verifies diff shape, never
truthfulness). Only a Judge reading content caught it.

For every `- **PR #N**: <title>` / `- **Issue #N** (closed): <title>` line
ADDED to WORK_LOG.md between a base and a head commit, this gate asserts
against `{owner}/{repo}` resolved from `git remote get-url origin`:

  1. N exists in this repo (and is a PR for a `PR` entry, an issue for an
     `Issue` entry);
  2. the claimed title equals the actual title exactly;
  3. the entry sits under the `### YYYY-MM-DD` heading equal to its real
     merge (PR) / close (Issue) date, UTC.

A number-only check is not enough: a foreign number that happens to exist
in range passes it (110 of PR #415's 161 entries). Pre-existing lines are
never re-judged (cost would grow with the log and legacy entries nobody is
touching would be flagged); archives under work_log/ are out of scope.

Exit codes (distinct on purpose):
  0  every added entry verified (or none added)
  1  content failure: at least one entry is untrue (named, with expected
     vs found, and a count)
  2  the forge could not be consulted (network, rate limit, no token,
     unresolvable origin): NOT a pass and NOT a content failure

The Guide-side repo-identity assertion is upstream Loom, out of scope here.

`selftest` is hermetic: fixture text and a stubbed forge lookup.

Stdlib only; shells out to `git` and `gh` for the real gate.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _gate_common import (FAILURES, dispatch, fail, ok,  # noqa: E402
                          report_cases, reset)

REPO_ROOT = Path(__file__).resolve().parents[1]
WORK_LOG = "WORK_LOG.md"

HEADING_RE = re.compile(r"^### (\d{4}-\d{2}-\d{2})\s*$")
ENTRY_RE = re.compile(
    r"^- \*\*(PR|Issue) #(\d+)\*\*(?: \(closed\))?: (.*?)\s*$")
HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
REMOTE_RE = re.compile(
    r"(?:github\.com[:/])(?P<owner>[^/\s]+)/(?P<repo>[^/\s]+?)(?:\.git)?/?$")

EXIT_OK, EXIT_CONTENT, EXIT_FORGE = 0, 1, 2


class ForgeError(Exception):
    """The forge could not be consulted (distinct from a content failure)."""


# A lookup maps an issue/PR number to the forge's `issues/N` payload, or
# None when the number does not exist (404). Anything else raises ForgeError.
Lookup = Callable[[int], "dict | None"]


def parse_repo(remote_url: str) -> str:
    m = REMOTE_RE.search(remote_url.strip())
    if not m:
        raise ForgeError(f"cannot derive owner/repo from origin URL "
                         f"{remote_url!r}")
    return f"{m['owner']}/{m['repo']}"


def added_line_numbers(diff_text: str) -> set[int]:
    """1-based head-side line numbers added by a `git diff --unified=0`."""
    added: set[int] = set()
    for line in diff_text.splitlines():
        m = HUNK_RE.match(line)
        if m:
            start = int(m.group(1))
            count = 1 if m.group(2) is None else int(m.group(2))
            added.update(range(start, start + count))
    return added


def added_entries(head_text: str, added: set[int]):
    """(lineno, kind, number, title, heading_date) for each added entry."""
    out = []
    heading = None
    for n, line in enumerate(head_text.splitlines(), 1):
        h = HEADING_RE.match(line)
        if h:
            heading = h.group(1)
            continue
        if n not in added:
            continue
        m = ENTRY_RE.match(line)
        if m:
            out.append((n, m.group(1), int(m.group(2)), m.group(3), heading))
    return out


def real_date(kind: str, payload: dict) -> str | None:
    """UTC date a PR was merged / an issue was closed, or None."""
    if kind == "PR":
        stamp = (payload.get("pull_request") or {}).get("merged_at")
    else:
        stamp = payload.get("closed_at")
    if not stamp:
        return None
    return datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone(
        timezone.utc).strftime("%Y-%m-%d")


def check_entries(entries, lookup: Lookup, repo: str) -> int:
    """Run checks 1-3 on each entry; failures go through `fail()`.

    Returns the number of entries with at least one failure.

    ForgeError propagates (the caller maps it to its own exit code).
    """
    bad = 0
    for lineno, kind, num, title, heading in entries:
        before = len(FAILURES)
        who = f"{WORK_LOG}:{lineno} {kind} #{num}"
        payload = lookup(num)
        if payload is None:
            fail(f"{who}: number does not exist in {repo} (check 1)")
            bad += 1
            continue
        is_pr = "pull_request" in payload
        if (kind == "PR") != is_pr:
            fail(f"{who}: entry says {kind} but {repo}#{num} is "
                 f"{'a PR' if is_pr else 'an issue'} (check 1)")
            bad += 1
            continue
        if title != payload.get("title"):
            fail(f"{who}: title mismatch (check 2): expected "
                 f"{payload.get('title')!r}, found {title!r}")
        actual = real_date(kind, payload)
        if actual is None:
            fail(f"{who}: {'not merged' if is_pr else 'not closed'} in "
                 f"{repo}, so it has no date to log under (check 3)")
        elif heading != actual:
            fail(f"{who}: date heading mismatch (check 3): expected "
                 f"### {actual}, found ### {heading}")
        bad += len(FAILURES) > before
    return bad


def gh_lookup_factory(repo: str) -> Lookup:
    def lookup(num: int):
        proc = subprocess.run(
            ["gh", "api", f"repos/{repo}/issues/{num}"],
            capture_output=True, text=True, check=False)
        if proc.returncode == 0:
            return json.loads(proc.stdout)
        err = (proc.stderr + proc.stdout).strip()
        if "HTTP 404" in err or "Not Found" in err:
            return None
        raise ForgeError(f"gh api repos/{repo}/issues/{num} failed "
                         f"(rc={proc.returncode}): {err[:300]}")
    return lookup


def git(*args: str, root: Path) -> str:
    proc = subprocess.run(["git", "-C", str(root), *args],
                          capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise ForgeError(f"git {' '.join(args)} failed: "
                         f"{proc.stderr.strip()[:300]}")
    return proc.stdout


def run_gate(args) -> int:
    root = Path(args.repo_root)
    reset()
    try:
        merge_base = git("merge-base", args.base, args.head,
                         root=root).strip()
        diff = git("diff", "--unified=0", merge_base, args.head, "--",
                   WORK_LOG, root=root)
        added = added_line_numbers(diff)
        if not added:
            ok(f"{WORK_LOG}: no added lines between base and head")
            return EXIT_OK
        head_text = git("show", f"{args.head}:{WORK_LOG}", root=root)
        entries = added_entries(head_text, added)
        if not entries:
            ok(f"{WORK_LOG}: {len(added)} added line(s), none are "
               "PR/Issue entries")
            return EXIT_OK
        repo = parse_repo(git("remote", "get-url", "origin", root=root))
        print(f"gate: checking {len(entries)} added entr"
              f"{'y' if len(entries) == 1 else 'ies'} against {repo}")
        bad = check_entries(entries, gh_lookup_factory(repo), repo)
    except ForgeError as exc:
        print(f"gate: FORGE-ERROR: {exc} -- the log could not be verified; "
              "this is not a content verdict")
        return EXIT_FORGE
    if bad:
        print(f"gate: {bad} of {len(entries)} added entries "
              f"failed verification against {repo}")
        return EXIT_CONTENT
    ok(f"all {len(entries)} added entries verified against {repo}")
    return EXIT_OK


def run_selftest(args) -> int:
    del args
    results = []

    def mk(num, title, *, pr, when):
        p = {"number": num, "title": title,
             "closed_at": None if when is None else f"{when}T12:00:00Z"}
        if pr:
            p["pull_request"] = {
                "merged_at": None if when is None else f"{when}T12:00:00Z"}
        return p

    forge = {
        10: mk(10, "fix: real pr", pr=True, when="2026-11-23"),
        11: mk(11, "Real issue", pr=False, when="2026-11-22"),
        12: mk(12, "fix: late pr", pr=True, when="2026-11-22"),
        13: mk(13, "unmerged pr", pr=True, when=None),
    }
    forge[12]["pull_request"]["merged_at"] = "2026-11-22T23:59:59Z"

    def lookup(n):
        if n == 99:
            raise ForgeError("stub: rate limited")
        return forge.get(n)

    def log(*lines):
        return "# Work Log\n\n" + "\n".join(lines) + "\n"

    def run(text, added=None):
        reset()
        nums = set(range(1, text.count("\n") + 2)) if added is None else added
        entries = added_entries(text, nums)
        bad = check_entries(entries, lookup, "o/r")
        return bad, entries

    def case(name, text, expect_fail, added=None):
        n, _ = run(text, added)
        results.append((name, (n > 0) == expect_fail))

    good = log("### 2026-11-23", "",
               "- **PR #10**: fix: real pr", "",
               "### 2026-11-22", "",
               "- **Issue #11** (closed): Real issue")
    case("clean PR + issue entries pass", good, False)
    case("absent number fails", log(
        "### 2026-11-23", "- **PR #500**: fix: nothing"), True)
    case("title mismatch fails (number exists, title differs: the foreign "
         "entry shape)", log(
             "### 2026-11-23", "- **PR #10**: Foreign PDK LNA bring-up"),
         True)
    case("wrong date heading fails", log(
        "### 2026-11-22", "- **PR #10**: fix: real pr"), True)
    case("PR entry naming an issue number fails", log(
        "### 2026-11-22", "- **PR #11**: Real issue"), True)
    case("Issue entry naming a PR number fails", log(
        "### 2026-11-23", "- **Issue #10** (closed): fix: real pr"), True)
    case("unmerged PR fails (no merge date)", log(
        "### 2026-11-23", "- **PR #13**: unmerged pr"), True)
    case("merge near UTC midnight buckets by UTC date", log(
        "### 2026-11-22", "- **PR #12**: fix: late pr"), False)

    bad = log("### 2026-11-23", "- **PR #500**: ghost",
              "- **PR #10**: fix: real pr")
    case("unchanged pre-existing bad lines are ignored", bad, False,
         added={bad.splitlines().index("- **PR #10**: fix: real pr") + 1})

    n, ents = run(log("### 2026-11-23", "- **PR #10**: fix: real pr",
                      "prose line that is not an entry"))
    results.append(("non-entry added lines are not entries "
                    f"(got {len(ents)})", len(ents) == 1 and n == 0))

    contaminated = log("### 2026-11-23", *(
        f"- **PR #{k}**: Foreign title {k}" for k in (10, 11, 12, 500, 501)))
    n, _ = run(contaminated)
    results.append((f"contamination batch counts each bad entry (got {n}, "
                    "want 5)", n == 5))

    reset()
    try:
        check_entries(added_entries(log("### 2026-11-23",
                                        "- **PR #99**: x"), {4}),
                      lookup, "o/r")
        results.append(("forge lookup error raises ForgeError, not a "
                        "content failure", False))
    except ForgeError:
        results.append(("forge lookup error raises ForgeError, not a "
                        "content failure", not FAILURES))

    # Distinct exit codes are the contract the workflow relies on.
    results.append(("exit codes are distinct",
                    len({EXIT_OK, EXIT_CONTENT, EXIT_FORGE}) == 3))

    diff = ("@@ -4,0 +5,2 @@\n+a\n+b\n@@ -9 +11 @@\n-x\n+y\n"
            "@@ -20,2 +22,0 @@\n-gone\n-gone\n")
    results.append(("diff hunk parsing: +5,2 / +11 / pure deletion",
                    added_line_numbers(diff) == {5, 6, 11}))

    for url, want in (("https://github.com/2AMLogic/sky130-comparator.git",
                       "2AMLogic/sky130-comparator"),
                      ("git@github.com:2AMLogic/sky130-comparator.git",
                       "2AMLogic/sky130-comparator"),
                      ("https://x-access-token:t@github.com/o/r", "o/r")):
        results.append((f"origin URL {url} -> {want}",
                        parse_repo(url) == want))
    try:
        parse_repo("https://example.com/nope")
        results.append(("non-GitHub origin raises ForgeError", False))
    except ForgeError:
        results.append(("non-GitHub origin raises ForgeError", True))

    reset()
    return report_cases(results)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="WORK_LOG.md gate (issue #418): every entry added "
        "between base and head must exist in this repo's own forge with "
        "the exact title, under the real merge/close date heading")
    sub = parser.add_subparsers(dest="mode", required=True)
    p_gate = sub.add_parser(
        "gate", help="verify entries added to WORK_LOG.md in base..head")
    p_gate.add_argument("--base", required=True,
                        help="base commit (merge-base with head is used)")
    p_gate.add_argument("--head", default="HEAD")
    p_gate.add_argument("--repo-root", default=str(REPO_ROOT))
    return dispatch(parser, sub, argv, run_gate, run_selftest)


if __name__ == "__main__":
    raise SystemExit(main())
