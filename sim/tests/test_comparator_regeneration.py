"""Tests for sim/comparator-regeneration/ladder.py (issue #171): request
shape, gf180 measure-name parity, and positive/negative controls for the
grader. No ngspice; the live sims are recorded evidence (records/)."""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SIM_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "ladder", SIM_DIR / "comparator-regeneration" / "ladder.py")
ladder = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ladder)

# The forward-ladder names gf180-comparator's tb.json uses (reverse names: REVERSE_NAMES, #170).
GF180_FORWARD = {
    "td_od50_ns", "td_od1_ns", "td_od01_ns", "tau_ps", "td_od1_over_tau",
    "resolve_decades", "dout_od50_end", "dout_od1_end", "dout_od01_end",
    "dout_od50_first", "dout_od1_first", "dout_od01_first", "i_static_ua",
    "e_dec_fj",
}
REVERSE_NAMES = {
    "td_od50_rev_ns", "td_od1_rev_ns", "td_od01_rev_ns", "tau_rev_ps",
    "dout_od50_rev_first", "dout_od1_rev_first", "dout_od01_rev_first",
    "dout_od50_rev_end", "dout_od1_rev_end", "dout_od01_rev_end",
    "dtd_od50_rev_ps", "dtd_od1_rev_ps", "dtd_od01_rev_ps", "dtau_rev_ps",
}
# Pinned from origin/main @ b96e554 (the issue #171 forward ladder).
FORWARD_NETLIST_SHA = "024d6d41adab34112a590f66f707abda750408af48ce1d568f7dde54f26d66eb"
FORWARD_MANIFEST_SHA = "c5e9676a937f9f55512960ee76f21ccdd35bfe21e4a01202c290e7fb4b726595"
GOOD = {
    "td_od50_ns": 0.44, "td_od1_ns": 1.09, "td_od01_ns": 1.46, "tau_ps": 163.0,
    "td_od1_over_tau": 6.7, "resolve_decades": 6.7,
    "dout_od50_end": 0.96, "dout_od1_end": 0.88, "dout_od01_end": 0.88,
    "dout_od50_first": 0.04, "dout_od1_first": 0.12, "dout_od01_first": 0.12,
    "i_static_ua": 53.0, "e_dec_fj": 1990.0,
}


GOOD_REV = {
    "td_od50_rev_ns": 0.45, "td_od1_rev_ns": 1.1, "td_od01_rev_ns": 1.5,
    "tau_rev_ps": 170.0, "dtd_od50_rev_ps": 9.0, "dtd_od1_rev_ps": 10.0,
    "dtd_od01_rev_ps": 40.0, "dtau_rev_ps": 7.0,
    "dout_od50_rev_first": 0.96, "dout_od1_rev_first": 0.88, "dout_od01_rev_first": 0.88,
    "dout_od50_rev_end": 0.04, "dout_od1_rev_end": 0.12, "dout_od01_rev_end": 0.12,
}


def _response(process_scale=1.0, reverse=None, **override):
    """A synthetic klt-sim response over the 45-point grid. td_od50_ns moves
    with process and temperature (like the real circuit) unless
    process_scale is 0."""
    corners = []
    for proc, k in (("tt", 0.0), ("ss", 1.0), ("ff", -1.0), ("sf", 0.3), ("fs", -0.3)):
        for t, kt in ((-40, -0.2), (27, 0.0), (125, 0.3)):
            for v in (1.62, 1.8, 1.98):
                vals = dict(GOOD)
                vals.update(GOOD_REV if reverse is None else reverse)
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

    def test_negative_control_runaway_spread_fails_ceiling(self):
        # Issue #235's failure scenario: a max_spread_pct_by_axis ceiling
        # used to be silently ignored here (the ladder's local copy graded
        # floors only). Through the shared evaluator it must fail a
        # response whose temperature-axis spread runs away.
        m = json.loads(json.dumps(self.m))
        m["checks"]["td_od50_ns"]["max_spread_pct_by_axis"] = {"temperature": 40.0}
        fails = ladder.grade(_response(), m)
        self.assertTrue(
            any("td_od50_ns: temperature-axis spread" in f and "above ceiling" in f
                for f in fails), fails)

    def test_grade_with_typo_axis_name_skips_instead_of_crashing(self):
        # Unified with sim/harness/runner.py (issue #235): an axis named in
        # a floor but absent from the spreads is skipped by the shared
        # evaluator's guard, not a KeyError from the ladder's local copy.
        m = json.loads(json.dumps(self.m))
        m["checks"]["td_od50_ns"]["min_spread_pct_by_axis"]["tepmreature"] = 5.0
        self.assertEqual(ladder.grade(_response(), m), [])


