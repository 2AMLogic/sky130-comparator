"""Unit tests for `layout/extract_pex.py`'s netlist rewrite (issue #57).

Hermetic: no `klt`, no PDK, no ngspice. The rewrite is exercised against the
COMMITTED `layout/comparator.extract.spice` (the extractor's own verbatim
output), which is exactly the input the committed `layout/comparator.pex.spice`,
`layout/comparator.pex-preamp.spice` and `layout/comparator.pex-latch.spice`
were derived from -- so these tests also pin the committed set to its stated
derivation without re-extracting.

What is worth testing here is not "does it produce text" but the four
properties the post-layout evidence depends on:

  1. Every extracted device keeps its extracted PARAMETERS. The rewrite is
     name-level; a rewrite that also normalised (say) the res_high_po drawn
     width would silently turn a post-layout measurement back into a
     schematic one.
  2. Every device is paired with a schematic instance name, and the parallel
     fingers of a split device are distinguishable. That pairing is what lets
     the deck probe `v(OUTP1)` and what lets the preamp partition be checked.
  3. The preamp partition is the loop break the schematic-side `noise`
     sub-model makes -- and drops the latch nets' parasitics with the latch
     devices, leaving no dangling star leg.
  4. The latch front-end partition (issue #65) is the counterpart of the
     schematic-side steering+tail sub-model `noise-tran` stage 2 uses, under
     the same no-dangling-leg property.
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
EXTRACT_PEX = REPO_ROOT / "layout" / "extract_pex.py"


def _load_extract_pex():
    spec = importlib.util.spec_from_file_location("extract_pex", EXTRACT_PEX)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


pex = _load_extract_pex()

RAW = (REPO_ROOT / "layout" / "comparator.extract.spice").read_text()


def _nodes(fragment: str) -> set[str]:
    """Every node token named by a device or parasitic line of a fragment."""
    out: set[str] = set()
    for name, tokens in _instances(fragment).items():
        if name[0].upper() in ("R", "C", "V"):
            out.update(tokens[:2])
            continue
        model_idx = next(
            i for i, t in enumerate(tokens) if t.startswith("sky130_fd_pr__")
        )
        out.update(tokens[:model_idx])
    return out


def _instances(fragment: str) -> dict[str, list[str]]:
    """{instance name: tokens} for the device (X...) lines of a fragment."""
    out: dict[str, list[str]] = {}
    current: str | None = None
    for raw in fragment.splitlines():
        line = raw.strip()
        if not line or line.startswith("*"):
            continue
        if line.startswith("+"):
            if current is not None:
                out[current].extend(line[1:].split())
            continue
        tokens = line.split()
        current = tokens[0]
        out[current] = tokens[1:]
    return out


class TestRewriteMatchesCommittedOutput(unittest.TestCase):
    """The committed set must be reproducible from the committed input."""

    def setUp(self):
        self.dut, self.preamp, self.latch, self.warnings = pex.rewrite(RAW)

    def test_no_unpaired_devices(self):
        self.assertEqual(self.warnings, [])

    def test_committed_dut_fragment_is_this_rewrite(self):
        self.assertEqual((REPO_ROOT / "layout" / "comparator.pex.spice").read_text(),
                         self.dut)

    def test_committed_preamp_fragment_is_this_rewrite(self):
        self.assertEqual(
            (REPO_ROOT / "layout" / "comparator.pex-preamp.spice").read_text(),
            self.preamp,
        )

    def test_committed_latch_fragment_is_this_rewrite(self):
        self.assertEqual(
            (REPO_ROOT / "layout" / "comparator.pex-latch.spice").read_text(),
            self.latch,
        )


class TestNameLevelOnly(unittest.TestCase):
    """Property 1: values pass through untouched."""

    def setUp(self):
        self.dut, _, _, _ = pex.rewrite(RAW)

    def test_every_extracted_parameter_survives(self):
        raw_params = sorted(
            tuple(sorted(t for t in tokens if "=" in t))
            for tokens in _instances(RAW).values()
            if any(t.startswith("sky130_fd_pr__") for t in tokens)
        )
        new_params = sorted(
            tuple(sorted(t for t in tokens if "=" in t))
            for tokens in _instances(self.dut).values()
            if any(t.startswith("sky130_fd_pr__") for t in tokens)
        )
        self.assertEqual(raw_params, new_params)

    def test_parasitic_values_survive(self):
        def values(text: str) -> list[str]:
            return sorted(
                tokens[-1]
                for name, tokens in _instances(text).items()
                if name[0].upper() in ("R", "C") and len(tokens) == 3
            )
        self.assertEqual(values(RAW), values(self.dut))

    def test_drawn_resistor_width_is_not_normalised_to_the_schematic(self):
        # The disclosed PR #55 delta: drawn w=0.42um vs the schematic's
        # _0p35 wrapper. A post-layout netlist that "fixed" this would stop
        # describing the layout.
        loads = [t for n, t in _instances(self.dut).items() if n.startswith("XR_L")]
        self.assertEqual(len(loads), 2)
        for tokens in loads:
            self.assertIn("w=0.42", tokens)
            self.assertIn("l=22", tokens)


class TestSchematicPairing(unittest.TestCase):
    """Property 2: extracted devices carry schematic instance names."""

    def setUp(self):
        self.dut, _, _, _ = pex.rewrite(RAW)
        self.names = set(_instances(self.dut))

    def test_every_schematic_instance_is_represented(self):
        for name in pex._schematic_devices():
            with self.subTest(name=name):
                self.assertTrue(
                    name in self.names
                    or any(n.startswith(f"{name}__") for n in self.names),
                    f"{name} has no extracted counterpart",
                )

    def test_split_input_pair_fingers_are_distinguishable(self):
        for base in ("XM_PINN", "XM_PINP"):
            with self.subTest(base=base):
                halves = sorted(n for n in self.names if n.startswith(f"{base}__"))
                self.assertEqual(halves, [f"{base}__a", f"{base}__b"])
                for half in halves:
                    self.assertIn("W=6.5", _instances(self.dut)[half])

    def test_internal_nets_carry_schematic_names(self):
        nodes = _nodes(self.dut)
        self.assertFalse([n for n in nodes if "$" in n])
        self.assertLessEqual(
            {"TAILP", "OUTP1", "OUTN1", "TAIL2", "CLKT"},
            {n.partition("__t")[0] for n in nodes},
        )

    def test_substrate_is_tied(self):
        self.assertIn("Vvsubs vsubs 0 dc 0", self.dut)


class TestPreampPartition(unittest.TestCase):
    """Property 3: the partition is the schematic sub-model's loop break."""

    def setUp(self):
        _, self.preamp, _, _ = pex.rewrite(RAW)
        self.instances = _instances(self.preamp)

    def test_holds_exactly_the_nine_drawn_preamp_devices(self):
        devices = {
            n for n, t in self.instances.items()
            if any(x.startswith("sky130_fd_pr__") for x in t)
        }
        self.assertEqual(devices, {
            "XM_PTAIL", "XM_PINN__a", "XM_PINN__b", "XM_PINP__a", "XM_PINP__b",
            "XR_LP", "XR_LN", "XM_C1P", "XM_C1N",
        })

    def test_omits_every_latch_net(self):
        hubs = {n.partition("__t")[0] for n in _nodes(self.preamp)}
        self.assertEqual(hubs & pex.LATCH_NETS, set())

    def test_no_dangling_star_leg(self):
        # Every `__t` leg node in the partition must appear at least twice:
        # once on its device, once on its star resistor to the hub.
        counts: dict[str, int] = {}
        for tokens in self.instances.values():
            for token in tokens:
                if "__t" in token:
                    counts[token] = counts.get(token, 0) + 1
        self.assertTrue(counts, "partition has no star legs at all")
        for node, count in sorted(counts.items()):
            with self.subTest(node=node):
                self.assertGreaterEqual(count, 2)


