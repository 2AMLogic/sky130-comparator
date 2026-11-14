#!/usr/bin/env python3
"""Toolchain-pin CI gate (issue #245): the workflow's install lines cannot
drift from the pin's single source of truth.

    python3 scripts/check-toolchain-pin.py gate
    python3 scripts/check-toolchain-pin.py selftest

The klt / klayout toolchain pin used to be restated as five Python constants
across three modules plus one hand-maintained `pip install` line per CI job.
The constants now live only in `layout/gen_comparator.py` (`KLT_VERSION` /
`KLAYOUT_VERSION`, and the composite `KLT_PIN` derived from them);
`layout/extract_pex.py` and `scripts/layout-envelope.py` import them. What
remained un-checked was the workflow text itself: `.github/workflows/
t1-signoff.yml` carries one `pip install "klayout-tools==…" "klayout==…"`
line per job, and a bump that edits the Python constant but misses one job's
line would install a different toolchain in CI than the artifacts declare.

`gate` re-derives the pin from `gen_comparator.py` and fails if ANY
`klayout-tools==` / `klayout==` occurrence in the workflow disagrees with it,
or if the pin has vanished from the workflow entirely. The scan is
deliberately job-count-agnostic -- the file is scanned line by line, so a
job added later is covered without touching this gate (the count of install
lines is reported, never assumed).

`selftest` is hermetic (stdlib file reads only, no klt, no PDK): it proves
the composite `KLT_PIN` derivation still renders the string the committed
artifacts carry byte for byte, that the scanner accepts a matching
multi-install-line workflow, and that it rejects the drift shapes -- a
partial bump of one line's either pin, and each pin vanishing.

Same `_gate_common` convention as the other gates in this directory, and the
same cross-directory import precedent as `check-layout-device-count.py`
importing its counter from `layout/gen_comparator.py`.

Stdlib only, no virtualenv required.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "layout"))

from _gate_common import (FAILURES, dispatch, fail, ok,  # noqa: E402
                          report_cases, reset)
from gen_comparator import KLAYOUT_VERSION, KLT_PIN, KLT_VERSION  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = Path(".github/workflows/t1-signoff.yml")
#: The committed artifact whose `tool.klt_pin` the composite is asserted
#: against byte for byte (re-asserted in CI by check-layout-device-count.py).
KLT_PIN_ARTIFACT = Path("layout/extract-device-count.json")

TOOLS_RE = re.compile(r"klayout-tools==([^\s\"'`]+)")
ENGINE_RE = re.compile(r"\bklayout==([^\s\"'`]+)")


def scan_workflow(text: str) -> tuple[list[tuple[int, str]], list[tuple[int, str]]]:
    """Every `klayout-tools==` / `klayout==` occurrence, as (lineno, version).

    Line-by-line on purpose (issue #245): no job parsing, no install-line
    count assumption, so jobs added later are covered for free. The two
    patterns cannot cross-match -- `klayout-tools==` does not contain
    `klayout==` (the `klayout` there is followed by `-tools==`).
    """
    tools: list[tuple[int, str]] = []
    engine: list[tuple[int, str]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if line.lstrip().startswith("#"):
            continue  # comment prose may mention the pin without pinning it
        tools.extend((lineno, m.group(1)) for m in TOOLS_RE.finditer(line))
        engine.extend((lineno, m.group(1)) for m in ENGINE_RE.finditer(line))
    return tools, engine


def check_workflow(text: str, name: str) -> None:
    tools, engine = scan_workflow(text)
    if not tools:
        fail(f"{name}: no `klayout-tools==` install line found -- the klt pin "
             "has vanished from CI")
    if not engine:
        fail(f"{name}: no `klayout==` install line found -- the klayout engine "
             "pin has vanished from CI")
    for lineno, version in tools:
        if version != KLT_VERSION:
            fail(f"{name}:{lineno}: installs klayout-tools=={version}, but the "
                 f"single source of truth (layout/gen_comparator.py) pins "
                 f"klayout-tools=={KLT_VERSION}")
    for lineno, version in engine:
        if version != KLAYOUT_VERSION:
            fail(f"{name}:{lineno}: installs klayout=={version}, but the "
                 f"single source of truth (layout/gen_comparator.py) pins "
                 f"klayout=={KLAYOUT_VERSION}")
    if not FAILURES:
        ok(f"{name}: all {len(tools)} klayout-tools== and {len(engine)} "
           f"klayout== install line(s) match the pin "
           f"{KLT_VERSION} / {KLAYOUT_VERSION}")


def run_gate(args: argparse.Namespace) -> int:
    path = Path(args.repo_root).resolve() / WORKFLOW
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        fail(f"workflow not found: {path}")
        return 1
    check_workflow(text, str(WORKFLOW))
    if FAILURES:
        print(f"gate: {len(FAILURES)} failure(s) -- see above")
        return 1
    return 0


def run_selftest(args: argparse.Namespace) -> int:
    repo = Path(getattr(args, "repo_root", str(REPO_ROOT))).resolve()
    case_results = []

    # Step 2 of the issue: the composite must render, byte for byte, the
    # string the committed artifacts carry -- the derivation moving a single
    # character would silently re-brand committed provenance.
    try:
        doc = json.loads((repo / KLT_PIN_ARTIFACT).read_text(encoding="utf-8"))
        committed_pin = doc["tool"]["klt_pin"]
        case_results.append((
            f"derived KLT_PIN renders {KLT_PIN_ARTIFACT}'s committed "
            "tool.klt_pin byte for byte",
            KLT_PIN == committed_pin,
        ))
    except (FileNotFoundError, KeyError, json.JSONDecodeError) as exc:
        case_results.append((f"reading {KLT_PIN_ARTIFACT} for the "
                             f"byte-for-byte assertion ({exc})", False))

    def check(name, expect_fail, text):
        # reset() clears the shared tally in place -- rebinding FAILURES here
        # would detach it from the list fail() appends to (_gate_common).
        reset()
        check_workflow(text, "fx-workflow")
        case_results.append((name, (len(FAILURES) > 0) == expect_fail))

    good_line = (f'        run: python -m pip install '
                 f'"klayout-tools=={KLT_VERSION}" '
                 f'"klayout=={KLAYOUT_VERSION}"\n')
    # Multi-line on purpose: the scanner must not care how many jobs install.
    check("accepts a workflow with three matching install lines",
          False, "# jobs a, b, c\n" + good_line * 3)
    check("accepts an unquoted install line matching the pin",
          False, f"run: pip install klayout-tools=={KLT_VERSION} "
                 f"klayout=={KLAYOUT_VERSION}\n")
    bumped_tools = ('        run: python -m pip install "klayout-tools==9.9.9" '
                    f'"klayout=={KLAYOUT_VERSION}"\n')
    check("rejects one bumped klayout-tools== line among matching ones",
          True, good_line + bumped_tools + good_line)
    bumped_engine = (f'        run: python -m pip install '
                     f'"klayout-tools=={KLT_VERSION}" "klayout==0.0.1"\n')
    check("rejects one bumped klayout== line among matching ones",
          True, good_line + good_line + bumped_engine)
    check("rejects a workflow where the klt pin has vanished",
          True, f'        run: python -m pip install "klayout=={KLAYOUT_VERSION}"\n')
    check("rejects a workflow where the klayout engine pin has vanished",
          True, f'        run: python -m pip install "klayout-tools=={KLT_VERSION}"\n')
    check("rejects a workflow with no install lines at all",
          True, "# nothing pinned here\n")
    check("ignores comment prose that mentions a different pin",
          False, "# bump the klayout-tools==9.9.9 line below\n" + good_line)
    check("still scans install lines when comments are present",
          True, "# prose\n" + good_line + "# more prose klayout==0.0.1\n"
                + bumped_tools)

    return report_cases(case_results)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Toolchain-pin CI gate: the t1-signoff workflow's "
        "klayout-tools==/klayout== install lines vs the pin's single source "
        "of truth in layout/gen_comparator.py (issue #245)"
    )
    sub = parser.add_subparsers(dest="mode", required=True)

    p_gate = sub.add_parser(
        "gate", help="fail if any workflow install line disagrees with the pin"
    )
    p_gate.add_argument("--repo-root", default=str(REPO_ROOT))

    return dispatch(parser, sub, argv, run_gate, run_selftest)


if __name__ == "__main__":
    raise SystemExit(main())
