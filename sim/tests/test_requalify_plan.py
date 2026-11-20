"""Unit tests for sim/comparator-decision/check-requalify-plan.py (issue
#358): the requalify plan's existence/uniqueness gate must actually bite --
a missing record id and a duplicate id each fail the check, an unresolved
entry fails it too, and the committed plan itself passes.

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


def _load_check_module():
    # The hyphenated directory name is not importable as a package (the
    # same reason sim/comparator-decision/run.py is loaded by path -- see
    # that file's docstring); load the check the same way.
    spec = importlib.util.spec_from_file_location("check_requalify_plan", _PLAN_MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestRequalifyPlanCheck(unittest.TestCase):
    def setUp(self):
        self.check = _load_check_module()
        self.committed = json.loads((SIM_DIR / "comparator-decision" / "requalify-plan.json").read_text())
        self.assertTrue(self.committed["entries"], "committed plan must not be empty")

    def test_committed_plan_passes(self):
        records_dir = SIM_DIR / "comparator-decision" / "records"
        self.assertEqual(self.check.check_plan(self.committed, records_dir), [])

    def test_missing_record_fails(self):
        plan = copy.deepcopy(self.committed)
        plan["entries"][0]["record_id"] = "20990101-000000-nonexist"
        with tempfile.TemporaryDirectory() as td:
            # A records dir that HAS the committed ids but not the sabotaged
            # one: existence is checked by filename, so an empty dir also
            # works, but this keeps the failure to exactly the sabotage.
            records = Path(td)
            (records / (self.committed["entries"][1]["record_id"] + ".md")).write_text("x\n")
            problems = self.check.check_plan(plan, records)
        self.assertTrue(any("nonexist" in p and ("no record file" in p or "--supersedes" in p) for p in problems),
                        problems)

    def test_duplicate_record_fails(self):
        plan = copy.deepcopy(self.committed)
        plan["entries"].append(copy.deepcopy(plan["entries"][0]))
        records_dir = SIM_DIR / "comparator-decision" / "records"
        problems = self.check.check_plan(plan, records_dir)
        self.assertTrue(any("appears 2 times" in p for p in problems), problems)

    def test_unresolved_entry_fails_without_flag(self):
        plan = copy.deepcopy(self.committed)
        plan["entries"][0]["needs_resolution"] = True
        plan["entries"][0]["resolution_reason"] = "sabotage: value unknown"
        records_dir = SIM_DIR / "comparator-decision" / "records"
        problems = self.check.check_plan(plan, records_dir)
        self.assertTrue(any("unresolved" in p for p in problems), problems)
        self.assertEqual(self.check.check_plan(plan, records_dir, allow_unresolved=True), [])

    def test_cli_missing_plan_file_fails(self):
        rc = self.check.main(["--plan", "/nonexistent/requalify-plan.json"])
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
