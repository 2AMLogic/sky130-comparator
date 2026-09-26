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
``layout/extract-device-count.json``, ``layout/drc-report.json``,
``layout/lvs-request.json`` + ``layout/lvs-report.json``,
``layout/lvs-coverage-probe.json``, and ``layout/erc-spec.json`` +
``layout/erc-report.json`` + ``layout/erc-coverage-probe.json`` (the last
seven re-run from the repo root against the *emitted* GDS -- see
``emit_drc_evidence`` / ``emit_lvs_evidence`` / ``emit_lvs_coverage_probe`` /
``emit_erc_evidence`` / ``emit_erc_coverage_probe``).
``drc-report.json`` is what ``manifests/sky130-comparator.json`` cites for
T1 item 3; ``lvs-report.json`` is committed but deliberately NOT cited for
item 4, and layout/README.md's "Why item 4 is left uncited" says why; the
``erc-*`` trio is likewise committed and deliberately NOT cited for item 11
("Why item 11 is left uncited" in the same file).

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

* **Devices** are 100% ``klt gen`` geometry -- one block per schematic
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
  1.06-1.13x at the DR-004 anchors, a 1% stretch-bound breach already
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

* **Body ties**: a p-substrate tap outside every n-well contacted up to GND,
  and an n-well tap inside the merged pfet well contacted up to VDD, so
  ``klt extract`` sees real supply-referenced bodies rather than a synthesized
  proxy net -- without them, item 4's LVS would not be comparing the layout
  this repo claims to deliver (``lvs-report.json`` records
  ``body_verification.status: "verified"`` because of them).  They are also
  the two ``ties[]`` entries the T1 item 11 supply spec declares
  (``build_erc_spec``), and the only 65/44 geometry in the stream -- which is
  what makes that spec's ``tap_is_dedicated`` a measured fact rather than an
  assumption (``emit_erc_evidence`` re-counts it before committing).

