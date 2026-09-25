"""Shared CI-gate helpers for the scripts/check-*.py gates (issue #56).

One source of truth for the output convention every gate in this directory
already agreed on informally:

    gate: FAIL: <msg>      a hard failure; recorded in FAILURES
    gate: WARN: <msg>      a non-fatal observation; recorded in WARNINGS
    gate: ok: <msg>        a passing check

plus `load_json()`, the three-way JSON reader (missing file / bad JSON /
non-object payload all raise `ValueError`, which every gate's `main()`
already catches and prints as `gate: FAIL: ...`).

Extracted from `check-integrator-view.py` and `check-t1-signoff.py`, which
had byte-for-byte identical copies of `fail`/`ok`/`load_json`: if the
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


def reset() -> None:
    """Empty the failure/warning tallies in place (selftest case isolation).

    In place, so that `FAILURES`/`WARNINGS` names already imported by a gate
    keep pointing at the same lists `fail()`/`warn()` append to.
    """
    FAILURES.clear()
    WARNINGS.clear()
