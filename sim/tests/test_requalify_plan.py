"""Unit tests for sim/comparator-decision/check-requalify-plan.py (issues
#358, #361): the requalify plan's shape gate must actually bite -- a missing
record id, a duplicate id and an unresolved entry each fail the check, and
the committed plan itself passes -- and since #361 the plan-discharge half
must bite too: following an entry's Supersedes links forward has to end at
exactly one terminal record carrying the sim/pdk.json pin, in the entry's
own mode and DUT. A direct replacement, a corrected reissue (two links) and
a branch with a dead-end old-pin terminal all pass; a removed replacement, a
wrong-pin replacement, a wrong-mode replacement and a second terminal at the
pin all fail.

Hermetic: the sabotaged copies live in a temp dir; no ngspice, no PDK."""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SIM_DIR))

_PLAN_MODULE_PATH = SIM_DIR / "comparator-decision" / "check-requalify-plan.py"

PIN = "f" * 40
OLD_PIN = "c" * 40


def _load_check_module():
    # The hyphenated directory name is not importable as a package (the
    # same reason sim/comparator-decision/run.py is loaded by path -- see
    # that file's docstring); load the check the same way.
    spec = importlib.util.spec_from_file_location("check_requalify_plan", _PLAN_MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _record(rid: str, *, supersedes="(none)", pdk=OLD_PIN, mode="offset",
            dut="schematic") -> str:
    provenance = (
        "POST-LAYOUT / EXTRACTED (layout/comparator.gds ...)" if dut == "extracted"
        else "schematic-derived (design/comparator.sch -> ...)"
    )
    return f"""# Record {rid}

- **Record ID**: {rid}
- **Netlist provenance**: {provenance}

## Environment

- PDK: sky130A @ {pdk}
- ngspice: ngspice-47

- **Supersedes**: {supersedes}

Written by `sim/comparator-decision/run.py {mode}`. Append-only: never edit or delete this file.
"""


class TestRequalifyPlanCheck(unittest.TestCase):
    def setUp(self):
        self.check = _load_check_module()
        self.committed = json.loads((SIM_DIR / "comparator-decision" / "requalify-plan.json").read_text())
        self.assertTrue(self.committed["entries"], "committed plan must not be empty")

    # ---- issue #358: plan shape -------------------------------------------------

    def test_committed_plan_passes(self):
        records_dir = SIM_DIR / "comparator-decision" / "records"
        problems, terminals = self.check.check_plan(self.committed, records_dir)
        self.assertEqual(problems, [])
        self.assertEqual(len(terminals), len(self.committed["entries"]))
        # The discharge map's values are the current-pin records the report
        # must cite: the 36 extracted entries end at the a22c816 reissues,
        # the 28 schematic ones at the 4d73da9/059ee87 generation.
        self.assertEqual(
            sum(1 for t in terminals.values() if t.endswith("-a22c816")), 36)
        self.assertEqual(
            sum(1 for t in terminals.values() if not t.endswith("-a22c816")), 28)

    def test_missing_record_fails(self):
        plan = copy.deepcopy(self.committed)
        plan["entries"][0]["record_id"] = "20990101-000000-nonexist"
        with tempfile.TemporaryDirectory() as td:
            # A records dir that HAS the committed ids but not the sabotaged
            # one: existence is checked by filename, so an empty dir also
            # works, but this keeps the failure to exactly the sabotage.
            records = Path(td)
            (records / (self.committed["entries"][1]["record_id"] + ".md")).write_text("x\n")
            problems, _ = self.check.check_plan(plan, records)
        self.assertTrue(any("nonexist" in p and ("no record file" in p or "--supersedes" in p) for p in problems),
                        problems)

    def test_duplicate_record_fails(self):
        plan = copy.deepcopy(self.committed)
        plan["entries"].append(copy.deepcopy(plan["entries"][0]))
        records_dir = SIM_DIR / "comparator-decision" / "records"
        problems, _ = self.check.check_plan(plan, records_dir)
        self.assertTrue(any("appears 2 times" in p for p in problems), problems)

    def test_unresolved_entry_fails_without_flag(self):
        plan = copy.deepcopy(self.committed)
        plan["entries"][0]["needs_resolution"] = True
        plan["entries"][0]["resolution_reason"] = "sabotage: value unknown"
        records_dir = SIM_DIR / "comparator-decision" / "records"
        problems, _ = self.check.check_plan(plan, records_dir)
        self.assertTrue(any("unresolved" in p for p in problems), problems)
        problems, _ = self.check.check_plan(plan, records_dir, allow_unresolved=True)
        self.assertEqual(problems, [])

    def test_cli_missing_plan_file_fails(self):
        rc = self.check.main(["--plan", "/nonexistent/requalify-plan.json"])
        self.assertEqual(rc, 1)

    # ---- issue #361: plan discharge ----------------------------------------------

    def _fixture_plan(self, **overrides):
        entry = {
            "record_id": "20260901-000000-aaaaaaa",
            "mode": "offset",
            "dut": "schematic",
            "corner": "tt",
            "run_py_args": ["offset", "--corner", "tt", "--record",
                            "--supersedes", "20260901-000000-aaaaaaa"],
            "needs_resume_dir": False,
            "defaults_assumed": [],
            "needs_resolution": False,
        }
        entry.update(overrides)
        entry["run_py_args"] = [entry["mode"], "--corner", "tt", "--record",
                                "--supersedes", entry["record_id"]]
        return {"entries": [entry]}

    def _records_dir(self, records: dict[str, str]) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        for rid, text in records.items():
            (root / f"{rid}.md").write_text(text)
        return root

    def test_direct_replacement_passes(self):
        records = {
            "20260901-000000-aaaaaaa": _record("20260901-000000-aaaaaaa"),
            "20261101-000000-bbbbbbb": _record(
                "20261101-000000-bbbbbbb",
                supersedes="20260901-000000-aaaaaaa", pdk=PIN),
        }
        root = self._records_dir(records)
        problems, terminals = self.check.check_plan(
            self._fixture_plan(), root, pdk_commit=PIN)
        self.assertEqual(problems, [])
        self.assertEqual(terminals, {"20260901-000000-aaaaaaa": "20261101-000000-bbbbbbb"})

    def test_corrected_reissue_chain_passes(self):
        # The extracted shape: campaign measurement, then its corrected
        # reissue -- the terminal is two links from the plan entry, and a
        # single-hop lookup would stop too early.
        records = {
            "20260901-000000-aaaaaaa": _record("20260901-000000-aaaaaaa", dut="extracted"),
            "20261101-000000-bbbbbbb": _record(
                "20261101-000000-bbbbbbb", supersedes="20260901-000000-aaaaaaa",
                pdk=PIN, dut="extracted"),
            "20261102-000000-ccccccc": _record(
                "20261102-000000-ccccccc", supersedes="20261101-000000-bbbbbbb",
                pdk=PIN, dut="extracted"),
        }
        root = self._records_dir(records)
        problems, terminals = self.check.check_plan(
            self._fixture_plan(dut="extracted"), root, pdk_commit=PIN)
        self.assertEqual(problems, [])
        self.assertEqual(terminals, {"20260901-000000-aaaaaaa": "20261102-000000-ccccccc"})

    def test_removed_replacement_fails(self):
        # The entry itself plus nothing at the pin: the replacement record
        # is gone (or was never minted).
        records = {
            "20260901-000000-aaaaaaa": _record("20260901-000000-aaaaaaa"),
            "20261101-000000-bbbbbbb": _record(
                "20261101-000000-bbbbbbb",
                supersedes="20260901-000000-aaaaaaa", pdk=OLD_PIN),
        }
        root = self._records_dir(records)
        problems, _ = self.check.check_plan(self._fixture_plan(), root, pdk_commit=PIN)
        self.assertTrue(any("no terminal replacement at the pinned PDK" in p for p in problems),
                        problems)

    def test_wrong_pin_replacement_fails(self):
        records = {
            "20260901-000000-aaaaaaa": _record("20260901-000000-aaaaaaa"),
            "20261101-000000-bbbbbbb": _record(
                "20261101-000000-bbbbbbb",
                supersedes="20260901-000000-aaaaaaa", pdk=OLD_PIN),
        }
        root = self._records_dir(records)
        problems, _ = self.check.check_plan(self._fixture_plan(), root, pdk_commit=PIN)
        self.assertTrue(
            any("no terminal replacement at the pinned PDK" in p
                and "bbbbbbb@" + OLD_PIN in p for p in problems),
            problems)

    def test_old_pin_dead_end_branch_still_passes(self):
        # The extracted regen shape: the plan record branches into the
        # 0.35 um geometry re-draw (a dead-end old-pin terminal) AND the
        # new-pin chain. Only the new-pin terminal counts; the historical
        # dead end must not fail the check.
        records = {
            "20260901-000000-aaaaaaa": _record("20260901-000000-aaaaaaa", dut="extracted"),
            "20261001-000000-ddddddd": _record(
                "20261001-000000-ddddddd", supersedes="20260901-000000-aaaaaaa",
                pdk=OLD_PIN, mode="regen", dut="extracted"),
            "20261101-000000-bbbbbbb": _record(
                "20261101-000000-bbbbbbb", supersedes="20260901-000000-aaaaaaa",
                pdk=PIN, mode="regen", dut="extracted"),
        }
        root = self._records_dir(records)
        problems, terminals = self.check.check_plan(
            self._fixture_plan(mode="regen", dut="extracted"), root, pdk_commit=PIN)
        self.assertEqual(problems, [])
        self.assertEqual(terminals, {"20260901-000000-aaaaaaa": "20261101-000000-bbbbbbb"})

    def test_wrong_mode_replacement_fails(self):
        records = {
            "20260901-000000-aaaaaaa": _record("20260901-000000-aaaaaaa"),
            "20261101-000000-bbbbbbb": _record(
                "20261101-000000-bbbbbbb",
                supersedes="20260901-000000-aaaaaaa", pdk=PIN, mode="regen"),
        }
        root = self._records_dir(records)
        problems, _ = self.check.check_plan(self._fixture_plan(), root, pdk_commit=PIN)
        self.assertTrue(any("different measurement" in p for p in problems), problems)

    def test_wrong_dut_replacement_fails(self):
        records = {
            "20260901-000000-aaaaaaa": _record("20260901-000000-aaaaaaa"),
            "20261101-000000-bbbbbbb": _record(
                "20261101-000000-bbbbbbb",
                supersedes="20260901-000000-aaaaaaa", pdk=PIN, dut="extracted"),
        }
        root = self._records_dir(records)
        problems, _ = self.check.check_plan(self._fixture_plan(), root, pdk_commit=PIN)
        self.assertTrue(any("netlist provenance" in p for p in problems), problems)

    def test_two_terminals_at_pin_fail(self):
        records = {
            "20260901-000000-aaaaaaa": _record("20260901-000000-aaaaaaa"),
            "20261101-000000-bbbbbbb": _record(
                "20261101-000000-bbbbbbb",
                supersedes="20260901-000000-aaaaaaa", pdk=PIN),
            "20261102-000000-ccccccc": _record(
                "20261102-000000-ccccccc",
                supersedes="20260901-000000-aaaaaaa", pdk=PIN),
        }
        root = self._records_dir(records)
        problems, _ = self.check.check_plan(self._fixture_plan(), root, pdk_commit=PIN)
        self.assertTrue(any("two records claim to be the current replacement" in p
                            or "terminal records at the pinned PDK" in p for p in problems),
                        problems)

    def test_supersedes_cycle_is_reported(self):
        records = {
            "20260901-000000-aaaaaaa": _record("20260901-000000-aaaaaaa"),
            "20261101-000000-bbbbbbb": _record(
                "20261101-000000-bbbbbbb",
                supersedes="20260901-000000-aaaaaaa, 20261102-000000-ccccccc",
                pdk=PIN),
            "20261102-000000-ccccccc": _record(
                "20261102-000000-ccccccc",
                supersedes="20261101-000000-bbbbbbb", pdk=PIN),
        }
        root = self._records_dir(records)
        problems, _ = self.check.check_plan(self._fixture_plan(), root, pdk_commit=PIN)
        self.assertTrue(any("cycle" in p or "broken supersession edge" in p for p in problems),
                        problems)

    def test_unreadable_pdk_pin_fails_closed(self):
        records = {
            "20260901-000000-aaaaaaa": _record("20260901-000000-aaaaaaa"),
            "20261101-000000-bbbbbbb": _record(
                "20261101-000000-bbbbbbb",
                supersedes="20260901-000000-aaaaaaa", pdk=PIN),
        }
        root = self._records_dir(records)
        # No pdk_commit passed: check_plan falls back to the real sim/pdk.json,
        # so exercise the unreadable-pin path through the module's constant.
        original = self.check.PDK_JSON
        self.check.PDK_JSON = root / "no-such-pdk.json"
        try:
            problems, _ = self.check.check_plan(self._fixture_plan(), root)
        finally:
            self.check.PDK_JSON = original
        self.assertTrue(any("cannot read the PDK pin" in p for p in problems), problems)


if __name__ == "__main__":
    unittest.main()
