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
import dataclasses
import hashlib
import importlib.util
import io
import json
import math
import sys
import tempfile
import unittest
import unittest.mock
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
    """`pair_sigma_mv()` (issue #41): the pair-symmetric decision-statistic
    estimator. Checks against hand-derived Gaussian fractions, offset
    cancellation, and the degenerate-pair guard."""

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

    def test_noise_tran_anchors_match_the_committed_schematic_records(self):
        """Issue #89: `noise-tran` had an anchor at tt/27C only, even though
        the issue #41 schematic-level campaign also committed records at
        `ss`/-40C and `ff`/125C. A post-layout run at either corner therefore
        printed the "no committed schematic-level record exists" note while a
        counterpart sat in `records/` -- honest in form, false in fact.

        The anchor set must be exactly the set of corners a schematic-level
        `noise-tran` record was committed at: the three below have one, the
        other four graded points genuinely do not and must keep falling
        through to the "no committed counterpart" path rather than inventing
        a ratio."""
        measured = {("tt", 27.0), ("ss", -40.0), ("ff", 125.0)}
        for corner, temp_c in cd_run.GRADED_CORNERS:
            base = cd_run.baseline_for("noise-tran", corner, temp_c)
            with self.subTest(corner=corner, temp_c=temp_c):
                if (corner, temp_c) in measured:
                    self.assertIsNotNone(
                        base,
                        f"no schematic-level noise-tran anchor at "
                        f"{corner}/{temp_c}C, but a committed record exists",
                    )
                else:
                    self.assertIsNone(
                        base,
                        f"noise-tran anchor at {corner}/{temp_c}C claims a "
                        "schematic-level counterpart that was never run",
                    )

    def test_noise_tran_skew_corners_say_no_counterpart_exists(self):
        """The four graded `noise-tran` corners with no schematic-level
        counterpart must print the note, not a fabricated ratio (issue #89's
        acceptance criterion for the skew-corner records)."""
        cd_run.set_dut_provenance("extracted")
        for corner, temp_c in (
            ("sf", -40.0), ("sf", 125.0), ("fs", -40.0), ("fs", 125.0),
        ):
            with self.subTest(corner=corner, temp_c=temp_c):
                text = "\n".join(cd_run.post_layout_delta_lines(
                    "noise-tran", corner, temp_c, 0.2))
                self.assertIn("No committed schematic-level", text)
                self.assertNotIn("Ratio", text)

    def test_noise_tran_measured_corners_emit_a_real_ratio(self):
        """The counterpart of the test above: at the three corners that DO
        have a schematic-level record, a post-layout figure must difference
        against it (issue #89 item 1's whole point)."""
        cd_run.set_dut_provenance("extracted")
        for corner, temp_c, record_id, sigma in (
            ("ss", -40.0, "20260922-205857-ebea4e2", 0.1213),
            ("ff", 125.0, "20260923-010427-ebea4e2", 0.1754),
        ):
            with self.subTest(corner=corner, temp_c=temp_c):
                text = "\n".join(cd_run.post_layout_delta_lines(
                    "noise-tran", corner, temp_c, sigma * 2.0))
                self.assertIn(record_id, text)
                self.assertIn(f"{sigma:.4f} mV", text)
                self.assertIn("2.000x", text)
                self.assertNotIn("No committed schematic-level", text)

    def test_every_mismatch_corner_has_an_offset_baseline(self):
        """Issue #80: the post-layout `offset` campaign differences all five
        `_mm` mismatch corners at 27 C, so an anchor must exist for each.
        Issue #64's campaign skipped the four non-`tt` corners and the
        anchors were never added; a run without one silently records a bare
        post-layout number instead of the delta issue #57's acceptance
        criteria require."""
        for corner, temp_c in cd_run.OFFSET_GRADED_CORNERS:
            with self.subTest(corner=corner, temp_c=temp_c):
                self.assertIsNotNone(
                    cd_run.baseline_for("offset", corner, temp_c),
                    f"no schematic-level offset anchor at {corner}_mm/"
                    f"{temp_c}C",
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


class _FakeNgspiceDecks:
    """Deterministic stand-in for one `ngspice` invocation, wired in by
    monkeypatching `cd_run._run` (issue #100).

    Every deck's contribution is a pure function of its LOG NAME (and, for
    the decision decks, of the overdrive sign written into the deck's own
    header comment). That is exactly the property a resumable runner's
    equivalence claim rests on: which invocation happened to run a deck must
    not change what that deck contributes. The real thing has the same
    property for a different reason -- every Monte Carlo deck pins its own
    `.option rndseed=<stable seed>` -- so a fake that did NOT have it would
    be testing something the bench does not do.

    Writes the same two-vector `wrdata` csv shape `_pickoff_value()` and
    `_decision_from_csv()` read (`time0 v(OUTP) time1 v(OUTN)`), so both
    extractors run their real code against it.
    """

    GAIN_V_PER_V = 50.0

    def __init__(self):
        self.calls: list[str] = []

    @staticmethod
    def _unit(name: str) -> float:
        """A stable pseudo-random [0, 1) drawn from the deck name."""
        digest = hashlib.sha256(name.encode()).digest()
        return int.from_bytes(digest[:8], "big") / 2.0 ** 64

    def __call__(self, deck_text: str, scratch_dir: Path, log_name: str) -> str:
        self.calls.append(log_name)
        if log_name.startswith(("injcal", "trncal")):
            return "cal_std=8.6e-04\n"
        if log_name.startswith("gaincal_"):
            vindiff_mv = float(log_name[len("gaincal_"):-len("mV")])
            diff = self.GAIN_V_PER_V * vindiff_mv / 1000.0
        elif log_name.startswith("po_"):
            diff = 1e-3 * (2.0 * self._unit(log_name) - 1.0)
        elif log_name.startswith("dec_"):
            # Decide with the deck's own overdrive sign, flipped for one seed
            # index in two at the NEGATIVE overdrive, which puts p+ = 1 and
            # p- = 0.5 -- a pair the probit estimator can actually invert, so
            # these tests exercise the MEASURABLE cross-check branch and not
            # only the degenerate one every committed corner happens to hit.
            negative = "vindiff=-" in deck_text
            sign = -1.0 if negative else 1.0
            if negative and int(log_name.rsplit("_", 1)[1]) % 2 == 1:
                sign = -sign
            diff = 0.5 * sign
        else:
            raise AssertionError(f"unexpected deck {log_name!r}")
        target_s = (cd_run.RESET_NS + cd_run.RESET_TR_NS + cd_run.PICKOFF_NS) * 1e-9
        rows = [(0.0, 0.0), (target_s, diff), (10.0 * target_s, diff)]
        (scratch_dir / f"{log_name}.csv").write_text(
            "".join(f"{t:.12g} {v:.12g} {t:.12g} 0\n" for t, v in rows)
        )
        return f"* fake ngspice log for {log_name}\n"


@contextlib.contextmanager
def _stubbed_noise_tran(fake: _FakeNgspiceDecks):
    """Run `run_noise_tran()`'s real control flow with no PDK and no ngspice.

    Only the three AC/calibration stages are stubbed wholesale (they have
    their own deck-shape tests above); every Monte Carlo deck still goes
    through the real deck builders, the real `_run_many*` batching and the
    real csv extractors, against `fake`.
    """
    preamp = cd_run.NoiseResult(
        single_ended_rms_v=1.2e-4, differential_rms_v=1.2e-4 * 2 ** 0.5,
        op_tailp_v=0.9, op_outp1_v=1.18, op_outn1_v=1.18,
        log_text="fake preamp noise log", corner="tt", temp_c=27.0,
    )
    latch = cd_run.LatchNoiseResult(
        gate_rms_v=3.4e-4, op_tail2_v=0.2, log_text="fake latch noise log",
        corner="tt", temp_c=27.0, gate_cm_v=1.18, cl_ff=cd_run.LATCH_NOISE_CL_FF,
    )
    with contextlib.ExitStack() as stack:
        patch = stack.enter_context
        patch(unittest.mock.patch.object(cd_run, "_run", fake))
        patch(unittest.mock.patch.object(cd_run, "run_noise", lambda **kw: preamp))
        patch(unittest.mock.patch.object(cd_run, "run_latch_noise", lambda **kw: latch))
        patch(unittest.mock.patch.object(cd_run, "run_trnoise_calibration", lambda **kw: 0.86))
        patch(unittest.mock.patch.object(cd_run.pdk, "resolve_or_raise", lambda: FakePdkInfo()))
        yield


class TestNoiseTranResumableCampaign(unittest.TestCase):
    """`--resume-dir` / `--chunk-decks`: the chunked, resumable `noise-tran`
    runner (issue #100).

    A full-N (N=128, 4 gaincal + 128 pick-off + 256 decision = 388 decks)
    post-layout corner cannot run as one command on this host -- the
    ~60-minute wall-clock ceiling measured by #89 kills it an order of
    magnitude short, and a killed run produced NOTHING committable. These
    tests pin the two properties that make a sequence of sub-ceiling commands
    a valid substitute for the one command that cannot run: a chunk resumes
    only the decks it has not already done, and the campaign it completes is
    the same campaign an unchunked run would have produced.
    """

    N_PICKOFF = 6
    SEEDS_PER_POINT = 2

    def _campaign(self, **kw):
        return cd_run.run_noise_tran(
            corner="tt", temp_c=27.0, n_pickoff=self.N_PICKOFF,
            seeds_per_point=self.SEEDS_PER_POINT, quiet=True, **kw
        )

    def _expected_deck_names(self) -> list[str]:
        names = [f"gaincal_{v}mV" for v in cd_run.VINDIFF_GAIN_CAL_MV]
        names += [f"po_{i}" for i in range(self.N_PICKOFF)]
        for k in cd_run.NOISE_TRAN_DECIDE_PAIRS:
            for sign in ("+", "-"):
                for i in range(self.SEEDS_PER_POINT):
                    names.append(f"dec_{k:g}_{sign}_{i}".replace(".", "p"))
        return sorted(names)

    @staticmethod
    def _record_inputs(result) -> str:
        """Everything the committed record is a function of, serialized at
        full float precision so the comparison is textual (and so NaN
        compares equal to NaN, which `==` does not).

        Excludes only the raw per-deck ngspice logs -- of which just
        `latch_noise` / `injcal_*` ever reach a record, and those three are
        persisted whole with the campaign's AC/calibration preamble rather
        than re-derived per chunk."""
        fields = {k: v for k, v in dataclasses.asdict(result).items() if k != "logs"}
        return json.dumps(fields, sort_keys=True, default=repr)

    def test_resuming_from_a_partial_scratch_dir_runs_only_the_missing_decks(self):
        with tempfile.TemporaryDirectory(prefix="noise-tran-resume-") as tmp:
            resume_dir = Path(tmp)
            first_fake = _FakeNgspiceDecks()
            with _stubbed_noise_tran(first_fake):
                with self.assertRaises(cd_run.NoiseTranCampaignIncomplete) as caught:
                    self._campaign(resume_dir=resume_dir, chunk_decks=5)
            first = [c for c in first_fake.calls if not c.startswith("injcal")]
            self.assertEqual(len(first), 5, "the chunk budget was not honoured")
            self.assertEqual(caught.exception.completed, 5)
            self.assertEqual(caught.exception.total, len(self._expected_deck_names()))

            second_fake = _FakeNgspiceDecks()
            with _stubbed_noise_tran(second_fake):
                result = self._campaign(resume_dir=resume_dir)
            second = second_fake.calls

            # No deck ran twice, the union is the whole campaign, and the
            # AC/calibration preamble (the `injcal_*` decks) was resumed too.
            self.assertEqual(sorted(set(first) & set(second)), [])
            self.assertEqual(sorted(set(first) | set(second)), self._expected_deck_names())
            self.assertEqual([c for c in second if c.startswith("injcal")], [])
            self.assertEqual(len(result.pickoff_diffs), self.N_PICKOFF)

    def test_a_resumed_campaign_matches_an_unchunked_run_at_the_same_n(self):
        with _stubbed_noise_tran(_FakeNgspiceDecks()):
            unchunked = self._campaign()

        invocations = 0
        chunked = None
        with tempfile.TemporaryDirectory(prefix="noise-tran-equiv-") as tmp:
            for _ in range(40):
                invocations += 1
                with _stubbed_noise_tran(_FakeNgspiceDecks()):
                    try:
                        chunked = self._campaign(resume_dir=Path(tmp), chunk_decks=3)
                    except cd_run.NoiseTranCampaignIncomplete:
                        continue
                break
        self.assertIsNotNone(chunked, "chunked campaign never completed")
        self.assertGreater(invocations, 1, "the campaign was not actually chunked")
        self.assertEqual(self._record_inputs(unchunked), self._record_inputs(chunked))
        self.assertEqual(
            cd_run.two_statistics_line(unchunked), cd_run.two_statistics_line(chunked),
        )
        # The cross-check really was measurable, so this compared the full
        # record shape and not just its degenerate branch.
        self.assertEqual(chunked.sigma_decision_mv, chunked.sigma_decision_mv)

    def test_an_interrupted_chunk_writes_no_record_and_leaves_a_resumable_dir(self):
        argv = [
            "noise-tran", "--n", str(self.N_PICKOFF),
            "--seeds-per-point", str(self.SEEDS_PER_POINT), "--quiet", "--record",
        ]
        written: list[tuple] = []

        def _fake_writer(*args, **kwargs):
            written.append(args)
            return Path("records/fake.md")

        with tempfile.TemporaryDirectory(prefix="noise-tran-nokill-") as tmp:
            with _stubbed_noise_tran(_FakeNgspiceDecks()), unittest.mock.patch.object(
                cd_run, "write_noise_tran_evidence", _fake_writer,
            ):
                rc = cd_run.main(argv + ["--resume-dir", tmp, "--chunk-decks", "5"])
            self.assertEqual(rc, cd_run.NOISE_TRAN_INCOMPLETE_EXIT)
            self.assertEqual(written, [], "an incomplete campaign wrote a record")
            self.assertTrue((Path(tmp) / "campaign.json").is_file())
            self.assertEqual(len(list((Path(tmp) / "decks").glob("*.json"))), 5)

            with _stubbed_noise_tran(_FakeNgspiceDecks()), unittest.mock.patch.object(
                cd_run, "write_noise_tran_evidence", _fake_writer,
            ):
                rc = cd_run.main(argv + ["--resume-dir", tmp])
            self.assertEqual(rc, 0)
            self.assertEqual(len(written), 1, "the completed campaign wrote no record")

    def test_re_invoking_a_complete_campaign_re_runs_nothing(self):
        with tempfile.TemporaryDirectory(prefix="noise-tran-complete-") as tmp:
            with _stubbed_noise_tran(_FakeNgspiceDecks()):
                first = self._campaign(resume_dir=Path(tmp))
            again = _FakeNgspiceDecks()
            with _stubbed_noise_tran(again):
                second = self._campaign(resume_dir=Path(tmp))
            self.assertEqual(again.calls, [])
            self.assertEqual(self._record_inputs(first), self._record_inputs(second))

    def test_a_scratch_dir_from_a_different_campaign_is_refused(self):
        with tempfile.TemporaryDirectory(prefix="noise-tran-mismatch-") as tmp:
            with _stubbed_noise_tran(_FakeNgspiceDecks()):
                with self.assertRaises(cd_run.NoiseTranCampaignIncomplete):
                    self._campaign(resume_dir=Path(tmp), chunk_decks=2)
            for changed in (
                {"n_pickoff": self.N_PICKOFF + 2},
                {"seeds_per_point": self.SEEDS_PER_POINT + 1},
                {"corner": "ss"},
                {"temp_c": -40.0},
            ):
                with self.subTest(**changed):
                    kw = dict(
                        corner="tt", temp_c=27.0, n_pickoff=self.N_PICKOFF,
                        seeds_per_point=self.SEEDS_PER_POINT, quiet=True,
                        resume_dir=Path(tmp),
                    )
                    kw.update(changed)
                    with _stubbed_noise_tran(_FakeNgspiceDecks()):
                        with self.assertRaises(RuntimeError) as caught:
                            cd_run.run_noise_tran(**kw)
                    self.assertIn("DIFFERENT campaign", str(caught.exception))

    def test_chunking_without_a_resume_dir_is_refused(self):
        with _stubbed_noise_tran(_FakeNgspiceDecks()):
            with self.assertRaises(ValueError):
                self._campaign(chunk_decks=4)


def _wrdata_text(rows: list[tuple], n_vectors: int) -> str:
    """Synthesize an ngspice `wrdata` file: ngspice repeats the time column
    once per vector (`time0 a time1 b time2 c`), which is exactly what
    `toolchain.read_wrdata_csv` parses. Each row carries the time plus
    `n_vectors` values."""
    lines = []
    for row in rows:
        assert len(row) == n_vectors + 1, row
        cols = [f"{row[0]:.9g} {row[i + 1]:.9g}" for i in range(n_vectors)]
        lines.append(" ".join(cols))
    return "\n".join(lines) + "\n"


def _decision_rows(
    *, settle_sign: int, cross_ns: float | None,
    eval_start_ns: float = 5.1, t_end_ns: float = 45.0, step_ns: float = 0.1,
    with_clk: bool = False,
) -> list[tuple]:
    """Synthetic reset->evaluate rows. Before `eval_start_ns` both outputs
    sit at the reset level (equal outputs, no difference). After it, the
    difference ramps linearly to `settle_sign * 1.2 V` reaching the
    DECIDE_THRESHOLD_V crossing exactly `cross_ns` after the evaluate edge
    (so the crossing time is assertable), or -- `settle_sign=0` /
    `cross_ns=None` -- never separates at all (a non-decision).

    Rows carry the clock vector too when `with_clk` (the `regen` deck's
    `wrdata v(CLK) v(OUTP) v(OUTN)` shape); the `offset-bisect` deck
    writes OUTP/OUTN only."""
    rows: list[tuple] = []
    threshold = cd_run.DECIDE_THRESHOLD_V
    n = int(round((t_end_ns) / step_ns))
    for i in range(n + 1):
        t_ns = i * step_ns
        if t_ns < eval_start_ns or settle_sign == 0 or cross_ns is None:
            diff = 0.0
        else:
            slope = threshold / cross_ns
            diff = settle_sign * min(slope * (t_ns - eval_start_ns), 1.2)
        outp, outn = 0.9 + diff / 2, 0.9 - diff / 2
        if with_clk:
            rows.append((t_ns * 1e-9, 0.0 if t_ns < eval_start_ns else 1.8, outp, outn))
        else:
            rows.append((t_ns * 1e-9, outp, outn))
    return rows


class TestDecisionClassification(unittest.TestCase):
    """`_classify_decision` -- the issue #66 polarity split. `regen`'s old
    criterion was sign-corrected, so a wrong-polarity decision and a genuine
    non-decision both read `UNRESOLVED`; these tests pin the three-way
    outcome (resolved / wrong-polarity / non-decision) and the
    evaluate-relative crossing time of whichever sign crossed."""

    def _classify(self, rows, expected_sign):
        t = [r[0] for r in rows]; outp = [r[2] for r in rows]; outn = [r[3] for r in rows]
        return cd_run._classify_decision(
            t, outp, outn, evaluate_start_ns=5.1, expected_sign=expected_sign,
        )

    def test_expected_sign_crossing_is_resolved_with_crossing_time(self):
        outcome, cross_ns = self._classify(
            _decision_rows(settle_sign=+1, cross_ns=2.0, with_clk=True), +1.0)
        self.assertEqual(outcome, "resolved")
        self.assertAlmostEqual(cross_ns, 2.0, delta=0.2)

    def test_opposite_sign_crossing_is_wrong_polarity(self):
        outcome, cross_ns = self._classify(
            _decision_rows(settle_sign=-1, cross_ns=1.5, with_clk=True), +1.0)
        self.assertEqual(outcome, "wrong-polarity")
        self.assertAlmostEqual(cross_ns, 1.5, delta=0.2)

    def test_no_crossing_is_non_decision(self):
        outcome, cross_ns = self._classify(
            _decision_rows(settle_sign=0, cross_ns=None, with_clk=True), +1.0)
        self.assertEqual(outcome, "non-decision")
        self.assertIsNone(cross_ns)

    def test_pre_evaluate_window_samples_are_ignored(self):
        # A pre-evaluate separation (an unphysical reset-phase glitch, but
        # exactly what the old loop's `tt < evaluate_start_ns` guard skipped)
        # must not classify the point: only crossings AFTER the evaluate
        # edge count.
        rows = [
            (t - 4.0e-9, clk, 1.4, 0.4) if t < 4.5e-9 else (t, clk, outp, outn)
            for t, clk, outp, outn
            in _decision_rows(settle_sign=0, cross_ns=None, with_clk=True)
        ]
        outcome, _ = self._classify(rows, +1.0)
        self.assertEqual(outcome, "non-decision")

    def test_expected_sign_negative_resolves_negative_difference(self):
        # A negative-vindiff regen point expects sign(outp-outn) < 0; the
        # classifier must follow the EXPECTED sign, not hardcode +.
        outcome, cross_ns = self._classify(
            _decision_rows(settle_sign=-1, cross_ns=3.0, with_clk=True), -1.0)
        self.assertEqual(outcome, "resolved")
        self.assertAlmostEqual(cross_ns, 3.0, delta=0.2)


class TestRegenSweepPolarity(unittest.TestCase):
    """`run_regen_sweep` labels each point resolved / wrong-polarity /
    non-decision, against a fake comparator with a known decision flip
    (the exact shape issue #66 measured post-layout at `ss`/-40C: small
    positive overdrives decide the WRONG way)."""

    FLIP_MV = 12.0

    @staticmethod
    def _regen_probe_mv(name: str) -> float:
        # `regen_<v>mV` with "-" -> "neg" and "." -> "p" (run_regen_sweep's
        # own naming), parsed back.
        body = name.removeprefix("regen_").removesuffix("mV")
        sign = 1.0
        if body.startswith("neg"):
            sign, body = -1.0, body[3:]
        return sign * float(body.replace("p", "."))

    def _fake_run_many(self, jobs, scratch_dir, workers=1):
        out = {}
        for name, _deck in jobs:
            v = self._regen_probe_mv(name)
            # wrong side of the flip -> settles the wrong way (fast); right
            # side -> settles correctly; exactly on it -> non-decision.
            if abs(v - self.FLIP_MV) < 1e-9:
                rows = _decision_rows(settle_sign=0, cross_ns=None, with_clk=True)
            elif v > self.FLIP_MV:
                rows = _decision_rows(settle_sign=+1, cross_ns=0.5, with_clk=True)
            else:
                rows = _decision_rows(settle_sign=-1, cross_ns=2.0, with_clk=True)
            (Path(scratch_dir) / f"{name}.csv").write_text(_wrdata_text(rows, 3))
            out[name] = f"fake log {name}"
        return out

    def test_outcomes_follow_the_flip(self):
        with unittest.mock.patch.object(cd_run, "_run_many", self._fake_run_many):
            with unittest.mock.patch.object(cd_run.pdk, "resolve_or_raise"):
                points = cd_run.run_regen_sweep(quiet=True)
        by_v = {p.vindiff_mv: p for p in points}
        self.assertEqual(by_v[-10.0].outcome, "resolved")          # below flip, - sign expected
        self.assertAlmostEqual(by_v[-10.0].regen_time_ns, 2.0, places=6)  # the crossing time is kept
        self.assertEqual(by_v[+5.0].outcome, "wrong-polarity")     # 0 < 5 < flip
        self.assertEqual(by_v[+10.0].outcome, "wrong-polarity")
        self.assertEqual(by_v[+20.0].outcome, "resolved")
        self.assertEqual(by_v[+50.0].outcome, "resolved")


class TestOffsetBisectDeck(unittest.TestCase):
    """The issue #66 `offset-bisect` deck: same stimulus shape as `regen`,
    but a longer evaluate window (near the flip the latch regenerates
    slowly, and the bisection must not misread a slow correct decision as
    a flip), and OUTP/OUTN only (no CLK vector needed)."""

    def setUp(self):
        self.info = FakePdkInfo()
        self.addCleanup(cd_run.set_dut_provenance, "schematic")

    def _deck(self, vindiff_mv=3.25):
        return cd_run._offset_bisect_deck(self.info, "ss", -40.0, vindiff_mv, "probe")

    def test_uses_the_longer_evaluate_window(self):
        deck = self._deck()
        tstop = cd_run.RESET_NS + cd_run.RESET_TR_NS + cd_run.BISECT_EVALUATE_NS
        self.assertIn(f"tran 0.005n {tstop}n", deck)
        self.assertGreater(
            cd_run.BISECT_EVALUATE_NS, cd_run.EVALUATE_NS,
            "the bisection window must be longer than regen's, or slow "
            "near-flip decisions would misclassify",
        )

    def test_clock_pulse_width_matches_the_window(self):
        # The PULSE width must be the bisect window, so exactly ONE
        # evaluate edge occurs inside the transient (the regen convention).
        deck = self._deck()
        expected = (
            f"PULSE(0 {{vdd_val}} {cd_run.RESET_NS}n {cd_run.RESET_TR_NS}n "
            f"{cd_run.RESET_TR_NS}n {cd_run.BISECT_EVALUATE_NS}n"
        )
        self.assertIn(expected, deck)

    def test_input_split_is_centered_on_vcm(self):
        deck = self._deck(vindiff_mv=4.0)
        self.assertIn(f"dc {cd_run.VCM + 0.002}", deck)
        self.assertIn(f"dc {cd_run.VCM - 0.002}", deck)

    def test_includes_dut_lines_verbatim(self):
        deck = self._deck()
        self.assertIn(cd_run.DUT_FRAGMENT.read_text(), deck)

    def test_extracted_dut_inlines_the_extracted_fragment(self):
        cd_run.set_dut_provenance("extracted")
        deck = self._deck()
        self.assertIn(cd_run.PEX_FRAGMENT.read_text(), deck)
        self.assertIn("vsubs", deck)

    def test_wrdata_has_both_output_nodes(self):
        self.assertIn("wrdata probe.csv v(OUTP) v(OUTN)", self._deck())


class TestOffsetBisectSearch(unittest.TestCase):
    """`run_offset_bisect` against fake comparators with known decision
    structure: the two edge bisections must converge to the flip within
    the stated tolerance, bracket-expand past a wrong initial guess,
    collapse to ~0 on the symmetric fragment (the negative control), and
    report a measured NON-DECISION BAND as a band -- not pretend a single
    flip exists inside it."""

    def _run_with_fake(self, flip_mv, *, bracket_start=None, dead_band=None,
                       timeout_band=None):
        calls = []

        def fake_run_many(jobs, scratch_dir, workers=1):
            out = {}
            t_end = cd_run.RESET_NS + cd_run.RESET_TR_NS + cd_run.BISECT_EVALUATE_NS
            for name, _deck in jobs:
                v = cd_run._bisect_probe_mv(name)
                calls.append(v)
                if timeout_band is not None and timeout_band[0] <= v <= timeout_band[1]:
                    raise RuntimeError(
                        "ngspice timed out after 120s running "
                        f"{name}.spice (last output:\n)"
                    )
                if dead_band is not None and dead_band[0] <= v <= dead_band[1]:
                    rows = _decision_rows(settle_sign=0, cross_ns=None, t_end_ns=t_end)
                elif v > flip_mv:
                    rows = _decision_rows(settle_sign=+1, cross_ns=1.0, t_end_ns=t_end)
                else:
                    rows = _decision_rows(settle_sign=-1, cross_ns=2.0, t_end_ns=t_end)
                (Path(scratch_dir) / f"{name}.csv").write_text(_wrdata_text(rows, 2))
                out[name] = f"fake log {name}"
            return out

        kwargs = {"quiet": True}
        if bracket_start is not None:
            kwargs["bracket_start_mv"] = bracket_start
        with unittest.mock.patch.object(cd_run, "_run_many", fake_run_many):
            with unittest.mock.patch.object(cd_run.pdk, "resolve_or_raise"):
                result = cd_run.run_offset_bisect(corner="tt", temp_c=27.0, **kwargs)
        return result, calls

    def test_converges_to_a_positive_flip(self):
        result, _ = self._run_with_fake(flip_mv=12.0)
        self.assertTrue(result.converged)
        self.assertLessEqual(result.band_mv, cd_run.BISECT_TOL_MV)
        self.assertLessEqual(abs(result.flip_mv - 12.0), cd_run.BISECT_TOL_MV)
        self.assertLessEqual(result.wrong_edge_bracket[0], 12.0)
        self.assertGreaterEqual(result.resolved_edge_bracket[1], 12.0)

    def test_bracket_expands_past_a_too_small_initial_guess(self):
        # flip outside the default +/-10 mV start: the +10 mV probe decides
        # the wrong way, so the high end must expand until it resolves.
        result, calls = self._run_with_fake(flip_mv=14.0)
        self.assertTrue(result.converged)
        self.assertLessEqual(result.band_mv, cd_run.BISECT_TOL_MV)
        self.assertLessEqual(abs(result.flip_mv - 14.0), cd_run.BISECT_TOL_MV)
        self.assertIn(20.0, calls, "the bracket must have expanded to +20 mV")

    def test_negative_flip_is_bracketed_by_expanding_low(self):
        result, calls = self._run_with_fake(flip_mv=-25.0)
        self.assertTrue(result.converged)
        self.assertLessEqual(abs(result.flip_mv - (-25.0)), cd_run.BISECT_TOL_MV)
        self.assertIn(-40.0, calls)

    def test_symmetric_fragment_collapses_to_zero(self):
        # The symmetric-fragment shape: at exactly vindiff=0 the comparator
        # is ideally metastable (a non-decision). Both edge bisections must
        # converge to it from either side -- the negative control.
        result, _ = self._run_with_fake(flip_mv=0.0, dead_band=(0.0, 0.0))
        self.assertTrue(result.converged)
        self.assertLessEqual(result.band_mv, cd_run.BISECT_TOL_MV)
        self.assertAlmostEqual(result.flip_mv, 0.0, delta=cd_run.BISECT_TOL_MV)

    def test_dead_band_is_reported_as_a_band_not_a_flip(self):
        # The shape the ss/-40C post-layout re-run found: wrong-polarity
        # below 2 mV, NO decision from 2 to 12 mV, resolved above 12 mV.
        # The result must carry the band's measured edges, not a flip.
        result, _ = self._run_with_fake(flip_mv=12.0, dead_band=(2.0, 12.0))
        self.assertTrue(result.converged)
        self.assertGreater(result.band_mv, cd_run.BISECT_TOL_MV)
        self.assertAlmostEqual(result.wrong_edge_mv, 2.0, delta=cd_run.BISECT_TOL_MV)
        self.assertAlmostEqual(result.resolved_edge_mv, 12.0, delta=cd_run.BISECT_TOL_MV)
        self.assertAlmostEqual(result.band_mv, 10.0, delta=2 * cd_run.BISECT_TOL_MV)

    def test_unbracketable_flip_raises(self):
        # flip beyond the bracket ceiling: honest failure, no result.
        with self.assertRaises(RuntimeError):
            self._run_with_fake(flip_mv=1e6)

    def test_solver_floor_stops_the_edge_without_fabricating(self):
        # The numerically balanced latch: probes too close to the flip
        # exhaust the solver's wall-clock budget. The edge bisection must
        # STOP there (recorded as a timeout probe, bracket left as-is),
        # never classifying the probe as a circuit outcome.
        result, _ = self._run_with_fake(flip_mv=0.0, timeout_band=(-0.5, 0.5))
        self.assertTrue(result.solver_floor_hit)
        self.assertFalse(result.converged)
        # The timeout probe is recorded as a timeout, not an outcome.
        self.assertIn((0.0, "timeout"), result.probes)
        # Both edges' brackets still bound the flip.
        self.assertLessEqual(result.wrong_edge_bracket[0], 0.0)
        self.assertGreaterEqual(result.wrong_edge_bracket[1], 0.0)
        self.assertLessEqual(result.resolved_edge_bracket[0], 0.0)
        self.assertGreaterEqual(result.resolved_edge_bracket[1], 0.0)

    def test_non_timeout_solver_failure_propagates(self):
        # A nonzero ngspice exit is a real error, not a floor hit.
        def fake_run_many(jobs, scratch_dir, workers=1):
            raise RuntimeError("ngspice exited 1 running x.spice")
        with unittest.mock.patch.object(cd_run, "_run_many", fake_run_many):
            with unittest.mock.patch.object(cd_run.pdk, "resolve_or_raise"):
                with self.assertRaises(RuntimeError):
                    cd_run.run_offset_bisect(corner="tt", temp_c=27.0, quiet=True)

    def test_probe_names_round_trip(self):
        # Names quantize to microvolts (by design -- that is ~1000x finer
        # than BISECT_TOL_MV), so round-trip to that resolution, not exactly.
        for v in (0.0, 10.0, -10.0, 12.34375, -0.05, 160.0):
            name = cd_run._bisect_probe_name(v)
            self.assertTrue(name.startswith("bisect_"))
            self.assertNotIn("-", name, "job names must not carry a raw minus sign")
            self.assertAlmostEqual(
                cd_run._bisect_probe_mv(name), v, delta=1e-3)


class TestOffsetBisectCli(unittest.TestCase):
    """Parse-level: the `offset-bisect` mode exists and routes."""

    def test_offset_bisect_mode_in_choices(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            with self.assertRaises(SystemExit) as cm:
                cd_run.main(["offset-bisect", "--help"])
        self.assertEqual(cm.exception.code, 0)
        self.assertIn("offset-bisect", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
