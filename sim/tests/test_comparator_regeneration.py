"""Tests for sim/comparator-regeneration/ladder.py (issue #171): request
shape, gf180 measure-name parity, and positive/negative controls for the
grader. No ngspice; the live sims are recorded evidence (records/)."""

from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "ladder", SIM_DIR / "comparator-regeneration" / "ladder.py")
ladder = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ladder)

# The forward-ladder names gf180-comparator's tb.json uses (reverse names are #170).
GF180_FORWARD = {
    "td_od50_ns", "td_od1_ns", "td_od01_ns", "tau_ps", "td_od1_over_tau",
    "resolve_decades", "dout_od50_end", "dout_od1_end", "dout_od01_end",
    "dout_od50_first", "dout_od1_first", "dout_od01_first", "i_static_ua",
    "e_dec_fj",
}
GOOD = {
    "td_od50_ns": 0.44, "td_od1_ns": 1.09, "td_od01_ns": 1.46, "tau_ps": 163.0,
    "td_od1_over_tau": 6.7, "resolve_decades": 6.7,
    "dout_od50_end": 0.96, "dout_od1_end": 0.88, "dout_od01_end": 0.88,
    "dout_od50_first": 0.04, "dout_od1_first": 0.12, "dout_od01_first": 0.12,
    "i_static_ua": 53.0, "e_dec_fj": 1990.0,
}


def _response(process_scale=1.0, **override):
    """A synthetic klt-sim response over the 45-point grid. td_od50_ns moves
    with process and temperature (like the real circuit) unless
    process_scale is 0."""
    corners = []
    for proc, k in (("tt", 0.0), ("ss", 1.0), ("ff", -1.0), ("sf", 0.3), ("fs", -0.3)):
        for t, kt in ((-40, -0.2), (27, 0.0), (125, 0.3)):
            for v in (1.62, 1.8, 1.98):
                vals = dict(GOOD)
                vals["td_od50_ns"] = GOOD["td_od50_ns"] * (1 + 0.2 * k * process_scale + kt)
                vals.update(override)
                corners.append({
                    "corner_id": f"{proc}/{v:.3f}V/{t}C", "process": proc,
                    "supply_v": {"vsup": v, "vsupa": v}, "temperature_c": t,
                    "measurements": [{"name": n, "value": x} for n, x in vals.items()],
                })
    return {"corners": corners}


class RequestShape(unittest.TestCase):
    def test_measure_names_match_gf180_forward_ladder(self):
        m = ladder.load_manifest()
        self.assertEqual(set(m["measure"]), GF180_FORWARD)
        self.assertTrue(set(m["checks"]) <= GF180_FORWARD)

    def test_requests_cover_pvt_axes_and_graded_corners(self):
        reqs = ladder.build_requests()
        self.assertEqual(set(reqs), {"process", "temperature", "supply", "graded-cold", "graded-hot"})
        self.assertEqual(reqs["process"]["corners"]["process"], ["tt", "ss", "ff", "sf", "fs"])
        self.assertEqual(reqs["temperature"]["corners"]["temperature_c"], [-40, 27, 125])
        sup = reqs["supply"]["corners"]["supply_v"]
        self.assertEqual(sup["vsup"], [1.62, 1.8, 1.98])
        self.assertEqual(sup["vsupa"], sup["vsup"])
        covered = {("tt", 27.0)}
        for r in reqs.values():
            c = r["corners"]
            excl = {(e["process"], e["temperature_c"]) for e in r.get("exclude", [])}
            covered |= {(p, float(t)) for p in c["process"] for t in c["temperature_c"]
                        if (p, t) not in excl and c["supply_v"]["vsup"] == [1.8]}
        for pair in ladder.load_manifest()["graded_corners"]:
            self.assertIn((pair[0], float(pair[1])), covered)
        for r in reqs.values():
            self.assertLessEqual(len(r["corners"]["process"]) * len(r["corners"]["temperature_c"])
                                 * len(r["corners"]["supply_v"]["vsup"]), 5)
            self.assertTrue(GF180_FORWARD <= {x["name"] for x in r["measurements"]})

    def test_every_measurement_is_one_meas_card_and_tran(self):
        req = ladder.build_requests()["process"]
        self.assertEqual(req["analysis"]["kind"], "tran")
        for x in req["measurements"]:
            self.assertTrue(x["spice"].startswith(".meas tran "), x)

    def test_netlist_is_a_circuit_body_with_three_rungs(self):
        n = ladder.build_netlist(dut_text="XM1 a b c d nfet\n")
        self.assertNotIn(".control", n)
        self.assertNotIn(".end\n", n.replace(".ends", ""))
        for r in "abc":
            self.assertIn(f"X{r} ", n)
        self.assertIn("pwl(0 -0.05 25n -0.05 26n 0.05)", n)

    def test_sabotage_swaps_stimulus_signs_only(self):
        good = ladder.build_netlist(dut_text="*\n")
        bad = ladder.build_netlist(dut_text="*\n", sabotage_polarity=True)
        self.assertNotEqual(good, bad)
        self.assertIn("pwl(0 0.05 25n 0.05 26n -0.05)", bad)


class GraderControls(unittest.TestCase):
    def setUp(self):
        self.m = ladder.load_manifest()

    def test_positive_control_passes(self):
        self.assertEqual(ladder.grade(_response(), self.m), [])

    def test_negative_control_wrong_polarity_fails(self):
        r = _response(dout_od50_end=0.04, dout_od50_first=0.96)
        fails = ladder.grade(r, self.m)
        self.assertTrue(any("dout_od50_end" in f for f in fails))
        self.assertTrue(any("dout_od50_first" in f for f in fails))

    def test_negative_control_missing_delay_fails(self):
        fails = ladder.grade(_response(td_od50_ns=None), self.m)
        self.assertTrue(any("td_od50_ns: no value" in f for f in fails))

    def test_negative_control_flat_corners_fail_spread_floor(self):
        # A runner that silently simulates typical everywhere: no process
        # sensitivity. The per-axis floor must catch it.
        m = json.loads(json.dumps(self.m))
        floor = m["checks"]["td_od50_ns"]["min_spread_pct_by_axis"]["process"]
        self.assertGreater(floor, 0, "process floor must be calibrated (>0)")
        fails = ladder.grade(_response(process_scale=0.0), m)
        self.assertTrue(any("process-axis spread" in f for f in fails), fails)


if __name__ == "__main__":
    unittest.main()
