"""Unit tests for sim/comparator-decision/run.py's `kickback` deck-builder
and result-grading logic (issue #26), the `_noise_deck` sub-model shape
(re-derived onto the DR-004 static preamp by issue #34), and the
`_reset_device_block` gnd-tied counterfactual (re-derived onto the
steering pair by issue #34).

Construction/import-level coverage only -- no ngspice/PDK invocation, same
level `regen`/`offset`/`reset` are exercised at today (none of those three
has a dedicated unit test yet; this is the first, added per issue #26's
own Test Plan, which asked for at least this level of coverage on the new
deck-builder function).

`sim/comparator-decision/run.py` lives under a hyphenated directory name,
so it cannot be imported with a normal `import` statement -- it is loaded
here via `importlib.util` from its file path instead, the same file
`run.py` itself resolves paths from (`Path(__file__).resolve()`), so the
loaded module's own `sys.path.insert(0, SIM_DIR)` for `from harness import
...` still works unchanged.
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parent.parent
COMPARATOR_DECISION_RUN = SIM_DIR / "comparator-decision" / "run.py"


def _load_comparator_decision_run():
    spec = importlib.util.spec_from_file_location(
        "comparator_decision_run", COMPARATOR_DECISION_RUN,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


cd_run = _load_comparator_decision_run()


class FakePdkInfo:
    """Just enough of pdk.PdkInfo's shape for deck-text construction --
    `_kickback_deck()` only ever reads `.ngspice_lib`."""

    def __init__(self):
        self.ngspice_lib = "sky130.lib.spice"
        self.variant = "sky130A"


class TestKickbackDeck(unittest.TestCase):
    """`_kickback_deck()` -- the `loaded` vs. `ideal` variant shape."""

    def setUp(self):
        self.info = FakePdkInfo()

    def test_loaded_variant_drives_through_series_resistor(self):
        deck = cd_run._kickback_deck(self.info, "tt", 27.0, "loaded", "kb_loaded")
        self.assertIn(f"Rsp VSRC_P VINP {cd_run.KICKBACK_RS_OHM}", deck)
        self.assertIn(f"Rsn VSRC_N VINN {cd_run.KICKBACK_RS_OHM}", deck)
        self.assertIn("Vsrcp VSRC_P 0 dc", deck)
        self.assertIn("Vsrcn VSRC_N 0 dc", deck)
        # `loaded` must NOT also tie VINP/VINN directly to an ideal source --
        # that would defeat the whole point of the series resistor.
        self.assertNotIn("Vinp VINP 0 dc", deck)
        self.assertNotIn("Vinn VINN 0 dc", deck)

    def test_ideal_variant_drives_directly_with_no_series_resistor(self):
        deck = cd_run._kickback_deck(self.info, "tt", 27.0, "ideal", "kb_ideal")
        self.assertIn("Vinp VINP 0 dc", deck)
        self.assertIn("Vinn VINN 0 dc", deck)
        # `ideal` is the zero-source-impedance control -- no resistor, no
        # separate VSRC nodes at all.
        self.assertNotIn("Rsp", deck)
        self.assertNotIn("Rsn", deck)
        self.assertNotIn("VSRC_P", deck)
        self.assertNotIn("VSRC_N", deck)

    def test_unknown_variant_raises(self):
        with self.assertRaises(ValueError):
            cd_run._kickback_deck(self.info, "tt", 27.0, "bogus", "kb_bogus")

    def test_deck_includes_dut_lines_verbatim(self):
        deck = cd_run._kickback_deck(self.info, "tt", 27.0, "loaded", "kb_loaded")
        first_dut_line = cd_run._dut_lines().strip().splitlines()[0]
        self.assertIn(first_dut_line, deck)

    def test_both_variants_run_the_same_reset_evaluate_stimulus_shape(self):
        loaded = cd_run._kickback_deck(self.info, "tt", 27.0, "loaded", "kb_loaded")
        ideal = cd_run._kickback_deck(self.info, "tt", 27.0, "ideal", "kb_ideal")
        for deck in (loaded, ideal):
            self.assertIn(f"{cd_run.RESET_NS}n", deck)
            self.assertIn("PULSE(0", deck)
            self.assertIn(".control", deck)
            self.assertIn("tran ", deck)


class TestKickbackPointOk(unittest.TestCase):
    """KickbackPoint.ok's sensitivity contract: `loaded` must show a
    disturbance clearly above the numerical floor, `ideal` must collapse to
    (numerically) zero -- neither variant's check can trivially always
    pass, the same "must be able to fail" shape ResetPoint.ok already
    establishes for the `reset` sub-command's own positive control."""

    def _point(self, variant: str, peak_p: float, peak_n: float = 0.0):
        return cd_run.KickbackPoint(
            corner="tt", temp_c=27.0, variant=variant,
            quiescent_vinp_v=0.9, quiescent_vinn_v=0.9,
            peak_dev_vinp_v=peak_p, peak_dev_vinn_v=peak_n,
            log_text="",
        )

    def test_loaded_with_negligible_disturbance_is_not_ok(self):
        # A `loaded` run reading back near-zero disturbance would mean the
        # deck is not actually sensitive to the effect it screens for.
        point = self._point("loaded", peak_p=1e-6)
        self.assertFalse(point.ok)

    def test_loaded_with_clear_disturbance_is_ok(self):
        point = self._point("loaded", peak_p=0.05)  # 50 mV
        self.assertTrue(point.ok)

    def test_ideal_with_zero_disturbance_is_ok(self):
        point = self._point("ideal", peak_p=0.0)
        self.assertTrue(point.ok)

    def test_ideal_with_nonzero_disturbance_is_not_ok(self):
        # An `ideal` (zero-source-impedance) run must collapse to zero by
        # construction; anything else means the deck leaked the effect it
        # is supposed to isolate away from.
        point = self._point("ideal", peak_p=0.01)  # 10 mV
        self.assertFalse(point.ok)

    def test_peak_dev_v_is_worst_of_the_two_nodes(self):
        point = self._point("loaded", peak_p=0.05, peak_n=0.12)
        self.assertAlmostEqual(point.peak_dev_v, 0.12)


