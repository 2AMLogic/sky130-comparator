"""Shared preamble for the `comparator-decision` experiment modules.

Everything the sibling experiment modules in this directory have in common:
the DUT-provenance switch (`--dut schematic` / `extracted`) and the fragment
parsing/re-tying that supports it, the fixed testbench constants, the
record-preamble prose and the committed schematic-level baselines, the ngspice
invocation seams, and the evidence-record head/tail.

Read `run.py`'s module docstring first: it is this experiment's documentation,
and it explains why the experiment has a bespoke driver at all. Issue #224
moved this code out of that module unchanged, so every deck built on top of it
still emits byte-identical text.

`sim/comparator-decision/` is not a legal Python package name (the hyphen), so
`run.py` is loaded by path rather than imported, and its siblings reach each
other -- and `sim/harness/` -- through `sys.path`, exactly as `run.py` has
always reached the harness. This module performs that path setup for both
directories, and importing it is what makes `import regen` (etc.) work.

MONKEYPATCH SEAM: `_run` and `_run_many` are the only two functions in this
directory that invoke ngspice, and every caller reaches them as
`_shared._run(...)` / `_shared._run_many(...)` rather than through an imported
name. That is deliberate: it gives a test exactly one place to stub ngspice
out for every experiment at once.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

EXPERIMENT_DIR = Path(__file__).resolve().parent
SIM_DIR = EXPERIMENT_DIR.parent
for _path in (str(SIM_DIR), str(EXPERIMENT_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from harness import evidence, pdk, toolchain  # noqa: E402


TESTBENCH_DIR = EXPERIMENT_DIR / "testbench"
DUT_FRAGMENT = TESTBENCH_DIR / "comparator_core.spice"

# --- DUT provenance: schematic-level vs. post-layout (issue #57, T1 item 7).
#
# Both fragments are FLAT device-level SPICE that inlines at the same place in
# every deck the sibling experiment modules build, expose the same node names (CLK/VDD/GND/VINP/VINN/OUTP/
# OUTN plus the internal TAILP/OUTP1/OUTN1/TAIL2/CLKT), and are selected by
# `--dut`. The post-layout pair is generated and documented by
# `layout/extract_pex.py` -- read that module's docstring for the derivation,
# for why `klt pex` is not the path here, and for the disclosed res_high_po
# drawn-width delta the extracted fragment deliberately carries.
#
# The schematic path is BYTE-IDENTICAL to what it was before this switch
# existed: `--dut schematic` (the default) inlines exactly the same fragment
# into exactly the same deck text, so a post-layout figure and the committed
# schematic-level record it is differenced against come from decks that
# differ only in the DUT. That is the whole point of the comparison, so it is
# a property worth stating rather than assuming.
REPO_ROOT = EXPERIMENT_DIR.parent.parent
LAYOUT_DIR = REPO_ROOT / "layout"
PEX_FRAGMENT = LAYOUT_DIR / "comparator.pex.spice"
PEX_PREAMP_FRAGMENT = LAYOUT_DIR / "comparator.pex-preamp.spice"
PEX_LATCH_FRAGMENT = LAYOUT_DIR / "comparator.pex-latch.spice"
PEX_ENVELOPE = LAYOUT_DIR / "extract-parasitics.json"

DUT_PROVENANCES = ("schematic", "extracted")
# Module-level rather than threaded through ~15 deck builders and their
# callers: provenance is a property of the whole run, set once by main() (or
# by set_dut_provenance() from a test), never varied mid-run.
_DUT_PROVENANCE = "schematic"


def set_dut_provenance(which: str) -> None:
    global _DUT_PROVENANCE
    if which not in DUT_PROVENANCES:
        raise ValueError(f"unknown DUT provenance {which!r}")
    if which == "extracted":
        missing = [
            p for p in (PEX_FRAGMENT, PEX_PREAMP_FRAGMENT, PEX_LATCH_FRAGMENT)
            if not p.exists()
        ]
        if missing:
            raise SystemExit(
                "post-layout DUT requested but "
                + ", ".join(str(p.relative_to(REPO_ROOT)) for p in missing)
                + " is missing -- run `python3 layout/extract_pex.py` first"
            )
    _DUT_PROVENANCE = which


def dut_provenance() -> str:
    return _DUT_PROVENANCE


def _dut_fragment() -> Path:
    return PEX_FRAGMENT if _DUT_PROVENANCE == "extracted" else DUT_FRAGMENT


# --- POST-LAYOUT DECK SURGERY: moving a terminal of the extracted DUT
# (issue #65; issue #57 refused to guess these three rules, this is the
# answer it deferred).
#
# `reset` and `noise-tran` do not simulate the DUT fragment as committed:
# each builds a deck in which ONE terminal of the latch steering pair is
# attached somewhere else. On the schematic fragment that is a text edit with
# no ambiguity in it -- the terminal names the node. On the extracted
# fragment it is three separate questions, and all three are answered here,
# next to the code that implements them, rather than in a commit message.
#
#   RULE 1 -- WHICH DEVICE, when the layout drew one schematic device as
#   several. `layout/extract_pex.py` names the parallel fingers of a split
#   schematic device `NAME__a`, `NAME__b`, ... (each W=13 input-pair device
#   is two W=6.5 fingers, which is why the extraction reports 18 devices
#   against the schematic's 16). CONVENTION: naming a schematic device in a
#   transformation names EVERY drawn instance of it, and they are transformed
#   together -- they are one device that happens to be drawn in pieces, and
#   splitting them would build a circuit the schematic counterfactual does
#   not describe. `_instance_names()` implements it and refuses a name
#   that resolves to nothing. On the committed layout neither sub-command
#   exercises the convention: the steering pair (W=8) is drawn unsplit, and
#   the split devices are the input pair, which neither sub-command moves.
#   That is a fact about this layout, not a property of the rule, so it is
#   asserted by a test rather than assumed.
#
#   RULE 2 -- WHERE TO CUT, when no terminal sits on the node. The extractor
#   gives every device terminal its own star leg node (`TAIL2__t2`) tied to
#   the net's hub (`TAIL2`) through that terminal's share of the net's series
#   resistance (`R_TAIL2__t2_TAIL2`). Nothing is attached to the logical node
#   directly. CONVENTION: THE STAR LEG TRAVELS WITH THE TERMINAL. Moving a
#   terminal to a new net re-points that leg resistor's HUB end at the new
#   net (and renames it to match); the device line itself is never edited.
#   Consequences, stated because they are the reason for the choice: the leg
#   is not stranded on a one-connection node, no extracted resistance is
#   deleted, and none is re-attributed to a net it was not extracted for --
#   the leg keeps its own value and its own terminal, it just terminates
#   elsewhere. The two alternatives both lose information: moving the device
#   terminal to the new net and dropping the leg silently deletes that
#   terminal's extracted resistance, and moving it while leaving the leg
#   behind strands the leg. What the rule does NOT claim is that this is the
#   resistance the re-routed layout would have had -- it is a
#   netlist-level counterfactual, exactly as the schematic-level one is.
#
#   RULE 3 -- WHICH SIDE OF THE LEG a series source is inserted on. This one
#   has a determinate answer rather than a preference. A star-leg node has
#   exactly TWO connections -- its own device terminal and its own leg
#   resistor -- so the leg resistor and an inserted ideal (zero-impedance)
#   voltage source are two two-terminal elements in series, and series
#   elements commute: inserting the source between the device terminal and
#   its leg gives the electrically IDENTICAL network to inserting it between
#   the leg's far end and the hub. `_star_leg_resistor()` asserts the
#   two-connection premise rather than assuming it, so the equivalence is
#   checked on the fragment actually being simulated. Given the freedom, the
#   deck inserts on the HUB side (leg re-pointed to the injected node, source
#   from the injected node to the hub) because that is the same single
#   mechanism RULE 2 already uses, and it makes the deck's source line
#   (`Vstp GST_P OUTP1`) textually identical to the schematic deck's.


def _parse_devices(text: str) -> dict[str, list[str]]:
    """{instance name: [token, ...]} for one flat SPICE fragment.

    Continuation lines ('+ ...') are folded into the instance they continue,
    and comment/blank lines are dropped -- so the result is one flat token
    list per device instance, in file order.
    """
    devices: dict[str, list[str]] = {}
    current: str | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("*"):
            continue
        if line.startswith("+"):
            if current is not None:
                devices[current].extend(line[1:].split())
            continue
        tokens = line.split()
        current = tokens[0]
        devices[current] = tokens[1:]
    return devices


def _instance_names(devices: dict[str, list[str]], base: str) -> list[str]:
    """RULE 1: every drawn instance of the schematic device `base`."""
    if base in devices:
        return [base]
    fingers = sorted(n for n in devices if n.startswith(f"{base}__"))
    if not fingers:
        raise KeyError(
            f"no instance named {base!r} in this DUT fragment, and no "
            f"{base}__<finger> split of it either"
        )
    return fingers


def _star_leg_hub(token: str) -> str | None:
    """The hub net of an extractor star-leg node, or None for a bare net."""
    base, sep, leg = token.partition("__t")
    return base if sep and leg.isdigit() else None


def _star_leg_resistor(devices: dict[str, list[str]], leg_node: str) -> tuple[str, str]:
    """(resistor name, value) of the star leg tying `leg_node` to its hub.

    Asserts RULE 3's premise: the leg node is PRIVATE to exactly one device
    terminal and exactly one star resistor. If a future extraction ever
    attached something else there, series-commutation would stop holding and
    "which side of the leg" would become a real choice again -- so this
    fails loudly instead of quietly changing what the deck measures.
    """
    hub = _star_leg_hub(leg_node)
    users = [
        name for name, tokens in devices.items()
        if leg_node in [t for t in tokens if "=" not in t]
    ]
    resistors = [
        n for n in users
        if n.startswith("R_") and devices[n][:2] == [leg_node, hub]
    ]
    if len(users) != 2 or len(resistors) != 1:
        raise RuntimeError(
            f"star-leg node {leg_node!r} is attached to {len(users)} elements "
            f"({', '.join(sorted(users))}) with {len(resistors)} star "
            "resistor(s) to its hub; this deck's terminal-move rules assume "
            "exactly one device terminal plus one star resistor there (see "
            "the POST-LAYOUT DECK SURGERY note in this file)"
        )
    return resistors[0], devices[resistors[0]][2]


def _retie_star_legs(text: str, moves: list[tuple[str, int, str]]) -> str:
    """RULE 2 applied to an extracted fragment.

    `moves` is a list of (schematic device name, terminal index, new net).
    Returns the fragment text with each named terminal's star-leg resistor
    re-pointed from its own hub to `new net`, every other line byte-identical
    to the input. Terminal indices are the SPICE order d/g/s/b.
    """
    devices = _parse_devices(text)
    plan: dict[str, str] = {}
    for base, terminal, new_net in moves:
        for inst in _instance_names(devices, base):
            leg_node = devices[inst][terminal]
            if _star_leg_hub(leg_node) is None:
                raise RuntimeError(
                    f"{inst} terminal {terminal} is on bare net "
                    f"{leg_node!r}, not on a parasitic star leg -- this "
                    "fragment is not an extracted one"
                )
            name, _value = _star_leg_resistor(devices, leg_node)
            plan[name] = new_net
    out: list[str] = []
    retied: set[str] = set()
    for raw in text.splitlines():
        tokens = raw.split()
        if len(tokens) == 4 and tokens[0] in plan:
            leg_node, new_net, value = tokens[1], plan[tokens[0]], tokens[3]
            out.append(f"R_{leg_node}_{new_net} {leg_node} {new_net} {value}")
            retied.add(tokens[0])
        else:
            out.append(raw)
    if retied != set(plan):
        raise RuntimeError(
            "failed to re-point star legs "
            + ", ".join(sorted(set(plan) - retied))
        )
    return "\n".join(out) + ("\n" if text.endswith("\n") else "")


# The two terminal moves this driver makes, as (schematic device, terminal
# index, replacement). Named once so the reset counterfactual, the noise-tran
# injection and their tests all refer to the same definition.
TERMINAL_GATE, TERMINAL_SOURCE = 1, 2
RESET_GND_TIE_MOVES = [
    ("XM_STN_P", TERMINAL_SOURCE, "GND"),
    ("XM_STN_N", TERMINAL_SOURCE, "GND"),
]
STEERING_GATE_INJECTION = (
    # (schematic device, injected node, its drain node, its gate net)
    ("XM_STN_P", "GST_P", "OUTP", "OUTP1"),
    ("XM_STN_N", "GST_N", "OUTN", "OUTN1"),
)

# --- Fixed testbench constants. This repo's target-spec table (top-level
# README) is DRAFT (spec/README.md), so nothing here is graded against a
# ratified line -- these are planning values only, matching the constants
# sky130-sar-adc's comparator-decision driver used at the same DUT nodes. ---
VDD = 1.8  # V -- this repo's own 1.8V core-supply constraint (CLAUDE.md).
VCM = VDD / 2  # 0.9V common-mode input.
RESET_NS = 5.0  # reset (CLK=0) duration before the single evaluate edge.
RESET_TR_NS = 0.1  # clock edge rise/fall time.
DECIDE_THRESHOLD_V = 0.5 * VDD  # |v(outp)-v(outn)| crossing this = "decided"
PICKOFF_NS = 0.65
# 0.3 ns until DR-003 (issue #30), 1.0 ns until DR-004 (issue #34). The
# pick-off point is a METHODOLOGY constant: it must land in the linear,
# mid-separation window of |OUTP-OUTN|, wherever the design's evaluate
# onset puts that window. The pre-DR-003 design's ~100 ps onset put it at
# 0.3 ns (gain 5.8156 V/V, record 20260916-003531-52eb9b2). The DR-003
# soft-clock shaper stretched the onset and 0.3 ns fell into the shaped
# dead zone (the superseded record 20260921-192020-bb32850 measured onset
# latency dispersion, not offset); 1.0 ns re-anchored it for the DR-003
# design (ideal-device gains 0.8 -> 9.4, 1.0 -> 13.2 V/V). The DR-004
# preamp makes the whole decision so much faster that at 1.0 ns every
# calibration input is rail-saturated (1 mV -> 0.74 V, 10 mV -> 1.48 V,
# gain fit garbage), so it re-anchors again to 0.65 ns -- measured
# calibration line: 1 mV -> 68.1 mV, 2 -> 135.5, 5 -> 329.5, 10 -> 639.3
# (6% top-to-bottom compression, mid-separation window, and past the
# shaper's onset the DR-003 incident established must be cleared). The
# record's own Methodology line prints this constant, so every record
# states which pick-off point produced it.
# The DR-002-ratified Offset row's bounds -- recorded here so the record
# states its own comparison against the ratified row (values cite DR-002
# Decision 1: target <= 15 mV 3-sigma, stretch <= 8 mV 3-sigma, input-referred).
OFFSET_TARGET_MV = 15.0
OFFSET_STRETCH_MV = 8.0  # time after evaluate-start used as the offset pick-off
# point -- see the `offset` methodology comment at the top of offset.py.
NOISE_FSTART_HZ = 1e3
NOISE_FSTOP_HZ = 1e9

PROCESS_CORNERS = ["tt", "ss", "ff", "sf", "fs"]

# --- Shared evidence-record preamble fields. Since issue #24 the DUT is this
# repo's OWN design (design/comparator.sch), not the sky130-sar-adc-ported
# placeholder issue #9 stood up the plumbing against -- but the top-level
# README target-spec table is still DRAFT and unratified, so a measurement
# here still substantiates no spec ROW. Both halves of that have to be said,
# and said the same way in every record this driver writes. ---
CLAIM_TEXT = (
    "- **Claim**: None by itself -- top-level README target-spec rows are "
    "graded by their ratifying decision record, and per DR-002 (2026-09-16, "
    "merged) the Offset sigma, Input-referred noise, and Kickback rows are "
    "RATIFIED while per DR-005 (2026-09-22, this campaign's record) Decision "
    "time vs. overdrive is RATIFIED and only Supply/power stays DRAFT/OPEN. "
    "What this record characterizes is **this repo's own "
    "comparator**: `design/comparator.sch`, the DR-004 static-preamplifier + "
    "StrongARM-latch topology (superseding DR-001's no-preamp scoping) with "
    "the DR-003 soft-clock shaper still on the clock port, at a sizing "
    "derived from this PDK's own mismatch models (see the schematic's "
    "sizing-rationale block, DR-001 Amendment 1, DR-003, DR-004, and "
    "DR-005). Any statement about a ratified row's compliance made below "
    "cites the bound and the number side by side."
)
SCHEMATIC_NETLIST_PROVENANCE = (
    "- **Netlist provenance**: schematic-derived "
    "(`design/comparator.sch` -> `./design/netlist.sh` -> "
    "`sim/comparator-decision/testbench/comparator_core.spice`)"
)
def extracted_netlist_provenance() -> str:
    """The POST-LAYOUT provenance line, with its RC summary and TOOL PIN read
    out of the committed `layout/extract-parasitics.json` rather than
    transcribed.

    Derived, not hardcoded, because both halves are re-generated evidence.
    The RC totals change whenever the layout or the extractor does, and PR
    #67's review found the harder case: klt/klayout builds that agree on
    every capacitance to the last digit but differ by up to 2.3x per net on
    RESISTANCE (17.52 kohm vs 14.70 kohm in total on this block). A
    transcribed figure silently describes the wrong extraction after a
    re-run; a derived one cannot. Each record therefore states the exact
    extraction build its numbers came from.
    """
    report = json.loads(PEX_ENVELOPE.read_text())
    par = report["parasitics"]
    prov = report["provenance"]
    return (
        "- **Netlist provenance**: POST-LAYOUT / EXTRACTED "
        "(`layout/comparator.gds` -> `klt extract --parasitics` -> "
        "`layout/comparator.extract.spice` -> `layout/extract_pex.py` -> "
        f"`layout/comparator.pex.spice`), extracted by klt "
        f"{prov['klt_version']} on klayout {prov['klayout_version']} -- the "
        "pin `docs/environment-setup.md` records and CI installs, asserted "
        "by `layout/extract_pex.py` because extracted resistances are not "
        f"stable across builds. Lumped-RC parasitics: {par['r_count']} star "
        f"resistors, {par['c_count']} net-to-ground capacitors and "
        f"{par['cc_count']} net-to-net coupling capacitors, "
        f"{par['total_capacitance_ff']:.2f} fF total ground capacitance and "
        f"{par['total_resistance_ohm'] / 1000.0:.2f} kohm total series "
        f"resistance over {report['net_count']} nets "
        "(`layout/extract-parasitics.json`). The per-net series R is the "
        "extractor's DEFAULT single-lumped-star model, which is coarse on "
        "the supply nets specifically (GND and VDD carry the bulk of it) "
        "and is expected to be pessimistic there -- see "
        "`sim/comparator-decision/README.md`. "
        "Net names are the SCHEMATIC names, carried across by the 12/12 net "
        "correspondence in the committed `layout/lvs-report.json`, so every "
        "probe in this deck names the same circuit node the schematic-level "
        "record's probe named. This fragment deliberately carries the "
        "`res_high_po` w=0.42 um drawn vs. w=0.35 um schematic delta disclosed "
        "by PR #55 / `layout/lvs-coverage-probe.json` -- it is what the layout "
        "actually draws, so it is what a post-layout measurement must see."
    )


def netlist_provenance() -> str:
    return (
        extracted_netlist_provenance() if _DUT_PROVENANCE == "extracted"
        else SCHEMATIC_NETLIST_PROVENANCE
    )


# --- Schematic-level anchors the post-layout re-runs are differenced against
# (issue #57 acceptance criteria: "each post-layout record documents its
# schematic-level counterpart record path AND the numeric delta -- not just
# the new number in isolation"). Every entry names a COMMITTED record under
# records/ measured at the same corner/temperature/methodology constants by
# the same sub-command, so the difference is attributable to the DUT and not
# to the bench. Values are transcribed from those records (and are the same
# figures the top-level README's target-spec rows cite). ---
@dataclass(frozen=True)
class Baseline:
    record_id: str
    quantity: str
    value: float
    unit: str
    conditions: str


# The seven PVT points DR-005 grades the ratified rows across, in one place so
# a coverage claim can be checked against a list rather than against prose.
# `offset` grades the `_mm` mismatch variant of each process corner (and the
# committed schematic-level `_mm` campaign ran them all at 27 C), so this
# tuple is the temperature axis for the non-Monte-Carlo sub-commands.
GRADED_CORNERS: tuple[tuple[str, float], ...] = (
    ("tt", 27.0),
    ("ss", -40.0),
    ("ff", 125.0),
    ("sf", -40.0),
    ("sf", 125.0),
    ("fs", -40.0),
    ("fs", 125.0),
)

# `offset`'s own graded axis, which is NOT GRADED_CORNERS. The sub-command
# grades the `_mm` mismatch variant of each process corner, and every
# committed offset record in this repo -- schematic-level and post-layout
# alike -- holds temperature at 27 C so the five figures differ only in
# process. So the coverage question for this row is "all five `_mm` corners
# at 27 C", not "all seven (corner, temperature) points". Named once here so
# a coverage claim is checkable against a list (issue #80).
OFFSET_GRADED_CORNERS: tuple[tuple[str, float], ...] = tuple(
    (corner, 27.0) for corner in PROCESS_CORNERS
)


SCHEMATIC_BASELINES: dict[tuple[str, str, float], Baseline] = {
    ("regen", "tt", 27.0): Baseline(
        "20260922-070800-e084b55", "regeneration time at 50 mV overdrive",
        0.4025, "ns", "8/8 sweep points resolved",
    ),
    ("regen", "ss", -40.0): Baseline(
        "20260922-071313-e084b55", "regeneration time at 50 mV overdrive",
        0.3575, "ns", "7/8 sweep points resolved (0.5 mV does not resolve)",
    ),
    # The remaining five graded `regen` corners (DR-005's full-corner campaign,
    # issue #41). Added by issue #64, which extends the post-layout campaign off
    # the two anchors #57 measured; every value is transcribed from the named
    # committed record's own 50 mV sweep row.
    ("regen", "ff", 125.0): Baseline(
        "20260922-175252-e23c509", "regeneration time at 50 mV overdrive",
        0.4975, "ns", "8/8 sweep points resolved",
    ),
    ("regen", "sf", -40.0): Baseline(
        "20260922-175425-e23c509", "regeneration time at 50 mV overdrive",
        0.3475, "ns", "8/8 sweep points resolved",
    ),
    ("regen", "sf", 125.0): Baseline(
        "20260922-175554-e23c509", "regeneration time at 50 mV overdrive",
        0.4725, "ns", "8/8 sweep points resolved",
    ),
    ("regen", "fs", -40.0): Baseline(
        "20260922-175734-e23c509", "regeneration time at 50 mV overdrive",
        0.3725, "ns", "8/8 sweep points resolved",
    ),
    ("regen", "fs", 125.0): Baseline(
        "20260922-175918-e23c509", "regeneration time at 50 mV overdrive",
        0.5375, "ns", "8/8 sweep points resolved",
    ),
    ("offset-bisect", "tt", 27.0): Baseline(
        "20261002-000502-e2b808c", "decision-flip vindiff (input-referred systematic offset)",
        -0.0391, "mV", "18 probes, tolerance 0.1 mV; the symmetric fragment's "
        "flip sits at ~0 by construction (negative control, issue #66)",
    ),
    # The ss/-40C schematic counterpart has NO single flip: a symmetric
    # +/-0.8203 mV NON-DECISION band (neither sign crosses within the
    # 200 ns bisection window) is that corner's intrinsic resolvable-
    # overdrive floor, centered on 0 by symmetry. The baseline value is
    # the band midpoint; the extracted counterpart's delta against it is
    # the layout's systematic SHIFT of the usable-decision region, and its
    # own record states its band edges (record 20261002-002613-e2b808c,
    # issue #66).
    ("offset-bisect", "ss", -40.0): Baseline(
        "20261002-002613-e2b808c",
        "decision-boundary midpoint (schematic: symmetric +/-0.8203 mV non-decision band)",
        0.0, "mV", "wrong-polarity edge -0.8203, resolved edge +0.8203 mV; "
        "18 probes, tolerance 0.1 mV",
    ),
    ("kickback", "tt", 27.0): Baseline(
        "20260922-070119-e084b55", "peak `loaded` input-node disturbance",
        1.8902, "mV", "1 kohm source impedance, 50 mV overdrive, "
        "`ideal` control 0.0000 mV",
    ),
    # The remaining six graded `kickback` corners: `ss`/-40C and `ff`/125C from
    # DR-004 (issue #34), the four `sf`/`fs` skews from DR-005 (issue #41).
    # Added by issue #64. `sf`/-40C is the schematic-level worst case and the
    # only pre-layout stretch-figure breach, which is why #64 runs it first.
    ("kickback", "ss", -40.0): Baseline(
        "20260922-070212-e084b55", "peak `loaded` input-node disturbance",
        1.8605, "mV", "1 kohm source impedance, 50 mV overdrive, "
        "`ideal` control 0.0000 mV",
    ),
    ("kickback", "ff", 125.0): Baseline(
        "20260922-070307-e084b55", "peak `loaded` input-node disturbance",
        1.7677, "mV", "1 kohm source impedance, 50 mV overdrive, "
        "`ideal` control 0.0000 mV",
    ),
    ("kickback", "sf", -40.0): Baseline(
        "20260922-180026-e23c509", "peak `loaded` input-node disturbance",
        2.0208, "mV", "1 kohm source impedance, 50 mV overdrive, "
        "`ideal` control 0.0000 mV; the only schematic-level corner over the "
        "<= 2 mV stretch figure (by 1%)",
    ),
    ("kickback", "sf", 125.0): Baseline(
        "20260922-180157-e23c509", "peak `loaded` input-node disturbance",
        1.7837, "mV", "1 kohm source impedance, 50 mV overdrive, "
        "`ideal` control 0.0000 mV",
    ),
    ("kickback", "fs", -40.0): Baseline(
        "20260922-180319-e23c509", "peak `loaded` input-node disturbance",
        1.8408, "mV", "1 kohm source impedance, 50 mV overdrive, "
        "`ideal` control 0.0000 mV",
    ),
    ("kickback", "fs", 125.0): Baseline(
        "20260922-180425-e23c509", "peak `loaded` input-node disturbance",
        1.6091, "mV", "1 kohm source impedance, 50 mV overdrive, "
        "`ideal` control 0.0000 mV",
    ),
    ("offset", "tt", 27.0): Baseline(
        "20260922-065300-e084b55", "input-referred offset stdev",
        1.7857, "mV", "N=16 draws at `tt_mm`, seed 1, pick-off 0.65 ns, "
        "same-seed negative control stdev exactly 0",
    ),
    # The other four `_mm` mismatch corners of the DR-005 schematic-level
    # campaign (issue #41), all at 27 C -- `offset` grades the mismatch
    # variant of each process corner at the ONE temperature every committed
    # offset record in this repo uses, so its corner axis is the five `_mm`
    # corners rather than the seven (corner, temperature) points
    # GRADED_CORNERS lists. Added by issue #80, which runs the post-layout
    # counterparts #64 deliberately skipped; without these anchors each of
    # those runs would fall back to `post_layout_delta_lines()`'s
    # "no committed counterpart" note and record a bare number.
    ("offset", "ss", 27.0): Baseline(
        "20260922-173622-e23c509", "input-referred offset stdev",
        1.8244, "mV", "N=16 draws at `ss_mm`, seed 1, pick-off 0.65 ns, "
        "same-seed negative control stdev exactly 0; the nominally binding "
        "schematic-level corner",
    ),
    ("offset", "ff", 27.0): Baseline(
        "20260922-174326-e23c509", "input-referred offset stdev",
        1.5954, "mV", "N=16 draws at `ff_mm`, seed 1, pick-off 0.65 ns, "
        "same-seed negative control stdev exactly 0",
    ),
    ("offset", "sf", 27.0): Baseline(
        "20260922-174831-e23c509", "input-referred offset stdev",
        1.6706, "mV", "N=16 draws at `sf_mm`, seed 1, pick-off 0.65 ns, "
        "same-seed negative control stdev exactly 0",
    ),
    ("offset", "fs", 27.0): Baseline(
        "20260922-175152-e23c509", "input-referred offset stdev",
        1.8218, "mV", "N=16 draws at `fs_mm`, seed 1, pick-off 0.65 ns, "
        "same-seed negative control stdev exactly 0",
    ),
    ("noise", "tt", 27.0): Baseline(
        "20260922-065534-e084b55", "differential input-referred noise",
        0.5704, "mV rms", "loop-broken AC sub-model of the DR-004 preamp, "
        "1 kHz-1 GHz",
    ),
    ("noise-tran", "tt", 27.0): Baseline(
        "20260922-192722-e23c509",
        "decision-referred input-referred noise sigma (pick-off MC)",
        0.1362, "mV", "N=128 pick-off seeds, 95% CI [0.1216, 0.1493] mV, "
        "gain 64.4571 V/V, decision-transition cross-check 0.1342 mV "
        "(64 seeds/sign/point)",
    ),
    # The two graded `noise-tran` corners beyond tt/27C that the issue #41
    # schematic-level campaign measured: `ss`/-40C and `ff`/125C, the
    # slow/cold and fast/hot anchors. Added by issue #89. Without these
    # entries a post-layout run at either corner printed
    # `post_layout_delta_lines()`'s "no committed schematic-level record
    # exists" note -- honest in form but FALSE in fact, since a committed
    # counterpart sat in `records/` the whole time. The four remaining graded
    # points (`sf`/-40C, `sf`/125C, `fs`/-40C, `fs`/125C) genuinely have no
    # schematic-level `noise-tran` counterpart, so they correctly keep
    # falling through to that note.
    ("noise-tran", "ss", -40.0): Baseline(
        "20260922-205857-ebea4e2",
        "decision-referred input-referred noise sigma (pick-off MC)",
        0.1213, "mV", "N=128 pick-off seeds, 95% CI [0.1084, 0.1335] mV, "
        "gain 77.6506 V/V; the decision-transition cross-check is NOT "
        "MEASURABLE at this corner (every pair degenerate -- the "
        "sigma-scaled overdrives sit below this corner's "
        "resolvable-overdrive floor), so the pick-off statistic stands "
        "alone",
    ),
    ("noise-tran", "ff", 125.0): Baseline(
        "20260923-010427-ebea4e2",
        "decision-referred input-referred noise sigma (pick-off MC)",
        0.1754, "mV", "N=128 pick-off seeds, 95% CI [0.1594, 0.1905] mV, "
        "gain 38.1254 V/V, decision-transition cross-check 0.1515 mV "
        "(64 seeds/sign/point)",
    ),
}

# `reset` has no scalar to difference -- it is a four-criterion pass/fail
# screen with a paired positive control -- so its post-layout record names
# its schematic-level counterpart here and compares VERDICTS plus the two
# supply-current columns, rather than going through
# `post_layout_delta_lines()` (issue #65).
RESET_SCHEMATIC_COUNTERPART = "20260922-070024-e084b55"


def baseline_for(mode: str, corner: str, temp_c: float) -> Baseline | None:
    return SCHEMATIC_BASELINES.get((mode, corner, float(temp_c)))


def kickback_subset_justification(corner: str, temp_c: float) -> str:
    """Why a `kickback` record is allowed to run one PVT point.

    Issue #30 minted this justification when tt/27C was the ONLY corner the
    Kickback row had been measured at, and hardcoded its tt/27C wording. Issue
    #41 (schematic-level) and #64 (post-layout) then ran the other six graded
    corners, at which point that fixed text became a false statement printed
    into a record whose own `Corner matrix run` line said `sf`/-40C. Derive it
    from the corner actually run instead, so a record can never claim to have
    measured a point it did not.
    """
    if (corner, float(temp_c)) == ("tt", 27.0):
        return (
            "this record re-measures the SAME single nominal corner "
            "(tt/27C, 1 kOhm, 50 mV overdrive) issue #26's kickback record "
            "(20260916-060139-f1eb978, the pre-mitigation measurement "
            "DR-002's Kickback disposition cites) used, so the before/after "
            "comparison DR-002 asked for is direct and like-for-like per "
            "issue #30's acceptance criteria"
        )
    return (
        f"one corner per record, by design -- this record measures "
        f"{corner}/{temp_c:g}C, one of the seven PVT points DR-005 grades the "
        "ratified rows across. The Kickback row's full graded corner set is "
        "assembled from one such record per corner rather than from a single "
        "multi-corner record, so each corner keeps its own independently "
        "citable evidence and its own delta against the schematic-level "
        "counterpart at the SAME corner. See the corner-coverage table in "
        "`sim/comparator-decision/README.md` for which corners are measured "
        "at which DUT provenance"
    )


def post_layout_delta_lines(
    mode: str, corner: str, temp_c: float, measured: float, unit_scale: float = 1.0,
) -> list[str]:
    """The "## Post-layout delta" section every `--dut extracted` record
    carries. Returns [] on a schematic-provenance run, and an explicit
    "no committed counterpart" note when the anchor is missing -- a
    post-layout number with nothing to difference it against is still worth
    recording, but must not look like it was compared when it was not."""
    if _DUT_PROVENANCE != "extracted":
        return []
    out = ["", "## Post-layout delta vs. the schematic-level record", ""]
    base = baseline_for(mode, corner, temp_c)
    if base is None:
        out.append(
            f"No committed schematic-level `{mode}` record exists at "
            f"{corner}/{temp_c}C to difference this figure against, so this "
            "record states the post-layout number alone. It is not a delta."
        )
        return out
    value = measured * unit_scale
    delta = value - base.value
    ratio = value / base.value if base.value else float("nan")
    out.extend([
        "| Quantity | Schematic-level | Post-layout | Delta | Ratio |",
        "|---|---|---|---|---|",
        f"| {base.quantity} | {base.value:.4f} {base.unit} | "
        f"{value:.4f} {base.unit} | {delta:+.4f} {base.unit} | "
        f"{ratio:.3f}x |",
        "",
        f"- **Schematic-level counterpart record**: "
        f"`sim/comparator-decision/records/{base.record_id}.md` "
        f"({base.conditions})",
        "- **What differs between the two runs**: the DUT fragment, and "
        "nothing else. Same sub-command, same corner/temperature/supply, "
        "same methodology constants, same deck template -- the "
        "schematic-side deck text is byte-identical to the one that "
        "produced the counterpart record.",
    ])
    return out


def _dut_lines() -> str:
    return _dut_fragment().read_text()


def _dut_devices() -> dict[str, list[str]]:
    """Parse the selected DUT fragment into {instance name: [token, ...]}.

    This exists so derived sub-model decks (the `noise` sub-command's
    loop-broken model) are built from the SAME device lines the schematic
    netlister emitted, rather than from sizing transcribed into this file by
    hand. Before issue #24 the noise sub-model carried its own hardcoded
    copy of the placeholder DUT's W/L values, which silently would not have
    tracked design/comparator.sch's real sizing.
    """
    return _parse_devices(_dut_lines())


def _dut_device_line(name: str, *, nodes: list[str] | None = None) -> str:
    """Re-emit one parsed DUT device instance, optionally on different nodes.

    `nodes`, when given, replaces the instance's four terminal nodes
    (d g s b) -- used by the noise sub-model to diode-connect a device.
    Everything after the terminals (model name, W/L and the netlister's
    geometry parameters) is passed through untouched.
    """
    tokens = _dut_devices()[name]
    tail = tokens[4:]
    terminals = nodes if nodes is not None else tokens[:4]
    return " ".join([name, *terminals, *tail])


def _run(deck_text: str, scratch_dir: Path, log_name: str) -> str:
    return toolchain.run_ngspice(deck_text, scratch_dir, log_name)


def _run_many(
    jobs: list[tuple[str, str]], scratch_dir: Path, workers: int = 1,
) -> dict[str, str]:
    """Run a batch of independent (log_name, deck_text) ngspice jobs, in
    parallel when `workers` > 1. Every deck in a batch must be independent
    of every other's result -- the callers that use this (the `offset`
    draws/negative-control runs, the `regen` sweep points, the `kickback`
    variants, and the `noise-tran` Monte Carlo seeds) are single-shot
    transient analyses whose only shared state is the scratch directory
    (each job writes its own uniquely-named log/csv pair). Threads, not
    processes: `toolchain.run_ngspice` blocks on a subprocess, so the GIL
    is released for the whole wait and a ThreadPoolExecutor parallelizes
    the ngspice invocations themselves. Issue #41's campaign sized this:
    a single pick-off transient costs ~21s wall (model-library load
    dominates), and the O(100s)-draw offset campaign plus the
    transient-noise Monte Carlo are thousands of such runs.
    """
    if workers <= 1 or len(jobs) <= 1:
        return {name: _run(deck, scratch_dir, name) for name, deck in jobs}
    import concurrent.futures
    results: dict[str, str] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_run, deck, scratch_dir, name): name
            for name, deck in jobs
        }
        for future in concurrent.futures.as_completed(futures):
            results[futures[future]] = future.result()
    return results


def _resolve_pdk_line(info: pdk.PdkInfo) -> str:
    return f"{info.variant} @ {pdk.resolved_commit(info)}"


def _begin_dut_record(subdir: str) -> tuple[pdk.PdkInfo, str, str, Path, Path]:
    """Shared head, the counterpart of `_finalize_record` below: resolve the
    PDK, mint a record id, hash + snapshot the DUT fragment, and create the
    per-record log directory the caller drops its raw ngspice logs into.

    Returns `(info, record_id, netlist_sha, record_path, logs_dir)`, where
    `logs_dir` is `<EXPERIMENT_DIR>/<subdir>/<record_id>` -- `subdir` is the
    one thing that varies across callers today (`"corners"` for the
    deterministic sweeps, `"mc-draws"` for the Monte Carlo runner)."""
    info = pdk.resolve()
    # Atomic, exclusive reservation of the whole namespace (issue #144):
    # never reuses an existing record id / log directory / snapshot.
    resv = evidence.reserve_record(EXPERIMENT_DIR, (subdir,))
    record_id = resv.record_id
    netlist_sha = evidence.sha256_file(_dut_fragment())
    evidence.write_netlist_snapshot(EXPERIMENT_DIR, record_id, _dut_fragment())
    record_path = resv.record_path
    logs_dir = resv.log_dirs[subdir]
    return info, record_id, netlist_sha, record_path, logs_dir


def _finalize_record(
    lines: list[str],
    record_path: Path,
    info: pdk.PdkInfo,
    netlist_sha: str,
    cmd: str,
    extra: dict[str, str] | None = None,
    supersedes: str = "",
) -> Path:
    """Shared tail: append the environment block + append-only footer and
    write the record. `cmd` is the subcommand name, used in the "Written by"
    attribution. The PDK and ngspice identity lines are resolved here from
    `info` so no caller has to repeat that derivation."""
    lines.extend(evidence.environment_block(
        pdk_line=_resolve_pdk_line(info),
        ngspice_line=toolchain._ngspice_version() or "unknown",
        netlist_sha256=netlist_sha,
        extra=extra,
    ))
    lines.append("")
    lines.extend(evidence.footer_lines(f"sim/comparator-decision/run.py {cmd}", supersedes))
    return evidence.publish_record(record_path, "\n".join(lines))
