"""Shared CI-gate helpers for the scripts/check-*.py gates (issue #56).

One source of truth for the output convention every gate in this directory
already agreed on informally:

    gate: FAIL: <msg>      a hard failure; recorded in FAILURES
    gate: WARN: <msg>      a non-fatal observation; recorded in WARNINGS
    gate: ok: <msg>        a passing check

and the matching selftest convention, `report_cases()`:

    selftest: ok: <case>   a passing selftest case
    selftest: FAIL: <case> a failing selftest case
    selftest: all N cases passed / selftest: N case(s) failed

plus `load_json()`, the three-way JSON reader (missing file / bad JSON /
non-object payload all raise `ValueError`), and `dispatch()`, the
gate/selftest argv tail that turns such a `ValueError` into
`gate: FAIL: ...` with exit code 1.

Extracted from `check-integrator-view.py` and `check-t1-signoff.py`, which
had byte-for-byte identical copies of `fail`/`ok`/`load_json` (issue #56)
and of the selftest tally and `main()` dispatch tails (issue #69): if the
message prefix or the JSON-load error wording ever changes it must now
change in one place, so the gates cannot drift.  Same rationale as
`check-layout-device-count.py` importing its counter from
`layout/gen_comparator.py`.

IMPORTANT for callers: `FAILURES` and `WARNINGS` are module-level lists
shared by identity with every importer (`from _gate_common import
FAILURES`).  Mutate them in place -- use `reset()` (or `.clear()`), never
`FAILURES = []`, which would rebind only the caller's own name and leave
`fail()` appending to a list nobody reads.

Stdlib only, no virtualenv required.  Private-by-convention (leading
underscore): a helper module for this directory's gates, not a published
interface.
"""

import json
from pathlib import Path

FAILURES = []
WARNINGS = []


def fail(msg: str) -> None:
    FAILURES.append(msg)
    print(f"gate: FAIL: {msg}")


def warn(msg: str) -> None:
    WARNINGS.append(msg)
    print(f"gate: WARN: {msg}")


def ok(msg: str) -> None:
    print(f"gate: ok: {msg}")


def load_json(path, what: str) -> dict:
    try:
        with Path(path).open(encoding="utf-8") as fh:
            doc = json.load(fh)
    except FileNotFoundError:
        raise ValueError(f"{what} file not found: {path}") from None
    except json.JSONDecodeError as exc:
        raise ValueError(f"{what} file is not valid JSON: {path}: {exc}") from None
    if not isinstance(doc, dict):
        raise ValueError(f"{what} file is not a JSON object: {path}")
    return doc


def report_cases(case_results) -> int:
    """Print a selftest's per-case verdicts and tally; return the exit code.

    `case_results` is a list of `(name, passed)` pairs in run order.  Each
    name states what the case expected, so a `FAIL` line needs no further
    detail to be read.
    """
    failed = [name for name, passed in case_results if not passed]
    for name, passed in case_results:
        print(f"selftest: {'ok' if passed else 'FAIL'}: {name}")
    if failed:
        print(f"selftest: {len(failed)} case(s) failed")
        return 1
    print(f"selftest: all {len(case_results)} cases passed")
    return 0


def dispatch(parser, sub, argv, run_gate, run_selftest) -> int:
    """Register the `selftest` mode, parse `argv`, and run the chosen path.

    A `ValueError` from either path -- notably the ones `load_json()` raises
    -- becomes `gate: FAIL: <exc>` on stdout with exit code 1.

    `sub` is the caller's own `add_subparsers()` result: the gate must
    register its `gate` subparser (with its own options) first, and argparse
    exposes no public accessor for an already-created subparsers action.
    """
    sub.add_parser("selftest", help="hermetic fixture test of the gate logic")

    args = parser.parse_args(argv)
    try:
        if args.mode == "gate":
            return run_gate(args)
        return run_selftest(args)
    except ValueError as exc:
        print(f"gate: FAIL: {exc}")
        return 1


def reset() -> None:
    """Empty the failure/warning tallies in place (selftest case isolation).

    In place, so that `FAILURES`/`WARNINGS` names already imported by a gate
    keep pointing at the same lists `fail()`/`warn()` append to.
    """
    FAILURES.clear()
    WARNINGS.clear()