class TestNoiseDeckPreampSubModel(unittest.TestCase):
    """`_noise_deck()` -- the DR-004 static-preamp sub-model (issue #34).

    Since DR-004 the committed DUT is a continuously-biased preamplifier
    ahead of the clocked latch, and the loop-broken noise sub-model is that
    REAL static stage re-emitted verbatim: preamp tail, input pair, both
    poly loads, and both OUT1 absorber caps. Everything past the preamp
    outputs (steering pair, latch tail, cross-coupled PMOS, reset PMOS,
    and the DR-003 shaper) is the loop break and must be absent; and
    because the sub-model now contains no clocked device at all, the
    pre-DR-004 Vclkfix/Vclkfixt steady-bias lines must be gone too.
    """

    def setUp(self):
        self.info = FakePdkInfo()

    def test_noise_deck_re_emits_preamp_stage_verbatim(self):
        deck = cd_run._noise_deck(self.info, "tt", 27.0)
        deck_joined = " ".join(deck.split())
        for name in ("XM_PTAIL", "XM_PINN", "XM_PINP",
                     "XR_LP", "XR_LN", "XM_C1P", "XM_C1N"):
            joined = " ".join(cd_run._dut_device_line(name).split())
            self.assertIn(joined, deck_joined,
                          f"{name} should be re-emitted verbatim")

    def test_noise_deck_omits_everything_past_the_preamp_outputs(self):
        # The loop break: no latch, no steering, no reset, no shaper.
        deck = cd_run._noise_deck(self.info, "tt", 27.0)
        for absent in ("XM_STN_P", "XM_STN_N", "XM_TAIL2",
                       "XM_LATP_P", "XM_LATP_N", "XM_RST_P", "XM_RST_N",
                       "XR_CLKS", "XM_CLKCAP"):
            self.assertNotIn(absent, deck,
                             f"{absent} is past the loop break and must be omitted")

    def test_noise_deck_needs_no_steady_clock_bias(self):
        # The pre-DR-004 sub-model had to bias CLK/CLKT at VDD to hold the
        # dynamic tail on; the static preamp has no clocked device, so those
        # lines are gone.
        deck = cd_run._noise_deck(self.info, "tt", 27.0)
        self.assertNotIn("Vclkfix", deck)

    def test_noise_deck_measures_at_the_preamp_outputs(self):
        deck = cd_run._noise_deck(self.info, "tt", 27.0)
        self.assertIn("noise v(outp1,outn1) Vinp", deck)
        self.assertIn("print v(TAILP) v(OUTP1) v(OUTN1)", deck)