class TestLatchFrontEndPartition(unittest.TestCase):
    """Issue #65's partition: the post-layout counterpart of `run.py`'s
    steering+tail AC sub-model, which gives `noise-tran` its stage-2
    gate-referred injection amplitude."""

    def setUp(self):
        _, _, self.latch, _ = pex.rewrite(RAW)
        self.instances = _instances(self.latch)

    def test_holds_exactly_the_three_latch_front_end_devices(self):
        devices = {
            n for n, t in self.instances.items()
            if any(x.startswith("sky130_fd_pr__") for x in t)
        }
        self.assertEqual(devices, {"XM_STN_P", "XM_STN_N", "XM_TAIL2"})

    def test_omits_the_preamp_and_the_latch_output_stage(self):
        for absent in ("XM_PTAIL", "XM_PINN__a", "XM_PINP__a", "XR_LP",
                       "XR_LN", "XM_C1P", "XM_C1N", "XM_LATP_P", "XM_LATP_N",
                       "XM_RST_P", "XM_RST_N", "XR_CLKS", "XM_CLKCAP"):
            with self.subTest(absent=absent):
                self.assertNotIn(absent, self.instances)

    def test_carries_the_steering_pairs_own_parasitics(self):
        for parasitic in ("R_TAIL2__t0_TAIL2", "R_TAIL2__t1_TAIL2",
                          "R_TAIL2__t2_TAIL2", "R_OUTP1__t4_OUTP1",
                          "R_OUTN1__t4_OUTN1", "C_TAIL2_vsubs"):
            with self.subTest(parasitic=parasitic):
                self.assertIn(parasitic, self.instances)

    def test_no_dangling_star_leg(self):
        counts: dict[str, int] = {}
        for tokens in self.instances.values():
            for token in tokens:
                if "__t" in token:
                    counts[token] = counts.get(token, 0) + 1
        self.assertTrue(counts, "partition has no star legs at all")
        for node, count in sorted(counts.items()):
            with self.subTest(node=node):
                self.assertGreaterEqual(count, 2)

    def test_substrate_is_tied(self):
        self.assertIn("Vvsubs vsubs 0 dc 0", self.latch)


