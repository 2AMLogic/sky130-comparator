#!/usr/bin/env python3
"""layout/gen_comparator.py -- generate the comparator's GDS layout (issue #44).

The single reviewable source for ``layout/comparator.gds``: it generates
every device block with ``klt gen`` (klayout-tools 0.6.0 on the klayout
0.30.10 engine, pinned the same way as ``docs/environment-setup.md`` and
``.github/workflows/t1-signoff.yml``),
places and routes them with a deterministic router this repo controls, and
verifies the composition (per-block DRC, composed DRC, ``klt extract``
device count).  Running it writes scratch under ``layout/_gen/`` (gitignored)
and refreshes the committed deliverables ``layout/comparator.gds``,
``layout/compose-report.json``, ``layout/route-summary.json``,
``layout/extract-device-count.json`` and ``layout/drc-report.json`` (the
last re-run from the repo root against the *emitted* GDS, since it is the
envelope ``manifests/sky130-comparator.json`` cites for T1 item 3 -- see
``emit_drc_evidence``).

    python3 layout/gen_comparator.py            # regenerate + verify + emit
    python3 layout/gen_comparator.py --check    # byte-compare against the
                                                # committed GDS, change nothing

PDK resolution defaults to the repo pin (``sim/pdk.json``: sky130A at
``~/.volare``, open_pdks ``c6d73a35f5...``); override with ``--pdk-root``.
Every artifact this script writes carries relative paths only -- no absolute
host paths anywhere (the gf180 twin hit exactly that: gf180-comparator#45).

Method (adapted from the sky130-sar-adc comparator sub-block's proven flow,
same PDK pin, same klt version; and the gf180 twin's ``gen_comparator.py``
naming convention):

* **Devices** are 100%% ``klt gen`` geometry -- one block per schematic
  device group, no hand-drawn transistors:

    - ``inpair`` -- M_PINN/M_PINP, the offset-critical input pair
      (DR-001 Amendment 1 derives the offset budget from this pair's ``_mm``
      mismatch model), gets ``diff_pair`` with ``splits=2``: a true
      common-centroid cross-quad interleave of two W=6.5um legs per device
      (combining to the schematic's W=13um), cancelling a linear process
      gradient to first order.
    - ``rload`` (R_LP/R_LN), ``stn`` (M_STN_P/N), ``latp`` (M_LATP_P/N),
      ``rst`` (M_RST_P/N) -- matched pairs symmetric by role
      (interchangeable under the OUTP<->OUTN swap) but not the static-offset
      net: plain ``splits=1`` A/B placement at full schematic size.
      The two load resistors additionally sit as the two folded rows of one
      ``res_array`` (adjacent identical bodies, shared environment).
    - ``absorb`` (M_C1P/M_C1N) -- the OUT1 absorber caps, a symmetric
      ``diff_pair`` of W=40um gate-cap devices.
    - ``ptail`` (M_PTAIL), ``tail2`` (M_TAIL2) -- single devices, ``mos_array``
      1x1, reusing the validated unit-device primitive.
    - ``rclks`` (R_CLKS) + ``clkcap`` (M_CLKCAP) -- the DR-003 soft-clock
      shaper, one ``res_array`` unit + one ``mos_array`` gate-cap.

  Known generator gap (filed per CLAUDE.md's friction protocol as a
  klayout-tools issue; see layout/README.md for the number): ``res_array``
  rejects ``width_um < 0.42``, so the netlist's 0.35um-wide
  ``res_high_po_0p35`` variant is not expressible -- the load and shaper
  resistors are drawn at the generator floor, 0.42um, at the schematic's
  lengths.  The drawn width is recorded in extract-device-count.json.

* **Placement and every wire** come from this script's floorplan + greedy
  channel router, emitted as a ``klt draw`` shape document and merged with
  the device blocks by ``klt gen-compose`` used as a *placer only*
  (``placement.strategy: "explicit"``, no ``routing`` block).
  ``klt gen-compose``'s own routing is not used as a signoff path
  (klayout-tools#1386: legs it reports ``routed: true`` land li1/met1
  spacing violations, and a block with more than one same-block self-net --
  which a ``splits``-interleaved pair inherently is -- can only get one of
  them routed).  The split is safe because every ``klt gen`` block draws
  only nwell/diff/poly/licon1/li1: met1 and met2 belong entirely to the
  routing cell, so a route cannot short into a block; only a deliberately
  placed ``mcon`` connects a route to a block's li1 pad.

* **Floorplan against the parasitic asymmetry** (DR-004/DR-005 Open items):
  layout capacitance at VINP/VINN raises kickback (Kickback row margin thin:
  1.06-1.13x at the DR-004 anchors, a 1%% stretch-bound breach already
  recorded at sf/-40C), so the block order keeps the clock shaper
  (``rclks``/``clkcap``, the CLKT net) and the three large gate-cap devices
  (``absorb`` W=40 x2, ``clkcap`` W=20) on the far side of the steering
  pair from the input pair, with the VINP/VINN trunks short (they exist
  only beside ``inpair``) and the input-pair gates' branches local.  The
  CLKT trunk set lives at x >= 17.3um; ``inpair`` geometry ends at x ~ 8.6um
  and the VIN trunks at x ~ 5.1um, so the clock net never crosses the input
  region.  OUTP1/OUTN1 wire capacitance (lowers noise, slows the preamp;
  Decision-time ratified <= 1.5ns vs 0.5375ns worst graded corner) is the
  axis that pays for that separation -- the route summary measures the
  OUTP1/OUTN1 and VINP/VINN wire-area imbalance so the trade is a number,
  not an assertion.

* **Body ties** are drawn even though ERC is graded later (T1 item 11): a
  p-substrate tap outside every n-well contacted up to GND, and an n-well
  tap inside the merged pfet well contacted up to VDD, so ``klt extract``
  sees real supply-referenced bodies rather than a synthesized proxy net --
  without them, item 4's eventual LVS would not be comparing the layout
  this issue claims to deliver.

Determinism: no randomness and no dict-ordering dependence anywhere (the
router's candidate ordering is a pure function of the geometry), so a
re-run at the same klt pin reproduces ``comparator.gds`` byte-for-byte --
that is exactly what ``--check`` asserts.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

# --- layer table (sky130A GDS numbers, as klt's own curated deck names them) --
L_NWELL = (64, 20)
L_TAP = (65, 44)
L_LICON = (66, 44)
L_MCON = (67, 44)
L_LI1 = (67, 20)
L_MET1 = (68, 20)
L_MET1_PIN = (68, 5)
L_VIA = (68, 44)
L_MET2 = (69, 20)

# --- rule-derived geometry (sky130 deck thresholds + margin) -----------------
MCON_UM = 0.17   # ct.2 spacing 0.19 respected by the track pitch below
VIA_UM = 0.15    # via.1a_a min size 0.15
PAD_UM = 0.30    # met1/met2 landing pad: 0.065 over mcon, 0.075 over via
WIRE_UM = 0.30   # met1/met2 wire width (m1.1/m2.1 minimum is 0.14)
MET1_SPACE_UM = 0.14  # m1.2
MCON_SPACE_UM = 0.19  # ct.2
TRACK_PITCH_UM = 0.50  # y pitch for met1 branches: 0.30 wire + 0.20 gap
PAD_MARGIN_UM = 0.12   # keep an mcon this far inside its li1 pad's own edges
LICON_UM = 0.17
LICON_PITCH_UM = 0.60
DBU = 1000

# --- PDK pin (mirrors sim/pdk.json) ------------------------------------------
PDK_VARIANT = "sky130A"
PDK_ROOT_DEFAULT = "~/.volare"  # default_pdk_root in sim/pdk.json
KLT_PIN = "klayout-tools 0.6.0 (klt 0.6.0), klayout 0.30.10"


def nm(value_um: float) -> int:
    return int(round(value_um * DBU))


class Rect:
    """An axis-aligned rectangle in integer nanometres."""

    __slots__ = ("x0", "y0", "x1", "y1")

    def __init__(self, x0: int, y0: int, x1: int, y1: int) -> None:
        self.x0, self.y0, self.x1, self.y1 = x0, y0, x1, y1

    @classmethod
    def um(cls, x0: float, y0: float, x1: float, y1: float) -> "Rect":
        return cls(nm(x0), nm(y0), nm(x1), nm(y1))

    @classmethod
    def centred(cls, cx: float, cy: float, w: float, h: float) -> "Rect":
        return cls(nm(cx - w / 2), nm(cy - h / 2), nm(cx + w / 2), nm(cy + h / 2))

    def as_um(self) -> list[float]:
        return [self.x0 / DBU, self.y0 / DBU, self.x1 / DBU, self.y1 / DBU]

    def within(self, other: "Rect", clearance: int) -> bool:
        """True when ``self`` comes closer than ``clearance`` to ``other``."""
        return (
            self.x0 - clearance < other.x1
            and other.x0 < self.x1 + clearance
            and self.y0 - clearance < other.y1
            and other.y0 < self.y1 + clearance
        )


# --- the ten device blocks ----------------------------------------------------
# (id, generator, cell_name, params).  Params intentionally spelled out in
# full (not derived from the netlist at runtime) so this script has no
# import-time dependency on sim/; the correspondence with
# sim/comparator-decision/testbench/comparator_core.spice (16 devices: 9
# nfet_01v8 + 4 pfet_01v8 + 3 res_high_po_0p35) is asserted at the end of
# the flow by the klt extract device count, not by construction.
#
# dummy=0 everywhere: a dummy column/element would extract as an extra
# device and break the 16-device count the flow asserts.
BLOCKS = [
    ("ptail", "mos_array", "PTAIL", {
        "w_um": 0.8, "l_um": 0.5, "fingers": 1, "rows": 1, "cols": 1,
        "dummy": 0, "flavor": "nfet", "gate_contact": True,
    }),
    ("inpair", "diff_pair", "INPAIR", {
        "w_um": 6.5, "l_um": 0.5, "splits": 2, "flavor": "nfet",
        "add_guard_ring": False, "gate_contact": True,
    }),
    ("rload", "res_array", "RLOAD", {
        "length_um": 22.0, "width_um": 0.42, "num": 2, "dummy": 0,
        "flavor": "high", "rows": 2,
    }),
    ("stn", "diff_pair", "STN", {
        "w_um": 8.0, "l_um": 0.5, "splits": 1, "flavor": "nfet",
        "add_guard_ring": False, "gate_contact": True,
    }),
    ("tail2", "mos_array", "TAIL2", {
        "w_um": 8.0, "l_um": 0.5, "fingers": 1, "rows": 1, "cols": 1,
        "dummy": 0, "flavor": "nfet", "gate_contact": True,
    }),
    ("latp", "diff_pair", "LATP", {
        "w_um": 16.0, "l_um": 0.5, "splits": 1, "flavor": "pfet",
        "add_guard_ring": False, "gate_contact": True,
    }),
    ("rst", "diff_pair", "RST", {
        "w_um": 8.0, "l_um": 0.5, "splits": 1, "flavor": "pfet",
        "add_guard_ring": False, "gate_contact": True,
    }),
    ("absorb", "diff_pair", "ABSORB", {
        "w_um": 40.0, "l_um": 0.5, "splits": 1, "flavor": "nfet",
        "add_guard_ring": False, "gate_contact": True,
    }),
    ("clkcap", "mos_array", "CLKCAP", {
        "w_um": 20.0, "l_um": 0.5, "fingers": 1, "rows": 1, "cols": 1,
        "dummy": 0, "flavor": "nfet", "gate_contact": True,
    }),
    ("rclks", "res_array", "RCLKS", {
        "length_um": 1.75, "width_um": 0.42, "num": 1, "dummy": 0,
        "flavor": "high",
    }),
]

# --- schematic connectivity --------------------------------------------------
# Net -> [(block id, port name)], transcribed device-by-device from
# sim/comparator-decision/testbench/comparator_core.spice (D G S B order;
# that netlist is the xschem-derived ground truth, re-derivable with
# ./design/netlist.sh --check):
#
#   XM_PTAIL  TAILP VDD  GND  -> ptail.U0        (D G S)
#   XM_PINN   OUTN1 VINN TAILP -> inpair.Q1_{1,2}
#   XM_PINP   OUTP1 VINP TAILP -> inpair.Q2_{1,2}
#   XM_STN_P  OUTP  OUTP1 TAIL2 -> stn.Q1_1
#   XM_STN_N  OUTN  OUTN1 TAIL2 -> stn.Q2_1
#   XM_TAIL2  TAIL2 CLKT GND   -> tail2.U0
#   XM_LATP_P OUTP  OUTN VDD   -> latp.Q1_1      (cross-coupled)
#   XM_LATP_N OUTN  OUTP VDD   -> latp.Q2_1
#   XM_RST_P  OUTP  CLKT VDD   -> rst.Q1_1
#   XM_RST_N  OUTN  CLKT VDD   -> rst.Q2_1
#   XR_LP     OUTN1 VDD        -> rload.R0       (netlist: R_LP loads OUTN1)
#   XR_LN     OUTP1 VDD        -> rload.R1
#   XR_CLKS   CLKT  CLK        -> rclks.R0
#   XM_CLKCAP GND   CLKT       -> clkcap.U0      (gate cap on CLKT)
#   XM_C1P    GND   OUTP1      -> absorb.Q1_1    (gate cap on OUTP1)
#   XM_C1N    GND   OUTN1      -> absorb.Q2_1    (gate cap on OUTN1)
NET_PINS: dict[str, list[tuple[str, str]]] = {
    "VDD": [
        ("ptail", "U0_G"),
        ("rload", "R0_B"), ("rload", "R1_B"),
        ("latp", "Q1_1_S"), ("latp", "Q2_1_S"),
        ("rst", "Q1_1_S"), ("rst", "Q2_1_S"),
    ],
    "GND": [
        ("ptail", "U0_S"), ("tail2", "U0_S"),
        ("clkcap", "U0_S"), ("clkcap", "U0_D"),
        ("absorb", "Q1_1_S"), ("absorb", "Q1_1_D"),
        ("absorb", "Q2_1_S"), ("absorb", "Q2_1_D"),
    ],
    "TAILP": [
        ("ptail", "U0_D"),
        ("inpair", "Q1_1_S"), ("inpair", "Q2_1_S"),
        ("inpair", "Q2_2_S"), ("inpair", "Q1_2_S"),
    ],
    "OUTP1": [
        ("inpair", "Q2_1_D"), ("inpair", "Q2_2_D"),
        ("stn", "Q1_1_G"),
        ("rload", "R1_A"),
        ("absorb", "Q1_1_G"),
    ],
    "OUTN1": [
        ("inpair", "Q1_1_D"), ("inpair", "Q1_2_D"),
        ("stn", "Q2_1_G"),
        ("rload", "R0_A"),
        ("absorb", "Q2_1_G"),
    ],
    "TAIL2": [
        ("tail2", "U0_D"),
        ("stn", "Q1_1_S"), ("stn", "Q2_1_S"),
    ],
    "OUTP": [
        ("stn", "Q1_1_D"),
        ("latp", "Q1_1_D"), ("latp", "Q2_1_G"),
        ("rst", "Q1_1_D"),
    ],
    "OUTN": [
        ("stn", "Q2_1_D"),
        ("latp", "Q2_1_D"), ("latp", "Q1_1_G"),
        ("rst", "Q2_1_D"),
    ],
    "VINN": [("inpair", "Q1_1_G"), ("inpair", "Q1_2_G")],
    "VINP": [("inpair", "Q2_1_G"), ("inpair", "Q2_2_G")],
    "CLKT": [
        ("rclks", "R0_A"),
        ("clkcap", "U0_G"),
        ("tail2", "U0_G"),
        ("rst", "Q1_1_G"), ("rst", "Q2_1_G"),
    ],
    "CLK": [("rclks", "R0_B")],
}

#: Nets promoted to top-level pins (labelled on met1.pin) -- the seven ports
#: of manifests/integrator-view.json.
PIN_NETS = ("VDD", "GND", "CLK", "VINP", "VINN", "OUTP", "OUTN")

#: Route order.  Gate-fed nets first (a gate pad is only 0.42um tall, so its
#: mcon y is pinned and it has least freedom to route around); the positive
#: half of each differential pair before its negative half (see MIRROR_PIN).
ROUTE_ORDER = ("VINN", "VINP", "OUTP1", "OUTN1", "CLKT",
               "OUTP", "OUTN", "TAIL2", "TAILP", "GND", "VDD", "CLK")

#: Mirror pairing for differential S/D pins: ``upper-half pin -> lower-half
#: pin it is the Y_AXIS mirror image of``.  Each negative-half branch prefers
#: the reflected track of its positive-half counterpart, so the two halves of
#: every differential net see matched wire capacitance (a dynamic
#: comparator's decision is a race -- unequal OUTP/OUTN, OUTP1/OUTN1 or
#: VINP/VINN loading biases it exactly like a device Vth mismatch).
#: Gate pads are related by translation, not reflection (both halves put the
#: gate pad above their own diffusion), so gates use SAME_TRACK_PIN instead.
MIRROR_PIN: dict[tuple[str, str], tuple[str, str]] = {
    # cross-quad: the mirror of a bottom-row leg is the top-row leg of the
    # *other* device in the same column -- that is what makes it common-centroid
    ("inpair", "Q2_1_D"): ("inpair", "Q1_2_D"),
    ("inpair", "Q2_2_D"): ("inpair", "Q1_1_D"),
    ("stn", "Q2_1_D"): ("stn", "Q1_1_D"),
    ("stn", "Q2_1_S"): ("stn", "Q1_1_S"),
    ("latp", "Q2_1_D"): ("latp", "Q1_1_D"),
    ("latp", "Q2_1_S"): ("latp", "Q1_1_S"),
    ("rst", "Q2_1_D"): ("rst", "Q1_1_D"),
    ("absorb", "Q2_1_D"): ("absorb", "Q1_1_D"),
    ("absorb", "Q2_1_S"): ("absorb", "Q1_1_S"),
}

#: Gate-side counterpart: ``pin -> pin whose y-track it reuses verbatim``.
#: The two input nets' gate pads pair up by row (adjacent columns, same y);
#: routing both on one track equalises the input nets' trunk lengths.
SAME_TRACK_PIN: dict[tuple[str, str], tuple[str, str]] = {
    ("inpair", "Q2_1_G"): ("inpair", "Q1_1_G"),
    ("inpair", "Q2_2_G"): ("inpair", "Q1_2_G"),
}

# --- floorplan ----------------------------------------------------------------
#: Horizontal axis every diff_pair block's Q1/Q2 boundary is aligned to.
Y_AXIS = 45.0

#: Block left edges (um), left to right in signal-flow order:
#: preamp tail -> input pair -> steering pair -> latch tail -> cross-coupled
#: latch -> reset -> absorber caps -> clock cap -> clock shaper resistor.
#: Channels between blocks are ~2um -- room for the met2 trunks each carries.
BLOCK_X = {
    "ptail": 2.00,
    "inpair": 5.50,
    "stn": 11.00,
    "tail2": 15.00,
    "latp": 18.50,
    "rst": 22.50,
    "absorb": 30.00,
    "clkcap": 34.00,
    "rclks": 38.00,
}

#: The load-resistor strip is folded (res_array rows=2) and placed as one
#: horizontal strip above the active row, clear of the merged n-well (which
#: tops out below it) -- VDD straps its two B ends, OUTP1/OUTN1 reach its
#: two A ends.  rclks sits on the axis at the right edge.
RLOAD_ORIGIN = {"x": 5.50, "y": 65.00}

#: Per-net met2 trunk x positions (um).  Sorted across all nets these are
#: >= 0.5um apart (asserted at build time), clearing m2.2 (0.14) for a
#: 0.30um wire by a wide margin.  A net with N>1 entries gets N-1 met1
#: spines chaining them into one wire.
TRUNK_X: dict[str, tuple[float, ...]] = {
    "GND": (1.30, 17.90, 32.90),
    "VDD": (3.90, 19.60, 23.40, 24.50),
    "TAILP": (4.60,),
    "VINN": (5.10,),
    "VINP": (9.10,),
    "OUTP1": (9.60, 29.30),
    "OUTN1": (10.10, 29.80),
    "CLKT": (17.30, 21.80, 30.90, 36.40),
    "OUTP": (13.60, 20.60),
    "OUTN": (14.10, 21.10),
    "TAIL2": (13.00,),
    "CLK": (37.90,),
}

#: Preferred y for each multi-trunk net's spine.  Chosen in the sparsely
#: used bands below the device row (y ~ 10-15) and above it (y ~ 63-75).
SPINE_HINT_Y: dict[str, float] = {
    "GND": 10.0,
    "OUTP": 12.0,
    "OUTN": 11.0,
    "CLKT": 32.0,
    "OUTN1": 63.0,
    "OUTP1": 64.0,
    "VDD": 75.0,
}

#: Body-tie structures (see module docstring).  GND tie outside every
#: n-well at the left edge; VDD tie inside the merged pfet well at the right
#: of the rst block.
TAPS: dict[str, dict] = {
    "GND": {"x0": 0.00, "x1": 0.60, "y0": 42.00, "y1": 48.00},
    "VDD": {"x0": 24.20, "x1": 24.80, "y0": 42.00, "y1": 48.00},
}

#: One n-well rectangle enclosing the two pfet blocks' own local wells
#: (merging them) plus the VDD tie.  Kept clear of every nfet block and of
#: the rload strip above it.
NWELL_BOX = {"x0": 18.30, "y0": 28.00, "x1": 25.20, "y1": 63.00}

#: y-track grid for met1 branches.
TRACK_Y0 = 1.50
TRACK_Y1 = 90.00

COMPOSE_TOP = "gen_compose_0"


class RouteError(RuntimeError):
    """The greedy track router could not place a branch."""


class Pin:
    """A block port this router has to reach, in composed coordinates."""

    def __init__(self, block: str, port: str, x: float, ylo: float, yhi: float) -> None:
        self.block = block
        self.port = port
        self.x = x
        self.ylo = ylo
        self.yhi = yhi

    @property
    def ymid(self) -> float:
        return (self.ylo + self.yhi) / 2

    def clamp(self, y: float) -> float:
        return min(max(y, self.ylo), self.yhi)

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return f"{self.block}.{self.port}@({self.x:.3f},{self.ylo:.3f}..{self.yhi:.3f})"


def run(cmd: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    if check and result.returncode != 0:
        raise RuntimeError(
            f"command failed (rc={result.returncode}): {' '.join(cmd)}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


def gen_blocks(klt: str, pdk_args: list[str], out_dir: Path) -> dict[str, dict]:
    """Run every `klt gen` block; returns {block_id: parsed report}."""
    reports: dict[str, dict] = {}
    for block_id, generator, cell_name, params in BLOCKS:
        r = run(
            [klt, "gen", generator, "--params", json.dumps(params)] + pdk_args
            + ["--cell-name", cell_name, "-o", f"{block_id}.gds", "--format", "json"],
            cwd=out_dir,
        )
        report = json.loads(r.stdout)
        if report.get("error"):
            raise RuntimeError(f"klt gen {block_id}: {report['error']}")
        (out_dir / f"{block_id}.json").write_text(r.stdout)
        reports[block_id] = report
        print(f"  gen {block_id}: {report.get('device_count')} device(s), "
              f"bbox {report['bbox_um']}")
    return reports


def anchor_y(block_id: str, generator: str, report: dict) -> float:
    """Block-local y that should land on Y_AXIS (the symmetry axis).

    diff_pair: the Q1/Q2 boundary -- the generator places the Q1 gate row
    exactly on it, so Q1_1_G's y *is* the boundary (verified against the
    generated reports: for splits=1 it is the midpoint of Q1's device top
    and Q2's device bottom; for the splits=2 cross-quad it is the midline
    between the two device rows).  mos_array: the single device's centre
    (its S/D port y).  res_array: the strip centreline (R0_A's y).
    """
    if generator == "diff_pair":
        return port_y(report, "Q1_1_G")
    if generator == "mos_array":
        return port_y(report, "U0_S")
    return port_y(report, "R0_A")


def port_y(report: dict, port: str) -> float:
    for p in report["ports"]:
        if p["name"] == port:
            return p["y_um"]
    raise KeyError(f"port {port!r} not in report (ports: "
                   f"{[p['name'] for p in report['ports']]})")


def load_ports(report: dict) -> dict[str, tuple[float, float, float, float]]:
    return {
        p["name"]: (p["x_um"], p["y_um"], p["width_um"], p["direction_deg"])
        for p in report["ports"]
    }


def pin_from_port(block: str, port: str, info, dx: float, dy: float) -> Pin:
    """Translate a block-local port into a composed-coordinate Pin.

    A `klt gen` port reports its pad centre plus the pad's extent
    perpendicular to the direction it faces: S/D ports (facing +/-x) report
    the pad height; a gate port (facing +y) reports the pad width (the pad
    is square, 0.42um).
    """
    x_um, y_um, width_um, direction = info
    extent = width_um if direction in (0, 180) else 0.42
    half = extent / 2 - PAD_MARGIN_UM
    if half <= 0:
        raise RouteError(f"{block}.{port}: pad too small to land an mcon in")
    return Pin(block, port, x_um + dx, y_um + dy - half, y_um + dy + half)


def tap_shapes(spec: dict) -> tuple[list[tuple[tuple[int, int], Rect]], Pin]:
    """One body-tie structure: tap + li1 strip with a licon1 column."""
    x0, x1, y0, y1 = spec["x0"], spec["x1"], spec["y0"], spec["y1"]
    shapes = [
        (L_TAP, Rect.um(x0, y0, x1, y1)),
        (L_LI1, Rect.um(x0, y0, x1, y1)),
    ]
    cx = (x0 + x1) / 2
    y = y0 + LICON_PITCH_UM / 2
    while y + LICON_PITCH_UM / 2 <= y1 + 1e-9:
        shapes.append((L_LICON, Rect.centred(cx, y, LICON_UM, LICON_UM)))
        y += LICON_PITCH_UM
    pin = Pin("tie", "TIE", cx, y0 + PAD_MARGIN_UM, y1 - PAD_MARGIN_UM)
    return shapes, pin


def track_candidates(preferred: float) -> list[float]:
    count = int(round((TRACK_Y1 - TRACK_Y0) / TRACK_PITCH_UM)) + 1
    tracks = [TRACK_Y0 + i * TRACK_PITCH_UM for i in range(count)]
    return sorted(tracks, key=lambda y: (abs(y - preferred), y))


def union_area_um2(rects: list[Rect]) -> float:
    """Exact area of a union of axis-aligned rectangles (coordinate
    compression) -- overlap is common (pad/stub/run share corners) and
    double-counting it would make the symmetry numbers meaningless."""
    if not rects:
        return 0.0
    xs = sorted({v for r in rects for v in (r.x0, r.x1)})
    ys = sorted({v for r in rects for v in (r.y0, r.y1)})
    total = 0
    for i in range(len(xs) - 1):
        x0, x1 = xs[i], xs[i + 1]
        for j in range(len(ys) - 1):
            y0, y1 = ys[j], ys[j + 1]
            if any(r.x0 <= x0 and x1 <= r.x1 and r.y0 <= y0 and y1 <= r.y1 for r in rects):
                total += (x1 - x0) * (y1 - y0)
    return total / (DBU * DBU)


class Router:
    """Greedy met1 track router over a fixed set of met2 trunks.

    met1 carries every horizontal branch and the short vertical stub that
    lifts a branch off its pad's own y; met2 carries per-net vertical trunks
    plus nothing else.  Deterministic: candidate tracks ordered
    nearest-first with ties to the lower track, no randomness, no
    dict-ordering dependence.
    """

    def __init__(self) -> None:
        self.met1: list[tuple[str, Rect]] = []
        self.mcons: list[Rect] = []
        self.shapes: list[tuple[tuple[int, int], Rect]] = []
        self.trunk_span: dict[tuple[str, float], tuple[float, float]] = {}
        self.labels: list[tuple[tuple[int, int], str, float, float]] = []
        self.net_met1: dict[str, list[Rect]] = {}
        self.net_met2: dict[str, list[Rect]] = {}
        self.via_count: dict[str, int] = {}
        self.mcon_count: dict[str, int] = {}

    def met1_free(self, net: str, rects: list[Rect]) -> bool:
        clearance = nm(MET1_SPACE_UM)
        for owner, placed in self.met1:
            if owner == net:
                continue
            for rect in rects:
                if rect.within(placed, clearance):
                    return False
        return True

    def mcon_free(self, rect: Rect) -> bool:
        clearance = nm(MCON_SPACE_UM)
        return not any(rect.within(placed, clearance) for placed in self.mcons)

    def add_met1(self, net: str, rects: list[Rect]) -> None:
        for rect in rects:
            self.met1.append((net, rect))
            self.shapes.append((L_MET1, rect))
            self.net_met1.setdefault(net, []).append(rect)

    def add_via(self, net: str, trunk_x: float, y: float) -> None:
        self.shapes.append((L_VIA, Rect.centred(trunk_x, y, VIA_UM, VIA_UM)))
        self.via_count[net] = self.via_count.get(net, 0) + 1
        key = (net, trunk_x)
        lo, hi = self.trunk_span.get(key, (y, y))
        self.trunk_span[key] = (min(lo, y), max(hi, y))

    def add_mcon(self, net: str, x: float, y: float) -> None:
        rect = Rect.centred(x, y, MCON_UM, MCON_UM)
        self.mcons.append(rect)
        self.shapes.append((L_MCON, rect))
        self.mcon_count[net] = self.mcon_count.get(net, 0) + 1

    def _branch_rects(self, pin_x: float, pin_y: float, trunk_x: float,
                      track_y: float) -> list[Rect]:
        rects = [Rect.centred(pin_x, pin_y, PAD_UM, PAD_UM)]
        if abs(track_y - pin_y) > 1e-9:
            lo, hi = sorted((pin_y, track_y))
            rects.append(Rect.um(pin_x - WIRE_UM / 2, lo - WIRE_UM / 2,
                                 pin_x + WIRE_UM / 2, hi + WIRE_UM / 2))
        lo, hi = sorted((pin_x, trunk_x))
        rects.append(Rect.um(lo - WIRE_UM / 2, track_y - WIRE_UM / 2,
                             hi + WIRE_UM / 2, track_y + WIRE_UM / 2))
        return rects

    def reserve_pad(self, net: str, pin: Pin) -> None:
        """Keep other nets' met1 out of a gate pin's only legal pad spot.

        A gate li1 pad is 0.42x0.42um, so its mcon -- and the met1 pad that
        mcon must land in -- is pinned to a ~0.2um y window it cannot escape.
        Without this reservation an earlier net's horizontal branch can run
        straight through a later gate pin's only legal pad position.
        """
        half = PAD_UM / 2
        self.met1.append(
            (net, Rect.um(pin.x - half, pin.ylo - half, pin.x + half, pin.yhi + half))
        )

    def route_branch(self, net: str, pin: Pin, trunk_x: float,
                     preferred_y: float | None = None) -> float:
        for track_y in track_candidates(pin.ymid if preferred_y is None else preferred_y):
            pin_y = pin.clamp(track_y)
            mcon = Rect.centred(pin.x, pin_y, MCON_UM, MCON_UM)
            if not self.mcon_free(mcon):
                continue
            rects = self._branch_rects(pin.x, pin_y, trunk_x, track_y)
            if not self.met1_free(net, rects):
                continue
            self.add_mcon(net, pin.x, pin_y)
            self.add_met1(net, rects)
            self.add_via(net, trunk_x, track_y)
            return track_y
        raise RouteError(f"no free y-track for {net} pin {pin} -> trunk x={trunk_x}")

    def route_spine(self, net: str, xa: float, xb: float, preferred: float) -> float:
        lo, hi = sorted((xa, xb))
        for track_y in track_candidates(preferred):
            rect = Rect.um(lo - WIRE_UM / 2, track_y - WIRE_UM / 2,
                           hi + WIRE_UM / 2, track_y + WIRE_UM / 2)
            if not self.met1_free(net, [rect]):
                continue
            self.add_met1(net, [rect])
            self.add_via(net, xa, track_y)
            self.add_via(net, xb, track_y)
            return track_y
        raise RouteError(f"no free y-track for {net} spine {xa} <-> {xb}")

    def finish_trunks(self) -> None:
        for (net, trunk_x), (lo, hi) in sorted(self.trunk_span.items()):
            rect = Rect.um(trunk_x - WIRE_UM / 2, lo - WIRE_UM / 2,
                           trunk_x + WIRE_UM / 2, hi + WIRE_UM / 2)
            self.shapes.append((L_MET2, rect))
            self.net_met2.setdefault(net, []).append(rect)

    def summary(self) -> dict[str, dict[str, float | int]]:
        out: dict[str, dict[str, float | int]] = {}
        for net in sorted(set(self.net_met1) | set(self.net_met2)):
            met1 = union_area_um2(self.net_met1.get(net, []))
            met2 = union_area_um2(self.net_met2.get(net, []))
            out[net] = {
                "met1_area_um2": round(met1, 4),
                "met2_area_um2": round(met2, 4),
                "wire_area_um2": round(met1 + met2, 4),
                "via_count": self.via_count.get(net, 0),
                "mcon_count": self.mcon_count.get(net, 0),
            }
        return out


def build(reports: dict[str, dict]):
    """Floorplan + route.  Returns (draw params, compose request, summary)."""
    # -- trunk spacing invariant (re-derived, never trusted from the table) --
    all_trunks = sorted((x, net) for net, xs in TRUNK_X.items() for x in xs)
    for (xa, na), (xb, nb) in zip(all_trunks, all_trunks[1:]):
        if xb - xa < 0.5 - 1e-9:
            raise RouteError(
                f"met2 trunks {na}@{xa} and {nb}@{xb} are {xb - xa:.3f}um apart "
                f"(< 0.5um wire+space pitch)")

    origins: dict[str, dict[str, float]] = {}
    pins: dict[tuple[str, str], Pin] = {}
    for block_id, generator, _cell, _params in BLOCKS:
        if block_id == "rload":
            dx, dy = RLOAD_ORIGIN["x"], RLOAD_ORIGIN["y"]
        elif block_id == "rclks":
            dx = BLOCK_X[block_id]
            dy = Y_AXIS - anchor_y(block_id, generator, reports[block_id])
        else:
            dx = BLOCK_X[block_id]
            dy = Y_AXIS - anchor_y(block_id, generator, reports[block_id])
        origins[block_id] = {"x": dx, "y": dy}
        for port_name, info in load_ports(reports[block_id]).items():
            pins[(block_id, port_name)] = pin_from_port(block_id, port_name, info, dx, dy)

    router = Router()
    # Body ties + merged n-well first: their li1 pads are ordinary GND/VDD pins.
    router.shapes.append(
        (L_NWELL, Rect.um(NWELL_BOX["x0"], NWELL_BOX["y0"],
                          NWELL_BOX["x1"], NWELL_BOX["y1"])))
    tap_pins: dict[str, Pin] = {}
    for net in sorted(TAPS):
        shapes, pin = tap_shapes(TAPS[net])
        router.shapes.extend(shapes)
        tap_pins[net] = pin

    # Gate pads get their landing spots reserved before any net routes.
    for net in ROUTE_ORDER:
        for block, port in NET_PINS[net]:
            if port.endswith("_G") or port in ("R0_A", "R0_B"):
                router.reserve_pad(net, pins[(block, port)])

    tracks: dict[tuple[str, str], float] = {}
    for net in ROUTE_ORDER:
        trunks = TRUNK_X[net]
        keyed_pins: list[tuple[tuple[str, str] | None, Pin]] = [
            (key, pins[key]) for key in NET_PINS[net]
        ]
        if net in tap_pins:
            keyed_pins.append((None, tap_pins[net]))
        first_via = None
        for key, pin in keyed_pins:
            trunk_x = min(trunks, key=lambda tx: (abs(tx - pin.x), tx))
            mirror = MIRROR_PIN.get(key) if key is not None else None
            sibling = SAME_TRACK_PIN.get(key) if key is not None else None
            preferred = None
            if mirror in tracks:
                preferred = 2 * Y_AXIS - tracks[mirror]
            elif sibling in tracks:
                preferred = tracks[sibling]
            track_y = router.route_branch(net, pin, trunk_x, preferred)
            if key is not None:
                tracks[key] = track_y
            if first_via is None:
                first_via = (trunk_x, track_y)
        for xa, xb in zip(trunks, trunks[1:]):
            router.route_spine(net, xa, xb, SPINE_HINT_Y[net])
        if net in PIN_NETS:
            assert first_via is not None
            router.labels.append((L_MET1_PIN, net, first_via[0], first_via[1]))

    router.finish_trunks()

    draw_params = {
        "shapes": [
            {"layer": list(layer), "rect_um": rect.as_um()}
            for layer, rect in router.shapes
        ],
        "labels": [
            {"layer": list(layer), "text": text, "at_um": [x, y]}
            for layer, text, x, y in router.labels
        ],
    }
    order = [b for b, _g, _c, _p in BLOCKS] + ["route"]
    compose_request = {
        "schema": "klt.gen_compose.request/1",
        "pdk": {"variant": PDK_VARIANT},
        "blocks": [{"id": bid, "generator_report": f"{bid}.json"}
                   for bid, _g, _c, _p in BLOCKS]
        + [{"id": "route", "generator_report": "draw.json"}],
        "placement": {
            "strategy": "explicit",
            "order": order,
            "origins_um": {**origins, "route": {"x": 0.0, "y": 0.0}},
        },
        # Deliberately no `routing` block: klt gen-compose is a placer only
        # here; every wire lives in the route block (see module docstring).
        "connectivity": [],
    }

    per_net = router.summary()

    def symmetry(positive: str, negative: str) -> dict:
        a = float(per_net.get(positive, {}).get("wire_area_um2", 0.0))
        b = float(per_net.get(negative, {}).get("wire_area_um2", 0.0))
        denom = (a + b) / 2 or 1.0
        return {
            "pair": [positive, negative],
            "wire_area_um2": [a, b],
            "delta_um2": round(abs(a - b), 4),
            "delta_percent": round(100 * abs(a - b) / denom, 2),
        }

    route_summary = {
        "y_axis_um": Y_AXIS,
        "block_origins_um": origins,
        "trunk_x_um": {net: list(xs) for net, xs in TRUNK_X.items()},
        "nets": per_net,
        "differential_symmetry": [
            symmetry("OUTP", "OUTN"),
            symmetry("OUTP1", "OUTN1"),
            symmetry("VINP", "VINN"),
        ],
    }
    return draw_params, compose_request, route_summary


def parse_extract_devices(netlist_text: str) -> tuple[Counter, Counter]:
    """Count extracted devices by model, merging parallel same-net devices.

    The extraction deck emits one line per drawn transistor, so a
    ``splits=2`` cross-quad leg pair appears as two W=6.5um devices that the
    schematic declares as one W=13um device.  Counting therefore merges
    devices that share the same model AND all terminals (parallel
    combination), the way an LVS "combine parallel devices" pass does --
    and returns both the raw and merged counts so the merge is visible,
    not silent.  A device line looks like::

        X$1 \\$10 VINN \\$4 GND|VDD sky130_fd_pr__nfet_01v8 L=0.5 W=6.5 ...
        X$16 \\$3 CLK GND|VDD sky130_fd_pr__res_high_po l=1.75 w=0.42

    so the model is the one token carrying the PDK prefix, and the terminal
    tokens are those between the instance name and the model.
    """
    raw: Counter = Counter()
    groups: dict[tuple[str, tuple[str, ...]], int] = {}
    for line in netlist_text.splitlines():
        tok = line.split()
        if not tok or not tok[0].startswith("X"):
            continue
        model = next((t for t in tok if "sky130_fd_pr__" in t), None)
        if model is None:
            continue
        terminals = tuple(tok[1:tok.index(model)])
        raw[model] += 1
        groups[(model, terminals)] = groups.get((model, terminals), 0) + 1
    combined: Counter = Counter()
    for (model, _terminals), n in groups.items():
        combined[model] += 1
    return raw, combined


def count_check(combined: Counter) -> tuple[bool, dict]:
    """The AC's 16-device assertion: 9 nfet_01v8 + 4 pfet_01v8 + 3 high-R."""
    nfet = sum(v for k, v in combined.items() if "nfet_01v8" in k)
    pfet = sum(v for k, v in combined.items() if "pfet_01v8" in k)
    res = sum(v for k, v in combined.items() if "res_high_po" in k)
    other = {k: v for k, v in combined.items()
             if "nfet_01v8" not in k and "pfet_01v8" not in k and "res_high_po" not in k}
    ok = (nfet, pfet, res) == (9, 4, 3) and not other
    return ok, {
        "expected": {"nfet_01v8": 9, "pfet_01v8": 4, "res_high_po": 3, "total": 16},
        "found": {"nfet_01v8": nfet, "pfet_01v8": pfet, "res_high_po": res,
                  "total": nfet + pfet + res},
        "unexpected_models": other,
    }


def flow(klt: str, pdk_root: Path, out_dir: Path) -> int:
    """Run the full generate -> verify -> emit flow into ``out_dir``."""
    pdk_args = ["--pdk", PDK_VARIANT, "--pdk-root", str(pdk_root)]
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"gen_comparator.py: scratch {out_dir}")

    print("[1/7] klt gen blocks")
    reports = gen_blocks(klt, pdk_args, out_dir)

    print("[2/7] per-block DRC (each block must be clean in isolation)")
    drc_blocks = {}
    for block_id, _g, _c, _p in BLOCKS:
        r = run([klt, "drc", f"{block_id}.gds", "--deck", "sky130"] + pdk_args
                + ["--format", "json"], cwd=out_dir, check=False)
        envelope = json.loads(r.stdout) if r.stdout.strip() else {"error": r.stderr}
        drc_blocks[block_id] = envelope
        count = envelope.get("violation_count", "?")
        print(f"  drc {block_id}: violations={count}")
        if envelope.get("violation_count", 1) != 0:
            raise RuntimeError(f"block {block_id} is not DRC-clean in isolation")

    print("[3/7] floorplan + route")
    draw_params, compose_request, route_summary = build(reports)
    (out_dir / "draw.request.json").write_text(json.dumps(draw_params, indent=2) + "\n")
    (out_dir / "compose.request.json").write_text(json.dumps(compose_request, indent=2) + "\n")
    (out_dir / "route.summary.json").write_text(json.dumps(route_summary, indent=2) + "\n")
    for entry in route_summary["differential_symmetry"]:
        print(f"  {entry['pair'][0]}/{entry['pair'][1]} wire area "
              f"{entry['wire_area_um2'][0]} / {entry['wire_area_um2'][1]} um^2 "
              f"({entry['delta_percent']}% imbalance)")

    print("[4/7] klt draw (routing cell)")
    r = run([klt, "draw", "--params", "draw.request.json", "--cell-name", "ROUTE",
             "-o", "route.gds", "--format", "json"], cwd=out_dir)
    (out_dir / "draw.json").write_text(r.stdout)

    print("[5/7] klt gen-compose (explicit placement)")
    r = run([klt, "gen-compose", "compose.request.json", "--format", "json"],
            cwd=out_dir)
    (out_dir / "compose.json").write_text(r.stdout)
    if not (out_dir / f"{COMPOSE_TOP}.gds").exists():
        raise RuntimeError(f"gen-compose did not write {COMPOSE_TOP}.gds")
    (out_dir / f"{COMPOSE_TOP}.gds").rename(out_dir / "comparator.gds")

    print("[6/7] composed DRC")
    r = run([klt, "drc", "comparator.gds", "--deck", "sky130"] + pdk_args
            + ["--format", "json"], cwd=out_dir, check=False)
    drc = json.loads(r.stdout) if r.stdout.strip() else {"error": r.stderr}
    (out_dir / "drc.json").write_text(json.dumps(drc, indent=2) + "\n")
    print(f"  composed drc: violations={drc.get('violation_count', '?')}")

    print("[7/7] klt extract (device count evidence)")
    run([klt, "extract", "comparator.gds", "--deck", "sky130", "--top", COMPOSE_TOP]
        + pdk_args + ["-o", "comparator.extract.spice", "--format", "json"],
        cwd=out_dir)
    netlist = (out_dir / "comparator.extract.spice").read_text()
    raw, combined = parse_extract_devices(netlist)
    ok, tally = count_check(combined)
    extract_evidence = {
        "tool": {"klt_pin": KLT_PIN, "deck": "sky130", "top_cell": COMPOSE_TOP},
        "method": ("klt extract over layout/comparator.gds; devices counted by "
                   "model from the extracted netlist (parallel same-net devices "
                   "merged, mirroring an LVS combine pass -- the raw pre-merge "
                   "counts are recorded beside the merged ones)"),
        "raw_counts": dict(sorted(raw.items())),
        "merged_counts": dict(sorted(combined.items())),
        "check": tally,
        "pass": ok,
    }
    (out_dir / "extract-device-count.json").write_text(
        json.dumps(extract_evidence, indent=2) + "\n")
    print(f"  extract device count (merged): {tally['found']} "
          f"{'PASS' if ok else 'FAIL'}")
    if not ok:
        raise RuntimeError("extract device count check FAILED -- see above")
    return 0