Determinism: no randomness and no dict-ordering dependence anywhere (the
router's candidate ordering is a pure function of the geometry), so a
re-run at the same klt pin reproduces ``comparator.gds`` byte-for-byte --
that is exactly what ``--check`` asserts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

# --- layer table (sky130A GDS numbers, as klt's own curated deck names them) --
L_NWELL = (64, 20)
L_DIFF = (65, 20)
L_TAP = (65, 44)
L_POLY = (66, 20)
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

# --- T1 item 4 (LVS) request -------------------------------------------------
# The reference side is the schematic's own derivation product -- what
# ``design/netlist.sh`` writes out of ``design/comparator.sch``, never
# hand-edited (``./design/netlist.sh --check`` asserts exactly that).  It is
# the item-1 netlist ``manifests/design-evidence-tiers.md`` item 4 requires the
# compare to run against.
LVS_REFERENCE = "sim/comparator-decision/testbench/comparator_core.spice"
LVS_TOP = "gen_compose_0"

# sky130 spells its poly resistor two ways: the geometry-parameterised
# primitive ``sky130_fd_pr__res_high_po`` (``l``/``w`` at the call site) and a
# family of fixed-width wrappers that instantiate it with the width baked into
# the *name* -- ``sky130_fd_pr__res_high_po_0p35`` is literally
# ``x0 r0 r1 sub sky130_fd_pr__res_high_po l=l w=0.35``.  The schematic uses
# the wrapper; klt's extraction deck curates only the primitive, so
# ``reference.device_map`` binds one to the other.  The object form is
# required because this is a 3-terminal resistor, not a 4-terminal MOS.
#
# ``length_param``/``width_param`` deliberately name a parameter no call site
# carries, which makes the conversion carry *no* geometry for this class.  That
# is not a convenience: klt 0.6.0's subckt-call conversion rejects a call that
# supplies one of L/W without the other ("both 'L' and 'W' must be given
# together"), and a fixed-width wrapper structurally cannot supply W -- so
# without this the compare does not run at all.  It is verdict-neutral, and
# ``layout/README.md`` -> "LVS signoff" records the negative control that
# proves it: KLayout compares only a resistor's *primary* parameter R (which
# this reference form excludes as a documented ``0`` placeholder), never the
# secondary L/W.  A reference carrying a deliberately absurd resistor width
# still grades ``match``.
LVS_RESISTOR_WRAPPER = "sky130_fd_pr__res_high_po_0p35"
LVS_GEOMETRY_NOT_ON_CARD = "__geometry_not_on_card__"

LVS_REQUEST = {
    "engine": "klayout",
    "layout": {
        "file": "layout/comparator.gds",
        "deck": "sky130",
        "top": LVS_TOP,
    },
    "reference": {
        "netlist": LVS_REFERENCE,
        "form": "subckt-call",
        "deck": "sky130",
        "device_map": {
            LVS_RESISTOR_WRAPPER: {
                "kind": "resistor",
                "class": "res_high_po",
                "length_param": LVS_GEOMETRY_NOT_ON_CARD,
                "width_param": LVS_GEOMETRY_NOT_ON_CARD,
            },
        },
    },
    # The layout folds the input pair into two W=6.5um legs per device (the
    # common-centroid cross-quad); the schematic states one W=13um device.
    # combine_devices is what reconciles the two -- the same fold
    # extract-device-count.json's "merged_counts" already records.
    "options": {"combine_devices": True},
}

# --- T1 item 11 (ERC, power delivery *structural*) supply spec ----------------
# ``klt erc``'s spec document, built by :func:`build_erc_spec` and committed as
# ``layout/erc-spec.json``.  Item 11 asks one question -- "is the supply
# connected to what it powers?" -- and grades it on: at least one
# ``"kind": "supply"`` net declared, at least one ``ties[]`` entry declared and
# actually checked (not skipped as degenerate), and no supply-side finding.
# IR drop and electromigration (``klt power``) are explicitly outside it.
#
# The supply-spec run is the *structural* half only.  What it is NOT is a claim
# about the antenna verdict it also carries, or about T1 item 4 -- see
# layout/README.md -> "ERC: supply-spec run, committed -- and why T1 item 11 is
# still not claimed".
ERC_SPEC_PATH = "layout/erc-spec.json"
ERC_REPORT_PATH = "layout/erc-report.json"
ERC_PROBE_PATH = "layout/erc-coverage-probe.json"

#: ``klt erc``'s antenna-ratio limit *table* name (not the PDK variant): the
#: flag selects a curated limit table and needs no PDK install, unlike
#: ``klt drc --pdk sky130A --pdk-root ...``.
ERC_ANTENNA_PDK = "sky130"

#: The curated extraction deck whose own device-body markers are carved out of
#: the matching conductor role (klayout-tools#2183/#2204).  Without it the
#: three poly resistor *bodies* read as plain poly wires and VDD conducts
#: through them into OUTP1/OUTN1 -- the false-positive caveat the item-11
#: checklist text requires be checked before a finding is believed.  With it,
#: ``provenance.devices[]`` records the carve-out (``res_high_po``, 66/20) so
#: the narrowing is stated in the evidence rather than applied silently.
ERC_DECK = "sky130"

#: Fabrication-order conductor roles the supplies route on.  ``stackup[0]``
#: must be the gate role; ``active_layer`` makes the gate area ``poly n diff``
#: rather than raw poly-net area, so a poly shape with no diffusion under it
#: (a resistor body) is not counted as a gate.
ERC_STACKUP = (
    {"name": "poly", "layer": L_POLY, "role": "gate", "active_layer": L_DIFF},
    {"name": "li1", "layer": L_LI1},
    {"name": "met1", "layer": L_MET1, "label_layer": L_MET1_PIN},
    {"name": "met2", "layer": L_MET2},
)

#: The cuts between those roles.  ``diff`` is deliberately NOT a stackup role:
#: registering it as a conductor would short every MOS source to its own drain
#: through the channel and collapse VDD and GND into one island (the
#: ``supply_short_via_diff`` probe row measures exactly that).  licon1 over
#: diffusion therefore lands on li1 only, which is the real connection.
ERC_VIAS = (
    {"name": "licon1", "layer": L_LICON, "between": ("poly", "li1")},
    {"name": "mcon", "layer": L_MCON, "between": ("li1", "met1")},
    {"name": "via", "layer": L_VIA, "between": ("met1", "met2")},
)

#: The supplies whose continuity item 11 is about, in the order the spec
#: declares them.  Both are labelled on met1.pin by the router (``PIN_NETS``).
ERC_SUPPLY_NETS = ("VDD", "GND")


def layer_id(layer: tuple[int, int]) -> str:
    """One GDS layer/datatype pair in klt's ``"<layer>/<datatype>"`` spelling."""
    return f"{layer[0]}/{layer[1]}"


def substrate_boxes(bbox: dict) -> list[list[float]]:
    """The p-substrate region this block asserts for its GND tie: the top
    cell's own extent minus the drawn n-well, as ``[left, bottom, right, top]``
    micrometre boxes.

    sky130 draws no pwell/tub layer for a native-substrate NMOS block -- there
    is nothing to name as ``ties[].well_layer`` -- so the GND tie uses klt's
    native-substrate form (``"well_layer": null`` + ``well_boxes``,
    klayout-tools#2255) and names the region instead.  Derived from the
    composed bbox and ``NWELL_BOX`` rather than transcribed, so a floorplan
    move carries the assertion with it.

    Held to klt's own falsifiability test: an assertion covering the whole
    top-cell extent (to within 1%) is graded *skipped*
    (``degenerate_well_assertion``), not clean, because "the entire die is the
    substrate" makes ``erc.missing_tie`` satisfiable by any contact anywhere.
    Subtracting the n-well leaves 241.5 um^2 of the 3330.0 um^2 extent
    uncovered (7.25%), and the four boxes merge into the one ring-shaped
    polygon the substrate actually is -- which must therefore contain a tap
    that reaches GND.  The ``degenerate_well`` probe row asserts the
    whole-extent form is still rejected.
    """
    if not bbox:
        raise RuntimeError(
            "klt gen-compose reported no composed bbox, so the GND tie has no "
            "top-cell extent to assert its substrate region against")
    x0, y0 = round(bbox["x0"], 3), round(bbox["y0"], 3)
    x1, y1 = round(bbox["x1"], 3), round(bbox["y1"], 3)
    w = NWELL_BOX
    boxes = []
    if w["x0"] > x0:
        boxes.append([x0, y0, w["x0"], y1])
    if w["x1"] < x1:
        boxes.append([w["x1"], y0, x1, y1])
    if w["y0"] > y0:
        boxes.append([w["x0"], y0, w["x1"], w["y0"]])
    if w["y1"] < y1:
        boxes.append([w["x0"], w["y1"], w["x1"], y1])
    if not boxes:
        raise RuntimeError(
            "the drawn n-well covers the whole composed extent, so there is no "
            "p-substrate region to assert for the GND tie")
    return boxes


def build_erc_spec(bbox: dict) -> dict:
    """The ``klt erc`` supply spec for the committed GDS.

    ``tap_is_dedicated: true`` on both ties is the load-bearing declaration:
    klt grades a tie whose tap region is "whatever that layer draws inside the
    well" as *skipped* rather than clean (klayout-tools#2199), because an
    ordinary PMOS source contact would then satisfy it.  sky130's ``tap``
    (65/44) is a tap-only layer by PDK definition, and this stream draws it in
    exactly two places -- the two body-tie structures ``TAPS`` places (``klt
    gen`` blocks draw only nwell/diff/poly/licon1/li1, never tap).  Asserted,
    not assumed: ``emit_erc_evidence`` re-counts 65/44 against ``TAPS`` before
    it will commit the envelope.
    """
    return {
        "stackup": [
            {
                "name": entry["name"],
                "layer": layer_id(entry["layer"]),
                **({"role": entry["role"]} if "role" in entry else {}),
                **({"active_layer": layer_id(entry["active_layer"])}
                   if "active_layer" in entry else {}),
                **({"label_layer": layer_id(entry["label_layer"])}
                   if "label_layer" in entry else {}),
            }
            for entry in ERC_STACKUP
        ],
        "vias": [
            {
                "name": via["name"],
                "layer": layer_id(via["layer"]),
                "between": list(via["between"]),
            }
            for via in ERC_VIAS
        ],
        "nets": [{"name": net, "kind": "supply"} for net in ERC_SUPPLY_NETS],
        "ties": [
            {
                "name": "psub_gnd",
                "well_layer": None,
                "well_boxes": substrate_boxes(bbox),
                "tap_layer": layer_id(L_TAP),
                "tap_is_dedicated": True,
                "connect_to": "li1",
                "net": "GND",
            },
            {
                "name": "nwell_vdd",
                "well_layer": layer_id(L_NWELL),
                "tap_layer": layer_id(L_TAP),
                "tap_is_dedicated": True,
                "connect_to": "li1",
                "net": "VDD",
            },
        ],
    }


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


def run(cmd: list[str], cwd: Path | None = None, check: bool = True,
        stdin_text: str | None = None) -> subprocess.CompletedProcess:
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd,
                            input=stdin_text)
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


def _run_lvs(klt: str, request: dict, repo_root: Path) -> tuple[dict, int]:
    """Run one ``klt lvs`` compare from ``repo_root``; return (envelope, rc).

    The request goes in on **stdin** rather than as a file path on purpose:
    relative paths inside a request *file* resolve against that file's own
    directory, while the stdin form resolves them against the current working
    directory.  Running from the repo root with the stdin form is therefore
    what makes the envelope echo repo-root-relative paths
    (``layout/comparator.gds``, ``sim/.../comparator_core.spice``) -- the paths
    CI and ``klt signoff`` resolve -- instead of host-specific absolute ones.
    """
    r = run([klt, "lvs", "-", "--format", "json"], cwd=repo_root, check=False,
            stdin_text=json.dumps(request))
    if not r.stdout.strip():
        raise RuntimeError(f"klt lvs produced no output (rc={r.returncode}): {r.stderr}")
    return json.loads(r.stdout), r.returncode


