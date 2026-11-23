"""Hermetic tests for scripts/pex-measure-command.py (issue #187): no ngspice."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_spec = importlib.util.spec_from_file_location(
    "pex_measure_command", REPO_ROOT / "scripts" / "pex-measure-command.py")
pmc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pmc)


class _Regen:
    def __init__(self, outcome="resolved", ns=0.5):
        self.outcome, self.ns = outcome, ns

    def run_regen_sweep(self, **kw):
        assert kw["vindiff_sweep_mv"] == [50.0]
        return [SimpleNamespace(outcome=self.outcome, regen_time_ns=self.ns)]


class _Kick:
    def __init__(self, peak=2.5e-3):
        self.peak, self.calls = peak, []

    def run_kickback(self, **kw):
        self.calls.append(kw)
        return [SimpleNamespace(variant="ideal", peak_dev_v=0.0),
                SimpleNamespace(variant="loaded", peak_dev_v=self.peak)]


class Tests(unittest.TestCase):
    def test_document_shape(self):
        doc = pmc.build_document(
            lambda c, t: pmc.measure_corner(_Regen(), _Kick(), c, t),
            [("tt", 27.0), ("ss", -40.0)], 1.8)
        self.assertEqual([c["corner_id"] for c in doc["corners"]],
                         ["tt/1.800V/27C", "ss/1.800V/-40C"])
        m = {x["name"]: x["value"] for x in doc["corners"][0]["measurements"]}
        self.assertEqual(m[pmc.ROW_DECISION], 0.5)
        self.assertAlmostEqual(m[pmc.ROW_KICKBACK], 2.5)

    def test_unresolved_is_null_with_message(self):
        rows = pmc.measure_corner(_Regen("non-decision", None), _Kick(), "tt", 27.0)
        self.assertIsNone(rows[0]["value"])
        self.assertIn("non-decision", rows[0]["message"])

    def test_only_loaded_variant_is_simulated(self):
        k = _Kick()
        pmc.measure_corner(_Regen(), k, "tt", 27.0)
        self.assertEqual(k.calls[0]["variants"], ("loaded",))

    def test_non_finite_values_become_named_null_rows(self):
        nan = float("nan")
        doc = pmc.build_document(
            lambda c, t: pmc.measure_corner(_Regen("resolved", nan), _Kick(nan), c, t),
            [("tt", 27.0)], 1.8)
        for row in doc["corners"][0]["measurements"]:
            self.assertIsNone(row["value"])
            self.assertIn("message", row)
        json.dumps(doc, allow_nan=False)  # must not raise

    def test_corners_flag_is_required(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as cm:
            pmc.main(["x.spice"])
        self.assertEqual(cm.exception.code, 2)

    def test_parse_corners(self):
        graded = (("tt", 27.0), ("ss", -40.0), ("sf", 125.0))
        self.assertEqual(pmc.parse_corners("all", graded), list(graded))
        self.assertEqual(pmc.parse_corners("sf:125", graded), [("sf", 125.0)])
        with self.assertRaises(ValueError):
            pmc.parse_corners("tt", graded)
        with self.assertRaises(ValueError):
            pmc.parse_corners("zz:999", graded)

    def test_extracted_netlist_must_match_committed(self):
        self.assertIsNone(pmc.check_netlist("extracted", pmc.RAW_EXTRACT))
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.spice"
            p.write_text(pmc.RAW_EXTRACT.read_text() + "* drift\n")
            self.assertIn("differs", pmc.check_netlist("extracted", p))
            self.assertIn("does not exist", pmc.check_netlist("extracted", Path(d) / "no"))
            self.assertIn("unknown", pmc.check_netlist("bogus", p))
            p.write_text("* no circuit\n")
            self.assertIn("differs", pmc.check_netlist("schematic", p))
            # A subckt-bearing but wrong netlist (the extracted one) is rejected
            # as a schematic; the measured fragment itself is accepted.
            self.assertIn("differs", pmc.check_netlist("schematic", pmc.RAW_EXTRACT))
        self.assertIsNone(pmc.check_netlist("schematic", pmc.SCHEMATIC_FRAGMENT))


if __name__ == "__main__":
    unittest.main()
