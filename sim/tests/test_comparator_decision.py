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

import contextlib
import importlib.util
import io
import math
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

    def test_all_unresolved_pair_is_nan(self):
        # p+ == p- (e.g. every run below the corner's resolvable-overdrive
        # floor) makes arg exactly 0.5 and probit 0 -- no sigma information.
        est = cd_run.pair_sigma_mv(0.5, 0, 64, 0, 64)
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
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            with self.assertRaises(SystemExit) as cm:
                cd_run.main(["offset", "--jobs", "4", "--help"])
        self.assertEqual(cm.exception.code, 0)
        self.assertIn("--jobs", buf.getvalue())

    def test_noise_tran_mode_in_choices(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            with self.assertRaises(SystemExit) as cm:
                cd_run.main(["noise-tran", "--help"])
        self.assertEqual(cm.exception.code, 0)
        self.assertIn("noise-tran", buf.getvalue())
        self.assertIn("--jobs", buf.getvalue())


class TestDutProvenance(unittest.TestCase):
    """`--dut schematic|extracted` -- the post-layout swap (issue #57).

    The whole value of the post-layout comparison is that the ONLY thing
    differing between a schematic-level record and its post-layout
    counterpart is the DUT. These tests pin that: the schematic deck text is
    unchanged by the switch existing, and the extracted deck really does
    carry the extracted netlist (and its parasitics).
    """

    def setUp(self):
        self.info = FakePdkInfo()
        self.addCleanup(cd_run.set_dut_provenance, "schematic")

    def test_default_provenance_is_schematic(self):
        self.assertEqual(cd_run.dut_provenance(), "schematic")
        self.assertEqual(cd_run._dut_fragment(), cd_run.DUT_FRAGMENT)

    def test_schematic_decks_are_unchanged_by_the_switch(self):
        before = cd_run._regen_deck(self.info, "tt", 27.0, 50.0, "x")
        cd_run.set_dut_provenance("extracted")
        cd_run.set_dut_provenance("schematic")
        self.assertEqual(before, cd_run._regen_deck(self.info, "tt", 27.0, 50.0, "x"))
        self.assertIn(cd_run.DUT_FRAGMENT.read_text(), before)

    def test_extracted_decks_inline_the_extracted_fragment(self):
        cd_run.set_dut_provenance("extracted")
        for deck in (
            cd_run._regen_deck(self.info, "tt", 27.0, 50.0, "x"),
            cd_run._pickoff_deck(self.info, "tt_mm", 27.0, 0.0, "x", rndseed=1),
            cd_run._kickback_deck(self.info, "tt", 27.0, "loaded", "x"),
        ):
            self.assertIn(cd_run.PEX_FRAGMENT.read_text(), deck)
            self.assertNotIn(cd_run.DUT_FRAGMENT.read_text(), deck)
            # Parasitics actually present, not merely a renamed schematic.
            self.assertIn("vsubs", deck)

    def test_extracted_noise_deck_uses_the_committed_preamp_partition(self):
        cd_run.set_dut_provenance("extracted")
        deck = cd_run._noise_deck(self.info, "tt", 27.0)
        self.assertIn(cd_run.PEX_PREAMP_FRAGMENT.read_text(), deck)
        # Same loop break, same probe as the schematic sub-model.
        self.assertIn("noise v(outp1,outn1) Vinp", deck)
        for absent in ("XM_STN_P", "XM_STN_N", "XM_TAIL2",
                       "XM_LATP_P", "XM_LATP_N", "XM_RST_P", "XM_RST_N",
                       "XR_CLKS", "XM_CLKCAP"):
            self.assertNotIn(absent, deck)

    def test_unknown_provenance_raises(self):
        with self.assertRaises(ValueError):
            cd_run.set_dut_provenance("post-layout")

    def test_no_sub_command_refuses_the_extracted_dut_any_more(self):
        # Issue #65 gave `reset` and `noise-tran` a post-layout deck form,
        # so the `_require_schematic_dut` refusal has no callers left. If a
        # future sub-command needs one back, it must come back with the
        # refusal's own test -- not by silently falling back.
        self.assertFalse(hasattr(cd_run, "_require_schematic_dut"))


class TestPostLayoutTerminalMoves(unittest.TestCase):
    """The three rules issue #57 deferred and issue #65 decided, as code:
    which device a schematic name means when the layout split it (RULE 1),
    what happens to a moved terminal's parasitic star leg (RULE 2), and
    which side of that leg a series source is inserted on (RULE 3).

    See the POST-LAYOUT DECK SURGERY note in `run.py` for the rules
    themselves; these tests exist so the rules cannot drift away from the
    decks silently.
    """

    def setUp(self):
        self.info = FakePdkInfo()
        self.addCleanup(cd_run.set_dut_provenance, "schematic")
        cd_run.set_dut_provenance("extracted")
        self.fragment = cd_run.PEX_FRAGMENT.read_text()

    @staticmethod
    def _changed(before: str, after: str) -> list[tuple[str, str]]:
        b, a = before.splitlines(), after.splitlines()
        assert len(b) == len(a), "a terminal move must not add or drop lines"
        return [(x, y) for x, y in zip(b, a) if x != y]

    # --- RULE 1: a schematic name means every drawn instance of it --------

    def test_instance_names_resolves_an_unsplit_device_to_itself(self):
        devices = cd_run._parse_devices(self.fragment)
        self.assertEqual(cd_run._instance_names(devices, "XM_STN_P"), ["XM_STN_P"])

    def test_instance_names_resolves_a_split_device_to_all_its_fingers(self):
        devices = cd_run._parse_devices(self.fragment)
        self.assertEqual(cd_run._instance_names(devices, "XM_PINP"),
                         ["XM_PINP__a", "XM_PINP__b"])

    def test_instance_names_refuses_a_name_that_resolves_to_nothing(self):
        devices = cd_run._parse_devices(self.fragment)
        with self.assertRaises(KeyError):
            cd_run._instance_names(devices, "XM_NOT_A_DEVICE")

    def test_the_moved_devices_are_unsplit_on_this_layout(self):
        # The convention ("all fingers move together") is implemented, but
        # both records must be able to say whether it was EXERCISED. On the
        # committed layout it is not: the steering pair is drawn unsplit.
        devices = cd_run._parse_devices(self.fragment)
        for base, _node, _drain, _gate in cd_run.STEERING_GATE_INJECTION:
            with self.subTest(base=base):
                self.assertEqual(cd_run._instance_names(devices, base), [base])

    # --- RULE 2: the star leg travels with the terminal -------------------

    def test_gnd_tie_repoints_exactly_the_two_source_star_legs(self):
        moved = cd_run._reset_device_block("gnd-tied")
        changed = self._changed(self.fragment, moved)
        self.assertEqual(len(changed), 2, changed)
        for before, after in changed:
            b, a = before.split(), after.split()
            self.assertTrue(b[0].startswith("R_TAIL2__t"), before)
            self.assertEqual(b[1], a[1])       # same star-leg node
            self.assertEqual(b[2], "TAIL2")    # old hub
            self.assertEqual(a[2], "GND")      # new net
            self.assertEqual(b[3], a[3])       # SAME extracted resistance
            self.assertEqual(a[0], f"R_{a[1]}_GND")

    def test_gnd_tie_leaves_every_device_line_untouched(self):
        moved = cd_run._reset_device_block("gnd-tied")
        before = cd_run._parse_devices(self.fragment)
        after = cd_run._parse_devices(moved)
        devices = [n for n, t in before.items()
                   if any(x.startswith("sky130_fd_pr__") for x in t)]
        self.assertEqual(len(devices), 18)
        for name in devices:
            with self.subTest(name=name):
                self.assertEqual(before[name], after[name])

    def test_gnd_tie_strands_no_star_leg_and_deletes_no_resistance(self):
        moved = cd_run._reset_device_block("gnd-tied")

        def leg_uses(text):
            counts = {}
            for tokens in cd_run._parse_devices(text).values():
                for token in tokens:
                    if "__t" in token and "=" not in token:
                        counts[token] = counts.get(token, 0) + 1
            return counts

        self.assertEqual(leg_uses(self.fragment), leg_uses(moved))
        for node, count in leg_uses(moved).items():
            with self.subTest(node=node):
                self.assertGreaterEqual(count, 2)

        def resistances(text):
            return sorted(
                t[2] for n, t in cd_run._parse_devices(text).items()
                if n.startswith("R_") and len(t) == 3
            )
        self.assertEqual(resistances(self.fragment), resistances(moved))

    def test_a_bare_net_terminal_is_refused_not_silently_accepted(self):
        # The schematic fragment has no star legs at all; asking for a
        # post-layout terminal move on it must fail loudly rather than
        # produce something that looks like a post-layout deck.
        with self.assertRaises(RuntimeError):
            cd_run._retie_star_legs(
                cd_run.DUT_FRAGMENT.read_text(), cd_run.RESET_GND_TIE_MOVES)

    def test_a_shared_star_leg_node_is_refused(self):
        # RULE 3's premise is that a leg node carries exactly one device
        # terminal and one star resistor. Break it and the deck builder must
        # stop, because series commutation (and hence "which side of the leg
        # does not matter") would no longer hold.
        tampered = self.fragment.replace(
            "C_TAIL2_GND TAIL2 GND", "C_TAIL2_GND TAIL2__t2 GND", 1)
        self.assertNotEqual(tampered, self.fragment)
        with self.assertRaises(RuntimeError):
            cd_run._retie_star_legs(tampered, cd_run.RESET_GND_TIE_MOVES)

    # --- RULE 3: the series source goes on the hub side of the leg --------

    def test_injection_repoints_exactly_the_two_gate_star_legs(self):
        block = "\n".join(cd_run._noise_tran_dut_block()) + "\n"
        changed = self._changed(self.fragment, block)
        self.assertEqual(len(changed), 2, changed)
        expected = {("R_OUTP1__t4_OUTP1", "OUTP1", "GST_P"),
                    ("R_OUTN1__t4_OUTN1", "OUTN1", "GST_N")}
        got = set()
        for before, after in changed:
            b, a = before.split(), after.split()
            got.add((b[0], b[2], a[2]))
            self.assertEqual(b[1], a[1])
            self.assertEqual(b[3], a[3])
        self.assertEqual(got, expected)

    def test_injection_sources_name_the_gate_net_in_both_provenances(self):
        # The consequence of inserting on the HUB side: the two source lines
        # are textually the same for schematic and extracted decks.
        cd_run.set_dut_provenance("schematic")
        schematic = cd_run._noise_tran_pickoff_deck(
            self.info, "tt", 27.0, 0.0, 1, 1e-3, 1e-3, "x")
        cd_run.set_dut_provenance("extracted")
        extracted = cd_run._noise_tran_pickoff_deck(
            self.info, "tt", 27.0, 0.0, 1, 1e-3, 1e-3, "x")
        for line in ("Vstp GST_P OUTP1 dc 0 TRNOISE",
                     "Vstn GST_N OUTN1 dc 0 TRNOISE"):
            self.assertIn(line, schematic)
            self.assertIn(line, extracted)

    def test_extracted_latch_sub_model_is_the_committed_latch_partition(self):
        deck = cd_run._latch_noise_deck(self.info, "tt", 27.0, 1.18, 10.0)
        partition = cd_run.PEX_LATCH_FRAGMENT.read_text()
        self.assertEqual(
            sorted(n for n, t in cd_run._parse_devices(partition).items()
                   if any(x.startswith("sky130_fd_pr__") for x in t)),
            ["XM_STN_N", "XM_STN_P", "XM_TAIL2"],
        )
        # Same three devices, same drive point, and the partition's own
        # parasitics really are in the deck.
        for name in ("XM_STN_P", "XM_STN_N", "XM_TAIL2"):
            self.assertIn(name, deck)
        for absent in ("XM_PINP", "XM_PINN", "XM_LATP_P", "XM_RST_P", "XR_LP"):
            self.assertNotIn(absent, deck)
        self.assertIn("R_TAIL2__t0_TAIL2", deck)
        # No terminal move here: the partition already ENDS at the gate net,
        # so the ideal drive attaches to the hub and the gates keep their own
        # extracted leg resistance between the drive and the channel.
        self.assertIn("R_OUTP1__t4_OUTP1", deck)
        self.assertIn("R_OUTN1__t4_OUTN1", deck)
        self.assertIn("Vstp OUTP1 0 dc", deck)
        self.assertIn("Vstn OUTN1 0 dc", deck)
        self.assertNotIn("GST_P", deck)

    def test_schematic_latch_sub_model_still_drives_the_gst_nodes(self):
        cd_run.set_dut_provenance("schematic")
        deck = cd_run._latch_noise_deck(self.info, "tt", 27.0, 1.18, 10.0)
        self.assertIn("Vstp GST_P 0 dc", deck)
        self.assertIn("Vstn GST_N 0 dc", deck)


class TestDegenerateCrossCheckReason(unittest.TestCase):
    """A degenerate decision cross-check has three physically different
    causes, and a record that names the wrong one is worse than one that
    names none. Issue #65 found this the hard way: the post-layout `tt`/27C
    run resolved every single seed and decided all of them the SAME way,
    while the record asserted -- unconditionally, from a canned string --
    that runs "never resolve within the window or all decide correctly",
    two lines above its own `unresolved = 0` counts.
    """

    @staticmethod
    def _points(plus, minus, unresolved, m=16):
        return [
            {"k": k, "v_mv": v, "m": m, "plus_ones": plus,
             "minus_ones": minus, "unresolved": unresolved}
            for k, v in ((0.75, 0.1129), (1.5, 0.2258))
        ]

    def test_unresolved_runs_are_named_as_the_overdrive_floor(self):
        reason = cd_run.degenerate_cross_check_reason(
            self._points(0, 0, unresolved=32))
        self.assertIn("never separated inside the decision window", reason)
        self.assertIn("resolvable-overdrive floor", reason)

    def test_all_one_way_is_named_as_a_deterministic_term(self):
        # The issue #65 post-layout case: every seed resolves, all negative.
        reason = cd_run.degenerate_cross_check_reason(
            self._points(0, 0, unresolved=0))
        self.assertIn("DETERMINISTIC term", reason)
        self.assertIn("negative", reason)
        self.assertNotIn("never separated", reason)
        self.assertNotIn("decided CORRECTLY", reason)

    def test_all_correct_is_not_confused_with_all_one_way(self):
        reason = cd_run.degenerate_cross_check_reason(
            self._points(16, 0, unresolved=0))
        self.assertIn("decided CORRECTLY at both signs", reason)
        self.assertNotIn("DETERMINISTIC term", reason)

    def _result(self, points, sigma_decision_mv):
        return cd_run.NoiseTranResult(
            corner="tt", temp_c=27.0, preamp=None, latch=None,
            trnoise_factor=0.86, na_input=5.4e-4, na_gate=3.6e-4,
            cal_achieved_input_rms_v=4.66e-4, cal_achieved_gate_rms_v=3.1e-4,
            gain_v_per_v=30.46, gain_cal_points=[],
            pickoff_diffs=[0.0] * 64, sigma_pickoff_mv=0.1506,
            sigma_pickoff_ci95_mv=(0.1294, 0.1678),
            decision_points=points, sigma_decision_mv=sigma_decision_mv,
        )

    def test_the_record_bullet_quotes_the_derived_reason(self):
        points = self._points(0, 0, unresolved=0)
        line = cd_run.two_statistics_line(self._result(points, float("nan")))
        self.assertIn(cd_run.degenerate_cross_check_reason(points), line)
        self.assertIn("NOT MEASURABLE", line)

    def test_a_measurable_cross_check_bullet_states_no_reason(self):
        points = self._points(13, 3, unresolved=0)
        line = cd_run.two_statistics_line(self._result(points, 0.1421))
        self.assertIn("0.1421 mV", line)
        self.assertNotIn("NOT MEASURABLE", line)
        self.assertNotIn("DETERMINISTIC term", line)


class TestPostLayoutDelta(unittest.TestCase):
    """`post_layout_delta_lines()` -- issue #57's "not just the new number
    in isolation" acceptance criterion, as code."""

    def setUp(self):
        self.addCleanup(cd_run.set_dut_provenance, "schematic")

    def test_schematic_runs_emit_no_delta_section(self):
        self.assertEqual(
            cd_run.post_layout_delta_lines("regen", "tt", 27.0, 0.5), [])

    def test_every_baseline_names_a_committed_record(self):
        records = cd_run.EXPERIMENT_DIR / "records"
        for key, base in cd_run.SCHEMATIC_BASELINES.items():
            with self.subTest(key=key):
                self.assertTrue((records / f"{base.record_id}.md").exists(),
                                f"{base.record_id} is not a committed record")

    def test_delta_section_states_record_path_delta_and_ratio(self):
        cd_run.set_dut_provenance("extracted")
        text = "\n".join(
            cd_run.post_layout_delta_lines("regen", "tt", 27.0, 0.4425))
        self.assertIn("20260922-070800-e084b55", text)
        self.assertIn("0.4025 ns", text)
        self.assertIn("+0.0400 ns", text)
        self.assertIn("1.099x", text)

    def test_missing_baseline_says_so_instead_of_faking_a_delta(self):
        # `noise` (the AC loop-broken sub-model) has a committed
        # schematic-level record at tt/27C only -- DR-005's corner campaign
        # ran `noise-tran`, not `noise`, off that anchor. So a post-layout
        # AC-noise figure at ff/125C genuinely has nothing to difference
        # against, and must say so rather than invent a ratio.
        cd_run.set_dut_provenance("extracted")
        text = "\n".join(
            cd_run.post_layout_delta_lines("noise", "ff", 125.0, 0.5))
        self.assertIn("No committed schematic-level", text)
        self.assertNotIn("Ratio", text)

    def test_every_graded_corner_has_a_kickback_and_regen_baseline(self):
        """Issue #64: the post-layout campaign differences `kickback` and
        `regen` at every one of DR-005's seven graded PVT corners, so an
        anchor must exist for each -- otherwise a corner run would silently
        emit a bare number instead of a delta."""
        for corner, temp_c in cd_run.GRADED_CORNERS:
            for mode in ("kickback", "regen"):
                with self.subTest(mode=mode, corner=corner, temp_c=temp_c):
                    self.assertIsNotNone(
                        cd_run.baseline_for(mode, corner, temp_c),
                        f"no schematic-level {mode} anchor at "
                        f"{corner}/{temp_c}C",
                    )


class TestKickbackSubsetJustification(unittest.TestCase):
    """Issue #64: the `kickback` record's subset-corner justification used to
    be a fixed string asserting the record measured tt/27C. Running the other
    six graded corners made that a false claim printed into records whose own
    `Corner matrix run` line named a different corner."""

    def test_tt_27c_keeps_the_issue_30_like_for_like_wording(self):
        text = cd_run.kickback_subset_justification("tt", 27.0)
        self.assertIn("20260916-060139-f1eb978", text)
        self.assertIn("like-for-like", text)

    def test_other_corners_do_not_claim_to_have_measured_tt_27c(self):
        for corner, temp_c in cd_run.GRADED_CORNERS:
            if (corner, temp_c) == ("tt", 27.0):
                continue
            with self.subTest(corner=corner, temp_c=temp_c):
                text = cd_run.kickback_subset_justification(corner, temp_c)
                self.assertNotIn("tt/27C", text)
                self.assertNotIn("20260916-060139-f1eb978", text)
                # ...and names the corner it actually ran.
                self.assertIn(f"{corner}/{temp_c:g}C", text)


if __name__ == "__main__":
    unittest.main()