#: Negative controls for the LVS compare, each a textual perturbation of the
#: committed reference netlist plus the verdict that perturbation MUST
#: produce.  A compare that cannot fail grades nothing (``sim/selftest.sh``'s
#: stage-4 discipline, applied to a signoff artifact), so ``mos_*`` and
#: ``connectivity`` establish that this one bites.  The ``res_*`` rows go
#: further and measure the compare's *reach*, which is the half that decides
#: whether the verdict may be cited: at klt's default parameter scope the
#: block's known drawn-versus-schematic resistor width delta is invisible,
#: and the two ``res_width_forced_*`` rows show the same tool reports it as a
#: ``device.property`` error as soon as the geometry is asked for.  That pair
#: is why T1 item 4 is NOT claimed from this run -- see layout/README.md.
#:
#: ``rewrite_resistors`` restates the three ``XR_`` cards as the generic
#: parent device at an explicit width -- exactly the expansion the PDK's own
#: fixed-width wrapper model file performs -- so a probe can vary a width the
#: signoff request structurally cannot express.  ``compare_parameters`` is
#: ``klt lvs``'s own ``options.compare_parameters``.
LVS_PROBES = (
    {
        "id": "res_width_as_schematic",
        "perturbation": "reference resistors restated at the fixed-width "
                        "wrapper's own w=0.35um against the drawn 0.42um",
        "rewrite_resistors": 0.35,
        "substitutions": (),
        "expected_status": "match",
        "covers": False,
        "reads": "at the default parameter scope the drawn-versus-schematic "
                 "width delta is NOT detected by this compare",
    },
    {
        "id": "res_width_10x",
        "perturbation": "reference resistors restated at w=3.5um, 10x the "
                        "schematic device and 8.3x the drawn geometry",
        "rewrite_resistors": 3.5,
        "substitutions": (),
        "expected_status": "match",
        "covers": False,
        "reads": "resistor width takes no part in the default compare at "
                 "all -- the 0.35/0.42 delta is not merely inside a tolerance",
    },
    {
        "id": "res_length_2x",
        "perturbation": "R_LP length doubled, 22um -> 44um",
        "rewrite_resistors": 0.35,
        "substitutions": (("XR_LP OUTN1 VDD GND sky130_fd_pr__res_high_po L=22",
                           "XR_LP OUTN1 VDD GND sky130_fd_pr__res_high_po L=44"),),
        "expected_status": "match",
        "covers": False,
        "reads": "resistor length is not compared either -- a drawn "
                 "resistor's whole geometry dimension is unverified here",
    },
    {
        "id": "res_width_forced_schematic",
        "perturbation": "as res_width_as_schematic, plus the resistor class's "
                        "geometry forced into the compare via "
                        "options.compare_parameters {res_high_po: [L, W]}",
        "rewrite_resistors": 0.35,
        "compare_parameters": {"res_high_po": ["L", "W"]},
        "substitutions": (),
        "expected_status": "mismatch",
        "covers": True,
        "reads": "asked for, the compare DOES report the drawn-versus-"
                 "schematic width delta -- device.property 'w_um', layout "
                 "0.42 vs reference 0.35, on all three resistors. The delta "
                 "is real and LVS-detectable; the signoff run's match rests "
                 "on the default parameter scope not asking",
    },
    {
        "id": "res_width_forced_drawn",
        "perturbation": "the same forced compare, with the reference "
                        "resistors restated at the DRAWN w=0.42um",
        "rewrite_resistors": 0.42,
        "compare_parameters": {"res_high_po": ["L", "W"]},
        "substitutions": (),
        "expected_status": "match",
        "covers": True,
        "reads": "attribution control for the row above: the same forced "
                 "compare matches once the reference carries the drawn "
                 "width, so that mismatch is the 0.35/0.42 delta itself and "
                 "not an artifact of forcing parameters into the compare",
    },
    {
        "id": "mos_width",
        "perturbation": "M_PINN width 13um -> 12um",
        "rewrite_resistors": None,
        "substitutions": (("VINN TAILP GND sky130_fd_pr__nfet_01v8 L=0.5 W=13",
                           "VINN TAILP GND sky130_fd_pr__nfet_01v8 L=0.5 W=12"),),
        "expected_status": "mismatch",
        "covers": True,
        "reads": "MOSFET width IS compared",
    },
    {
        "id": "mos_length",
        "perturbation": "M_PINN length 0.5um -> 0.6um",
        "rewrite_resistors": None,
        "substitutions": (("VINN TAILP GND sky130_fd_pr__nfet_01v8 L=0.5 W=13",
                           "VINN TAILP GND sky130_fd_pr__nfet_01v8 L=0.6 W=13"),),
        "expected_status": "mismatch",
        "covers": True,
        "reads": "MOSFET length IS compared",
    },
    {
        "id": "connectivity",
        "perturbation": "M_RST_N drain moved from OUTN to OUTP",
        "rewrite_resistors": None,
        "substitutions": (("XM_RST_N OUTN CLKT VDD VDD",
                           "XM_RST_N OUTP CLKT VDD VDD"),),
        "expected_status": "mismatch",
        "covers": True,
        "reads": "connectivity IS compared",
    },
)

#: Matches one ``XR_<name> <n1> <n2> <n3> sky130_fd_pr__res_high_po_0p35 L=<l>``
#: card head in the committed reference netlist.
_RES_CARD_RE = re.compile(
    rf"^(XR_\S+(?:\s+\S+){{3}}\s+){LVS_RESISTOR_WRAPPER}(\s+L=\S+)(.*)$",
    re.MULTILINE)


def _probe_reference(base: str, probe: dict) -> str:
    """Apply one probe's perturbation to the reference netlist text.

    Every substitution must actually bite -- a perturbation that silently
    failed to apply would turn a negative control into a second copy of the
    baseline and quietly assert nothing.
    """
    text = base
    width = probe["rewrite_resistors"]
    if width is not None:
        text, n = _RES_CARD_RE.subn(
            rf"\g<1>sky130_fd_pr__res_high_po\g<2> w={width}\g<3>", text)
        if n != 3:
            raise RuntimeError(
                f"LVS probe {probe['id']}: expected to rewrite 3 resistor "
                f"cards, rewrote {n} -- the reference netlist moved")
    for old, new in probe["substitutions"]:
        if old not in text:
            raise RuntimeError(
                f"LVS probe {probe['id']}: perturbation target not found in "
                f"the reference netlist ({old!r}) -- the netlist moved and "
                "this control would assert nothing")
        text = text.replace(old, new, 1)
    return text


def _property_findings(envelope: dict) -> list[dict]:
    """Distinct ``device.property`` (parameter, layout, reference) triples.

    One row per distinct compared-parameter disagreement, deduplicated over
    the device instances reporting it -- so the probe record carries the
    numbers a disagreement is actually about (``w_um`` 0.42 vs 0.35), not
    just a category tally.
    """
    seen: list[dict] = []
    for entry in envelope.get("mismatches") or ():
        if entry.get("category") != "device.property":
            continue
        prop = entry.get("property") or {}

        def rounded(value):
            # 9 dp kills float-repr noise (0.35000000000000003) without
            # touching any resolution a device parameter means anything at.
            return round(value, 9) if isinstance(value, float) else value

        row = {"class": (entry.get("device") or {}).get("class"),
               "parameter": prop.get("name"),
               "layout": rounded(prop.get("layout")),
               "reference": rounded(prop.get("reference"))}
        if row not in seen:
            seen.append(row)
    return seen