class TestResetDeviceBlockGndTied(unittest.TestCase):
    """`_reset_device_block()` -- the DR-004 gnd-tied counterfactual
    (issue #34): the steering pair's SOURCE terminals move from the floated
    internal node TAIL2 to GND, nothing else changes."""

    def test_as_drawn_is_the_fragment_verbatim(self):
        self.assertEqual(cd_run._reset_device_block("as-drawn"),
                         cd_run._dut_lines())

    def test_gnd_tied_moves_only_the_steering_sources(self):
        block = cd_run._reset_device_block("gnd-tied")
        lines = [" ".join(l.split()) for l in block.splitlines() if l.strip()]
        by_name = {l.split()[0]: l for l in lines}
        # The steering pair: same drains and gates, sources (and bulks) at GND.
        self.assertTrue(by_name["XM_STN_P"].split()[1:5] ==
                        ["OUTP", "OUTP1", "GND", "GND"])
        self.assertTrue(by_name["XM_STN_N"].split()[1:5] ==
                        ["OUTN", "OUTN1", "GND", "GND"])
        # Every other device is re-emitted verbatim from the fragment.
        for name, line in by_name.items():
            if name in ("XM_STN_P", "XM_STN_N"):
                continue
            self.assertEqual(line, " ".join(cd_run._dut_device_line(name).split()))
        # Same instance count as the committed fragment -- a single-edit
        # counterfactual, not a rebuild.
        self.assertEqual(len(by_name), len(cd_run._dut_devices()))

    def test_unknown_variant_raises(self):
        with self.assertRaises(ValueError):
            cd_run._reset_device_block("bogus")


