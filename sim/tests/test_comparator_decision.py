"""Unit tests for sim/comparator-decision/run.py's `kickback` deck-builder
and result-grading logic (issue #26).

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


if __name__ == "__main__":
    unittest.main()
