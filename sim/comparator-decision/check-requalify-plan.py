#!/usr/bin/env python3
"""Validate sim/comparator-decision/requalify-plan.json (issue #358).

The plan is the machine-readable contract the per-mode re-qualification
shards execute against, so its integrity is gated in sim/selftest.sh, not
left to the shard runner's good manners:

  * every entry names an EXISTING record under records/ (a typo'd or
    renamed record-id must fail here, not in a half-spent batch job);
  * no record appears twice (a double supersede would mint two records
    claiming to replace one, breaking the append-only chain's meaning);
  * every entry carries the required keys, a known mode/DUT, and a
  `run_py_args` whose first token is the mode and that ends the campaign
  bookkeeping itself (`--record` + `--supersedes <its own record_id>`);
  * no entry sits unresolved (`needs_resolution: true`): its shard must
    not run until the flagged value is established, so the plan as a
    whole is not executable while any entry is flagged. Pass
    --allow-unresolved to check a deliberately parked plan.

Usage:
    python3 sim/comparator-decision/check-requalify-plan.py [--plan PATH]
        [--records-dir PATH] [--allow-unresolved]

Exit status: 0 plan is consistent; 1 it is not (message on stderr).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

REQUIRED_KEYS = (
    "record_id", "mode", "dut", "corner", "run_py_args",
    "needs_resume_dir", "defaults_assumed", "needs_resolution",
)
MODES = ("regen", "offset", "offset-bisect", "noise", "noise-tran", "reset", "kickback")
DUTS = ("schematic", "extracted")


def check_plan(plan: dict, records_dir: Path, allow_unresolved: bool = False) -> list[str]:
    """Return the list of problems (empty == the plan is consistent)."""
    problems: list[str] = []
    entries = plan.get("entries")
    if not isinstance(entries, list) or not entries:
        return [f"plan has no entries list: {type(entries).__name__}"]

    seen: dict[str, int] = {}
    unresolved: list[str] = []
    for i, entry in enumerate(entries):
        where = f"entry[{i}]"
        if not isinstance(entry, dict):
            problems.append(f"{where}: not an object")
            continue
        rid = entry.get("record_id", "<missing>")
        where = f"entry {rid!r}"

        for key in REQUIRED_KEYS:
            if key not in entry:
                problems.append(f"{where}: missing required key {key!r}")
        if entry.get("mode") not in MODES:
            problems.append(f"{where}: mode {entry.get('mode')!r} not in {MODES}")
        if entry.get("dut") not in DUTS:
            problems.append(f"{where}: dut {entry.get('dut')!r} not in {DUTS}")

        args = entry.get("run_py_args")
        if not isinstance(args, list) or not args:
            problems.append(f"{where}: run_py_args is not a non-empty list")
        else:
            if args[0] != entry.get("mode"):
                problems.append(f"{where}: run_py_args[0] {args[0]!r} != mode {entry.get('mode')!r}")
            if "--record" not in args:
                problems.append(f"{where}: run_py_args lacks --record")
            if "--supersedes" in args:
                value = args[args.index("--supersedes") + 1] if args.index("--supersedes") + 1 < len(args) else None
                if value != rid:
                    problems.append(f"{where}: --supersedes {value!r} != its own record_id")
            else:
                problems.append(f"{where}: run_py_args lacks --supersedes")

        if not isinstance(entry.get("defaults_assumed", []), list):
            problems.append(f"{where}: defaults_assumed is not a list")
        if entry.get("needs_resolution"):
            unresolved.append(f"{where}: needs_resolution ({entry.get('resolution_reason')!r})")

        if rid != "<missing>":
            seen[rid] = seen.get(rid, 0) + 1
            if not (records_dir / f"{rid}.md").is_file():
                problems.append(f"{where}: no record file {records_dir / (rid + '.md')}")

    for rid, count in seen.items():
        if count > 1:
            problems.append(f"record {rid!r} appears {count} times in the plan")

    if unresolved and not allow_unresolved:
        problems.append(
            f"{len(unresolved)} entr{'y is' if len(unresolved) == 1 else 'ies are'} unresolved; "
            "their shards must not run until the flagged values are established "
            "(re-run with --allow-unresolved only to park them deliberately): "
            + "; ".join(unresolved)
        )
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--plan", default=str(HERE / "requalify-plan.json"),
                    help="path to the plan JSON (default: the committed one)")
    ap.add_argument("--records-dir", default=str(HERE / "records"),
                    help="directory of evidence records (default: this experiment's records/)")
    ap.add_argument("--allow-unresolved", action="store_true",
                    help="accept needs_resolution entries (deliberately parked plan)")
    args = ap.parse_args(argv)

    plan_path = Path(args.plan)
    try:
        plan = json.loads(plan_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        print(f"check-requalify-plan: cannot read plan {plan_path}: {exc}", file=sys.stderr)
        return 1

    problems = check_plan(plan, Path(args.records_dir), allow_unresolved=args.allow_unresolved)
    if problems:
        for p in problems:
            print(f"check-requalify-plan: FAIL {p}", file=sys.stderr)
        return 1
    print(f"check-requalify-plan: OK {len(plan['entries'])} entries, all records exist, no duplicates")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