class TestLatchNoiseDeck(unittest.TestCase):
    """`_latch_noise_deck()` (issue #41) -- the steering+tail AC sub-model
    whose gate-referred `inoise_total` supplies the noise-tran gate
    injection amplitude. Same shape discipline as `_noise_deck`: latch
    front-end devices verbatim (gates on driven nodes), everything else
    absent, noiseless loads only."""

    def setUp(self):
        self.info = FakePdkInfo()

    def test_re_emits_steering_pair_and_tail_verbatim(self):
        deck = cd_run._latch_noise_deck(self.info, "tt", 27.0, 1.18, 10.0)
        deck_joined = " ".join(deck.split())
        for name, nodes in (
            ("XM_STN_P", ["OUTP", "GST_P", "TAIL2", "GND"]),
            ("XM_STN_N", ["OUTN", "GST_N", "TAIL2", "GND"]),
        ):
            joined = " ".join(cd_run._dut_device_line(name, nodes=nodes).split())
            self.assertIn(joined, deck_joined, f"{name} should be re-emitted verbatim")
        self.assertIn(" ".join(cd_run._dut_device_line("XM_TAIL2").split()), deck_joined)

    def test_omits_everything_upstream_and_past_the_front_end(self):
        deck = cd_run._latch_noise_deck(self.info, "tt", 27.0, 1.18, 10.0)
        for absent in ("XM_PINN", "XM_PINP", "XM_PTAIL", "XR_LP", "XR_LN",
                       "XM_C1P", "XM_C1N", "XM_LATP_P", "XM_LATP_N",
                       "XM_RST_P", "XM_RST_N", "XR_CLKS", "XM_CLKCAP"):
            self.assertNotIn(absent, deck, f"{absent} must be omitted from the steering sub-model")

    def test_loads_are_noiseless(self):
        # Only inductors and capacitors load the drains -- a resistor would
        # contribute its own noise to onoise and contaminate the
        # gate-referred referral.
        deck = cd_run._latch_noise_deck(self.info, "tt", 27.0, 1.18, 10.0)
        self.assertIn("Lp OUTP VDD", deck)
        self.assertIn("Ln OUTN VDD", deck)
        self.assertIn("Cp OUTP 0", deck)
        self.assertIn("Cn OUTN 0", deck)
        self.assertNotIn("R", "\n".join(
            l for l in deck.splitlines() if l and not l.startswith(("*", "."))))

    def test_gate_bias_and_noise_analysis_shape(self):
        deck = cd_run._latch_noise_deck(self.info, "tt", 27.0, 1.18, 10.0)
        self.assertIn("vcmo = 1.180000", deck)  # gate CM bias param
        self.assertIn("dc {vcmo} AC 1", deck)   # input reference source
        self.assertIn(f"noise v(OUTP,OUTN) Vstp dec 20 "
                      f"{cd_run.NOISE_FSTART_HZ:g} {cd_run.NOISE_FSTOP_HZ:g}", deck)


class TestNoiseTranDecks(unittest.TestCase):
    """The `noise-tran` injection decks (issue #41): the FULL committed
    fragment (unlike both AC sub-models), with the steering pair's gates
    moved onto injected nodes and per-side TRNOISE sources at the inputs
    and in series with the gates."""

    def setUp(self):
        self.info = FakePdkInfo()

    def _pickoff(self, **kw):
        defaults = dict(corner="tt", temp_c=27.0, vindiff_mv=0.0, seed=7,
                        na_input=1e-3, na_gate=2e-3, log_name="nt")
        defaults.update(kw)
        return cd_run._noise_tran_pickoff_deck(self.info, **defaults)

    def test_includes_the_full_fragment_verbatim(self):
        deck = self._pickoff()
        # Fold SPICE continuation markers ("+") the same way _dut_devices
        # folds them, so a multi-line raw emit compares equal to the
        # helper's single-line re-emission.
        joined = " ".join(deck.split()).replace(" + ", " ")
        for name in cd_run._dut_devices():
            if name in ("XM_STN_P", "XM_STN_N"):
                continue
            self.assertIn(" ".join(cd_run._dut_device_line(name).split()),
                          joined,
                          f"{name} should appear verbatim")

    def test_steering_gates_moved_to_injected_nodes(self):
        deck = self._pickoff()
        deck_joined = " ".join(deck.split())
        self.assertIn(" ".join(cd_run._dut_device_line(
            "XM_STN_P", nodes=["OUTP", "GST_P", "TAIL2", "GND"]).split()), deck_joined)
        self.assertIn(" ".join(cd_run._dut_device_line(
            "XM_STN_N", nodes=["OUTN", "GST_N", "TAIL2", "GND"]).split()), deck_joined)

    def test_four_trnoise_sources_present_with_seed(self):
        deck = self._pickoff()
        self.assertIn(".option rndseed=7", deck)
        self.assertEqual(deck.count("TRNOISE("), 4)
        self.assertIn(f"Vinp VINP 0 dc {cd_run.VCM}", deck)
        self.assertIn(f"Vstp GST_P OUTP1 dc 0 TRNOISE(", deck)
        self.assertIn(f"Vstn GST_N OUTN1 dc 0 TRNOISE(", deck)

    def test_decision_deck_uses_the_longer_window(self):
        pickoff = self._pickoff()
        decision = cd_run._noise_tran_decision_deck(
            self.info, "tt", 27.0, 0.5, 9, 1e-3, 2e-3, "ntd")
        self.assertIn(f"tran 0.002n {cd_run.PICKOFF_TSTOP_NS}n", pickoff)
        self.assertIn(
            f"tran 0.01n {cd_run.RESET_NS + cd_run.RESET_TR_NS + cd_run.NOISE_TRAN_EVALUATE_NS}n",
            decision)

    def test_ts_parameterizes_the_update_interval(self):
        deck = self._pickoff(ts=4.1e-10)
        self.assertIn("4.1e-10", deck)