def _supply_pairing(envelope: dict) -> dict:
    """Whether this compare's ``net_correspondence`` pairs each supply net to a
    reference-side net -- the exact predicate T1 item 11's analog LVS half is
    graded on (``klt signoff``'s ``_lvs_reference_carries_supplies``).

    Measured per probe row because the predicate turns out **not** to be
    independent of the compare's overall verdict: ``net_correspondence`` lists
    only *matched* nets, so every ``match`` pairs both supplies and every
    ``mismatch`` drops at least one -- including ``mos_width``, whose
    perturbation is a transistor width and has nothing to do with the rails.
    Item 11's LVS half therefore carries no information beyond "item 4's
    envelope reports match", which is the measurement behind
    layout/README.md -> "Why item 11 is left uncited".
    """
    paired = {
        str(row.get("layout")).upper()
        for row in envelope.get("net_correspondence") or ()
        if isinstance(row, dict) and row.get("layout") and row.get("reference")
    }
    return {
        "net_correspondence_rows": len(envelope.get("net_correspondence") or ()),
        "nets_matched": ((envelope.get("counts") or {}).get("nets") or {})
        .get("matched"),
        "supplies_paired": {net: net.upper() in paired
                            for net in ERC_SUPPLY_NETS},
        "all_supplies_paired": all(net.upper() in paired
                                   for net in ERC_SUPPLY_NETS),
    }


def emit_lvs_coverage_probe(klt: str, repo_root: Path, signoff: dict) -> None:
    """Measure what the signoff LVS `match` does and does not cover.

    A `klt lvs` envelope states its verdict, not its reach.  Two things about
    this design's reach have to be stated with any claim and neither is
    readable off the envelope: that the compare can fail at all, and that the
    block's known drawn-versus-schematic resistor width delta (0.42um drawn
    vs the schematic's ``res_high_po_0p35``) sits in a blind spot of it.
    Both are measured here -- one compare per row of ``LVS_PROBES``, each
    against a perturbed **scratch** copy of the reference netlist; the
    committed ``sim/.../comparator_core.spice`` is never written to.

    Writes ``layout/lvs-coverage-probe.json``, and raises if any row's
    observed verdict differs from the one it asserts.
    """
    base = (repo_root / LVS_REFERENCE).read_text()
    rows = []
    with tempfile.TemporaryDirectory(prefix="loom-lvs-probe-") as tmp_str:
        tmp = Path(tmp_str)
        for probe in LVS_PROBES:
            scratch = tmp / f"{probe['id']}.spice"
            scratch.write_text(_probe_reference(base, probe))
            request = json.loads(json.dumps(LVS_REQUEST))
            request["reference"]["netlist"] = str(scratch)
            if probe["rewrite_resistors"] is not None:
                # The cards now name the curated generic device, so the
                # fixed-width wrapper mapping no longer applies.
                request["reference"]["device_map"] = {}
            if probe.get("compare_parameters") is not None:
                request["options"]["compare_parameters"] = \
                    probe["compare_parameters"]
            envelope, _rc = _run_lvs(klt, request, repo_root)
            observed = envelope.get("status")
            rows.append({
                "id": probe["id"],
                "perturbation": probe["perturbation"],
                "compare_parameters": probe.get("compare_parameters"),
                "compare_covers_this": probe["covers"],
                "reads_as": probe["reads"],
                "expected_status": probe["expected_status"],
                "observed_status": observed,
                "error_count": envelope.get("error_count"),
                "category_counts": envelope.get("category_counts"),
                "property_findings": _property_findings(envelope),
                "supply_pairing": _supply_pairing(envelope),
                "pass": observed == probe["expected_status"],
            })
            print(f"    probe {probe['id']}: {observed} "
                  f"(expected {probe['expected_status']}) "
                  f"{'PASS' if rows[-1]['pass'] else 'FAIL'}")
    ok = all(row["pass"] for row in rows)
    evidence = {
        "tool": {"klt_pin": KLT_PIN, "engine": signoff.get("engine"),
                 "engine_version": (signoff.get("environment") or {})
                 .get("engine_version")},
        "method": (
            "negative controls for layout/lvs-report.json: one klt lvs "
            "compare per row, each against a perturbed scratch copy of "
            f"{LVS_REFERENCE} (the committed netlist is never written to) "
            "and the same layout/comparator.gds the signoff run used. A row "
            "with compare_covers_this=true asserts the compare DETECTS that "
            "defect (so the signoff match is not vacuous); a row with "
            "compare_covers_this=false asserts it does NOT -- those are the "
            "holes layout/README.md's LVS section discloses. Each row also "
            "records supply_pairing, the measurement T1 item 11's LVS half is "
            "graded on (klt signoff's _lvs_reference_carries_supplies): see "
            "layout/README.md -> 'Why item 11 is left uncited'."),
        "signoff_report": "layout/lvs-report.json",
        "signoff_status": signoff.get("status"),
        "signoff_layout_sha256": (signoff.get("environment") or {})
        .get("layout_sha256"),
        "signoff_reference_sha256": (signoff.get("environment") or {})
        .get("reference_sha256"),
        "signoff_supply_pairing": _supply_pairing(signoff),
        "probes": rows,
        "pass": ok,
    }
    (repo_root / "layout" / "lvs-coverage-probe.json").write_text(
        json.dumps(evidence, indent=2) + "\n")
    if not ok:
        raise RuntimeError(
            "LVS coverage probe FAILED -- a negative control did not produce "
            "the verdict it asserts; see layout/lvs-coverage-probe.json")


