#!/usr/bin/env python3
"""WORK_PLAN.md guide:plan-body region gate (issue #344): the text between
`<!-- guide:plan-body:start -->` and `<!-- guide:plan-body:end -->` is
renderer-owned -- `update_work_plan()` (.loom/roles/guide.md) compares
`render_plan_body()`'s output byte-for-byte against the committed region --
so ANY line the renderer cannot produce makes `new_body != old_body` on
every Guide tick, regardless of label state, and the no-op debounce is
unreachable: the #5890/#5930 docs-churn failure mode the role file marks
DO NOT REINTRODUCE.

The observed recurrence (issue #344): two consecutive Guide docs PRs
(#342, #343) hand-typed a `_Generated: <timestamp> (snapshot; compare
against live labels)_` line as the first line inside the region.
`render_plan_body()` emits no such line (`grep -c Generated
.loom/roles/guide.md` -> 0), so the stamp is per-tick re-invention, and
each copy cost a Judge `changes-requested` pass plus a Doctor fix round
trip on a PR whose substantive label-state content was correct both
times. This gate turns that recurrence into a red CI run on the PR
itself, before the Judge sees it.

Deny-list, not renderer re-implementation: the gate cannot call the shell
renderer, and reimplementing `render_plan_body()` in Python would
duplicate the vendored role file and drift with it (rejected in issue
#344). The minimal mechanical check that catches the observed failure is
denying the timestamp-stamp prefix on any region line -- the observed
`_Generated: ...` shape, a bare `Generated: ...`, indented variants
included (`\\b` keeps a word like `GeneratedX` from matching). No
committed WORK_PLAN.md line starts with "Generated" (measured 2026-11-18
@ `9757cc9`: `grep -c Generated WORK_PLAN.md` -> 0), so the deny-list has
no legitimate shape to false-positive on. Other renderer-drift shapes are
out of scope (issue #344).

`selftest` is hermetic: the case matrix runs on fixture text through the
same pure check the gate uses (no repo reads for the matrix itself), plus
one committed-tree regression case -- the checked-in WORK_PLAN.md must
pass. Covered: a clean region passes; the `_Generated:` stamp inside the
region fails; the identical line outside the markers passes; missing
start / end / both markers fail; doubled (unbalanced) and out-of-order
markers fail; CRLF line endings extract and scan the same; and region
markdown the renderer legitimately emits (headings, bullets, `_None._`)
does not false-positive.

Same `_gate_common` convention as the other gates in this directory.

Stdlib only, no virtualenv required.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _gate_common import (FAILURES, dispatch, fail, ok,  # noqa: E402
                          report_cases, reset)

REPO_ROOT = Path(__file__).resolve().parents[1]
WORK_PLAN = Path("WORK_PLAN.md")

START_MARKER = "<!-- guide:plan-body:start -->"
END_MARKER = "<!-- guide:plan-body:end -->"

#: The timestamp-stamp prefix Guide ticks re-invent (issue #344). The
#: observed shape is `_Generated: <iso-stamp> (snapshot...)`; a bare
#: `Generated:` is the same stamp without the emphasis underscores.
#: Leading whitespace is tolerated -- an indented stamp defeats the
#: debounce just as thoroughly -- while `\\b` keeps a word merely starting
#: with "Generated" (e.g. `GeneratedX`) from matching.
STAMP_RE = re.compile(r"^\s*_?Generated\b")


def extract_region(text: str, name: str) -> tuple[list[str], int] | None:
    """The lines strictly between the plan-body markers, with the 1-based
    line number of the first body line; or None after failing.

    Fails (via `_gate_common.fail`) when either marker is missing, when
    either appears more than once (unbalanced), or when the start marker
    does not precede the end marker. `splitlines()` normalizes CRLF, so a
    Windows-checked-out file extracts the same region (issue #344 test
    plan). Split from the stamp scan so the selftest drives the whole
    matrix on fixture text.
    """
    lines = text.splitlines()
    starts = [n for n, line in enumerate(lines, 1) if START_MARKER in line]
    ends = [n for n, line in enumerate(lines, 1) if END_MARKER in line]
    if not starts and not ends:
        fail(f"{name}: neither {START_MARKER} nor {END_MARKER} found -- "
             "the renderer-owned region is missing entirely; without it "
             "update_work_plan() cannot compare or debounce at all")
        return None
    if not starts:
        fail(f"{name}: {START_MARKER} not found (end marker at line "
             f"{ends[0]}) -- unbalanced markers; the region cannot be "
             "extracted, so the renderer comparison is meaningless")
        return None
    if not ends:
        fail(f"{name}: {END_MARKER} not found (start marker at line "
             f"{starts[0]}) -- unbalanced markers; the region cannot be "
             "extracted, so the renderer comparison is meaningless")
        return None
    if len(starts) > 1 or len(ends) > 1:
        fail(f"{name}: markers are unbalanced -- {START_MARKER} appears "
             f"{len(starts)}x, {END_MARKER} appears {len(ends)}x; exactly "
             "one region must exist")
        return None
    if starts[0] >= ends[0]:
        fail(f"{name}: start marker (line {starts[0]}) does not precede "
             f"end marker (line {ends[0]}) -- the region is out of order")
        return None
    return lines[starts[0]:ends[0] - 1], starts[0] + 1


def check_plan_body(text: str, name: str) -> None:
    """The pure check: extract the region, deny the timestamp stamp.

    Reports via `_gate_common.fail()`/`ok()`; the failure message names
    the offending line and tells the author the region is renderer-owned
    and must not carry a timestamp (issue #344 acceptance criterion).
    """
    extracted = extract_region(text, name)
    if extracted is None:
        return
    body, first_lineno = extracted
    stamped = [(lineno, line)
               for lineno, line in enumerate(body, first_lineno)
               if STAMP_RE.match(line)]
    if stamped:
        for lineno, line in stamped:
            fail(f"{name}:{lineno}: `{line.strip()}` -- a timestamp stamp "
                 "inside the guide:plan-body region. This region is "
                 "RENDERER-OWNED: render_plan_body() emits every line of "
                 "it, and update_work_plan() compares that output "
                 "byte-for-byte against the committed region, so a "
                 "hand-typed stamp makes every Guide tick see a diff and "
                 "defeats the no-op debounce (issues #5890/#5930/#344). "
                 "Delete the line -- the region must not carry a "
                 "timestamp; the file-level snapshot note belongs OUTSIDE "
                 "the markers")
        return
    ok(f"{name}: plan-body region clean ({len(body)} renderer-owned "
       "line(s), no timestamp stamp)")


def run_gate(args: argparse.Namespace) -> int:
    path = Path(args.repo_root).resolve() / WORK_PLAN
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        fail(f"{WORK_PLAN} not found at {path} -- the Guide roadmap file "
             "is gone from the repo")
        return 1
    except UnicodeDecodeError as exc:
        fail(f"{WORK_PLAN} is not valid UTF-8: {exc}")
        return 1
    check_plan_body(text, str(WORK_PLAN))
    if FAILURES:
        print(f"gate: {len(FAILURES)} failure(s) -- see above")
        return 1
    return 0


def run_selftest(args: argparse.Namespace) -> int:
    del args  # no options; the matrix is fixture text + one committed read
    repo = REPO_ROOT
    case_results = []

    def check(name: str, expect_fail: bool, text: str) -> None:
        # reset() clears the shared tally in place -- rebinding FAILURES
        # here would detach it from the list fail() appends to
        # (_gate_common).
        reset()
        check_plan_body(text, "fx-work-plan")
        case_results.append((name, (len(FAILURES) > 0) == expect_fail))

    def wrap(body: str) -> str:
        return f"intro prose\n{START_MARKER}\n{body}{END_MARKER}\noutro\n"

    stamp = ("_Generated: 2026-11-18T13:45:00Z (snapshot; compare against "
             "live labels)_\n")
    # Region markdown the renderer legitimately emits (a slice of the
    # committed shape): headings, bullets, emphasis -- none of it starts
    # with "Generated", so none of it may trip the deny-list.
    legit_body = ("## Very Important\n\n_None._\n\n## Important\n\n"
                  "- **#288**: docs: condense target-spec Basis cells\n")

    check("accepts a clean region", False, wrap(legit_body))
    check("accepts an empty region (markers only)", False,
          wrap(""))
    check("rejects the observed _Generated: stamp inside the region", True,
          wrap(stamp + legit_body))
    check("rejects a bare Generated: stamp (no underscores) inside the "
          "region", True, wrap("Generated: 2026-11-18T00:00:00Z\n"))
    check("rejects an indented _Generated: stamp inside the region", True,
          wrap("  " + stamp))
    check("accepts the identical stamp line outside the markers (prose is "
          "free)", False,
          f"intro {START_MARKER}\n{legit_body}{END_MARKER}\n"
          f"_Generated: 2026-11-18T13:45:00Z (snapshot)_\n")
    check("accepts renderer-legitimate markdown that merely contains the "
          "word Generated mid-line", False,
          wrap("- see Generated artifacts in evidence/\n"))
    check("rejects a missing start marker", True,
          f"intro\n{legit_body}{END_MARKER}\noutro\n")
    check("rejects a missing end marker", True,
          f"intro\n{START_MARKER}\n{legit_body}outro\n")
    check("rejects a file with no markers at all (region absent)", True,
          "intro\nno region here\noutro\n")
    check("rejects a doubled start marker (unbalanced)", True,
          f"intro\n{START_MARKER}\n{START_MARKER}\n{END_MARKER}\n")
    check("rejects an out-of-order region (end before start)", True,
          f"intro\n{END_MARKER}\n{legit_body}{START_MARKER}\noutro\n")
    check("accepts a CRLF file whose region is clean", False,
          wrap(legit_body).replace("\n", "\r\n"))
    check("rejects a CRLF file whose region carries the stamp", True,
          wrap(stamp + legit_body).replace("\n", "\r\n"))

    # Committed-tree regression case (hermetic stdlib read): the checked-in
    # WORK_PLAN.md must pass the gate, so the #342/#343 stamp cannot be
    # re-added on main unnoticed.
    try:
        committed = (repo / WORK_PLAN).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        case_results.append((f"reading committed {WORK_PLAN} ({exc})", False))
    else:
        reset()
        check_plan_body(committed, str(WORK_PLAN))
        case_results.append((f"committed {WORK_PLAN} passes the gate",
                             not FAILURES))

    return report_cases(case_results)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="WORK_PLAN.md guide:plan-body gate: the region between "
        "the plan-body markers is renderer-owned (issue #344); fail on any "
        "line carrying a _Generated:/Generated: timestamp stamp, or on "
        "missing/unbalanced markers"
    )
    sub = parser.add_subparsers(dest="mode", required=True)

    p_gate = sub.add_parser(
        "gate", help="fail if the committed WORK_PLAN.md plan-body region "
        "carries a timestamp stamp or broken markers"
    )
    p_gate.add_argument("--repo-root", default=str(REPO_ROOT))

    return dispatch(parser, sub, argv, run_gate, run_selftest)


if __name__ == "__main__":
    raise SystemExit(main())