class TestPairSigmaEstimator(unittest.TestCase):
    """`pair_sigma_mv()` / `_probit()` (issue #41): the pair-symmetric
    decision-statistic estimator. Checks against hand-derived Gaussian
    fractions, offset cancellation, and the degenerate-pair guard."""

    def test_recovers_sigma_from_exact_gaussian_fractions(self):
        # Phi(1) ~= 0.8413: at v = sigma exactly, p+ - p- ~= 0.683.
        # All quantities in mV (sigma = 0.6 mV).
        import math
        sigma = 0.6
        v = 1.0 * sigma
        p_plus = 0.5 * (1 + math.erf(1 / math.sqrt(2)))
        p_minus = 0.5 * (1 - math.erf(1 / math.sqrt(2)))
        m = 100_000
        est = cd_run.pair_sigma_mv(v, round(p_plus * m), m, round(p_minus * m), m)
        self.assertAlmostEqual(est, 0.6, places=3)

    def test_offset_cancels_to_first_order(self):
        # The same offset shift on both signs moves p+ and p- together and
        # their difference is unchanged to first order -- the reason the
        # estimator is pair-symmetric. mV units throughout.
        import math
        sigma = 0.6
        v = sigma
        mu = 0.05  # mV offset
        p_plus = 0.5 * (1 + math.erf((v - mu) / sigma / math.sqrt(2)))
        p_minus = 0.5 * (1 + math.erf((-v - mu) / sigma / math.sqrt(2)))
        m = 100_000
        est = cd_run.pair_sigma_mv(v, round(p_plus * m), m, round(p_minus * m), m)
        self.assertAlmostEqual(est, 0.6, places=2)

    def test_degenerate_pair_is_nan(self):
        est = cd_run.pair_sigma_mv(0.5, 64, 64, 0, 64)
        self.assertNotEqual(est, est)  # NaN

    def test_probit_inverts_norm_cdf(self):
        for x in (-2.0, -0.5, 0.0, 0.37, 1.3, 2.7):
            self.assertAlmostEqual(cd_run._norm_cdf(cd_run._probit(cd_run._norm_cdf(x))), cd_run._norm_cdf(x), places=9)


class TestJobsPlumbing(unittest.TestCase):
    """The issue #41 CLI surface: `--jobs` and the `noise-tran` mode exist
    and route; `--jobs 1` preserves the sequential default."""

    def test_jobs_flag_parses(self):
        # Parse-level only: a real offset run would invoke the PDK; the
        # harness's own selftest covers the real path. argparse rejecting
        # the flag exits 2.
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            with self.assertRaises(SystemExit) as cm:
                cd_run.main(["offset", "--jobs", "4", "--help"])
        self.assertEqual(cm.exception.code, 0)
        self.assertIn("--jobs", buf.getvalue())

    def test_noise_tran_mode_in_choices(self):
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            with self.assertRaises(SystemExit) as cm:
                cd_run.main(["noise-tran", "--help"])
        self.assertEqual(cm.exception.code, 0)
        self.assertIn("noise-tran", buf.getvalue())
        self.assertIn("--jobs", buf.getvalue())

    def test_noise_tran_mode_in_choices(self):
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            with self.assertRaises(SystemExit) as cm:
                cd_run.main(["noise-tran", "--help"])
        self.assertEqual(cm.exception.code, 0)
        self.assertIn("noise-tran", buf.getvalue())
        self.assertIn("--jobs", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