def emit_lvs_evidence(klt: str, repo_root: Path) -> dict:
    """Run the signoff LVS over the *emitted* GDS and commit it.

    Mirrors :func:`emit_drc_evidence`: run from the repo root against
    ``layout/comparator.gds`` so the committed envelope records both the path
    ``scripts/check-t1-signoff.py`` resolves and the
    ``provenance.input.content_hash`` a manifest citation would pin --
    regenerating the GDS without refreshing this file would then render any
    such citation ``unmet`` (stale) rather than grading a superseded run.

    Writes two files.  ``layout/lvs-request.json`` is the request document
    itself, committed because the response echoes ``layout``/``reference``/
    ``options`` but **not** ``reference.form`` or ``reference.device_map`` --
    without it the committed envelope would not record the device-class
    mapping the compare was reached through.  ``layout/lvs-report.json`` is
    the envelope.

    **The envelope is committed but NOT cited for T1 item 4.**  Its verdict
    is real for connectivity and MOSFET geometry, and silent on drawn
    resistor geometry -- where this block's known 0.42um-drawn versus
    0.35um-schematic width delta sits.  :func:`emit_lvs_coverage_probe`
    measures both halves of that statement; layout/README.md's "Why item 4 is
    left uncited" carries the reasoning.

    The verdict guard fires after the envelope is on disk, so a failing run
    leaves the evidence to read rather than nothing: the result must be the
    one item 4 is graded on, ``status: "match"`` **and**
    ``power_connectivity.status != "mismatch"``
    (``manifests/design-evidence-tiers.md`` item 4).  Whether the compare can
    fail at all is no longer asserted here -- ``emit_lvs_coverage_probe``'s
    ``mos_*``/``connectivity`` rows are the same assertion, generalised, and
    run immediately after.
    """
    (repo_root / "layout" / "lvs-request.json").write_text(
        json.dumps(LVS_REQUEST, indent=2) + "\n")

    envelope, rc = _run_lvs(klt, LVS_REQUEST, repo_root)
    (repo_root / "layout" / "lvs-report.json").write_text(
        json.dumps(envelope, indent=2) + "\n")

    status = envelope.get("status")
    power = (envelope.get("power_connectivity") or {}).get("status")
    warnings = [m for m in envelope.get("mismatches", [])
                if m.get("severity") != "error"]
    print(f"  signoff lvs: status={status}, power_connectivity={power}, "
          f"errors={envelope.get('error_count')}, warnings={len(warnings)} "
          "(disclosure: layout/README.md)")
    for w in warnings:
        print(f"    warning [{w.get('category')}]: "
              f"{str(w.get('description'))[:100]}")

    if status != "match" or power == "mismatch":
        raise RuntimeError(
            f"signoff LVS over layout/comparator.gds is not clean "
            f"(rc={rc}, status={status!r}, power_connectivity={power!r}, "
            f"errors={envelope.get('error_count')}) -- the envelope was "
            "written for inspection, but layout/README.md's LVS section "
            "describes a clean match, so both it and any manifest citation "
            "must be revisited before this verdict is committed"
        )
    return envelope


def _run_erc(klt: str, layout: str, spec: str, repo_root: Path,
             ) -> tuple[dict, int]:
    """One ``klt erc`` run from the repo root; returns (envelope, rc).

    Run from ``repo_root`` with repo-relative paths so the envelope echoes
    ``file``/``spec`` exactly as ``klt signoff`` and CI resolve them -- the
    same reason :func:`_run_lvs` uses the stdin form.  ``klt erc``'s own exit
    code is 3 for findings and 4 for "nothing graded", both of which are
    *successful* runs; the caller gates on the payload.
    """
    r = run([klt, "erc", layout, spec, "--deck", ERC_DECK,
             "--pdk", ERC_ANTENNA_PDK, "--format", "json"],
            cwd=repo_root, check=False)
    if not r.stdout.strip():
        raise RuntimeError(f"klt erc produced no output (rc={r.returncode}): "
                           f"{r.stderr}")
    return json.loads(r.stdout), r.returncode


def _erc_skip_reasons(envelope: dict) -> list[str]:
    """Every ``erc_coverage.skipped[].reason`` the run recorded, sorted.

    This is the field that separates "the tie check ran and came back clean"
    from "the tie declaration could not be answered" -- klt records a
    degenerate tap declaration (klayout-tools#2199) or a whole-die substrate
    assertion (#2255) here, and ``erc_status`` then reads ``clean_partial``
    rather than ``clean``.  A signoff citation built on such a run renders
    ``supply_spec_incomplete``, never ``met``.
    """
    return sorted({
        str(entry.get("reason"))
        for entry in (envelope.get("erc_coverage") or {}).get("skipped") or []
    })


def _erc_rules(envelope: dict) -> list[str]:
    """The distinct ``erc_findings[].rule`` tokens a run reported, sorted."""
    return sorted({str(f.get("rule")) for f in envelope.get("erc_findings") or []})


def emit_erc_evidence(klt: str, repo_root: Path, bbox: dict) -> dict:
    """Write the ERC supply spec and run it over the *emitted* GDS.

    T1 item 11 ("Power delivery (structural)") is the **structural** supply
    question only: is each declared supply one electrical island, and is every
    well/substrate region tied to the supply that biases it?  IR drop and
    electromigration (``klt power``) are outside it.

    Writes ``layout/erc-spec.json`` (the spec document, committed because the
    envelope echoes its *path* and its content hash but not its declarations --
    without it nobody can read which nets were declared ``supply``) and
    ``layout/erc-report.json`` (the envelope), both from the repo root against
    ``layout/comparator.gds`` for the same path/hash reason
    :func:`emit_drc_evidence` and :func:`emit_lvs_evidence` do.

    **The envelope is committed but NOT cited for T1 item 11**, for a reason
    that is about the item's *LVS* half rather than this run -- see
    layout/README.md -> "ERC: supply-spec run, committed -- and why T1 item 11
    is still not claimed".

    Four guards, each refusing to commit a run that would not support the claim
    the README makes:

    1. the two ties this spec declares must be the only 65/44 geometry in the
       stream, so ``tap_is_dedicated: true`` is a measured fact rather than an
       assumption;
    2. ``erc_status`` must be ``clean`` with zero findings -- and, separately,
       ``erc_coverage.skipped`` must be **empty**: a degenerate tie reports
       zero ``erc.missing_tie`` findings for a reason that has nothing to do
       with taps, and ``clean`` alone cannot tell the two apart;
    3. every declared supply and every declared tie must appear in
       ``erc_coverage.checked``, so "the check ran" is read off the envelope
       rather than inferred from the absence of a finding;
    4. the envelope's own ``provenance.spec.content_hash`` must equal the
       sha256 of the committed spec file.  ``klt signoff``'s item-11 path
       re-reads that spec document from disk to find the declared supply nets
       and does **not** verify it against this hash (klt 0.6.0), so an edited
       spec would otherwise silently change what a citation is graded on.
    """
    spec = build_erc_spec(bbox)
    spec_text = json.dumps(spec, indent=2) + "\n"
    (repo_root / ERC_SPEC_PATH).write_text(spec_text)

    taps = json.loads(
        run([klt, "layers", "layout/comparator.gds", "--format", "json"],
            cwd=repo_root).stdout)
    drawn_taps = sum(entry["shapes"] for entry in taps["layers"]
                     if (entry["layer"], entry["datatype"]) == L_TAP)
    if drawn_taps != len(TAPS):
        raise RuntimeError(
            f"{layer_id(L_TAP)} (tap) carries {drawn_taps} shape(s) but this "
            f"spec's ties assert it is drawn only by the {len(TAPS)} body-tie "
            "structures in TAPS -- 'tap_is_dedicated: true' would no longer be "
            "a measured fact, so refusing to commit it")

    envelope, rc = _run_erc(klt, "layout/comparator.gds", ERC_SPEC_PATH, repo_root)
    (repo_root / ERC_REPORT_PATH).write_text(json.dumps(envelope, indent=2) + "\n")

    coverage = envelope.get("erc_coverage") or {}
    checked = set(coverage.get("checked") or [])
    skipped = _erc_skip_reasons(envelope)
    print(f"  signoff erc: erc_status={envelope.get('erc_status')}, "
          f"findings={envelope.get('erc_finding_count')}, "
          f"skipped={skipped or 'none'}, "
          f"antenna={envelope.get('status')} "
          f"({len((envelope.get('coverage') or {}).get('checked') or [])} level(s) "
          "checked) (disclosure: layout/README.md)")

    if envelope.get("erc_status") != "clean" or envelope.get("erc_finding_count"):
        raise RuntimeError(
            f"signoff ERC over layout/comparator.gds is not clean "
            f"(rc={rc}, erc_status={envelope.get('erc_status')!r}, "
            f"findings={_erc_rules(envelope)}) -- the envelope was written for "
            "inspection, but check the item-11 checklist's two documented "
            "false-positive caveats (klayout-tools#2180 diffusion/well "
            "continuity, #2183 device bodies read as wires) before treating a "
            "supply finding as a real defect")
    if skipped:
        raise RuntimeError(
            f"signoff ERC recorded skipped work {skipped} -- a declared tie klt "
            "could not answer grades 'supply_spec_incomplete', not 'met', so "
            "this envelope must not be committed as item-11 evidence")
    missing = sorted(
        identity for identity in
        [f'erc.net_connectivity:["{net}"]' for net in ERC_SUPPLY_NETS]
        + [f'erc.missing_tie:["{tie["name"]}"]' for tie in spec["ties"]]
        if identity not in checked)
    if missing:
        raise RuntimeError(
            f"signoff ERC did not record {missing} as checked work -- item 11 "
            "requires the supply and tie checks to have actually run, not "
            "merely to have reported nothing")
    spec_hash = "sha256:" + hashlib.sha256(spec_text.encode()).hexdigest()
    recorded = ((envelope.get("provenance") or {}).get("spec") or {}).get(
        "content_hash")
    if recorded != spec_hash:
        raise RuntimeError(
            f"the committed spec hashes to {spec_hash} but the envelope records "
            f"{recorded} -- klt signoff re-reads layout/erc-spec.json without "
            "checking that hash, so the two must not be allowed to diverge")
    return envelope