class TestGuards(unittest.TestCase):
    """The failure modes the rewrite refuses to paper over."""

    def test_latch_partition_drift_is_fatal(self):
        original = pex.LATCH_FRONT_END_NETS
        try:
            # Pretend the latch tail node acquired the preamp's tail too:
            # the partition would stop being the schematic sub-model's
            # counterpart, so it must fail loudly rather than quietly
            # measure a different circuit.
            pex.LATCH_FRONT_END_NETS = frozenset(original | {"TAILP"})
            with self.assertRaises(SystemExit):
                pex.rewrite(RAW)
        finally:
            pex.LATCH_FRONT_END_NETS = original

    def test_partition_drift_is_fatal(self):
        original = pex.LATCH_NETS
        try:
            # Pretend the layout moved the absorber caps onto a latch net:
            # the partition would no longer be the schematic sub-model's
            # counterpart, and that must fail loudly, not silently.
            pex.LATCH_NETS = frozenset(original | {"TAILP"})
            with self.assertRaises(SystemExit):
                pex.rewrite(RAW)
        finally:
            pex.LATCH_NETS = original

    def test_unmatched_device_is_warned_not_silently_renamed(self):
        # One cross-coupled latch PMOS with its gate moved onto its own drain
        # -- a connectivity no schematic device has. It is on the latch side,
        # so the preamp-partition assertion above stays satisfied and this
        # test exercises the pairing failure alone.
        mutated = RAW.replace("X$12 OUTP__t0 OUTN__t1", "X$12 OUTP__t0 OUTP__t1", 1)
        self.assertNotEqual(mutated, RAW)
        _dut, _preamp, _latch, warnings = pex.rewrite(mutated)
        self.assertTrue(any("pairs with no single schematic device" in w
                            for w in warnings), warnings)


if __name__ == "__main__":
    unittest.main()
