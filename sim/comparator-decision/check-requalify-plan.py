#!/usr/bin/env python3
"""Validate sim/comparator-decision/requalify-plan.json (issues #358, #361).

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

Since issue #361 (the campaign's rebuild step) it also checks the plan is
**discharged**: for every entry, the entry's `Supersedes` chain is followed
FORWARD -- from the pre-campaign record the entry names, through every
record that names it in `Supersedes` -- to the terminal replacement for the
same measurement and DUT, and that terminal's Environment PDK must equal
sim/pdk.json's full `open_pdks_commit` pin. The 36 extracted entries end in
a two-link chain (the campaign measurement plus its corrected reissue), and
the two extracted `regen` entries also branch at the 0.35 um geometry
re-draw into a dead-end old-pin terminal, so the check walks every branch
and requires exactly one terminal at the current pin (a second terminal at
the pin would be two records claiming to be the current one). A superseding
record whose mode or DUT differs from the plan entry fails too: a
replacement of the *wrong measurement* would otherwise pass a pin-only
check. Pass --print-terminals to emit the entry -> terminal map as JSON
instead of checking.

Usage:
    python3 sim/comparator-decision/check-requalify-plan.py [--plan PATH]
        [--records-dir PATH] [--allow-unresolved] [--pdk-json PATH]
        [--print-terminals]

Exit status: 0 plan is consistent; 1 it is not (message on stderr).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

PDK_JSON = HERE.parent / "pdk.json"

REQUIRED_KEYS = (
    "record_id", "mode", "dut", "corner", "run_py_args",
    "needs_resume_dir", "defaults_assumed", "needs_resolution",
)
MODES = ("regen", "offset", "offset-bisect", "noise", "noise-tran", "reset", "kickback")
DUTS = ("schematic", "extracted")

_RECORD_ID_RE = re.compile(r"\d{8}-\d{6}-[0-9a-f]+")
_SUPERSEDES_RE = re.compile(r"^- \*\*Supersedes\*\*: (.+)$", re.MULTILINE)
_PDK_RE = re.compile(r"^- PDK: sky130A @ ([0-9a-f]+)$", re.MULTILINE)
_FOOTER_RE = re.compile(
    r"(?:Written by|Original measurement produced by) "
    r"`sim/comparator-decision/run\.py ([a-z-]+)`"
)
_PROVENANCE_RE = re.compile(r"^- \*\*Netlist provenance\*\*: (.+)$", re.MULTILINE)


def read_pdk_commit(pdk_json: Path) -> str | None:
    """The full open_pdks commit pin the replacements must carry."""
    try:
        doc = json.loads(pdk_json.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    commit = doc.get("open_pdks_commit")
    return commit if isinstance(commit, str) and commit else None


class RecordIndex:
    """Every record under `records_dir`, indexed by what discharge needs.

    A record's `Supersedes` field may name several prior ids (comma- or
    space-separated); each is one forward edge. The PDK pin, the mode
    (the record footer's ``Written by ... run.py <mode>``) and the DUT
    (the `Netlist provenance` line) are read once per file.
    """

    def __init__(self, records_dir: Path):
        self.records_dir = records_dir
        self.supersedes: dict[str, list[str]] = {}
        self.succeeded_by: dict[str, list[str]] = {}
        self.pdk: dict[str, str | None] = {}
        self.mode: dict[str, str | None] = {}
        self.dut: dict[str, str | None] = {}
        for path in records_dir.glob("*.md"):
            rid = path.stem
            text = path.read_text(encoding="utf-8", errors="replace")
            ids: list[str] = []
            match = _SUPERSEDES_RE.search(text)
            if match and match.group(1).strip() != "(none)":
                ids = [
                    tok for tok in re.split(r"[,\s]+", match.group(1).strip())
                    if _RECORD_ID_RE.fullmatch(tok)
                ]
            self.supersedes[rid] = ids
            for prior in ids:
                self.succeeded_by.setdefault(prior, []).append(rid)
            pdk = _PDK_RE.search(text)
            self.pdk[rid] = pdk.group(1) if pdk else None
            footer = _FOOTER_RE.search(text)
            self.mode[rid] = footer.group(1) if footer else None
            prov = _PROVENANCE_RE.search(text)
            if prov is None:
                self.dut[rid] = None
            else:
                line = prov.group(1)
                self.dut[rid] = (
                    "extracted" if "POST-LAYOUT / EXTRACTED" in line
                    else "schematic" if line.startswith("schematic-derived")
                    else None
                )

    def successors(self, rid: str) -> list[str]:
        return sorted(
            s for s in self.succeeded_by.get(rid, [])
            if (self.records_dir / f"{s}.md").is_file()
        )

    def terminals(self, rid: str) -> tuple[list[str], list[str]]:
        """`(terminals, dead_edges)` following `Supersedes` forward from `rid`.

        `terminals` are the records no further record supersedes; a
        `Supersedes` edge naming a record with no file (or a cycle) is a
        dead edge and is reported rather than silently dropped.
        """
        terminals: list[str] = []
        dead: list[str] = []
        stack = [(rid, frozenset({rid}))]
        while stack:
            cur, seen = stack.pop()
            nxt = self.successors(cur)
            branched = False
            for succ in nxt:
                if succ in seen:
                    dead.append(f"{cur} -> {succ} (cycle)")
                    branched = True
                    continue
                stack.append((succ, seen | {succ}))
                branched = True
            if not branched:
                terminals.append(cur)
        return sorted(set(terminals)), sorted(set(dead))


def check_discharge(
    plan: dict, index: RecordIndex, pdk_commit: str
) -> tuple[list[str], dict[str, str]]:
    """Verify every plan entry's terminal replacement, at the full pin.

    Returns `(problems, terminal_map)`; `terminal_map` maps each entry's
    `record_id` to the one terminal record at `pdk_commit` (absent for
    entries that produced problems).
    """
    problems: list[str] = []
    terminal_map: dict[str, str] = {}
    for entry in plan.get("entries", []):
        if not isinstance(entry, dict):
            continue
        rid = entry.get("record_id")
        mode = entry.get("mode")
        dut = entry.get("dut")
        where = f"entry {rid!r}"
        terminals, dead = index.terminals(rid)
        for edge in dead:
            problems.append(f"{where}: broken supersession edge {edge}")
        at_pin = [t for t in terminals if index.pdk.get(t) == pdk_commit]
        if not at_pin:
            detail = ", ".join(
                f"{t}@{index.pdk.get(t) or 'no-pin'}" for t in terminals
            ) or "none"
            problems.append(
                f"{where}: no terminal replacement at the pinned PDK "
                f"{pdk_commit} (terminals: {detail}) -- the re-qualification "
                "record for this entry is missing or was minted off-pin"
            )
            continue
        if len(at_pin) > 1:
            problems.append(
                f"{where}: {len(at_pin)} terminal records at the pinned PDK "
                f"({', '.join(at_pin)}) -- two records claim to be the "
                "current replacement for one measurement"
            )
            continue
        terminal = at_pin[0]
        if index.mode.get(terminal) != mode:
            problems.append(
                f"{where}: terminal {terminal} was written by run.py "
                f"{index.mode.get(terminal)!r}, not {mode!r} -- it replaces "
                "the entry with a different measurement"
            )
            continue
        if index.dut.get(terminal) != dut:
            problems.append(
                f"{where}: terminal {terminal} has netlist provenance "
                f"{index.dut.get(terminal)!r}, not {dut!r}"
            )
            continue
        terminal_map[rid] = terminal
    return problems, terminal_map


def check_plan(
    plan: dict,
    records_dir: Path,
    allow_unresolved: bool = False,
    pdk_commit: str | None = None,
    index: RecordIndex | None = None,
) -> tuple[list[str], dict[str, str]]:
    """Return `(problems, terminal_map)`; empty problems == the plan is
    consistent and fully discharged at `pdk_commit`.

    `pdk_commit` defaults to sim/pdk.json's `open_pdks_commit`; pass a pin
    explicitly (as the unit-test fixtures do) to check against anything
    else. An unreadable pin file is itself a problem: a discharge check
    against an unknown pin is not a discharge check.
    """
    problems: list[str] = check_plan_shape(plan, records_dir, allow_unresolved)
    if problems:
        return problems, {}
    if pdk_commit is None:
        pdk_commit = read_pdk_commit(PDK_JSON)
    if not pdk_commit:
        problems.append(
            f"cannot read the PDK pin to discharge against: {PDK_JSON} has no "
            "readable open_pdks_commit"
        )
        return problems, {}
    if index is None:
        index = RecordIndex(records_dir)
    discharge_problems, terminal_map = check_discharge(plan, index, pdk_commit)
    problems.extend(discharge_problems)
    return problems, terminal_map


def check_plan_shape(
    plan: dict, records_dir: Path, allow_unresolved: bool = False
) -> list[str]:
    """The issue-#358 shape checks, unchanged (see module docstring)."""
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
    ap.add_argument("--pdk-json", default=str(PDK_JSON),
                    help="the sim/pdk.json whose open_pdks_commit the "
                         "replacements must carry (default: the committed pin)")
    ap.add_argument("--print-terminals", action="store_true",
                    help="print the entry record_id -> terminal record map as "
                         "JSON on stdout instead of checking")
    args = ap.parse_args(argv)

    plan_path = Path(args.plan)
    try:
        plan = json.loads(plan_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        print(f"check-requalify-plan: cannot read plan {plan_path}: {exc}", file=sys.stderr)
        return 1

    pdk_commit = read_pdk_commit(Path(args.pdk_json))
    records_dir = Path(args.records_dir)
    index = RecordIndex(records_dir)

    if args.print_terminals:
        if not pdk_commit:
            print(f"check-requalify-plan: cannot read PDK pin {args.pdk_json}", file=sys.stderr)
            return 1
        problems, terminal_map = check_discharge(plan, index, pdk_commit)
        if problems:
            for p in problems:
                print(f"check-requalify-plan: FAIL {p}", file=sys.stderr)
            return 1
        print(json.dumps(terminal_map, indent=2, sort_keys=True))
        return 0

    problems, _terminal_map = check_plan(
        plan, records_dir,
        allow_unresolved=args.allow_unresolved,
        pdk_commit=pdk_commit,
        index=index,
    )
    if problems:
        for p in problems:
            print(f"check-requalify-plan: FAIL {p}", file=sys.stderr)
        return 1
    pin = pdk_commit or "<unreadable>"
    print(
        f"check-requalify-plan: OK {len(plan['entries'])} entries, all records "
        f"exist, no duplicates, every entry discharged at PDK {pin}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