def _erc_probe_tie_wrong_net(spec: dict, _repo_root: Path, _tmp: Path) -> None:
    for tie in spec["ties"]:
        if tie["name"] == "nwell_vdd":
            tie["net"] = "GND"


def _erc_probe_tap_boxes_no_geometry(spec: dict, _repo_root: Path,
                                     _tmp: Path) -> None:
    for tie in spec["ties"]:
        if tie["name"] == "psub_gnd":
            tie["tap_boxes"] = [[5.0, 5.0, 6.0, 6.0]]


def _erc_probe_psub_split_untapped(spec: dict, _repo_root: Path,
                                   _tmp: Path) -> None:
    boxes = spec["ties"][0]["well_boxes"]
    left = min(boxes, key=lambda b: b[0])
    right = max(boxes, key=lambda b: b[0])
    for tie in spec["ties"]:
        if tie["name"] == "psub_gnd":
            tie["well_boxes"] = [left, right]


def _erc_probe_rail_split_no_via(spec: dict, _repo_root: Path,
                                 _tmp: Path) -> None:
    spec["vias"] = [v for v in spec["vias"] if v["name"] != "via"]


def _erc_probe_supply_short_via_diff(spec: dict, _repo_root: Path,
                                     _tmp: Path) -> None:
    spec["stackup"].insert(1, {"name": "diff", "layer": layer_id(L_DIFF)})
    spec["vias"].insert(0, {"name": "licon1_diff", "layer": layer_id(L_LICON),
                            "between": ["diff", "li1"]})


def _erc_probe_degenerate_tap(spec: dict, _repo_root: Path, _tmp: Path) -> None:
    for tie in spec["ties"]:
        tie.pop("tap_is_dedicated", None)


def _erc_probe_degenerate_well(spec: dict, _repo_root: Path, _tmp: Path) -> None:
    boxes = spec["ties"][0]["well_boxes"]
    extent = [min(b[0] for b in boxes), min(b[1] for b in boxes),
              max(b[2] for b in boxes), max(b[3] for b in boxes)]
    for tie in spec["ties"]:
        if tie["name"] == "psub_gnd":
            tie["well_boxes"] = [extent]


def _erc_probe_undeclared_supply_name(spec: dict, _repo_root: Path,
                                      _tmp: Path) -> None:
    spec["nets"].append({"name": "VPWR", "kind": "supply"})


def _erc_probe_stream_second_vdd_label(spec: dict, repo_root: Path,
                                       tmp: Path) -> str:
    """Perturb the *stream*, not the spec: duplicate a supply label onto a
    second, disconnected electrical island.

    Writes a scratch copy of the committed GDS with one extra ``VDD`` text on
    met1.pin, placed on top of the ``CLK`` label the router already drew -- so
    ``VDD`` names two islands that never touch.  The committed
    ``layout/comparator.gds`` is never written to (the same discipline
    :func:`emit_lvs_coverage_probe` applies to the reference netlist).

    This is the only row that exercises the *multi-island* branch of
    ``erc.unconnected_net``, which is the rule item 11's own wording is about
    ("every declared supply resolves to exactly one electrical island").  It
    also bounds what that rule can see: the island count klt reports is the
    number of islands **carrying the declared label**, so this stream -- which
    draws exactly one text per net -- can report zero islands or two-with-a-
    second-label, but never a rail physically split into a labelled piece and
    an unlabelled orphan.  That split shows up on the *tie* rule instead
    (``rail_split_no_via``), which is why item 11 needs both.
    """
    import klayout.db as kdb

    layout = kdb.Layout()
    layout.read(str(repo_root / "layout" / "comparator.gds"))
    pin_layer = layout.layer(*L_MET1_PIN)
    donor = None
    for cell in layout.each_cell():
        for shape in cell.shapes(pin_layer).each():
            if shape.is_text() and shape.text.string == "CLK":
                donor = (cell, shape.text.x, shape.text.y)
                break
        if donor is not None:
            break
    if donor is None:
        raise RuntimeError(
            "no 'CLK' met1.pin label in layout/comparator.gds -- the "
            "stream probe needs a non-supply labelled island to duplicate "
            "a supply label onto")
    cell, x, y = donor
    cell.shapes(pin_layer).insert(
        kdb.Text(ERC_SUPPLY_NETS[0], kdb.Trans(kdb.Vector(x, y))))
    scratch = tmp / "second-vdd-label.gds"
    layout.write(str(scratch))
    return str(scratch)