class TestManifestLoadValidation(unittest.TestCase):
    """ladder.load_manifest() validates both manifest blocks at load
    (issue #274): a typo'd spread axis, or a spread-carrying check absent
    from its block's `measure`, fails the load loudly instead of being
    silently ungraded at grading time. grade()'s runtime skip semantics
    are untouched (pinned unchanged by
    test_grade_with_typo_axis_name_skips_instead_of_crashing above), and
    grade_reverse() grades per-point min/max only -- so since issue #295
    a correctly spelled spread key in reverse_ladder.checks is rejected at
    load too: report-only blocks accept no ungraded pass/fail line."""

    @staticmethod
    @contextlib.contextmanager
    def _patched_manifest(mutate):
        """A copy of the committed ladder.json with `mutate` applied, and
        ladder.MANIFEST patched to point at it for one load."""
        m = json.loads(ladder.MANIFEST.read_text())
        mutate(m)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ladder_mutated.json"
            path.write_text(json.dumps(m))
            with mock.patch.object(ladder, "MANIFEST", path):
                yield

    def test_load_manifest_passes_validation(self):
        # Issue #274 AC: the committed manifest still loads unchanged,
        # through both validator call sites (top-level + reverse_ladder).
        m = ladder.load_manifest()
        self.assertIn("checks", m)
        self.assertIn("reverse_ladder", m)
        self.assertTrue(m["checks"])
        self.assertTrue(m["reverse_ladder"]["checks"])

    def test_load_manifest_rejects_typo_axis_top_level(self):
        def typo(m):
            floors = m["checks"]["td_od50_ns"]["min_spread_pct_by_axis"]
            floors["tepmreature"] = floors.pop("temperature")

        with self._patched_manifest(typo):
            with self.assertRaises(ValueError) as ctx:
                ladder.load_manifest()
        msg = str(ctx.exception)
        self.assertIn("tepmreature", msg)
        self.assertIn("'td_od50_ns'", msg)
        self.assertIn("[checks]", msg)
        self.assertIn("['process', 'supply', 'temperature']", msg)

    def test_load_manifest_rejects_typo_axis_in_reverse_ladder(self):
        def typo(m):
            m["reverse_ladder"]["checks"]["td_od50_rev_ns"][
                "min_spread_pct_by_axis"] = {"tepmreature": 5.0}

        with self._patched_manifest(typo):
            with self.assertRaises(ValueError) as ctx:
                ladder.load_manifest()
        msg = str(ctx.exception)
        self.assertIn("tepmreature", msg)
        self.assertIn("'td_od50_rev_ns'", msg)
        self.assertIn("[reverse_ladder.checks]", msg)

    def test_load_manifest_rejects_spread_check_absent_from_measure(self):
        def ghost(m):
            m["checks"]["ghost"] = {"min_spread_pct_by_axis": {"process": 1.0}}

        with self._patched_manifest(ghost):
            with self.assertRaises(ValueError) as ctx:
                ladder.load_manifest()
        self.assertIn("'ghost'", str(ctx.exception))

    def test_load_manifest_rejects_correctly_spelled_spread_in_reverse_ladder(self):
        # Issue #295 AC: grade_reverse() grades per-point min/max only
        # (DR-008, report-only), so a correctly spelled spread floor or
        # ceiling on a reverse check would pass the shared validator and
        # then be graded by nothing -- the load must reject it, naming the
        # check and stating the block is report-only.
        for key in ("min_spread_pct_by_axis", "max_spread_pct_by_axis"):
            with self.subTest(key=key):

                def spread(m, key=key):
                    m["reverse_ladder"]["checks"]["td_od50_rev_ns"][key] = {
                        "temperature": 5.0}

                with self._patched_manifest(spread):
                    with self.assertRaises(ValueError) as ctx:
                        ladder.load_manifest()
                msg = str(ctx.exception)
                self.assertIn("'td_od50_rev_ns'", msg)      # check name
                self.assertIn("[reverse_ladder.checks]", msg)  # block
                self.assertIn("report-only", msg)           # why rejected

    def test_load_manifest_top_level_spread_keys_still_load(self):
        # Issue #295 AC: the rejection is per-block -- the same spread key
        # on a top-level check (which grade() does grade through
        # spread_failures()) still loads unchanged.
        def spread(m):
            m["checks"]["tau_ps"]["min_spread_pct_by_axis"] = {
                "temperature": 5.0}

        with self._patched_manifest(spread):
            m = ladder.load_manifest()
        self.assertEqual(
            m["checks"]["tau_ps"]["min_spread_pct_by_axis"],
            {"temperature": 5.0})

    def test_load_manifest_accepts_manifest_without_reverse_ladder(self):
        def strip(m):
            del m["reverse_ladder"]

        with self._patched_manifest(strip):
            m = ladder.load_manifest()
        self.assertNotIn("reverse_ladder", m)