def emit(out_dir: Path, layout_dir: Path) -> dict:
    """Copy the verified deliverables from scratch into layout/ and return
    the composed bbox (the measured-area source)."""
    compose = json.loads((out_dir / "compose.json").read_text())
    deliverables = (
        "comparator.gds",
        ("compose.json", "compose-report.json"),
        ("route.summary.json", "route-summary.json"),
        "extract-device-count.json",
    )
    for item in deliverables:
        src, dst = item if isinstance(item, tuple) else (item, item)
        shutil.copyfile(out_dir / src, layout_dir / dst)
    bbox = compose.get("bbox_um") or compose.get("composed_bbox_um")
    if not bbox:
        bbox = compose.get("bbox")
    return bbox


def emit_drc_evidence(klt: str, pdk_args: list[str], repo_root: Path) -> None:
    """Re-run the composed DRC against the *emitted* GDS and commit it.

    This is T1 item 3's citable evidence (issue #46), distinct from the
    step-[6/7] run inside ``_gen/``: that one runs with ``cwd=_gen`` on a
    bare ``comparator.gds``, so the envelope it records names a path that
    does not resolve from the repo root where ``klt signoff`` /
    ``scripts/check-t1-signoff.py`` grade it.  Re-running from the repo root
    on ``layout/comparator.gds`` records both the path CI resolves and the
    ``provenance.input.content_hash`` the manifest pins -- so regenerating
    the GDS without refreshing this file renders item 3 ``unmet`` (stale
    evidence) rather than grading a superseded run.

    Unlike step [6/7] this checks the verdict: committing an envelope that
    records violations as *signoff evidence* would be a false claim.
    """
    r = run([klt, "drc", "layout/comparator.gds", "--deck", "sky130"] + pdk_args
            + ["--format", "json"], cwd=repo_root, check=False)
    envelope = json.loads(r.stdout) if r.stdout.strip() else {"error": r.stderr}
    if r.returncode != 0 or envelope.get("status") != "clean":
        raise RuntimeError(
            f"signoff DRC over layout/comparator.gds is not clean "
            f"(rc={r.returncode}, status={envelope.get('status')!r}, "
            f"violations={envelope.get('violation_count')}) -- refusing to "
            "commit it as T1 item 3 evidence"
        )
    (repo_root / "layout" / "drc-report.json").write_text(
        json.dumps(envelope, indent=2) + "\n")
    cov = envelope.get("coverage") or {}
    print("  signoff drc: status=clean, "
          f"layers_in_stream_without_rules={len(cov.get('layers_in_stream_without_rules', []))}, "
          f"rules_skipped={len(cov.get('rules_skipped', []))}, "
          f"deck_scope={len(cov.get('deck_scope', []))} "
          "(disclosure: layout/README.md)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="regenerate into a temp dir and byte-compare the "
                             "GDS against layout/comparator.gds; commit nothing")
    parser.add_argument("--klt", default="klt")
    parser.add_argument("--pdk-root", default=PDK_ROOT_DEFAULT)
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    pdk_root = Path(args.pdk_root).expanduser()

    if args.check:
        committed = repo_root / "layout" / "comparator.gds"
        if not committed.exists():
            print("gen_comparator.py --check: layout/comparator.gds does not "
                  "exist yet -- nothing to compare against", file=sys.stderr)
            return 1
        with tempfile.TemporaryDirectory(prefix="loom-layout-check-") as tmp_str:
            tmp = Path(tmp_str)
            rc = flow(args.klt, pdk_root, tmp)
            if rc != 0:
                return rc
            fresh = tmp / "comparator.gds"
            a, b = committed.read_bytes(), fresh.read_bytes()
            if a == b:
                print("gen_comparator.py --check: PASS -- regenerated GDS "
                      "is byte-identical to layout/comparator.gds")
                return 0
            print("gen_comparator.py --check: FAIL -- regenerated GDS "
                  f"differs (committed {len(a)} bytes vs fresh {len(b)} bytes)",
                  file=sys.stderr)
            return 1
    rc = flow(args.klt, pdk_root, repo_root / "layout" / "_gen")
    if rc != 0:
        return rc
    bbox = emit(repo_root / "layout" / "_gen", repo_root / "layout")
    print("[emit] signoff DRC over the emitted GDS (T1 item 3 evidence)")
    emit_drc_evidence(args.klt, ["--pdk", PDK_VARIANT, "--pdk-root", str(pdk_root)],
                      repo_root)
    area = None
    if bbox:
        area = round((bbox["x1"] - bbox["x0"]) * (bbox["y1"] - bbox["y0"]), 2)
    print(f"gen_comparator.py: emitted deliverables to layout/ "
          f"(bbox {bbox}, area {area} um^2)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