#: Negative controls for the ERC supply check, each a perturbation of a
#: **scratch copy** of the spec (or, for the last row, of the stream) plus the
#: findings and coverage classification that perturbation MUST produce.  A
#: check that cannot fail grades nothing -- ``sim/selftest.sh``'s stage-4
#: discipline, and the bar ``lvs-coverage-probe.json`` already set for item 4.
#:
#: Read together they establish four things the committed envelope's own
#: ``erc_status: "clean"`` cannot state on its own: that the tie check bites
#: (four independent ways), that the supply-short rule bites, that the
#: one-island-per-supply rule bites, and that klt's two *unfalsifiability*
#: rejections (a tap indistinguishable from a source/drain contact; a
#: substrate assertion indistinguishable from the whole die) both fire against
#: this very spec the moment its narrowing is removed -- so the committed run's
#: empty ``erc_coverage.skipped`` is a result, not a default.
ERC_PROBES = (
    {
        "id": "tie_wrong_net",
        "perturbation": "the n-well tie declares net GND instead of VDD",
        "mutate": _erc_probe_tie_wrong_net,
        "expect_rules": ["erc.missing_tie"],
        "expect_skipped": [],
        "reads": "the tie check verifies WHICH net the tap reaches, not merely "
                 "that a tap exists",
    },
    {
        "id": "tap_boxes_no_geometry",
        "perturbation": "the substrate tie's tap narrowed by tap_boxes to a "
                        "1x1um region with no tap geometry in it",
        "mutate": _erc_probe_tap_boxes_no_geometry,
        "expect_rules": ["erc.missing_tie"],
        "expect_skipped": [],
        "reads": "a tap assertion matching no drawn geometry is an honest 'no "
                 "tap' finding, not a silent pass",
    },
    {
        "id": "psub_split_untapped",
        "perturbation": "the asserted substrate region split into two "
                        "disjoint bands, only one of which holds the tap",
        "mutate": _erc_probe_psub_split_untapped,
        "expect_rules": ["erc.missing_tie"],
        "expect_skipped": [],
        "reads": "EVERY asserted substrate polygon must independently contain "
                 "a tap that reaches the net -- one tap does not cover the die",
    },
    {
        "id": "rail_split_no_via",
        "perturbation": "the met1<->met2 via role removed from the stackup, "
                        "cutting both rails at every layer change",
        "mutate": _erc_probe_rail_split_no_via,
        "expect_rules": ["erc.missing_tie"],
        "expect_skipped": [],
        "reads": "a rail severed between met1 and met2 is caught -- and caught "
                 "on the TIE rule, because the label-bearing island survives "
                 "(see stream_second_vdd_label)",
    },
    {
        "id": "supply_short_via_diff",
        "perturbation": "diff (65/20) declared as a conductor role, so every "
                        "MOS source conducts to its own drain",
        "mutate": _erc_probe_supply_short_via_diff,
        "expect_rules": ["erc.supply_short"],
        "expect_skipped": [],
        "reads": "the supply-short rule bites: VDD and GND resolving to one "
                 "island is reported, so the committed run's two islands are a "
                 "measurement",
    },
    {
        "id": "undeclared_supply_name",
        "perturbation": "a third supply net 'VPWR' declared, which nothing in "
                        "the stream labels",
        "mutate": _erc_probe_undeclared_supply_name,
        "expect_rules": ["erc.unconnected_net"],
        "expect_skipped": [],
        "reads": "a declared supply matching no labelled geometry is reported "
                 "rather than passing vacuously",
    },
    {
        "id": "degenerate_tap",
        "perturbation": "tap_is_dedicated dropped from both ties, leaving the "
                        "tap region 'whatever 65/44 draws inside the well'",
        "mutate": _erc_probe_degenerate_tap,
        "expect_rules": [],
        "expect_skipped": ["degenerate_tap_declaration"],
        "reads": "klayout-tools#2199's unfalsifiability rejection fires "
                 "against THIS spec -- zero findings, but the work is recorded "
                 "as skipped and item 11 would render supply_spec_incomplete",
    },
    {
        "id": "degenerate_well",
        "perturbation": "the asserted substrate region widened to the whole "
                        "top-cell extent",
        "mutate": _erc_probe_degenerate_well,
        "expect_rules": [],
        "expect_skipped": ["degenerate_well_assertion"],
        "reads": "klayout-tools#2255's counterpart rejection: 'the entire die "
                 "is the substrate' is skipped work, not a clean tie",
    },
    {
        "id": "stream_second_vdd_label",
        "perturbation": "a second VDD label drawn on met1.pin over the CLK "
                        "label, in a scratch copy of the GDS",
        "mutate": _erc_probe_stream_second_vdd_label,
        "perturbs_stream": True,
        "expect_rules": ["erc.unconnected_net"],
        "expect_skipped": [],
        "reads": "the multi-island branch bites -- and bounds the rule: klt "
                 "counts islands CARRYING THE LABEL, so a one-label rail can "
                 "never report a labelled/orphan split",
    },
)


#: The compound item-11 manifest entry this repo *could* add, and deliberately
#: does not (layout/README.md -> "Why item 11 is left uncited").  Probed rather
#: than asserted: :func:`_erc_grade_if_cited` writes it into a scratch manifest
#: and records what ``klt signoff`` makes of it, so the prose claim "the grader
#: would render met; we decline anyway" is a measurement a reader can re-run.
ERC_ITEM_11_PARTS = (ERC_REPORT_PATH, "layout/lvs-report.json")

TIERS_DOC = "manifests/design-evidence-tiers.md"
MANIFEST = "manifests/sky130-comparator.json"


def _erc_grade_if_cited(klt: str, repo_root: Path, tmp: Path,
                        content_hash: str) -> dict:
    """What ``klt signoff`` would make of an item-11 citation of the committed
    ERC + LVS envelopes -- graded against a **scratch** manifest, so
    ``manifests/sky130-comparator.json`` is not touched.

    This exists because "we decline to cite" is only meaningful if the citation
    would otherwise have been accepted.  It also rots loudly in the useful
    direction: if a future klt changes item 11's rules so this set no longer
    grades ``met``, the generator fails here and whoever bumps the pin has to
    revisit the README's reasoning instead of leaving stale prose behind.
    """
    manifest = json.loads((repo_root / MANIFEST).read_text())
    manifest["evidence"]["11"] = [
        {"file": part, "content_hash": content_hash}
        for part in ERC_ITEM_11_PARTS
    ]
    scratch = tmp / "manifest-with-item-11.json"
    scratch.write_text(json.dumps(manifest, indent=2) + "\n")
    r = run([klt, "signoff", "--manifest", str(scratch),
             "--tiers-doc", TIERS_DOC, "--format", "json"],
            cwd=repo_root, check=False)
    if not r.stdout.strip():
        raise RuntimeError(f"klt signoff produced no output (rc={r.returncode}): "
                           f"{r.stderr}")
    report = json.loads(r.stdout)
    row = next(item for item in report["items"] if item["id"] == 11)
    power = (row.get("citation") or {}).get("power_delivery") or {}
    result = {
        "method": (
            "klt signoff --manifest <scratch copy of "
            f"{MANIFEST} with an item-11 citation of "
            f"{' + '.join(ERC_ITEM_11_PARTS)}> --tiers-doc {TIERS_DOC}. The "
            "committed manifest is NOT modified: this row records what the "
            "grader would say, so 'left uncited' is a disclosed choice rather "
            "than an ungradeable envelope. Why the choice went that way is in "
            "layout/README.md -> 'Why item 11 is left uncited'."),
        "cited_parts": list(ERC_ITEM_11_PARTS),
        "item_11_status": row.get("status"),
        "item_11_reason": row.get("reason"),
        "t1_met_count_if_cited": report.get("t1_met_count"),
        "t1_item_count": report.get("t1_item_count"),
        "supply_nets_graded": power.get("supply_nets"),
        "power_connectivity_status": power.get("power_connectivity_status"),
        "ties_checked_by_well_assertion": power.get(
            "ties_checked_by_well_assertion"),
        "committed_manifest_cites_item_11": "11" in json.loads(
            (repo_root / MANIFEST).read_text())["evidence"],
    }
    if result["item_11_status"] != "met":
        raise RuntimeError(
            "the item-11 citation this repo declines to make no longer grades "
            f"'met' (got {result['item_11_status']!r}, reason "
            f"{result['item_11_reason']!r}) -- layout/README.md's 'Why item 11 "
            "is left uncited' argues from the premise that it would, so that "
            "reasoning must be revisited rather than silently outlived")
    if result["committed_manifest_cites_item_11"]:
        raise RuntimeError(
            f"{MANIFEST} now carries an item-11 citation, but "
            "layout/README.md and manifests/README.md still describe it as "
            "deliberately uncited -- reconcile the prose with the manifest")
    return result