class ReverseLadder(unittest.TestCase):
    def setUp(self):
        self.m = ladder.load_manifest()

    def test_reverse_names_exact_and_nine_cards(self):
        rl = self.m["reverse_ladder"]
        self.assertEqual(set(rl["measure"]), REVERSE_NAMES)
        self.assertTrue(set(rl["checks"]) <= REVERSE_NAMES)
        self.assertEqual(len(rl["analyses"]), 9)
        for c in rl["analyses"][:3]:
            self.assertIn("fall=1 td=35n", c)
        self.assertFalse(REVERSE_NAMES & set(self.m["measure"]))

    def test_forward_fields_and_netlist_unchanged(self):
        sub = {k: self.m[k] for k in ("analyses", "measure", "checks")}
        self.assertEqual(hashlib.sha256(json.dumps(sub, sort_keys=True).encode()).hexdigest(),
                         FORWARD_MANIFEST_SHA)
        fwd = ladder.build_netlist(dut_text="*\n", reverse=False)
        self.assertEqual(hashlib.sha256(fwd.encode()).hexdigest(), FORWARD_NETLIST_SHA)
        full = ladder.build_netlist(dut_text="*\n")
        self.assertTrue(full.startswith(fwd))  # reverse is append-only

    def test_reverse_netlist_mirrors_rungs(self):
        n = ladder.build_reverse_block()
        for r in "abc":
            self.assertIn(f"Xr{r} ", n)
        self.assertIn("pwl(0 0.05 25n 0.05 26n -0.05)", n)

    def test_suppress_flip_never_flips(self):
        n = ladder.build_reverse_block(suppress_flip=True)
        self.assertIn("pwl(0 0.05 25n 0.05 26n 0.05)", n)
        self.assertNotIn("-0.05", n)

    def test_requests_carry_reverse_measures_without_limits(self):
        names = {x["name"]: x for x in ladder.build_requests()["process"]["measurements"]}
        self.assertTrue(REVERSE_NAMES <= set(names))
        for n in REVERSE_NAMES:
            self.assertNotIn("limits", names[n])
        fwd_only = {x["name"] for x in ladder.build_requests(reverse=False)["process"]["measurements"]}
        self.assertFalse(REVERSE_NAMES & fwd_only)

    def test_positive_control_passes(self):
        self.assertEqual(ladder.grade_reverse(_response(), self.m), [])

    def test_negative_control_no_flip_fails(self):
        bad = dict(GOOD_REV, td_od50_rev_ns=None, dout_od50_rev_end=0.96, dout_od1_rev_end=0.88)
        fails = ladder.grade_reverse(_response(reverse=bad), self.m)
        self.assertTrue(any("td_od50_rev_ns: no value" in f for f in fails))
        self.assertTrue(any("dout_od50_rev_end" in f for f in fails))

    def test_reverse_failures_never_gate_forward_grade(self):
        bad = dict(GOOD_REV, dout_od1_rev_end=0.96)
        self.assertEqual(ladder.grade(_response(reverse=bad), self.m), [])


class GradeCLIEmptyCorners(unittest.TestCase):
    """Issue #384: a zero-corner response crashed the forward grade
    (IndexError on corners[0]) and passed the reverse grade vacuously
    (`PASS: 0 reverse check failure(s)`). The CLI rejects it as an input
    error in every flag combination -- --expect-fail included: the negative
    control needs an observed measurement failure to succeed."""

    def _grade(self, tmp, responses, flags):
        paths = []
        for name, obj in responses:
            p = Path(tmp) / name
            p.write_text(json.dumps(obj))
            paths.append(str(p))
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = ladder.main(["grade", *paths, *flags])
        return rc, out.getvalue(), err.getvalue()

    def test_empty_corners_is_an_input_error_in_all_four_modes(self):
        for flags in ([], ["--reverse"], ["--expect-fail"],
                      ["--reverse", "--expect-fail"]):
            with self.subTest(flags=flags):
                with tempfile.TemporaryDirectory() as tmp:
                    rc, out, err = self._grade(tmp, [("empty.json", {"corners": []})], flags)
                self.assertEqual(rc, 2)
                self.assertIn("no corners to grade", err)
                self.assertNotIn("PASS", out)

    def test_empty_response_alongside_a_good_one_still_grades(self):
        # The guard sits after the merge, so one empty response does not
        # reject a set whose other members supply usable corners.
        with tempfile.TemporaryDirectory() as tmp:
            rc, out, err = self._grade(
                tmp, [("empty.json", {"corners": []}), ("good.json", _response())], [])
        self.assertEqual(rc, 0)
        self.assertIn("PASS", out)


if __name__ == "__main__":
    unittest.main()