def emit_erc_coverage_probe(klt: str, repo_root: Path, bbox: dict,
                            signoff: dict) -> None:
    """Measure whether the committed ERC supply check can fail.

    ``layout/erc-report.json`` states ``erc_status: "clean"`` with an empty
    ``erc_coverage.skipped``.  Neither field says whether the check *could*
    have said anything else, and for a supply check that is the whole
    question: klt computes ``erc.unconnected_net``/``erc.supply_short`` only
    for nets the spec declares and ``erc.missing_tie`` only for ties it
    declares, so an under-declared spec reports a clean supply for the same
    reason a rule-free DRC deck reports zero violations.

    One ``klt erc`` run per row of :data:`ERC_PROBES`, each against a
    perturbed **scratch** copy of the spec -- or, for the stream row, of the
    GDS.  Neither committed artifact is written to.  Writes
    ``layout/erc-coverage-probe.json`` and raises if any row's observed
    findings or coverage classification differ from the ones it asserts.
    """
    base = build_erc_spec(bbox)
    rows = []
    with tempfile.TemporaryDirectory(prefix="loom-erc-probe-") as tmp_str:
        tmp = Path(tmp_str)
        for probe in ERC_PROBES:
            spec = json.loads(json.dumps(base))
            layout = "layout/comparator.gds"
            perturbed = probe["mutate"](spec, repo_root, tmp)
            if probe.get("perturbs_stream"):
                layout = perturbed
            spec_path = tmp / f"{probe['id']}.json"
            spec_path.write_text(json.dumps(spec, indent=2) + "\n")
            envelope, rc = _run_erc(klt, layout, str(spec_path), repo_root)
            rules = _erc_rules(envelope)
            skipped = _erc_skip_reasons(envelope)
            ok = (rules == sorted(probe["expect_rules"])
                  and skipped == sorted(probe["expect_skipped"]))
            rows.append({
                "id": probe["id"],
                "perturbation": probe["perturbation"],
                "perturbs": "stream" if probe.get("perturbs_stream") else "spec",
                "reads_as": probe["reads"],
                "expected_rules": sorted(probe["expect_rules"]),
                "observed_rules": rules,
                "expected_skipped_reasons": sorted(probe["expect_skipped"]),
                "observed_skipped_reasons": skipped,
                "erc_status": envelope.get("erc_status"),
                "erc_finding_count": envelope.get("erc_finding_count"),
                "exit_status": rc,
                "findings": [
                    {k: v for k, v in finding.items()
                     if k in ("rule", "net", "other_net", "description")}
                    for finding in envelope.get("erc_findings") or []
                ],
                "pass": ok,
            })
            print(f"    probe {probe['id']}: {envelope.get('erc_status')} "
                  f"rules={rules or 'none'} skipped={skipped or 'none'} "
                  f"{'PASS' if ok else 'FAIL'}")
        grade = _erc_grade_if_cited(
            klt, repo_root, tmp,
            ((signoff.get("provenance") or {}).get("input") or {})
            .get("content_hash"))
        print(f"    if cited: item 11 would grade {grade['item_11_status']} "
              f"({grade['t1_met_count_if_cited']}/{grade['t1_item_count']} T1 "
              "items) -- deliberately not cited, see layout/README.md")
    ok = all(row["pass"] for row in rows)
    evidence = {
        "tool": {"klt_pin": KLT_PIN,
                 "klt_version": (signoff.get("provenance") or {}).get("klt_version"),
                 "klayout_version": (signoff.get("provenance") or {})
                 .get("klayout_version"),
                 "antenna_pdk": ERC_ANTENNA_PDK, "deck": ERC_DECK},
        "method": (
            "negative controls for layout/erc-report.json: one klt erc run per "
            "row against a perturbed scratch copy of layout/erc-spec.json (or, "
            f"for the {'/'.join(p['id'] for p in ERC_PROBES if p.get('perturbs_stream'))}"
            " row, of layout/comparator.gds) -- neither committed artifact is "
            "written to. Each row asserts the exact set of erc_findings rules "
            "AND the exact set of erc_coverage.skipped reasons that "
            "perturbation must produce, because a supply check reports nothing "
            "both when it is clean and when it was never asked."),
        "signoff_report": ERC_REPORT_PATH,
        "signoff_spec": ERC_SPEC_PATH,
        "signoff_erc_status": signoff.get("erc_status"),
        "signoff_skipped_reasons": _erc_skip_reasons(signoff),
        "signoff_layout_content_hash": ((signoff.get("provenance") or {})
                                        .get("input") or {}).get("content_hash"),
        "signoff_spec_content_hash": ((signoff.get("provenance") or {})
                                      .get("spec") or {}).get("content_hash"),
        "probes": rows,
        "signoff_if_cited": grade,
        "pass": ok,
    }
    (repo_root / ERC_PROBE_PATH).write_text(json.dumps(evidence, indent=2) + "\n")
    if not ok:
        raise RuntimeError(
            "ERC coverage probe FAILED -- a negative control did not produce "
            f"the findings it asserts; see {ERC_PROBE_PATH}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate and verify layout/comparator.gds and its "
                    "committed evidence artifacts; see layout/README.md for "
                    "the floorplan, routing and verification rationale."
    )
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
    print("[emit] signoff LVS over the emitted GDS (item 4 evidence, uncited)")
    signoff_lvs = emit_lvs_evidence(args.klt, repo_root)
    print("[emit] LVS coverage probe (what that match does and does not cover)")
    emit_lvs_coverage_probe(args.klt, repo_root, signoff_lvs)
    print("[emit] signoff ERC supply spec + run (item 11 evidence, uncited)")
    signoff_erc = emit_erc_evidence(args.klt, repo_root, bbox)
    print("[emit] ERC coverage probe (whether that supply check can fail)")
    emit_erc_coverage_probe(args.klt, repo_root, bbox, signoff_erc)
    area = None
    if bbox:
        area = round((bbox["x1"] - bbox["x0"]) * (bbox["y1"] - bbox["y0"]), 2)
    print(f"gen_comparator.py: emitted deliverables to layout/ "
          f"(bbox {bbox}, area {area} um^2)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
