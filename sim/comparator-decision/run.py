#!/usr/bin/env python3
"""Standalone driver for the comparator-decision experiment (issues #9, #24,
#26).

Exercises the DUT fragment at
sim/comparator-decision/testbench/comparator_core.spice for its decision
behavior in isolation: mismatch-driven offset, input-referred noise,
regeneration time vs. differential input, reset integrity, and input-node
kickback disturbance. No CDAC array or SAR sequencer is involved -- every
source here is an ideal differential DC/pulse stimulus, because this repo has
no SAR ADC (spec/porting-plan.md "Next steps" item 3).

Since issue #24 that fragment is THIS REPO'S OWN design -- generated from
design/comparator.sch by ./design/netlist.sh -- not the sky130-sar-adc-ported
placeholder issue #9 stood the plumbing up against. Nothing in this driver
hardcodes the DUT's sizing: the `noise` sub-model is assembled from the
fragment's own device lines, so it tracks the schematic automatically.

    python3 sim/comparator-decision/run.py --check-env
    python3 sim/comparator-decision/run.py regen    --record
    python3 sim/comparator-decision/run.py offset   --record --n 16 --seed 1
    python3 sim/comparator-decision/run.py noise    --record
    python3 sim/comparator-decision/run.py noise-tran --record --n 128
    python3 sim/comparator-decision/run.py reset    --record
    python3 sim/comparator-decision/run.py kickback --record

Provenance (per sim/comparator-decision/README.md, in full): the bespoke
regen/offset/noise MEASUREMENT METHODOLOGY below is ported from
2AMLogic/sky130-sar-adc's sim/comparator-decision/run.py (commit
a94fde09244c5e86bafb2adb0a97533d2d59dd65, `main` as of 2026-09-09 -- see
README.md for the full verification), per spec/porting-plan.md's "Next
steps" item 3. What is deliberately NOT ported: sky130-sar-adc-specific numbers
(this repo has no ratified spec/target-spec.md to grade against yet -- the
top-level README's target-spec table is DRAFT), the `regen-corners` /
`noise-corners` full-PVT-sweep subcommands (later additions there, driven by
that repo's own topology bugs and ratified-corner-set campaigns -- issue #9's
acceptance criteria ask for one nominal-corner record per experiment, not a
corner campaign), and any CDAC/sequencer dependency (there is none to drop --
sky130-sar-adc's own comparator-decision experiment is itself standalone).

Why this is a bespoke driver, not sim/run_corners.py or sim/monte_carlo.py:
those two runners are deliberately built around a single ngspice analysis
type -- a plain `.op` operating point, driven through a `.control ... op ...
let/print ... .endc` block (sim/harness/testbench.py's `_render_body()`,
sim/harness/measure.py's docstring on why `.measure op` is not usable at
all). A dynamic latched comparator has no static DC operating point during
regeneration -- it is a clocked, bistable circuit -- so "offset" and
"regeneration time" are inherently transient-analysis quantities, and
"input-referred noise" needs an AC `.noise` analysis on a linearized,
loop-broken sub-model (see the `noise` subcommand below). This driver still
follows sim/README.md's directory convention (testbench/, netlist-snapshots/,
corners/, mc-draws/, records/) and reuses sim/harness/{pdk,toolchain,
evidence,corners}.py directly for PDK resolution, the ngspice invocation +
timeout, and the evidence-record scaffolding (record IDs, netlist SHA-256,
git/environment block) -- so records from this experiment are directly
comparable in format to every other record under sim/.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SIM_DIR))

from harness import corners as corners_mod, evidence, pdk, toolchain  # noqa: E402

EXPERIMENT_DIR = Path(__file__).resolve().parent
TESTBENCH_DIR = EXPERIMENT_DIR / "testbench"
DUT_FRAGMENT = TESTBENCH_DIR / "comparator_core.spice"

# --- DUT provenance: schematic-level vs. post-layout (issue #57, T1 item 7).
#
# Both fragments are FLAT device-level SPICE that inlines at the same place in
# every deck below, expose the same node names (CLK/VDD/GND/VINP/VINN/OUTP/
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
        missing = [p for p in (PEX_FRAGMENT, PEX_PREAMP_FRAGMENT) if not p.exists()]
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


def _require_schematic_dut(mode: str) -> None:
    """Refuse a sub-command whose deck construction has no post-layout form.

    `reset` and `noise-tran` build counterfactual/injection decks by
    re-emitting NAMED DUT device lines onto substituted nodes
    (`_dut_device_line(name, nodes=...)`). On the extracted fragment a
    schematic instance can correspond to more than one drawn device (each
    W=13 input-pair device is two W=6.5 fingers) and every terminal sits on a
    per-terminal parasitic star leg rather than on the node itself, so
    "re-emit this device somewhere else" is not a well-defined operation
    without also re-partitioning its parasitics. Refusing loudly is the point:
    silently falling back to the schematic DUT would produce a post-layout
    record that is not a post-layout measurement. Tracked as follow-on work,
    not smuggled in here.
    """
    raise SystemExit(
        f"`{mode}` has no post-layout deck form yet and this run would "
        "otherwise silently measure the schematic DUT -- see "
        "`_require_schematic_dut` in this file for why, and run it with "
        "`--dut schematic`"
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
# point -- see the `offset` subcommand's methodology comment below.
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
    ("noise", "tt", 27.0): Baseline(
        "20260922-065534-e084b55", "differential input-referred noise",
        0.5704, "mV rms", "loop-broken AC sub-model of the DR-004 preamp, "
        "1 kHz-1 GHz",
    ),
}


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
    """Parse the DUT fragment into {instance name: [token, ...]}.

    Continuation lines ('+ ...') are folded into the instance they continue,
    and comment/blank lines are dropped -- so the result is one flat token
    list per device instance, in file order.

    This exists so derived sub-model decks (the `noise` sub-command's
    loop-broken model) are built from the SAME device lines the schematic
    netlister emitted, rather than from sizing transcribed into this file by
    hand. Before issue #24 the noise sub-model carried its own hardcoded
    copy of the placeholder DUT's W/L values, which silently would not have
    tracked design/comparator.sch's real sizing.
    """
    devices: dict[str, list[str]] = {}
    current: str | None = None
    for raw in _dut_lines().splitlines():
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


def _finalize_record(
    lines: list[str],
    record_path: Path,
    pdk_line: str,
    ng_version: str,
    netlist_sha: str,
    cmd: str,
    extra: dict[str, str] | None = None,
    supersedes: str = "",
) -> Path:
    """Shared tail: append the environment block + append-only footer and
    write the record. `cmd` is the subcommand name, used in the "Written by"
    attribution."""
    lines.extend(evidence.environment_block(
        pdk_line=pdk_line,
        ngspice_line=ng_version,
        netlist_sha256=netlist_sha,
        extra=extra,
    ))
    lines.append("")
    lines.extend(evidence.footer_lines(f"sim/comparator-decision/run.py {cmd}", supersedes))
    record_path.write_text("\n".join(lines))
    return record_path


# ---------------------------------------------------------------------------
# regen: regeneration time vs. differential input (deterministic sweep)
# ---------------------------------------------------------------------------

DEFAULT_VINDIFF_SWEEP_MV = [0.5, 1, 2, 5, 10, 20, 50, -10]
EVALUATE_NS = 40.0


def _regen_deck(
    info: pdk.PdkInfo, corner: str, temp_c: float, vindiff_mv: float, log_name: str,
) -> str:
    """Single reset->evaluate transient deck for one (corner, temp,
    Vindiff) point at the nominal supply."""
    vindiff_v = vindiff_mv / 1000.0
    period_ns = RESET_NS + RESET_TR_NS + EVALUATE_NS + 10.0
    lines = [
        f"* comparator-decision regen-time sweep -- vindiff={vindiff_mv}mV "
        f"corner={corner} temp={temp_c}C (issue #9)",
        f".lib {info.ngspice_lib} {corner}",
        f".temp {temp_c}",
        f".param vdd_val = {VDD}",
        "",
        "Vdd VDD 0 dc {vdd_val}",
        f"Vclk CLK 0 PULSE(0 {{vdd_val}} {RESET_NS}n {RESET_TR_NS}n {RESET_TR_NS}n "
        f"{EVALUATE_NS}n {period_ns}n)",
        f"Vinp VINP 0 dc {VCM + vindiff_v / 2}",
        f"Vinn VINN 0 dc {VCM - vindiff_v / 2}",
        "",
        _dut_lines(),
        "",
        ".control",
        f"tran 0.005n {RESET_NS + RESET_TR_NS + EVALUATE_NS}n",
        f"wrdata {log_name}.csv v(CLK) v(OUTP) v(OUTN)",
        ".endc",
        ".end",
    ]
    return "\n".join(lines) + "\n"


@dataclass
class RegenPoint:
    vindiff_mv: float
    regen_time_ns: float | None
    log_text: str


def run_regen_sweep(
    corner: str = "tt", temp_c: float = 27.0,
    vindiff_sweep_mv: list[float] | None = None, quiet: bool = False, jobs: int = 1,
) -> list[RegenPoint]:
    info = pdk.resolve_or_raise()
    vindiff_sweep_mv = vindiff_sweep_mv or DEFAULT_VINDIFF_SWEEP_MV
    evaluate_start_ns = RESET_NS + RESET_TR_NS
    points: list[RegenPoint] = []
    with tempfile.TemporaryDirectory(prefix="comparator-decision-regen-") as scratch:
        scratch_dir = Path(scratch)
        sweep_jobs = [
            (f"regen_{v}mV".replace("-", "neg").replace(".", "p"),
             _regen_deck(info, corner, temp_c, v, f"regen_{v}mV".replace("-", "neg").replace(".", "p")))
            for v in vindiff_sweep_mv
        ]
        sweep_logs = _run_many(sweep_jobs, scratch_dir, jobs)
        for vindiff_mv in vindiff_sweep_mv:
            log_name = f"regen_{vindiff_mv}mV".replace("-", "neg").replace(".", "p")
            log_text = sweep_logs[log_name]
            csv_path = scratch_dir / f"{log_name}.csv"
            t, clk, outp, outn = toolchain.read_wrdata_csv(csv_path, 3)
            sign = 1.0 if vindiff_mv >= 0 else -1.0
            regen_ns = None
            for i, tt in enumerate(t):
                if tt < evaluate_start_ns * 1e-9:
                    continue
                diff = sign * (outp[i] - outn[i])
                if diff > DECIDE_THRESHOLD_V:
                    regen_ns = (tt - evaluate_start_ns * 1e-9) * 1e9
                    break
            points.append(RegenPoint(vindiff_mv=vindiff_mv, regen_time_ns=regen_ns, log_text=log_text))
            if not quiet:
                shown = f"{regen_ns:.4f}ns" if regen_ns is not None else "UNRESOLVED"
                print(f"  vindiff={vindiff_mv:+.4f}mV -> regen_time={shown}")
    return points


def write_regen_evidence(
    points: list[RegenPoint], corner: str, temp_c: float,
    note: str = "", supersedes: str = "",
) -> Path:
    info = pdk.resolve()
    record_id = evidence.new_record_id()
    netlist_sha = evidence.sha256_file(_dut_fragment())
    record_path = evidence.write_netlist_snapshot(EXPERIMENT_DIR, record_id, _dut_fragment())
    corners_dir = EXPERIMENT_DIR / "corners" / record_id
    corners_dir.mkdir(parents=True, exist_ok=True)
    for p in points:
        safe = f"{p.vindiff_mv}mV".replace("-", "neg").replace(".", "p")
        (corners_dir / f"vindiff_{safe}.log").write_text(p.log_text)

    lines: list[str] = []
    a = lines.append
    a(f"# Record {record_id}")
    a("")
    a(f"- **Record ID**: {record_id}")
    a(CLAIM_TEXT)
    a(netlist_provenance())
    a(
        f"- **Corner matrix run**: process=['{corner}'], temperature_c=[{temp_c}], "
        f"supply_v=[{VDD}] (1 PVT point -- **subset-corner justification**: "
        "single-point characterization of this repo's own design at the stated "
        "corner, per issue #24's acceptance criteria; a full ratified PVT "
        "corner sweep and Monte Carlo campaign remain open work, blocked on "
        "the top-level README target-spec table's ratification -- see issue #3 "
        "item 5 and DR-001's 'A full PVT sweep' open item)"
    )
    a(
        f"- **Stimulus**: single reset({RESET_NS}ns, CLK=0)->evaluate(CLK={VDD}V) "
        f"edge per run (not a repeating clock); decision threshold "
        f"|v(outp)-v(outn)| > {DECIDE_THRESHOLD_V}V (0.5*VDD); Vcm={VCM}V"
    )
    if note:
        a(f"- **Note**: {note}")
    unresolved = [p for p in points if p.regen_time_ns is None]
    a(f"- **Overall**: {'PASS' if not unresolved else 'INCOMPLETE'} "
      f"({len(points) - len(unresolved)}/{len(points)} points resolved within the "
      f"{EVALUATE_NS}ns evaluate window)")
    a("")
    a("## Regeneration time vs. differential input")
    a("")
    a("| Vindiff (mV) | regen time (ns) |")
    a("|---|---|")
    for p in sorted(points, key=lambda p: p.vindiff_mv):
        shown = f"{p.regen_time_ns:.4f}" if p.regen_time_ns is not None else "UNRESOLVED (> evaluate window)"
        a(f"| {p.vindiff_mv:+.2f} | {shown} |")
    a("")
    a(
        "Expected shape: regeneration time grows roughly as `ln(V_decided/Vindiff)` "
        "(standard positive-feedback latch behavior) as Vindiff shrinks -- the "
        "monotonic growth from 50mV to 0.5mV above is the qualitative plumbing "
        "check for that, not a quantitative claim against any spec row."
    )
    a("")
    ref = next(
        (p.regen_time_ns for p in points
         if p.vindiff_mv == 50 and p.regen_time_ns is not None),
        None,
    )
    if ref is not None:
        lines.extend(post_layout_delta_lines("regen", corner, temp_c, ref))
        a("")
    return _finalize_record(
        lines, record_path, _resolve_pdk_line(info), toolchain._ngspice_version() or "unknown",
        netlist_sha, "regen", supersedes=supersedes,
    )


# ---------------------------------------------------------------------------
# offset: Monte Carlo mismatch-induced offset, via a linearized pick-off
# statistic calibrated against an ideal-device Vindiff sweep
# ---------------------------------------------------------------------------
#
# Methodology (ported from 2AMLogic/sky130-sar-adc's sim/comparator-decision/
# run.py -- see this experiment's README.md for the exact commit): a dynamic
# latch has no static DC operating point once CLK evaluates, so offset cannot
# be read off a `.op` node voltage the way a static comparator's could.
# Instead:
#
#  1. "Gain calibration" -- at the plain corner (no mismatch), sweep a few
#     small ideal Vindiff points and record the differential output
#     v(outp)-v(outn) at a fixed early pick-off time (PICKOFF_NS after the
#     evaluate edge, well before the latch saturates to the rails). This
#     relationship is linear in that window -- fit a zero-intercept slope
#     ("gain", V/V) through it via least squares.
#  2. "Draws" -- at the `_mm` mismatch corner, run N single-shot transients
#     with Vindiff FIXED AT 0 and a distinct rndseed per draw, each measuring
#     the same pick-off statistic. Per-device mismatch breaks the ideal
#     symmetry, producing a nonzero pick-off value whose input-referred
#     equivalent is (pick-off value) / gain -- the offset for that draw.
#  3. "Negative control" -- N draws at the plain corner (mismatch disabled),
#     same seed sequence: must reproduce the SAME pick-off value on every
#     draw (stdev == 0), the same negative-control contract every other
#     Monte Carlo record in this repo uses (sim/README.md).

VINDIFF_GAIN_CAL_MV = [1, 2, 5, 10]
PICKOFF_TSTOP_NS = RESET_NS + RESET_TR_NS + 2.5


def _pickoff_deck(
    info: pdk.PdkInfo, corner: str, temp_c: float, vindiff_mv: float,
    log_name: str, rndseed: int | None = None,
) -> str:
    vindiff_v = vindiff_mv / 1000.0
    evaluate_ns = PICKOFF_TSTOP_NS - RESET_NS - RESET_TR_NS
    period_ns = RESET_NS + RESET_TR_NS + evaluate_ns + 10.0
    lines = [
        f"* comparator-decision offset pick-off -- vindiff={vindiff_mv}mV "
        f"corner={corner} temp={temp_c}C seed={rndseed} (issue #9)",
        f".lib {info.ngspice_lib} {corner}",
        f".temp {temp_c}",
        f".param vdd_val = {VDD}",
    ]
    if rndseed is not None:
        lines.append(f".option rndseed={rndseed}")
    lines += [
        "",
        "Vdd VDD 0 dc {vdd_val}",
        f"Vclk CLK 0 PULSE(0 {{vdd_val}} {RESET_NS}n {RESET_TR_NS}n {RESET_TR_NS}n "
        f"{evaluate_ns}n {period_ns}n)",
        f"Vinp VINP 0 dc {VCM + vindiff_v / 2}",
        f"Vinn VINN 0 dc {VCM - vindiff_v / 2}",
        "",
        _dut_lines(),
        "",
        ".control",
        f"tran 0.002n {PICKOFF_TSTOP_NS}n",
        f"wrdata {log_name}.csv v(OUTP) v(OUTN)",
        ".endc",
        ".end",
    ]
    return "\n".join(lines) + "\n"


def _pickoff_value(csv_path: Path) -> float:
    t, outp, outn = toolchain.read_wrdata_csv(csv_path, 2)
    target = (RESET_NS + RESET_TR_NS + PICKOFF_NS) * 1e-9
    idx = min(range(len(t)), key=lambda i: abs(t[i] - target))
    return outp[idx] - outn[idx]


@dataclass
class OffsetResult:
    gain_v_per_v: float
    gain_cal_points: list[tuple[float, float]]  # (vindiff_v, pickoff_diff)
    draws_pickoff: list[float]
    draws_offset_v: list[float]
    negctrl_pickoff: list[float]
    negctrl_offset_v: list[float]
    seed: int
    n: int
    corner: str
    mismatch_corner: str
    temp_c: float = 27.0
    logs: dict[str, str] = field(default_factory=dict)


def run_offset_mc(
    corner: str = "tt", temp_c: float = 27.0, seed: int = 1, n: int = 16,
    quiet: bool = False, jobs: int = 1,
) -> OffsetResult:
    info = pdk.resolve_or_raise()
    mismatch_corner = corners_mod.mismatch_corner_for(corner)
    logs: dict[str, str] = {}

    with tempfile.TemporaryDirectory(prefix="comparator-decision-offset-") as scratch:
        scratch_dir = Path(scratch)

        # 1. Gain calibration (ideal devices, plain corner).
        cal_points: list[tuple[float, float]] = []
        cal_jobs = [(f"gaincal_{v}mV", _pickoff_deck(info, corner, temp_c, v, f"gaincal_{v}mV"))
                    for v in VINDIFF_GAIN_CAL_MV]
        cal_logs = _run_many(cal_jobs, scratch_dir, jobs)
        logs.update(cal_logs)
        for vindiff_mv in VINDIFF_GAIN_CAL_MV:
            diff = _pickoff_value(scratch_dir / f"gaincal_{vindiff_mv}mV.csv")
            cal_points.append((vindiff_mv / 1000.0, diff))
            if not quiet:
                print(f"  gain-cal vindiff={vindiff_mv}mV -> pickoff_diff={diff:.6g}")
        sxy = sum(x * y for x, y in cal_points)
        sxx = sum(x * x for x, y in cal_points)
        gain = sxy / sxx if sxx else float("nan")
        if not quiet:
            print(f"  gain = {gain:.4f} V/V (from {len(cal_points)} calibration points)")

        # 2. Mismatch-enabled draws at Vindiff=0.
        draw_jobs = [
            (f"draw_{i}", _pickoff_deck(info, mismatch_corner, temp_c, 0.0, f"draw_{i}", rndseed=seed + i))
            for i in range(n)
        ]
        draw_logs = _run_many(draw_jobs, scratch_dir, jobs)
        logs.update(draw_logs)
        draws_pickoff = [
            _pickoff_value(scratch_dir / f"draw_{i}.csv") for i in range(n)
        ]
        if not quiet:
            for i in range(n):
                print(f"  draw {i} (seed={seed + i}, {mismatch_corner}): pickoff_diff={draws_pickoff[i]:.6g}")

        # 3. Negative control at the plain corner, same seed sequence.
        negctrl_jobs = [
            (f"negctrl_{i}", _pickoff_deck(info, corner, temp_c, 0.0, f"negctrl_{i}", rndseed=seed + i))
            for i in range(n)
        ]
        negctrl_logs = _run_many(negctrl_jobs, scratch_dir, jobs)
        logs.update(negctrl_logs)
        negctrl_pickoff = [
            _pickoff_value(scratch_dir / f"negctrl_{i}.csv") for i in range(n)
        ]
        if not quiet:
            for i in range(n):
                print(f"  negctrl {i} (seed={seed + i}, {corner}): pickoff_diff={negctrl_pickoff[i]:.6g}")

    draws_offset_v = [d / gain for d in draws_pickoff]
    negctrl_offset_v = [d / gain for d in negctrl_pickoff]

    return OffsetResult(
        gain_v_per_v=gain, gain_cal_points=cal_points,
        draws_pickoff=draws_pickoff, draws_offset_v=draws_offset_v,
        negctrl_pickoff=negctrl_pickoff, negctrl_offset_v=negctrl_offset_v,
        seed=seed, n=n, corner=corner, mismatch_corner=mismatch_corner,
        temp_c=temp_c, logs=logs,
    )


def write_offset_evidence(
    result: OffsetResult, note: str = "", supersedes: str = "",
) -> Path:
    info = pdk.resolve()
    record_id = evidence.new_record_id()
    netlist_sha = evidence.sha256_file(_dut_fragment())
    record_path = evidence.write_netlist_snapshot(EXPERIMENT_DIR, record_id, _dut_fragment())
    draws_dir = EXPERIMENT_DIR / "mc-draws" / record_id
    draws_dir.mkdir(parents=True, exist_ok=True)
    for name, text in result.logs.items():
        (draws_dir / f"{name}.log").write_text(text)

    negctrl_stdev = statistics.pstdev(result.negctrl_offset_v) if len(result.negctrl_offset_v) > 1 else 0.0
    negctrl_ok = negctrl_stdev == 0.0
    draws_stdev = statistics.pstdev(result.draws_offset_v) if len(result.draws_offset_v) > 1 else 0.0
    draws_mean = statistics.fmean(result.draws_offset_v) if result.draws_offset_v else float("nan")

    lines: list[str] = []
    a = lines.append
    a(f"# Monte Carlo record {record_id}")
    a("")
    a(f"- **Record ID**: {record_id}")
    a(CLAIM_TEXT)
    a(netlist_provenance())
    rel_se_pct = 100.0 / (2 * (result.n - 1)) ** 0.5 if result.n > 1 else float("inf")
    a(
        f"- **Statistical convention**: mismatch corner `{result.mismatch_corner}`, "
        f"N={result.n}, seed={result.seed} (draws use seed, seed+1, ..., "
        f"seed+N-1), PVT point process={result.corner} temp={result.temp_c}C supply={VDD}V. "
        f"Relative standard error on the estimated offset stdev, "
        f"SE(s)/s ~= 1/sqrt(2(N-1)): N={result.n} gives {rel_se_pct:.1f}%. "
        + (
            "A distribution-shape-adequate sample for this plumbing proof, not a "
            "sample sized for a tight yield-fraction claim (that needs O(100s))."
            if result.n < 100 else
            "An O(100s)-draw campaign-sized sample (issue #41): the stdev "
            "estimate carries a stated relative standard error and supports a "
            "yield-fraction claim at production-relevant confidence."
        )
    )
    a(
        f"- **Methodology**: linearized pick-off statistic at "
        f"t=evaluate_start+{PICKOFF_NS}ns, calibrated to an input-referred "
        f"gain of {result.gain_v_per_v:.4f} V/V via a {len(result.gain_cal_points)}-point "
        "ideal-device Vindiff sweep (zero-intercept least-squares fit)."
    )
    a(
        f"- **Negative control**: N={result.n} draws at the plain `{result.corner}` "
        f"corner (mismatch DISABLED), same seed sequence -- "
        f"{'PASS (stdev == 0 on the pick-off-derived offset)' if negctrl_ok else f'FAIL: stdev={negctrl_stdev:.6g} != 0'}"
    )
    a(
        f"- **Positive control**: N={result.n} draws at the `{result.mismatch_corner}` "
        f"corner (mismatch ENABLED) offset stdev={draws_stdev:.6g} V "
        f"({'> 0, shows genuine spread -- PASS' if draws_stdev > 0 else 'FAIL: zero spread despite mismatch enabled'})"
    )
    if note:
        a(f"- **Note**: {note}")
    overall_ok = negctrl_ok and draws_stdev > 0
    a(f"- **Overall**: {'PASS' if overall_ok else 'FAIL'}")
    a("")
    a(f"## Gain calibration (ideal devices, {result.corner} corner)")
    a("")
    a("| Vindiff (mV) | pick-off diff (V) |")
    a("|---|---|")
    for x, y in result.gain_cal_points:
        a(f"| {x * 1000:.2f} | {y:.6g} |")
    a(f"\nFitted gain (zero-intercept least squares): **{result.gain_v_per_v:.4f} V/V**")
    a("")
    a("## Offset distribution (mismatch-enabled draws, input-referred)")
    a("")
    a("| N | mean (mV) | stdev (mV) | min (mV) | max (mV) |")
    a("|---|---|---|---|---|")
    a(
        f"| {len(result.draws_offset_v)} | {draws_mean * 1000:.4f} | "
        f"{draws_stdev * 1000:.4f} | {min(result.draws_offset_v) * 1000:.4f} | "
        f"{max(result.draws_offset_v) * 1000:.4f} |"
    )
    if result.n >= 100:
        # Normal-approximation CI on the stdev (SE(s) ~ s/sqrt(2(N-1))),
        # adequate at O(100s) draws; stated so the yield-fraction claim
        # carries its confidence explicitly (issue #41's acceptance criteria).
        ci_lo = draws_stdev * (1 - 1.96 / (2 * (result.n - 1)) ** 0.5)
        ci_hi = draws_stdev * (1 + 1.96 / (2 * (result.n - 1)) ** 0.5)
        a(
            f"- **95% CI on the stdev** (normal approximation, "
            f"SE(s)/s = {1.0 / (2 * (result.n - 1)) ** 0.5:.4f}): "
            f"[{ci_lo * 1000:.4f}, {ci_hi * 1000:.4f}] mV"
        )
    a("")
    a(
        f"- **Ratified bound comparison (DR-002)**: the Offset sigma row is "
        f"RATIFIED at <= {OFFSET_TARGET_MV:g} mV, 3-sigma (target) / "
        f"<= {OFFSET_STRETCH_MV:g} mV, 3-sigma (stretch), input-referred. "
        f"This record's N={result.n} estimated stdev "
        f"{draws_stdev * 1000:.4f} mV gives 3-sigma = "
        f"{3 * draws_stdev * 1000:.4f} mV, which "
        f"{'clears' if 3 * draws_stdev * 1000 <= OFFSET_TARGET_MV else 'DOES NOT clear'} "
        f"the target bound"
        + (
            f" and {'clears' if 3 * draws_stdev * 1000 <= OFFSET_STRETCH_MV else 'DOES NOT yet clear'} "
            f"the stretch bound."
            if 3 * draws_stdev * 1000 <= OFFSET_TARGET_MV else
            " -- new information for the decision records to weigh, never "
            "silently superseding DR-002's disposition."
        )
        + (
            " N=16 is sized for distribution shape, not a yield-fraction claim "
            "(see the Statistical convention above)."
            if result.n == 16 else
            " See the Statistical convention above for this sample size's "
            "stated relative standard error."
        )
    )
    a("")
    a("## Negative control (mismatch-disabled, same seed sequence)")
    a("")
    negctrl_mean = statistics.fmean(result.negctrl_offset_v) if result.negctrl_offset_v else float("nan")
    a("| N | mean (mV) | stdev (mV, must be 0) |")
    a("|---|---|---|")
    a(f"| {len(result.negctrl_offset_v)} | {negctrl_mean * 1000:.4f} | {negctrl_stdev * 1000:.6g} |")
    a("")
    lines.extend(post_layout_delta_lines(
        "offset", result.corner, result.temp_c, draws_stdev, unit_scale=1000.0))
    a("")
    return _finalize_record(
        lines, record_path, _resolve_pdk_line(info), toolchain._ngspice_version() or "unknown",
        netlist_sha, "offset",
        extra={"MC seed": str(result.seed), "MC N": str(result.n)},
        supersedes=supersedes,
    )


# ---------------------------------------------------------------------------
# noise: input-referred noise via a linearized, loop-broken AC .noise model
# ---------------------------------------------------------------------------
#
# Methodology (ported from 2AMLogic/sky130-sar-adc, see README.md): the full
# comparator has no stable small-signal operating point once regeneration
# begins (the cross-coupled pair is a positive-feedback loop), so a direct
# `.noise` analysis on the full comparator_core.spice fragment is not
# meaningful. Instead this uses a REDUCED sub-model. Since DR-004 (issue
# #34) the DUT is a static preamplifier ahead of the clocked latch, and the
# reduced sub-model is simply the PREAMP ITSELF, verbatim from the
# committed fragment: preamp tail (gate at VDD), input pair, both poly
# loads, and both OUT1 absorber MOS caps. Unlike every earlier revision of
# this sub-model -- which had to proxy the integration phase of a dynamic
# input stage with diode-connected stand-in loads -- this is a REAL static
# stage: it holds its own DC operating point continuously, exactly as the
# committed design does, so the `.noise` linearization happens at the
# actual always-on bias. The loop break is the omission of everything past
# the preamp outputs (steering pair, latch tail, cross-coupled PMOS, reset
# PMOS): the latch has no steady small-signal state during regeneration,
# and its noise contribution referred to the input is divided by the
# preamp's gain (~13 V/V at the nominal sizing) -- the same division that
# demotes the steering pair's Vth mismatch to a second-order offset term.
# The steering pair's GATE capacitance at OUTx1 is likewise omitted from
# the sub-model's AC load (the absorber caps, which dominate that node's
# capacitance, are included); both omissions are stated here so the record
# inherits them. This remains a deliberate LOWER BOUND on the true
# regeneration-inclusive noise, per the port source's own DR-004.
#
# The AC stimulus is single-ended (Vinp gets AC=1, Vinn stays pure DC), and
# ngspice's `inoise_total` (referred back through Vinp) is reported as a
# single-ended input-referred rms noise voltage. For a symmetric
# differential pair with uncorrelated per-side noise contributions, the
# standard diff-pair noise-doubling result gives differential-input-referred
# variance = 2x the single-ended value, i.e.
# rms_differential = sqrt(2) * rms_single_ended -- applied here as a named,
# flagged approximation, not re-derived from scratch.

# The DR-002-ratified Input-referred noise row's bounds -- recorded here so
# the record states its own comparison against the ratified row (values cite
# DR-002 Decision 2: target <= 1.0 mV rms, stretch <= 0.6 mV rms, differential).
NOISE_TARGET_MV = 1.0
NOISE_STRETCH_MV = 0.6

VBIAS_NOTE = (
    "reduced sub-model of the DR-004 static preamplifier: preamp tail "
    "(gate at VDD) + input pair + both poly loads + both OUT1 absorber MOS "
    "caps, all re-emitted verbatim from the committed fragment; everything "
    "past the preamp outputs (steering pair, latch tail, cross-coupled "
    "PMOS, reset PMOS) omitted -- that is the loop break. Unlike the "
    "pre-DR-004 integration-phase proxy (diode-connected stand-in loads on "
    "a dynamic input stage), this stage holds its own real continuous DC "
    "operating point; noise taken at v(OUTP1,OUTN1)"
)
VBIAS_NOTE_PEX = (
    VBIAS_NOTE
    + ". POST-LAYOUT form: the same loop break applied to the EXTRACTED "
    "netlist instead of to the schematic fragment's device lines -- "
    "`layout/comparator.pex-preamp.spice`, generated by "
    "`layout/extract_pex.py` by dropping every extracted device that "
    "touches a latch net (CLK/CLKT/TAIL2/OUTP/OUTN) together with those "
    "nets' parasitics, and asserting that exactly the nine expected drawn "
    "devices survive (tail, four input-pair fingers, two poly loads, two "
    "absorber caps). The surviving nets keep their full extracted lumped-RC "
    "parasitics, including the per-terminal star legs on VINP/VINN/TAILP/"
    "OUTP1/OUTN1 and the net-to-net coupling capacitors among them"
)


def _noise_sub_model_lines() -> list[str]:
    """The loop-broken preamp sub-model, in the active DUT provenance.

    Schematic: built from the committed DUT fragment's OWN device lines
    (issue #24) -- tail, input pair, poly loads, absorber caps -- with
    everything past the preamp outputs omitted (the loop break; see the
    methodology note above). Sizing therefore tracks design/comparator.sch
    automatically; it is not transcribed here. The preamp contains no
    clocked device, so no CLK/CLKT steady-bias source is needed (the
    pre-DR-004 sub-model's Vclkfix/Vclkfixt lines existed to bias the
    omitted-from-latch tail's soft-clock gate; that device is no longer in
    the sub-model).

    Post-layout: the identical partition, but taken once at generation time
    by `layout/extract_pex.py` against the extracted netlist and committed,
    because on the extracted side "the preamp devices" is a connectivity
    question (a schematic device can be several drawn fingers, and each
    terminal hangs off a parasitic star leg) rather than a name lookup.
    """
    if _DUT_PROVENANCE == "extracted":
        return [PEX_PREAMP_FRAGMENT.read_text()]
    return [
        _dut_device_line("XM_PTAIL"),
        _dut_device_line("XM_PINN"),
        _dut_device_line("XM_PINP"),
        _dut_device_line("XR_LP"),
        _dut_device_line("XR_LN"),
        _dut_device_line("XM_C1P"),
        _dut_device_line("XM_C1N"),
    ]


def _noise_deck(info: pdk.PdkInfo, corner: str, temp_c: float) -> str:
    note = VBIAS_NOTE_PEX if _DUT_PROVENANCE == "extracted" else VBIAS_NOTE
    lines = [
        f"* comparator-decision input-referred noise ({note}) "
        f"corner={corner} temp={temp_c}C supply={VDD}V (issue #9)",
        f".lib {info.ngspice_lib} {corner}",
        f".temp {temp_c}",
        f".param vdd_val = {VDD}",
        "",
        "Vdd VDD 0 dc {vdd_val}",
        f"Vinp VINP 0 dc {VCM} AC 1",
        f"Vinn VINN 0 dc {VCM}",
        "",
        *_noise_sub_model_lines(),
        "",
        ".control",
        # sim/spiceinit sets 'option klu' repo-wide for corner-sweep speed,
        # but ngspice's KLU solver does not support .noise analysis. Switch
        # to SPARSE for this invocation only.
        "option sparse",
        "op",
        "print v(TAILP) v(OUTP1) v(OUTN1)",
        f"noise v(outp1,outn1) Vinp dec 20 {NOISE_FSTART_HZ:g} {NOISE_FSTOP_HZ:g} 20",
        "print inoise_total onoise_total",
        ".endc",
        ".end",
    ]
    return "\n".join(lines) + "\n"


@dataclass
class NoiseResult:
    single_ended_rms_v: float
    differential_rms_v: float
    op_tailp_v: float
    op_outp1_v: float
    op_outn1_v: float
    log_text: str
    corner: str
    temp_c: float


def run_noise(corner: str = "tt", temp_c: float = 27.0, quiet: bool = False) -> NoiseResult:
    info = pdk.resolve_or_raise()
    with tempfile.TemporaryDirectory(prefix="comparator-decision-noise-") as scratch:
        scratch_dir = Path(scratch)
        deck = _noise_deck(info, corner, temp_c)
        log_text = _run(deck, scratch_dir, "noise")

    op_tailp = op_outp1 = op_outn1 = float("nan")
    single_ended = float("nan")
    for line in log_text.splitlines():
        s = line.strip()
        if s.startswith("v(tailp)"):
            op_tailp = float(s.split("=")[1])
        elif s.startswith("v(outp1)"):
            op_outp1 = float(s.split("=")[1])
        elif s.startswith("v(outn1)"):
            op_outn1 = float(s.split("=")[1])
        elif s.startswith("inoise_total"):
            single_ended = float(s.split("=")[1])
    differential = single_ended * (2 ** 0.5)
    if not quiet:
        print(f"  op: TAILP={op_tailp:.4f}V OUTP1={op_outp1:.4f}V OUTN1={op_outn1:.4f}V")
        print(f"  inoise_total (single-ended) = {single_ended * 1000:.4f} mV rms")
        print(f"  differential estimate (x sqrt(2)) = {differential * 1000:.4f} mV rms")
    return NoiseResult(
        single_ended_rms_v=single_ended, differential_rms_v=differential,
        op_tailp_v=op_tailp, op_outp1_v=op_outp1, op_outn1_v=op_outn1,
        log_text=log_text, corner=corner, temp_c=temp_c,
    )


def write_noise_evidence(result: NoiseResult, note: str = "", supersedes: str = "") -> Path:
    info = pdk.resolve()
    netlist_text = _noise_deck(info, result.corner, result.temp_c)
    record_id = evidence.new_record_id()
    netlist_sha = evidence.sha256_text(netlist_text)
    record_path = evidence.write_netlist_snapshot_text(EXPERIMENT_DIR, record_id, netlist_text)
    runs_dir = EXPERIMENT_DIR / "corners" / record_id
    runs_dir.mkdir(parents=True, exist_ok=True)
    (runs_dir / "noise.log").write_text(result.log_text)

    lines: list[str] = []
    a = lines.append
    a(f"# Record {record_id}")
    a("")
    a(f"- **Record ID**: {record_id}")
    a(CLAIM_TEXT)
    a(
        (
            "- **Netlist provenance**: POST-LAYOUT / EXTRACTED, reduced "
            "sub-model -- the preamp partition of the extracted netlist "
            "(`layout/comparator.pex-preamp.spice`, from `layout/comparator.gds` "
            "via `klt extract --parasitics` and `layout/extract_pex.py`), WITH "
            "its extracted lumped-RC parasitics; everything past the preamp "
            "outputs is the loop break; see Methodology for what that omits "
            "and for how the partition is taken."
        ) if _DUT_PROVENANCE == "extracted" else (
            "- **Netlist provenance**: schematic-derived, reduced sub-model -- the "
            "DR-004 preamplifier stage's device lines (tail, input pair, poly "
            "loads, OUT1 absorber caps) are taken "
            "verbatim from `sim/comparator-decision/testbench/comparator_core.spice` "
            "(itself generated from `design/comparator.sch` by `./design/netlist.sh`); "
            "everything past the preamp outputs is the loop break; "
            "see Methodology for what that omits."
        )
    )
    a(f"- **Corner matrix run**: process=['{result.corner}'], temperature_c=[{result.temp_c}], supply_v=[{VDD}] (1 point)")
    a(
        f"- **Noise methodology**: `ac-based`, integration bandwidth "
        f"{NOISE_FSTART_HZ:g}Hz-{NOISE_FSTOP_HZ:g}Hz. REDUCED SUB-MODEL, not "
        f"the full comparator_core.spice fragment: "
        f"{VBIAS_NOTE_PEX if _DUT_PROVENANCE == 'extracted' else VBIAS_NOTE}. This is a "
        "named, flagged simplification (excludes the cross-coupled latch "
        "pair's own regenerative-phase noise contribution) -- a LOWER BOUND "
        "on the true regeneration-inclusive noise, per the port source's own "
        "documented derivation (see README.md)."
    )
    if note:
        a(f"- **Note**: {note}")
    a("- **Overall**: measured value recorded (informational plumbing proof, not pass/fail -- see Claim)")
    a("")
    a("## Measured value(s)")
    a("")
    a("| Quantity | Value | Corner condition |")
    a("|---|---|---|")
    a(f"| Op point: v(TAILP) | {result.op_tailp_v:.4f} V | {result.corner}/{result.temp_c}C/{VDD}V |")
    a(f"| Op point: v(OUTP1)=v(OUTN1) | {result.op_outp1_v:.4f} V | {result.corner}/{result.temp_c}C/{VDD}V |")
    a(
        f"| Single-ended input-referred noise (`inoise_total`, referred through Vinp) | "
        f"{result.single_ended_rms_v * 1000:.4f} mV rms | {result.corner}/{result.temp_c}C/{VDD}V |"
    )
    a(
        f"| **Differential input-referred noise estimate** (`sqrt(2) x` single-ended, "
        f"diff-pair noise-doubling approximation) | **{result.differential_rms_v * 1000:.4f} mV rms** | "
        f"{result.corner}/{result.temp_c}C/{VDD}V |"
    )
    a("")
    a(
        "- **Data provenance**: model-card-monte-carlo (sky130A BSIM4 device "
        "noise models via ngspice's `.noise` analysis; no literature/foundry-doc "
        "noise figure used)"
    )
    a(
        f"- **Ratified bound comparison (DR-002)**: the Input-referred noise "
        f"row is RATIFIED at <= {NOISE_TARGET_MV:g} mV rms differential "
        f"(target) / <= {NOISE_STRETCH_MV:g} mV rms (stretch). This record's "
        f"{result.differential_rms_v * 1000:.4f} mV rms differential estimate "
        f"(a LOWER BOUND, see Methodology) "
        f"{'clears' if result.differential_rms_v * 1000 <= NOISE_TARGET_MV else 'DOES NOT clear'} "
        f"the target bound"
        + (
            f" and {'clears' if result.differential_rms_v * 1000 <= NOISE_STRETCH_MV else 'DOES NOT yet clear'} "
            f"the stretch bound."
            if result.differential_rms_v * 1000 <= NOISE_TARGET_MV else
            " -- new information for the decision records to weigh, never "
            "silently superseding DR-002's disposition."
        )
    )
    a("")
    lines.extend(post_layout_delta_lines(
        "noise", result.corner, result.temp_c, result.differential_rms_v,
        unit_scale=1000.0))
    a("")
    return _finalize_record(
        lines, record_path, _resolve_pdk_line(info), toolchain._ngspice_version() or "unknown",
        netlist_sha, "noise", supersedes=supersedes,
    )


# ---------------------------------------------------------------------------
# noise-tran: REGENERATION-INCLUSIVE input-referred noise via transient-noise
# Monte Carlo with equivalent-source injection (issue #41)
# ---------------------------------------------------------------------------
#
# WHY THIS EXISTS. The `noise` sub-command above is, by its own statement, a
# LOWER BOUND: its loop-broken AC sub-model is the DR-004 preamplifier
# verbatim, linearized at its static bias -- so it excludes (a) the real
# time-varying propagation of that noise through the clocked evaluate
# trajectory (shaper ramp, TAIL2 descent, steering conduction onset) and
# (b) the latch front-end's own noise entering the decision after the
# preamp. DR-002's Open items and issue #41's acceptance criteria both ask
# for a regeneration-inclusive measurement "not the loop-broken
# lower-bound sub-model". ngspice-46 has NO device-noise-enabled transient
# analysis (verified against its NEWS: `trnoise` exists only on independent
# sources), so device noise cannot simply be switched on in a transient.
#
# METHOD -- equivalent-source injection into the FULL committed fragment,
# the standard workaround when the simulator lacks device transient noise,
# used deliberately and with its boundaries stated:
#
#  1. PREAMP term: the existing AC `noise` sub-command already yields the
#     preamp's input-referred rms (single-ended, 1kHz-1GHz). That figure is
#     re-injected per side as a TRNOISE() source in series with each
#     comparator input -- so the noise then propagates through the REAL
#     clocked trajectory of the full fragment (the time-varying part the AC
#     analysis cannot represent), not through a static linearization.
#  2. LATCH FRONT-END term: a NEW AC `.noise` sub-model of the steering
#     pair + strong tail verbatim (gates at the preamp's own static output
#     common mode from stage 1's op point, CLKT at VDD -- the evaluate
#     drive), drains DC-biased through ideal inductors to VDD and AC-loaded
#     only by noiseless capacitors. `inoise_total` referred through one
#     gate source is that stage's gate-referred rms over the same band.
#     The gate-referred figure is load-capacitance-insensitive (verified
#     5f-40fF: +-0.7%), because capacitors are noiseless and the
#     input-referral divides the load out; the load only shapes onoise.
#     That rms is re-injected per side as a TRNOISE() source in series
#     between each preamp output (OUTP1/OUTN1) and the corresponding
#     steering gate -- the exact node pair where latch noise physically
#     enters the decision.
#  3. TRNOISE() semantics were characterized empirically on this exact
#     ngspice build (see `run_trnoise_calibration`): the source emits
#     band-limited white Gaussian noise with time-domain std ~= 0.86*na,
#     updated every `ts`; independent streams per source; re-seeded by
#     `.option rndseed`. A calibration deck measures the actual injected
#     std at na=1mV and the target amplitudes are scaled off that measured
#     factor, so the record states achieved-vs-target injection rms
#     directly. Correlation time is 0.5ns (~the 1GHz AC integration band's
#     Nyquist interval); the PSD shape mismatch vs. the real shaped device
#     spectra is a stated approximation -- same band, same integrated rms.
#  4. MONTE CARLO, two statistics from the same seeded deck family:
#     a. PICK-OFF MC (primary): N seeds at Vindiff=0, each recording the
#        same v(OUTP)-v(OUTN) pick-off the `offset` sub-command uses, at
#        the same PICKOFF_NS after the evaluate edge. std(pickoff)/gain
#        (gain from the same ideal-device calibration) is the total
#        input-referred noise at the pick-off instant, propagated through
#        the real evaluate onset -- devices the AC sub-model omits are
#        present here, and both injected terms ride the true clocked
#        trajectory.
#     b. DECISION-TRANSITION cross-check (regeneration phase): at
#        +/-{0.75, 1.5} * sigma_hat_mv (sigma_hat from (a)) the same deck
#        runs M seeds per point through the FULL evaluate window and
#        records the final latched decision. The pair-symmetric estimator
#        p(+v)-p(-v) ~= 2*Phi(v/sigma)-1 inverts to a sigma per pair; if
#        the latch's regenerative phase added significant noise beyond
#        what (a) already sees at pick-off, the transition sigma comes out
#        LARGER than (a)'s -- the two statistics agreeing (within the
#        coarser CI of (b)) is the evidence that the regeneration phase
#        adds no material term beyond the injected device noise, which is
#        precisely the regeneration-inclusiveness claim this sub-command
#        exists to make. The residual omissions, stated: the cross-coupled
#        PMOS pair's noise DURING exponential separation (input-referred,
#        divided by the exponentially growing regenerative gain -- a
#        second-order term by the same division argument that demotes
#        steering-pair Vth mismatch) and the reset PMOS (off in evaluate).
#
# Injection topology note: the steering pair's device lines are re-emitted
# with their GATE terminals moved to injected nodes GST_P/GST_N (via
# `_dut_device_line(name, nodes=...)`, the same node-replacement helper the
# reset counterfactual uses), so the committed sizing still tracks the
# schematic verbatim; the trnoise sources sit in series between OUTP1/OUTN1
# and GST_P/GST_N with DC=0 (no bias disturbance).

NOISE_TRAN_TS = 0.37e-9         # trnoise update/correlation interval (s).
# NOT 0.5ns (the 1GHz band's Nyquist interval): a 0.5ns update grid puts a
# noise jump at t=5.0ns EXACTLY -- coincident with the reset->evaluate edge
# -- and the transient solver's timestep collapses there ("Timestep too
# small; time = 5e-09", observed on ngspice-46). 0.37ns keeps the grid off
# every critical instant (updates land at 0.37*k ns, never on 5.0 or 5.1)
# while leaving the injected band (~1.35GHz Nyquist) close to the AC
# integration band; the calibration targets the INTEGRATED rms, which is
# band-matched by construction. A per-deck retry with a perturbed interval
# (0.41ns, see _run_mc_deck) covers any residual pathological coincidence
# at other seeds/corners.
NOISE_TRAN_EVALUATE_NS = 20.0   # decision window (b): full separation + metastability margin
NOISE_TRAN_DECIDE_PAIRS = (0.75, 1.5)  # |Vod| points, in units of sigma_hat
NOISE_TRAN_SEEDS_PER_POINT = 64  # decision-transition seeds per (sign, point)
LATCH_NOISE_CL_FF = 10.0        # steering-sub-model drain load (bandwidth only -- noiseless)


NOISE_TRAN_RETRY_TS = 0.41e-9    # perturbed update grid for the per-deck retry


def _run_many_ts_retry(builds, scratch_dir: Path, workers: int = 1) -> dict[str, str]:
    """Parallel batch of noise-tran decks, each retried once at the
    perturbed update interval on ngspice failure. `builds` is a list of
    (name, build(ts)->deck). First pass runs everything at the default ts
    in parallel; decks that failed are retried individually at the
    perturbed ts (rare, so sequential retry is fine). The retry exists
    because a noise-update jump coinciding with a solver breakpoint can
    collapse the transient timestep (the t=5.0ns exact coincidence that
    ruled out the 0.5ns grid -- see NOISE_TRAN_TS); a different grid with
    identical statistics resolves it. A deck that fails BOTH grids is a
    real failure and propagates."""
    from concurrent.futures import ThreadPoolExecutor
    results: dict[str, str] = {}
    failed: list[tuple[str, object]] = []
    if workers <= 1:
        for name, build in builds:
            try:
                results[name] = _run(build(NOISE_TRAN_TS), scratch_dir, name)
            except RuntimeError:
                failed.append((name, build))
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_run, build(NOISE_TRAN_TS), scratch_dir, name): (name, build)
                       for name, build in builds}
            for future in futures:
                name, build = futures[future]
                try:
                    results[name] = future.result()
                except RuntimeError:
                    failed.append((name, build))
    for name, build in failed:
        results[name] = _run(build(NOISE_TRAN_RETRY_TS), scratch_dir, name)
    return results


def _trnoise_calibration_deck(na: float, ts: float) -> str:
    """Measure the actual injected time-domain std of a TRNOISE(na, ts, 0, 0)
    source on this ngspice build -- ngspice's manual states the parameter
    semantics only loosely for this source, so the campaign calibrates it
    empirically instead of trusting a formula (the record prints the
    achieved-vs-target rms). The deck drives a 1-ohm resistor from the
    source and reports mean/std of v(n1) computed inside ngspice, so the
    returned log parses to one `cal_std =` line."""
    npts = 100000
    return "\n".join([
        f"* trnoise injection calibration -- na={na} ts={ts}",
        ".options rndseed=41",
        f"V1 n1 0 DC 0 TRNOISE({na:g} {ts:g} 0 0)",
        "R1 n1 0 1",
        ".control",
        f"tran {ts:g} {npts * ts:g}",
        "let m = mean(v(n1))",
        "let s = sqrt(mean((v(n1)-m)*(v(n1)-m)))",
        f"echo cal_std=$&s",
        ".endc",
        ".end",
    ]) + "\n"


def run_trnoise_calibration(quiet: bool = False) -> float:
    """Return the measured std-per-unit-na of the TRNOISE source at the
    campaign's correlation time (fraction ~0.86 measured on ngspice-46)."""
    with tempfile.TemporaryDirectory(prefix="comparator-decision-trncal-") as scratch:
        scratch_dir = Path(scratch)
        log_text = _run(_trnoise_calibration_deck(1e-3, NOISE_TRAN_TS), scratch_dir, "trncal")
    factor = float("nan")
    for line in log_text.splitlines():
        if line.strip().startswith("cal_std="):
            factor = float(line.split("=")[1].strip()) / 1e-3
    if not (factor > 0):
        raise RuntimeError(f"trnoise calibration failed to parse: {log_text[-400:]}")
    if not quiet:
        print(f"  trnoise calibration: std = {factor:.4f} x na (na in volts, ts={NOISE_TRAN_TS:g}s)")
    return factor


def _latch_noise_deck(
    info: pdk.PdkInfo, corner: str, temp_c: float, gate_cm_v: float, cl_ff: float,
) -> str:
    """AC `.noise` deck for the latch front-end's gate-referred noise (stage
    2 above): steering pair + strong tail re-emitted verbatim from the
    committed fragment (gates moved to driven nodes), linearized at the
    preamp's own static output common mode with CLKT at VDD."""
    return "\n".join([
        f"* comparator-decision latch front-end gate-referred noise -- "
        f"corner={corner} temp={temp_c}C gate_cm={gate_cm_v:.4f}V (issue #41)",
        f".lib {info.ngspice_lib} {corner}",
        f".temp {temp_c}",
        f".param vdd_val = {VDD} vcmo = {gate_cm_v:.6f}",
        "",
        "Vdd VDD 0 dc {vdd_val}",
        "Vclkfix CLKT 0 dc {vdd_val}",
        "Vstp GST_P 0 dc {vcmo} AC 1",
        "Vstn GST_N 0 dc {vcmo}",
        "",
        "* steering pair + strong tail, verbatim device lines (gates on the",
        "* driven GST_* nodes -- the same node-replacement helper the reset",
        "* counterfactual uses)",
        _dut_device_line("XM_STN_P", nodes=["OUTP", "GST_P", "TAIL2", "GND"]),
        _dut_device_line("XM_STN_N", nodes=["OUTN", "GST_N", "TAIL2", "GND"]),
        _dut_device_line("XM_TAIL2"),
        "",
        "* noiseless loads: ideal inductors DC-bias the drains at VDD while",
        f"* presenting their band as open; shunt caps ({cl_ff:g}fF) shape only",
        "* onoise's bandwidth -- caps are noiseless, so inoise_total (the",
        "* gate-referred figure) is load-insensitive (verified 5f-40fF).",
        "Lp OUTP VDD 1",
        "Ln OUTN VDD 1",
        f"Cp OUTP 0 {cl_ff:g}f",
        f"Cn OUTN 0 {cl_ff:g}f",
        "",
        ".control",
        "option sparse",
        "op",
        "print v(TAIL2) v(OUTP) v(OUTN)",
        f"noise v(OUTP,OUTN) Vstp dec 20 {NOISE_FSTART_HZ:g} {NOISE_FSTOP_HZ:g} 20",
        "print inoise_total onoise_total",
        ".endc",
        ".end",
    ]) + "\n"


@dataclass
class LatchNoiseResult:
    gate_rms_v: float
    op_tail2_v: float
    log_text: str
    corner: str
    temp_c: float
    gate_cm_v: float
    cl_ff: float


def run_latch_noise(
    corner: str = "tt", temp_c: float = 27.0, gate_cm_v: float = 1.18,
    cl_ff: float = LATCH_NOISE_CL_FF, quiet: bool = False,
) -> LatchNoiseResult:
    info = pdk.resolve_or_raise()
    with tempfile.TemporaryDirectory(prefix="comparator-decision-lnoise-") as scratch:
        scratch_dir = Path(scratch)
        deck = _latch_noise_deck(info, corner, temp_c, gate_cm_v, cl_ff)
        log_text = _run(deck, scratch_dir, "latch_noise")
    op_tail2 = gate_rms = float("nan")
    for line in log_text.splitlines():
        s = line.strip()
        if s.startswith("v(tail2)"):
            op_tail2 = float(s.split("=")[1])
        elif s.startswith("inoise_total"):
            gate_rms = float(s.split("=")[1])
    if not quiet:
        print(
            f"  latch front-end (gate-referred, {corner}/{temp_c}C): "
            f"inoise_total = {gate_rms * 1000:.4f} mV rms (op TAIL2={op_tail2:.4f}V)"
        )
    return LatchNoiseResult(
        gate_rms_v=gate_rms, op_tail2_v=op_tail2, log_text=log_text,
        corner=corner, temp_c=temp_c, gate_cm_v=gate_cm_v, cl_ff=cl_ff,
    )


def _noise_tran_pickoff_deck(
    info: pdk.PdkInfo, corner: str, temp_c: float, vindiff_mv: float, seed: int,
    na_input: float, na_gate: float, log_name: str, ts: float = NOISE_TRAN_TS,
) -> str:
    """One noise-seeded pick-off transient (statistic (a) above): the full
    committed fragment, inputs driven through per-side trnoise sources of
    the calibrated preamp rms, steering gates driven through per-side
    trnoise sources of the calibrated latch rms."""
    vindiff_v = vindiff_mv / 1000.0
    evaluate_ns = PICKOFF_TSTOP_NS - RESET_NS - RESET_TR_NS
    period_ns = RESET_NS + RESET_TR_NS + evaluate_ns + 10.0
    lines = [
        f"* comparator-decision noise-tran pick-off -- vindiff={vindiff_mv}mV "
        f"seed={seed} corner={corner} temp={temp_c}C (issue #41)",
        f".lib {info.ngspice_lib} {corner}",
        f".temp {temp_c}",
        f".param vdd_val = {VDD}",
        f".option rndseed={seed}",
        "",
        "Vdd VDD 0 dc {vdd_val}",
        f"Vclk CLK 0 PULSE(0 {{vdd_val}} {RESET_NS}n {RESET_TR_NS}n {RESET_TR_NS}n "
        f"{evaluate_ns}n {period_ns}n)",
        f"Vinp VINP 0 dc {VCM + vindiff_v / 2} TRNOISE({na_input:g} {ts:g} 0 0)",
        f"Vinn VINN 0 dc {VCM - vindiff_v / 2} TRNOISE({na_input:g} {ts:g} 0 0)",
        "",
        "* full committed fragment, with the steering pair's gates moved to",
        "* the injected nodes GST_P/GST_N (sizing verbatim; the series",
        "* trnoise sources carry the latch front-end's gate-referred rms):",
    ]
    for raw in _dut_lines().splitlines():
        stripped = raw.strip()
        if stripped.startswith(("XM_STN_P", "XM_STN_N")):
            gate_node = "GST_P" if stripped.split()[0] == "XM_STN_P" else "GST_N"
            out_node = "OUTP" if stripped.split()[0] == "XM_STN_P" else "OUTN"
            lines.append(_dut_device_line(
                "XM_STN_P" if gate_node == "GST_P" else "XM_STN_N",
                nodes=[out_node, gate_node, "TAIL2", "GND"],
            ))
        else:
            lines.append(raw)
    lines += [
        "",
        f"Vstp GST_P OUTP1 dc 0 TRNOISE({na_gate:g} {ts:g} 0 0)",
        f"Vstn GST_N OUTN1 dc 0 TRNOISE({na_gate:g} {ts:g} 0 0)",
        "",
        ".control",
        f"tran 0.002n {PICKOFF_TSTOP_NS}n",
        f"wrdata {log_name}.csv v(OUTP) v(OUTN)",
        ".endc",
        ".end",
    ]
    return "\n".join(lines) + "\n"


def _noise_tran_decision_deck(
    info: pdk.PdkInfo, corner: str, temp_c: float, vindiff_mv: float, seed: int,
    na_input: float, na_gate: float, log_name: str, ts: float = NOISE_TRAN_TS,
) -> str:
    """One noise-seeded full-decision transient (statistic (b) above): same
    injection topology as the pick-off deck, but the full evaluate window
    (NOISE_TRAN_EVALUATE_NS) so the final latched decision is recorded."""
    vindiff_v = vindiff_mv / 1000.0
    period_ns = RESET_NS + RESET_TR_NS + NOISE_TRAN_EVALUATE_NS + 10.0
    lines = [
        f"* comparator-decision noise-tran decision -- vindiff={vindiff_mv}mV "
        f"seed={seed} corner={corner} temp={temp_c}C (issue #41)",
        f".lib {info.ngspice_lib} {corner}",
        f".temp {temp_c}",
        f".param vdd_val = {VDD}",
        f".option rndseed={seed}",
        "",
        "Vdd VDD 0 dc {vdd_val}",
        f"Vclk CLK 0 PULSE(0 {{vdd_val}} {RESET_NS}n {RESET_TR_NS}n {RESET_TR_NS}n "
        f"{NOISE_TRAN_EVALUATE_NS}n {period_ns}n)",
        f"Vinp VINP 0 dc {VCM + vindiff_v / 2} TRNOISE({na_input:g} {ts:g} 0 0)",
        f"Vinn VINN 0 dc {VCM - vindiff_v / 2} TRNOISE({na_input:g} {ts:g} 0 0)",
        "",
        "* full committed fragment, steering gates on injected nodes (see",
        "* the pick-off deck above for the topology note):",
    ]
    for raw in _dut_lines().splitlines():
        stripped = raw.strip()
        if stripped.startswith(("XM_STN_P", "XM_STN_N")):
            name = stripped.split()[0]
            gate_node = "GST_P" if name == "XM_STN_P" else "GST_N"
            out_node = "OUTP" if name == "XM_STN_P" else "OUTN"
            lines.append(_dut_device_line(name, nodes=[out_node, gate_node, "TAIL2", "GND"]))
        else:
            lines.append(raw)
    lines += [
        "",
        f"Vstp GST_P OUTP1 dc 0 TRNOISE({na_gate:g} {ts:g} 0 0)",
        f"Vstn GST_N OUTN1 dc 0 TRNOISE({na_gate:g} {ts:g} 0 0)",
        "",
        ".control",
        f"tran 0.01n {RESET_NS + RESET_TR_NS + NOISE_TRAN_EVALUATE_NS}n",
        f"wrdata {log_name}.csv v(OUTP) v(OUTN)",
        ".endc",
        ".end",
    ]
    return "\n".join(lines) + "\n"


def _decision_from_csv(csv_path: Path) -> int | None:
    """Final latched decision from a decision-window wrdata csv: +1 if
    OUTP-OUTN > 0 at the last sample, -1 if < 0, None if the run never
    separated (unresolved metastability inside the window)."""
    t, outp, outn = toolchain.read_wrdata_csv(csv_path, 2)
    diff = outp[-1] - outn[-1]
    if diff > 0.1:
        return 1
    if diff < -0.1:
        return -1
    return None


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + __import__("math").erf(x / 2 ** 0.5))


def _probit(p: float) -> float:
    """Inverse normal CDF by bisection on _norm_cdf (no scipy in the
    toolchain; the estimator only needs a few digits)."""
    lo, hi = -8.0, 8.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if _norm_cdf(mid) < p:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def pair_sigma_mv(v_mv: float, plus_ones: int, plus_n: int, minus_ones: int, minus_n: int) -> float:
    """Pair-symmetric sigma estimate (mV) from one +/-v_mv decision pair:
    p+ - p- ~= 2*Phi(v/sigma) - 1 (offset cancels to first order), so
    sigma = v / Phi^-1((1 + p+ - p-)/2). Returns NaN if the pair is
    degenerate -- all-same-way at both signs, or p+ == p- (all-unresolved
    or all-correct, e.g. when v sits below the corner's resolvable-overdrive
    floor so nothing decides, or so far above it that noise never flips a
    decision; either way the pair carries no sigma information)."""
    p_plus = plus_ones / plus_n
    p_minus = minus_ones / minus_n
    arg = 0.5 * (1.0 + p_plus - p_minus)
    if not (0.01 < arg < 0.99):
        return float("nan")
    denom = _probit(arg)
    if abs(denom) < 1e-9:
        return float("nan")
    return v_mv / denom


@dataclass
class NoiseTranResult:
    corner: str
    temp_c: float
    preamp: NoiseResult
    latch: LatchNoiseResult
    trnoise_factor: float
    na_input: float
    na_gate: float
    cal_achieved_input_rms_v: float
    cal_achieved_gate_rms_v: float
    gain_v_per_v: float
    gain_cal_points: list[tuple[float, float]]
    pickoff_diffs: list[float]          # v(OUTP)-v(OUTN) at pick-off, per seed
    sigma_pickoff_mv: float
    sigma_pickoff_ci95_mv: tuple[float, float]
    decision_points: list[dict]         # per |vod| point: {v_mv, plus_ones, minus_ones, unresolved, m}
    sigma_decision_mv: float            # inverse-variance-weighted mean over pairs
    logs: dict[str, str] = field(default_factory=dict)


def run_noise_tran(
    corner: str = "tt", temp_c: float = 27.0, n_pickoff: int = 128,
    seeds_per_point: int = NOISE_TRAN_SEEDS_PER_POINT, quiet: bool = False,
    jobs: int = 1,
) -> NoiseTranResult:
    info = pdk.resolve_or_raise()
    logs: dict[str, str] = {}

    # Stage 1: preamp input-referred rms + its op point (gate CM for stage 2).
    preamp = run_noise(corner=corner, temp_c=temp_c, quiet=quiet)
    # Stage 2: latch front-end gate-referred rms, biased at the preamp's own CM.
    gate_cm = preamp.op_outp1_v
    latch = run_latch_noise(corner=corner, temp_c=temp_c, gate_cm_v=gate_cm, quiet=quiet)
    logs["latch_noise"] = latch.log_text
    # Stage 3: calibrate TRNOISE std-per-na, then scale the two amplitudes.
    factor = run_trnoise_calibration(quiet=quiet)
    na_input = preamp.single_ended_rms_v / factor
    na_gate = latch.gate_rms_v / factor
    if not quiet:
        print(
            f"  injection amplitudes: input na={na_input:g}V "
            f"(target {preamp.single_ended_rms_v * 1000:.4f} mV rms/side), "
            f"gate na={na_gate:g}V (target {latch.gate_rms_v * 1000:.4f} mV rms/side)"
        )

    with tempfile.TemporaryDirectory(prefix="comparator-decision-noisetran-") as scratch:
        scratch_dir = Path(scratch)

        # Gain calibration: ideal devices, plain corner, NO noise -- the
        # same calibration the `offset` sub-command performs, so the
        # pick-off statistic is referred back through the identical gain.
        cal_jobs = [(f"gaincal_{v}mV", _pickoff_deck(info, corner, temp_c, v, f"gaincal_{v}mV"))
                    for v in VINDIFF_GAIN_CAL_MV]
        logs.update(_run_many(cal_jobs, scratch_dir, jobs))
        gain_cal_points = [
            (v / 1000.0, _pickoff_value(scratch_dir / f"gaincal_{v}mV.csv"))
            for v in VINDIFF_GAIN_CAL_MV
        ]
        sxy = sum(x * y for x, y in gain_cal_points)
        sxx = sum(x * x for x, y in gain_cal_points)
        gain = sxy / sxx if sxx else float("nan")
        if not quiet:
            print(f"  gain = {gain:.4f} V/V (from {len(gain_cal_points)} calibration points)")

        # Injection-rms verification decks: the same trnoise sources into a
        # 1-ohm load, one for each amplitude, so the record can state
        # achieved-vs-target injection rms directly.
        for tag, na in (("input", na_input), ("gate", na_gate)):
            cal_log = _trnoise_calibration_deck(na, NOISE_TRAN_TS)
            vlog = _run(cal_log, scratch_dir, f"injcal_{tag}")
            logs[f"injcal_{tag}"] = vlog
        achieved = {}
        for tag in ("input", "gate"):
            for line in logs[f"injcal_{tag}"].splitlines():
                if line.strip().startswith("cal_std="):
                    achieved[tag] = float(line.split("=")[1].strip())

        # Statistic (a): pick-off MC at Vindiff=0, n_pickoff seeds.
        seed_base = 10_000

        def _po_build(i: int):
            def build(ts: float) -> str:
                return _noise_tran_pickoff_deck(
                    info, corner, temp_c, 0.0, seed_base + i,
                    na_input, na_gate, f"po_{i}", ts=ts,
                )
            return build

        po_builds = [(f"po_{i}", _po_build(i)) for i in range(n_pickoff)]
        logs.update(_run_many_ts_retry(po_builds, scratch_dir, jobs))
        pickoff_diffs = [
            _pickoff_value(scratch_dir / f"po_{i}.csv") for i in range(n_pickoff)
        ]
        sigma_pickoff_v = (
            statistics.pstdev([d / gain for d in pickoff_diffs]) if n_pickoff > 1 else float("nan")
        )
        # Bootstrap 95% CI on the input-referred sigma (normal-approx SE is
        # available in closed form; bootstrap also captures the small-sample
        # skew -- 1000 resamples, stdlib random).
        import random as _random
        rng = _random.Random(20260922)
        referred = [d / gain for d in pickoff_diffs]
        boot = []
        for _ in range(1000):
            sample = rng.choices(referred, k=len(referred))
            boot.append(statistics.pstdev(sample))
        boot.sort()
        ci = (boot[49] * 1000, boot[949] * 1000)
        if not quiet:
            print(
                f"  pick-off MC: N={n_pickoff} -> sigma_in = {sigma_pickoff_v * 1000:.4f} mV "
                f"(95% CI [{ci[0]:.4f}, {ci[1]:.4f}] mV)"
            )

        # Statistic (b): decision-transition cross-check at +/-k*sigma_hat.
        sigma_hat_mv = sigma_pickoff_v * 1000
        decision_points: list[dict] = []
        dseed_base = 20_000
        for k in NOISE_TRAN_DECIDE_PAIRS:
            v_mv = k * sigma_hat_mv
            point = {"k": k, "v_mv": v_mv, "m": seeds_per_point,
                     "plus_ones": 0, "minus_ones": 0, "unresolved": 0}
            d_builds = []

            def _dec_build(name: str, vod_mv: float, dseed: int):
                def build(ts: float) -> str:
                    return _noise_tran_decision_deck(
                        info, corner, temp_c, vod_mv, dseed,
                        na_input, na_gate, name, ts=ts,
                    )
                return build

            for sign in (1, -1):
                for i in range(seeds_per_point):
                    name = f"dec_{k:g}_{ '+' if sign > 0 else '-'}_{i}".replace(".", "p")
                    dseed = (dseed_base + int(k * 1000) * 10_000
                             + (seeds_per_point if sign > 0 else 0) + i)
                    d_builds.append((name, _dec_build(name, sign * v_mv, dseed)))
            d_logs = _run_many_ts_retry(d_builds, scratch_dir, jobs)
            logs.update(d_logs)
            for sign in (1, -1):
                ones = 0
                unresolved = 0
                for i in range(seeds_per_point):
                    name = f"dec_{k:g}_{ '+' if sign > 0 else '-'}_{i}".replace(".", "p")
                    dec = _decision_from_csv(scratch_dir / f"{name}.csv")
                    if dec is None:
                        unresolved += 1
                    elif dec == 1:
                        ones += 1
                if sign > 0:
                    point["plus_ones"] = ones
                    point["plus_unresolved"] = unresolved
                else:
                    point["minus_ones"] = ones
                    point["minus_unresolved"] = unresolved
            point["unresolved"] = point.get("plus_unresolved", 0) + point.get("minus_unresolved", 0)
            decision_points.append(point)
            if not quiet:
                print(
                    f"  decision pair |v|={v_mv:.4f}mV: p+={point['plus_ones']}/{seeds_per_point} "
                    f"p-={point['minus_ones']}/{seeds_per_point} "
                    f"unresolved={point['unresolved']}"
                )

    # Combine pairs: inverse-variance weights via the delta-method variance
    # of each pair's probit (binomial on p+ - p-).
    pair_sigmas: list[tuple[float, float]] = []  # (sigma_mv, var)
    for point in decision_points:
        m = point["m"]
        sigma_i = pair_sigma_mv(
            point["v_mv"], point["plus_ones"], m, point["minus_ones"], m,
        )
        if sigma_i != sigma_i:  # NaN: degenerate pair
            continue
        p_plus = point["plus_ones"] / m
        p_minus = point["minus_ones"] / m
        arg = 0.5 * (1.0 + p_plus - p_minus)
        darg = _probit(arg)
        # var(sigma_i)/sigma_i^2 ~ (dPhi^-1/darg)^2 * var(arg) / darg^2
        dprobit = (2 * 3.141592653589793) ** 0.5 * pow(2.718281828459045, 0.5 * darg * darg)
        var_arg = (p_plus * (1 - p_plus) + p_minus * (1 - p_minus)) / m
        rel_var = (dprobit * dprobit * var_arg) / (darg * darg)
        pair_sigmas.append((sigma_i, (sigma_i * sigma_i) * rel_var))
    if pair_sigmas:
        wsum = sum(1.0 / v for _, v in pair_sigmas)
        sigma_decision = sum(s / v for s, v in pair_sigmas) / wsum
    else:
        sigma_decision = float("nan")

    return NoiseTranResult(
        corner=corner, temp_c=temp_c, preamp=preamp, latch=latch,
        trnoise_factor=factor, na_input=na_input, na_gate=na_gate,
        cal_achieved_input_rms_v=achieved.get("input", float("nan")),
        cal_achieved_gate_rms_v=achieved.get("gate", float("nan")),
        gain_v_per_v=gain, gain_cal_points=gain_cal_points,
        pickoff_diffs=pickoff_diffs,
        sigma_pickoff_mv=sigma_pickoff_v * 1000,
        sigma_pickoff_ci95_mv=ci,
        decision_points=decision_points,
        sigma_decision_mv=sigma_decision,
        logs=logs,
    )


def write_noise_tran_evidence(
    result: NoiseTranResult, note: str = "", supersedes: str = "",
) -> Path:
    info = pdk.resolve()
    netlist_text = _noise_tran_pickoff_deck(
        info, result.corner, result.temp_c, 0.0, 10000,
        result.na_input, result.na_gate, "noise_tran_pickoff",
    )
    record_id = evidence.new_record_id()
    netlist_sha = evidence.sha256_text(netlist_text)
    record_path = evidence.write_netlist_snapshot_text(EXPERIMENT_DIR, record_id, netlist_text)
    runs_dir = EXPERIMENT_DIR / "corners" / record_id
    runs_dir.mkdir(parents=True, exist_ok=True)
    for name in ("latch_noise", "injcal_input", "injcal_gate"):
        if name in result.logs:
            (runs_dir / f"{name}.log").write_text(result.logs[name])

    lines: list[str] = []
    a = lines.append
    a(f"# Record {record_id}")
    a("")
    a(f"- **Record ID**: {record_id}")
    a(CLAIM_TEXT)
    a(netlist_provenance())
    a(f"- **Corner matrix run**: process=['{result.corner}'], temperature_c=[{result.temp_c}], supply_v=[{VDD}] (1 point)")
    a(
        f"- **Noise methodology**: `tran-noise-mc` (issue #41), REGENERATION-"
        f"INCLUSIVE by equivalent-source injection -- per-side TRNOISE sources "
        f"at the comparator inputs (preamp input-referred rms from the AC "
        f"`noise` sub-command: {result.preamp.single_ended_rms_v * 1000:.4f} mV) "
        f"and in series with the steering gates (latch front-end gate-referred "
        f"rms from a new steering+tail AC sub-model: {result.latch.gate_rms_v * 1000:.4f} mV, "
        f"load-cap insensitivity verified), propagated through the FULL committed "
        f"fragment's real clocked evaluate trajectory. Injected rms calibrated "
        f"empirically against this ngspice build's TRNOISE semantics "
        f"(std = {result.trnoise_factor:.4f} x na; achieved "
        f"{result.cal_achieved_input_rms_v * 1000:.4f} mV input / "
        f"{result.cal_achieved_gate_rms_v * 1000:.4f} mV gate vs the AC targets), "
        f"correlation time {NOISE_TRAN_TS:g}s (~the 1GHz AC band's Nyquist "
        f"interval). Stated residual omissions: the cross-coupled PMOS pair's "
        f"noise during exponential separation (divided by the growing "
        f"regenerative gain) and the reset PMOS (off in evaluate)."
    )
    if result.sigma_decision_mv == result.sigma_decision_mv:
        a(
            f"- **Two statistics, one claim**: (a) pick-off MC at Vindiff=0, "
            f"N={len(result.pickoff_diffs)} seeds, gain "
            f"{result.gain_v_per_v:.4f} V/V -> input-referred sigma "
            f"**{result.sigma_pickoff_mv:.4f} mV** (95% CI "
            f"[{result.sigma_pickoff_ci95_mv[0]:.4f}, {result.sigma_pickoff_ci95_mv[1]:.4f}] mV); "
            f"(b) decision-transition cross-check at "
            f"+/-{NOISE_TRAN_DECIDE_PAIRS} sigma_hat, {result.decision_points[0]['m'] if result.decision_points else 0} "
            f"seeds/point -> sigma **{result.sigma_decision_mv:.4f} mV**. (b)'s agreeing "
            f"with (a) within (b)'s coarser CI is the evidence that the "
            f"regenerative phase adds no material noise term beyond the injected "
            f"device noise -- the regeneration-inclusiveness this record exists "
            f"to establish."
        )
    else:
        a(
            f"- **Two statistics, one claim**: (a) pick-off MC at Vindiff=0, "
            f"N={len(result.pickoff_diffs)} seeds, gain "
            f"{result.gain_v_per_v:.4f} V/V -> input-referred sigma "
            f"**{result.sigma_pickoff_mv:.4f} mV** (95% CI "
            f"[{result.sigma_pickoff_ci95_mv[0]:.4f}, {result.sigma_pickoff_ci95_mv[1]:.4f}] mV). "
            f"(b) The decision-transition cross-check is NOT MEASURABLE at this "
            f"corner: every pair was degenerate (see the table below -- the "
            f"sigma-scaled overdrives sit below this corner's resolvable-"
            f"overdrive floor, so runs either never resolve within the window "
            f"or all decide correctly). That is itself the physical statement: "
            f"at this corner the input-referred noise sigma is far below the "
            f"deterministic resolution floor DR-004 already documented, so "
            f"noise does not bound the decision statistics here and the pick-"
            f"off figure stands alone, with the cross-check deferred to the "
            f"corners where it is measurable."
        )
    if note:
        a(f"- **Note**: {note}")
    overall = "MEASURED" if result.sigma_pickoff_mv == result.sigma_pickoff_mv else "FAIL"
    a(f"- **Overall**: {overall} (informational characterization, not pass/fail -- see Claim)")
    a("")
    a("## Injection calibration")
    a("")
    a("| Injected term | AC target (mV rms/side) | achieved (mV rms/side) |")
    a("|---|---|---|")
    a(
        f"| preamp, at comparator inputs | {result.preamp.single_ended_rms_v * 1000:.4f} | "
        f"{result.cal_achieved_input_rms_v * 1000:.4f} |"
    )
    a(
        f"| latch front-end, in series with steering gates | {result.latch.gate_rms_v * 1000:.4f} | "
        f"{result.cal_achieved_gate_rms_v * 1000:.4f} |"
    )
    a("")
    a("## AC anchors (this corner)")
    a("")
    a("| Quantity | Value |")
    a("|---|---|")
    a(f"| Preamp single-ended input-referred (AC `noise` sub-command, 1kHz-1GHz) | {result.preamp.single_ended_rms_v * 1000:.4f} mV rms |")
    a(f"| Latch front-end gate-referred (steering+tail sub-model, same band, gate CM {result.latch.gate_cm_v:.4f}V, op TAIL2 {result.latch.op_tail2_v:.4f}V) | {result.latch.gate_rms_v * 1000:.4f} mV rms |")
    a(f"| Pick-off gain (ideal-device calibration) | {result.gain_v_per_v:.4f} V/V |")
    a("")
    a("## Pick-off Monte Carlo (statistic (a))")
    a("")
    a("| N | sigma input-referred (mV) | 95% CI (mV) |")
    a("|---|---|---|")
    a(
        f"| {len(result.pickoff_diffs)} | {result.sigma_pickoff_mv:.4f} | "
        f"[{result.sigma_pickoff_ci95_mv[0]:.4f}, {result.sigma_pickoff_ci95_mv[1]:.4f}] |"
    )
    a("")
    a("## Decision-transition cross-check (statistic (b))")
    a("")
    a("| \\|Vod\\| (mV) | k (x sigma_hat) | +Vod: ones/M | -Vod: ones/M | unresolved | pair sigma (mV) |")
    a("|---|---|---|---|---|---|")
    for point in result.decision_points:
        m = point["m"]
        pair = pair_sigma_mv(point["v_mv"], point["plus_ones"], m, point["minus_ones"], m)
        pair_shown = f"{pair:.4f}" if pair == pair else "degenerate"
        a(
            f"| {point['v_mv']:.4f} | {point['k']:g} | {point['plus_ones']}/{m} | "
            f"{point['minus_ones']}/{m} | {point['unresolved']} | {pair_shown} |"
        )
    a(
        f"\nInverse-variance-weighted decision sigma: "
        + (
            f"**{result.sigma_decision_mv:.4f} mV**"
            if result.sigma_decision_mv == result.sigma_decision_mv else
            "**not measurable at this corner** (every pair degenerate -- "
            "sigma-scaled overdrives sit below the corner's resolvable-"
            "overdrive floor; see the unresolved counts above)"
        )
    )
    a("")
    diff_rms_pickoff = result.sigma_pickoff_mv
    a(
        f"- **Ratified bound comparison (DR-002)**: the Input-referred noise "
        f"row is RATIFIED at <= {NOISE_TARGET_MV:g} mV rms differential "
        f"(target) / <= {NOISE_STRETCH_MV:g} mV (stretch). This record's "
        f"regeneration-inclusive pick-off sigma {diff_rms_pickoff:.4f} mV "
        f"(differential; the per-side injections are independent, the same "
        f"convention the sqrt(2) AC estimate uses) "
        f"{'clears' if diff_rms_pickoff <= NOISE_TARGET_MV else 'DOES NOT clear'} the target bound"
        + (
            f" and {'clears' if diff_rms_pickoff <= NOISE_STRETCH_MV else 'DOES NOT yet clear'} "
            f"the stretch bound."
            if diff_rms_pickoff <= NOISE_TARGET_MV else
            " -- new information for the decision records to weigh, never "
            "silently superseding DR-002's disposition."
        )
    )
    a("")
    return _finalize_record(
        lines, record_path, _resolve_pdk_line(info), toolchain._ngspice_version() or "unknown",
        netlist_sha, "noise-tran",
        extra={"noise-tran N pickoff": str(len(result.pickoff_diffs))},
        supersedes=supersedes,
    )


# ---------------------------------------------------------------------------
# reset: reset-integrity negative control (issue #24)
# ---------------------------------------------------------------------------
#
# WHY THIS EXISTS. DR-001 Decision 3 derives, from first principles, that a
# StrongARM-class cross-coupled pair must not be a live positive-feedback
# loop during the CLK=0 reset phase: if the latch NMOS pair's sources sat at
# GND while the outputs were held near VDD, every latch NMOS would conduct
# throughout reset, the loop gain would exceed unity with the inputs still
# floating, and the "reset" state would be an UNSTABLE equilibrium that any
# asymmetry can amplify toward either rail before the deliberate decision
# edge. DR-001 cites sky130-sar-adc's DR-004 Amendment A as same-PDK
# evidence that this is a real, measurable defect found the hard way there
# (a reset-integrity negative control failing at 3 of 9 PVT corners, outputs
# observed separating during the reset window with no input applied), and
# states the correct reset scheme up front specifically so this repo checks
# for it BEFORE, not after, being bitten. This sub-command is that check.
#
# METHOD -- a negative control, deliberately stacked against the design,
# paired with a positive control that proves the check can actually fail.
#
# Both variants are run at every corner:
#
#   AS-DRAWN     design/comparator.sch exactly as committed: the latch
#                steering pair's sources are the floated internal node
#                TAIL2 (cut off in reset because M_TAIL2 is off and TAIL2
#                floats to ~the steering gates' Vth).
#   GND-TIED     the SINGLE-EDIT counterfactual (the same shape DR-001
#                Decision 3 argued against for its own latch's
#                source-precharge scheme): M_STN_P and M_STN_N have their
#                source terminals moved from TAIL2 to GND, and nothing
#                else changes. This is the positive control. Without it the
#                negative control is vacuous -- a check that cannot be
#                shown to fail on the defect it screens for is not
#                evidence that the defect is absent.
#
# In both cases CLK is held at 0 for the whole window (reset asserted, never
# released) and NO differential input is applied (VINP = VINN = VCM). The
# transient starts from a maximally WRONG initial condition: the outputs
# pinned at OPPOSITE RAILS and the internal nodes at GND -- exactly the
# fully-separated state a broken reset would drift into. A sound reset
# rejects that asymmetry; an unstable one holds or amplifies it.
#
# Four things are asserted over the settled part of the window:
#
#   1. COLLAPSE     |v(OUTP) - v(OUTN)| decays to ~0. The deliberate initial
#                   asymmetry is rejected, not amplified.
#   2. PRECHARGE    OUTP/OUTN reach VDD.
#   3. LATCH OFF    max |Vgs| over the two cross-coupled latch PMOS is ~0.
#                   THIS IS THE PRIMARY CRITERION and it is essentially
#                   threshold-free: the DR-004 latch stage keeps DR-001
#                   Decision 3's mechanism on the (now PMOS) cross-coupled
#                   pair -- precharging the outputs to VDD puts every latch
#                   PMOS's gate AND source at VDD, so Vgs = 0 exactly and
#                   the loop gain is zero. |Vgs(M_LATP_P)| = VDD - v(OUTN)
#                   and |Vgs(M_LATP_N)| = VDD - v(OUTP) are that mechanism,
#                   measured. (In this topology the pair's gates ARE the
#                   precharged outputs, so criteria 2 and 3 read the same
#                   node pair through equal tolerances -- they coincide
#                   numerically by construction; the GND-tied control
#                   separates them from criterion 4's axis instead.) The
#                   GND-tied control puts both at ~VDD - 0.2 V, a ~1.6 V
#                   separation -- there is no tuning latitude here either.
#   4. NOT CONDUCTING  |I(VDD)| stays below RESET_IDD_TOL_A.
#
# On criterion 4's threshold, stated plainly because it is the one number
# here that is a judgement call. It is NOT "the supply current is zero":
# since DR-004 (issue #34) the design carries a CONTINUOUSLY-BIASED
# PREAMPLIFIER, whose static current (~23-38 uA across the five
# reset-matrix corners, measured) flows at all times including reset --
# that is the class-defining supply cost of the preamp topology, not a
# defect. On top of it there is an unavoidable small off-state path (VDD ->
# output reset PMOS -> steering pair, whose gates sit at the preamp's
# static output common mode -> TAIL2 -> subthreshold latch tail -> GND),
# self-limiting because TAIL2 floats up until the steering pair's Vgs
# falls to ~Vth (measured TAIL2 ~0.6-0.9 V at settle). RESET_IDD_TOL_A is
# therefore set well above that inherent floor and far below a genuinely
# conducting latch: the GND-tied positive control, whose steering branches
# are pinned on at Vgs ~ the preamp common mode through 8 um devices,
# draws ~1.0-1.2 mA across the same five corners (measured) -- a >5x
# separation on BOTH sides, and each record reports both numbers side by
# side so the separation is visible rather than asserted.

RESET_WINDOW_NS = 20.0
RESET_SETTLE_FRACTION = 0.5    # assert over the final half of the window
RESET_DIFF_TOL_V = 1e-3        # |OUTP-OUTN| must decay below this
RESET_PRECHARGE_TOL_V = 10e-3  # output nodes must reach VDD minus this
RESET_VGS_TOL_V = 10e-3        # cross-coupled latch PMOS |Vgs| at/below this
RESET_IDD_TOL_A = 2e-4         # |I(VDD)| bound -- see the note above

RESET_VARIANTS = ("as-drawn", "gnd-tied")


def _reset_device_block(variant: str) -> str:
    """The DUT device lines for one reset-check variant.

    `as-drawn` is the committed fragment verbatim. `gnd-tied` re-emits the
    latch steering pair with their SOURCE terminal moved from the floated
    internal node TAIL2 to GND, changing nothing else -- the minimal
    counterfactual for the DR-004 latch stage's reset scheme (the same
    counterfactual shape DR-001 Decision 3 established against its own
    latch's source precharge: pin the cross-coupled pair's current-source
    node where the reset scheme floats it away from, and the loop must
    conduct).
    """
    if variant == "as-drawn":
        return _dut_lines()
    if variant != "gnd-tied":
        raise ValueError(f"unknown reset variant {variant!r}")
    rewired = {
        "XM_STN_P": ["OUTP", "OUTP1", "GND", "GND"],
        "XM_STN_N": ["OUTN", "OUTN1", "GND", "GND"],
    }
    return "\n".join(
        _dut_device_line(name, nodes=rewired.get(name))
        for name in _dut_devices()
    )


def _reset_deck(info: pdk.PdkInfo, corner: str, temp_c: float, variant: str, log_name: str) -> str:
    lines = [
        f"* comparator-decision reset-integrity check -- variant={variant} "
        f"corner={corner} temp={temp_c}C supply={VDD}V (issue #24)",
        f".lib {info.ngspice_lib} {corner}",
        f".temp {temp_c}",
        f".param vdd_val = {VDD}",
        "",
        "Vdd VDD 0 dc {vdd_val}",
        "* CLK held LOW for the entire window: reset asserted, never released.",
        "Vclk CLK 0 dc 0",
        f"Vinp VINP 0 dc {VCM}",
        f"Vinn VINN 0 dc {VCM}",
        "",
        "* Deliberately WRONG starting state: outputs pinned at opposite rails,",
        "* latch internal nodes at GND; the preamp's static nodes start near",
        "* their own DC bias (uic defaults unspecified nodes to 0, and the",
        "* preamp's R*C settle from 0 would eat most of the window).",
        ".ic v(OUTP)=0 v(OUTN)={vdd_val} v(TAIL2)=0 v(CLKT)=0"
        " v(TAILP)=0.2 v(OUTP1)=1.2 v(OUTN1)=1.2",
        "",
        _reset_device_block(variant),
        "",
        ".control",
        f"tran 0.005n {RESET_WINDOW_NS}n uic",
        f"wrdata {log_name}.csv v(OUTP) v(OUTN) v(TAIL2) i(Vdd)",
        ".endc",
        ".end",
    ]
    return "\n".join(lines) + "\n"


@dataclass
class ResetPoint:
    corner: str
    temp_c: float
    variant: str
    worst_diff_v: float        # worst |OUTP-OUTN| over the settle window
    min_precharge_v: float     # worst (lowest) of the output nodes
    max_latch_vgs_v: float     # worst Vgs over the two cross-coupled latch NMOS
    max_abs_idd_a: float       # worst |I(VDD)| over the settle window
    log_text: str

    @property
    def collapse_ok(self) -> bool:
        return self.worst_diff_v <= RESET_DIFF_TOL_V

    @property
    def precharge_ok(self) -> bool:
        return self.min_precharge_v >= VDD - RESET_PRECHARGE_TOL_V

    @property
    def latch_off_ok(self) -> bool:
        return self.max_latch_vgs_v <= RESET_VGS_TOL_V

    @property
    def nonconducting_ok(self) -> bool:
        return self.max_abs_idd_a <= RESET_IDD_TOL_A

    @property
    def holds_reset(self) -> bool:
        """True iff this run holds a sound reset on all four criteria."""
        return (self.collapse_ok and self.precharge_ok
                and self.latch_off_ok and self.nonconducting_ok)

    @property
    def ok(self) -> bool:
        """Whether this run did what its VARIANT is supposed to do.

        `as-drawn` must hold reset. `gnd-tied` is the positive control: it
        must NOT hold reset, otherwise the check is not sensitive to the
        defect it screens for and the negative control proves nothing.
        """
        return self.holds_reset if self.variant == "as-drawn" else not self.holds_reset

    @property
    def verdict(self) -> str:
        failed = [
            name for name, good in (
                ("RESET-NOT-COLLAPSED", self.collapse_ok),
                ("RESET-NOT-PRECHARGED", self.precharge_ok),
                ("LATCH-NOT-OFF", self.latch_off_ok),
                ("RESET-CONDUCTING", self.nonconducting_ok),
            ) if not good
        ]
        state = "HOLDS-RESET" if not failed else "BREAKS-RESET (" + ", ".join(failed) + ")"
        return f"{state} -> {'as expected' if self.ok else 'UNEXPECTED'}"


DEFAULT_RESET_CORNERS = [("tt", 27.0), ("ss", -40.0), ("ff", 125.0), ("ss", 125.0), ("ff", -40.0)]


def run_reset_check(
    points: list[tuple[str, float]] | None = None, quiet: bool = False,
) -> list[ResetPoint]:
    info = pdk.resolve_or_raise()
    points = points or DEFAULT_RESET_CORNERS
    results: list[ResetPoint] = []
    settle_start_s = RESET_WINDOW_NS * RESET_SETTLE_FRACTION * 1e-9
    with tempfile.TemporaryDirectory(prefix="comparator-decision-reset-") as scratch:
        scratch_dir = Path(scratch)
        for variant in RESET_VARIANTS:
            for corner, temp_c in points:
                safe_t = str(temp_c).replace("-", "neg").replace(".", "p")
                log_name = f"reset_{variant.replace('-', '_')}_{corner}_{safe_t}c"
                deck = _reset_deck(info, corner, temp_c, variant, log_name)
                log_text = _run(deck, scratch_dir, log_name)
                t, outp, outn, tail2, idd = toolchain.read_wrdata_csv(
                    scratch_dir / f"{log_name}.csv", 4)
                idx = [i for i, tt in enumerate(t) if tt >= settle_start_s]
                # |Vgs| of the cross-coupled latch PMOS. Both variants'
                # sources sit at VDD (the rail), gates at the opposite
                # output: |Vgs| = VDD - v(gate), worst device = the lower
                # output node. In the as-drawn scheme the outputs are
                # precharged to VDD so this is ~0; the gnd-tied control's
                # steering pair drags an output down so it grows to ~VDD.
                def latch_vgs(i: int) -> float:
                    return VDD - min(outp[i], outn[i])
                point = ResetPoint(
                    corner=corner, temp_c=temp_c, variant=variant,
                    worst_diff_v=max(abs(outp[i] - outn[i]) for i in idx),
                    min_precharge_v=min(min(outp[i], outn[i]) for i in idx),
                    max_latch_vgs_v=max(latch_vgs(i) for i in idx),
                    max_abs_idd_a=max(abs(idd[i]) for i in idx),
                    log_text=log_text,
                )
                results.append(point)
                if not quiet:
                    print(
                        f"  [{variant}] {corner}/{temp_c}C: "
                        f"|OUTP-OUTN|<={point.worst_diff_v * 1e3:.6g}mV "
                        f"min(OUT)={point.min_precharge_v:.6g}V "
                        f"max Vgs(latch)={point.max_latch_vgs_v * 1e3:.6g}mV "
                        f"|I(VDD)|<={point.max_abs_idd_a:.4g}A -> {point.verdict}"
                    )
    return results


def write_reset_evidence(
    points: list[ResetPoint], note: str = "", supersedes: str = "",
) -> Path:
    info = pdk.resolve()
    record_id = evidence.new_record_id()
    netlist_sha = evidence.sha256_file(_dut_fragment())
    record_path = evidence.write_netlist_snapshot(EXPERIMENT_DIR, record_id, _dut_fragment())
    corners_dir = EXPERIMENT_DIR / "corners" / record_id
    corners_dir.mkdir(parents=True, exist_ok=True)
    for p in points:
        safe = f"{p.variant.replace('-', '_')}_{p.corner}_{str(p.temp_c).replace('-', 'neg').replace('.', 'p')}c"
        (corners_dir / f"reset_{safe}.log").write_text(p.log_text)

    as_drawn = [p for p in points if p.variant == "as-drawn"]
    control = [p for p in points if p.variant == "gnd-tied"]
    unexpected = [p for p in points if not p.ok]
    corner_set = sorted({(p.corner, p.temp_c) for p in points}, key=lambda c: (c[0], c[1]))

    lines: list[str] = []
    a = lines.append
    a(f"# Record {record_id}")
    a("")
    a(f"- **Record ID**: {record_id}")
    a(CLAIM_TEXT)
    a(netlist_provenance())
    a(
        "- **Corner matrix run**: "
        + ", ".join(f"{c}/{t}C" for c, t in corner_set)
        + f" at supply_v=[{VDD}], each run for BOTH variants "
        f"({len(points)} runs total -- **subset-corner justification**: a "
        "reset-integrity check is a functional-correctness screen whose "
        "failure mode is corner-dependent (the same-PDK prior art DR-001 "
        "Decision 3 cites failed at 3 of 9 corners), so the point set "
        "deliberately spans both temperature extremes against both the slow "
        "and the fast process skew, plus the nominal point; it is not the "
        "full ratified PVT matrix, which stays blocked on target-spec "
        "ratification)"
    )
    a(
        f"- **Stimulus**: CLK held at 0V for the whole {RESET_WINDOW_NS}ns window "
        f"(reset asserted, never released); NO differential input "
        f"(VINP=VINN={VCM}V); `uic` transient from a deliberately WRONG initial "
        f"condition -- v(OUTP)=0, v(OUTN)={VDD}V (outputs at OPPOSITE RAILS), "
        f"v(TAIL2)=v(CLKT)=0, with the preamp's static nodes (TAILP, OUTP1, "
        f"OUTN1) started near their own DC bias"
    )
    a(
        "- **Variants**: `as-drawn` = `design/comparator.sch` as committed "
        "(the latch steering pair's sources are the floated internal node "
        "TAIL2, cut off in reset because M_TAIL2 is off and TAIL2 floats to "
        "~the steering gates' Vth). "
        "`gnd-tied` = POSITIVE CONTROL, the single-edit counterfactual -- "
        "M_STN_P/M_STN_N sources moved from TAIL2 to GND, nothing else "
        "changed (the same counterfactual shape DR-001 Decision 3 established "
        "for its own latch's source-precharge scheme). `as-drawn` is expected "
        "to hold reset; `gnd-tied` is expected to BREAK it. Both expectations "
        "are graded, because a negative control that cannot be shown to fail "
        "on the defect it screens for is not evidence that the defect is "
        "absent."
    )
    a(
        f"- **Reset-held criteria** (all asserted over the final "
        f"{int(RESET_SETTLE_FRACTION * 100)}% of the window): "
        f"(1) collapse -- |v(OUTP)-v(OUTN)| <= {RESET_DIFF_TOL_V * 1e3:g}mV; "
        f"(2) precharge -- min(OUTP,OUTN) >= VDD-{RESET_PRECHARGE_TOL_V * 1e3:g}mV; "
        f"(3) latch off -- max |Vgs| over M_LATP_P/M_LATP_N <= {RESET_VGS_TOL_V * 1e3:g}mV "
        f"(= VDD - min(OUTP,OUTN): the pair's gates ARE the outputs); "
        f"(4) not conducting -- |I(VDD)| <= {RESET_IDD_TOL_A:g}A (the floor "
        f"under this bound is the DR-004 preamp's OWN static current, "
        f"~23-38uA across this matrix -- not leakage)"
    )
    if note:
        a(f"- **Note**: {note}")
    a(
        f"- **Overall**: {'PASS' if not unexpected else 'FAIL'} "
        f"({sum(1 for p in as_drawn if p.holds_reset)}/{len(as_drawn)} as-drawn "
        f"corners hold reset; "
        f"{sum(1 for p in control if not p.holds_reset)}/{len(control)} "
        f"positive-control corners correctly break it)"
    )
    a("")
    a("## As-drawn: reset-integrity negative control")
    a("")
    hdr = ("| Corner | Temp | worst \\|OUTP-OUTN\\| (mV) | worst min(OUTP,OUTN) (V) "
           "| worst \\|Vgs\\| (latch PMOS) (mV) | worst \\|I(VDD)\\| (A) | Result |")
    a(hdr)
    a("|---|---|---|---|---|---|---|")
    for p in as_drawn:
        a(
            f"| {p.corner} | {p.temp_c}C | {p.worst_diff_v * 1e3:.6g} | "
            f"{p.min_precharge_v:.6f} | {p.max_latch_vgs_v * 1e3:.6g} | "
            f"{p.max_abs_idd_a:.4g} | {p.verdict} |"
        )
    a("")
    a("## GND-tied: positive control (expected to BREAK reset)")
    a("")
    a(hdr)
    a("|---|---|---|---|---|---|---|")
    for p in control:
        a(
            f"| {p.corner} | {p.temp_c}C | {p.worst_diff_v * 1e3:.6g} | "
            f"{p.min_precharge_v:.6f} | {p.max_latch_vgs_v * 1e3:.6g} | "
            f"{p.max_abs_idd_a:.4g} | {p.verdict} |"
        )
    a("")
    a("## Reading this record")
    a("")
    a(
        "DR-001 Decision 3's mechanism -- precharging the cross-coupled "
        "pair's gate AND source nodes to the same rail forces `Vgs = 0`, so "
        "the loop gain is exactly zero and reset is a stable equilibrium -- "
        "is carried by the DR-004 latch stage on its (now PMOS) pair: the "
        "outputs ARE the pair's gates and are precharged with their sources "
        "to VDD. The `|Vgs| (latch PMOS)` column is that mechanism measured "
        "directly, and it is the load-bearing criterion here: it is "
        "essentially threshold-free, because the two variants sit most of a "
        "supply apart on it. In this topology it numerically coincides with "
        "the precharge criterion (same node pair, same tolerance) -- stated "
        "rather than hidden; the criteria that carry independent information "
        "are the collapse and current columns."
    )
    a("")
    a(
        "The `|I(VDD)|` column needs reading with its floor in mind. It is "
        "not zero even when reset is perfectly held, and cannot be: since "
        "DR-004 the design carries a continuously-biased preamplifier whose "
        "static current (~23-38 uA across this matrix) flows during reset "
        "too -- the class-defining supply cost of the preamp topology -- on "
        "top of a small self-limiting off-state path (VDD -> reset PMOS -> "
        "steering pair -> floated TAIL2 -> subthreshold latch tail -> GND; "
        "TAIL2 settles ~0.6-0.9 V, at the steering pair's Vth). That floor "
        "is a property of the topology class, not a defect, and it is what "
        "the as-drawn column reports. The positive control's ~1.0-1.2 mA is "
        "the contrast that gives the criterion its meaning."
    )
    a("")
    a(
        "Note also what the collapse criterion alone would NOT have caught: "
        "a GND-tied latch can sit at a symmetric point that looks settled on "
        "the output-difference column while both branches conduct steadily, "
        "which is precisely why criteria (3) and (4) exist alongside it."
    )
    a("")
    return _finalize_record(
        lines, record_path, _resolve_pdk_line(info), toolchain._ngspice_version() or "unknown",
        netlist_sha, "reset", supersedes=supersedes,
    )


# ---------------------------------------------------------------------------
# kickback: input-node disturbance from the comparator's own regeneration,
# through an explicit source impedance (issue #26)
# ---------------------------------------------------------------------------
#
# WHY THIS EXISTS. spec/porting-plan.md's "Next steps" item 4 calls for an
# ORIGINAL kickback experiment -- unlike regen/offset/noise (ported
# methodology, issue #9) there is no same-PDK standalone prior art to port
# for kickback specifically. The top-level README's target-spec table
# already carries a Kickback row (<= 5 mV disturbance into a 1 kOhm source
# impedance at the input nodes, single decision edge; stretch <= 2 mV) with
# an explicit note that no testbench exists yet -- this sub-command is that
# testbench's first cut.
#
# WHAT "KICKBACK" MEANS HERE. The voltage disturbance the comparator's own
# regeneration injects back onto its input nodes at the reset->evaluate
# transition, through the input-pair devices' gate-drain/gate-source
# parasitic capacitance and the common-mode step at TAIL. It is only visible
# to a real driving stage: an IDEAL (zero-impedance) voltage source absorbs
# any injected charge with no voltage deviation, which is exactly why the
# target-spec row's own bound is stated "into a 1 kOhm source impedance" --
# the source impedance is what turns injected charge into a voltage
# disturbance at all.
#
# METHOD -- two variants of the same reset->evaluate transient, differing
# only in how VINP/VINN are driven:
#
#   LOADED  VINP/VINN are biased through an explicit KICKBACK_RS_OHM series
#           resistor fed by an ideal DC source, per the target-spec row's own
#           stated methodology assumption. This is the measurement.
#   IDEAL   VINP/VINN are driven directly by the ideal DC source (zero source
#           impedance), everything else unchanged. This is the CONTROL: an
#           ideal voltage source cannot show a voltage deviation from itself
#           by construction, so this variant's peak disturbance must
#           collapse to (numerically) zero. Without it, a `loaded` reading of
#           (say) 0.000 mV would be indistinguishable between "this design
#           has no kickback" and "this deck is not actually measuring
#           anything" -- the same "a negative control that cannot be shown
#           to fail on the defect it screens for is not evidence the defect
#           is absent" bar the `reset` sub-command's own record already
#           states (see KickbackPoint.ok below for exactly what each variant
#           is graded against).
#
# In both variants a single static KICKBACK_VINDIFF_MV differential step is
# applied ahead of the drive (through the resistor, for `loaded`) -- sized to
# guarantee a clean, unambiguous decision, matching the `regen` sweep's
# largest tested overdrive and the target-spec table's own "Decision time vs.
# overdrive" 50 mV reference point -- then the same single
# reset(CLK=0, RESET_NS)->evaluate(CLK=VDD) edge the `regen`/`reset` decks
# already use is run. VINP and VINN are measured across the whole window
# relative to their own pre-edge (t <= RESET_NS) settled value; the peak
# absolute deviation from that quiescent point is the disturbance the
# target-spec row grades.

KICKBACK_RS_OHM = 1000.0
# The DR-002-ratified Kickback row's bounds -- recorded here so the record
# states its own comparison against the ratified row (values cite DR-002
# Decision 4: target <= 5 mV, stretch <= 2 mV, into 1 kOhm, single edge).
KICKBACK_TARGET_MV = 5.0
KICKBACK_STRETCH_MV = 2.0  # 1 kOhm source impedance -- the target-spec
# Kickback row's own stated methodology assumption (see module note above).
KICKBACK_VINDIFF_MV = 50.0  # matches the `regen` sweep's largest tested
# overdrive and the target-spec table's own "Decision time vs. overdrive"
# 50 mV reference point -- sized to guarantee a clean decision edge, not
# tuned to any particular disturbance figure.
KICKBACK_VARIANTS = ("loaded", "ideal")
KICKBACK_SENSITIVITY_MIN_V = 1e-3  # `loaded`'s peak disturbance must exceed
# this to prove the deck is actually sensitive to the effect it screens for.
# This design measures peak disturbances two orders of magnitude above this
# floor (tens of mV) -- the bar is set far below the expected signal, not
# tuned to it, per the same "must be able to fail" contract `reset`'s
# positive control already states.
KICKBACK_IDEAL_TOL_V = 1e-9  # `ideal`'s peak disturbance must be at/below
# this -- an ideal voltage source cannot show a voltage deviation from
# itself, so anything above numerical noise here means the deck is not
# actually isolating the source-impedance-dependent effect.


def _kickback_deck(
    info: pdk.PdkInfo, corner: str, temp_c: float, variant: str, log_name: str,
) -> str:
    """Single reset->evaluate transient deck for one (corner, temp,
    variant) kickback point. `variant` selects how VINP/VINN are driven --
    see the module note above for `loaded` vs. `ideal`."""
    if variant not in KICKBACK_VARIANTS:
        raise ValueError(f"unknown kickback variant {variant!r}")
    vindiff_v = KICKBACK_VINDIFF_MV / 1000.0
    period_ns = RESET_NS + RESET_TR_NS + EVALUATE_NS + 10.0
    rs_shown = KICKBACK_RS_OHM if variant == "loaded" else 0.0
    lines = [
        f"* comparator-decision kickback disturbance -- variant={variant} "
        f"Rs={rs_shown:g}ohm vindiff={KICKBACK_VINDIFF_MV}mV corner={corner} "
        f"temp={temp_c}C (issue #26)",
        f".lib {info.ngspice_lib} {corner}",
        f".temp {temp_c}",
        f".param vdd_val = {VDD}",
        "",
        "Vdd VDD 0 dc {vdd_val}",
        f"Vclk CLK 0 PULSE(0 {{vdd_val}} {RESET_NS}n {RESET_TR_NS}n {RESET_TR_NS}n "
        f"{EVALUATE_NS}n {period_ns}n)",
    ]
    if variant == "loaded":
        lines += [
            f"Vsrcp VSRC_P 0 dc {VCM + vindiff_v / 2}",
            f"Vsrcn VSRC_N 0 dc {VCM - vindiff_v / 2}",
            f"Rsp VSRC_P VINP {KICKBACK_RS_OHM}",
            f"Rsn VSRC_N VINN {KICKBACK_RS_OHM}",
        ]
    else:
        lines += [
            f"Vinp VINP 0 dc {VCM + vindiff_v / 2}",
            f"Vinn VINN 0 dc {VCM - vindiff_v / 2}",
        ]
    lines += [
        "",
        _dut_lines(),
        "",
        ".control",
        f"tran 0.005n {RESET_NS + RESET_TR_NS + EVALUATE_NS}n",
        f"wrdata {log_name}.csv v(CLK) v(VINP) v(VINN) v(OUTP) v(OUTN)",
        ".endc",
        ".end",
    ]
    return "\n".join(lines) + "\n"


@dataclass
class KickbackPoint:
    corner: str
    temp_c: float
    variant: str
    quiescent_vinp_v: float
    quiescent_vinn_v: float
    peak_dev_vinp_v: float
    peak_dev_vinn_v: float
    log_text: str

    @property
    def peak_dev_v(self) -> float:
        """Worst of the two input nodes -- the figure the target-spec row's
        single bound would be graded against, once ratified."""
        return max(self.peak_dev_vinp_v, self.peak_dev_vinn_v)

    @property
    def ok(self) -> bool:
        """Whether this run did what its VARIANT is supposed to do (same
        shape as ResetPoint.ok). `loaded` must show a disturbance clearly
        above the numerical floor (sensitivity); `ideal` must collapse to
        (numerically) zero."""
        if self.variant == "loaded":
            return self.peak_dev_v >= KICKBACK_SENSITIVITY_MIN_V
        return self.peak_dev_v <= KICKBACK_IDEAL_TOL_V

    @property
    def verdict(self) -> str:
        state = f"peak={self.peak_dev_v * 1e3:.4f}mV"
        return f"{state} -> {'as expected' if self.ok else 'UNEXPECTED'}"


def run_kickback(
    corner: str = "tt", temp_c: float = 27.0, quiet: bool = False, jobs: int = 1,
) -> list[KickbackPoint]:
    info = pdk.resolve_or_raise()
    results: list[KickbackPoint] = []
    with tempfile.TemporaryDirectory(prefix="comparator-decision-kickback-") as scratch:
        scratch_dir = Path(scratch)
        kb_jobs = [
            (f"kickback_{variant}", _kickback_deck(info, corner, temp_c, variant, f"kickback_{variant}"))
            for variant in KICKBACK_VARIANTS
        ]
        kb_logs = _run_many(kb_jobs, scratch_dir, jobs)
        for variant in KICKBACK_VARIANTS:
            log_name = f"kickback_{variant}"
            log_text = kb_logs[log_name]
            t, clk, vinp, vinn, outp, outn = toolchain.read_wrdata_csv(
                scratch_dir / f"{log_name}.csv", 5)
            # Quiescent = each node's own settled value at/before RESET_NS,
            # i.e. before the reset->evaluate CLK ramp begins.
            idx_pre = max(i for i, tt in enumerate(t) if tt <= RESET_NS * 1e-9)
            q_p, q_n = vinp[idx_pre], vinn[idx_pre]
            peak_p = max(abs(v - q_p) for v in vinp)
            peak_n = max(abs(v - q_n) for v in vinn)
            point = KickbackPoint(
                corner=corner, temp_c=temp_c, variant=variant,
                quiescent_vinp_v=q_p, quiescent_vinn_v=q_n,
                peak_dev_vinp_v=peak_p, peak_dev_vinn_v=peak_n,
                log_text=log_text,
            )
            results.append(point)
            if not quiet:
                print(
                    f"  [{variant}] {corner}/{temp_c}C: "
                    f"peak|VINP-q|={peak_p * 1e3:.4f}mV "
                    f"peak|VINN-q|={peak_n * 1e3:.4f}mV -> {point.verdict}"
                )
    return results


def write_kickback_evidence(
    points: list[KickbackPoint], note: str = "", supersedes: str = "",
) -> Path:
    info = pdk.resolve()
    record_id = evidence.new_record_id()
    netlist_sha = evidence.sha256_file(_dut_fragment())
    record_path = evidence.write_netlist_snapshot(EXPERIMENT_DIR, record_id, _dut_fragment())
    corners_dir = EXPERIMENT_DIR / "corners" / record_id
    corners_dir.mkdir(parents=True, exist_ok=True)
    for p in points:
        (corners_dir / f"kickback_{p.variant}.log").write_text(p.log_text)

    loaded = next(p for p in points if p.variant == "loaded")
    ideal = next(p for p in points if p.variant == "ideal")
    unexpected = [p for p in points if not p.ok]

    lines: list[str] = []
    a = lines.append
    a(f"# Record {record_id}")
    a("")
    a(f"- **Record ID**: {record_id}")
    a(CLAIM_TEXT)
    a(netlist_provenance())
    a(
        f"- **Corner matrix run**: process=['{loaded.corner}'], "
        f"temperature_c=[{loaded.temp_c}], supply_v=[{VDD}] (1 PVT point, "
        "both variants -- **subset-corner justification**: "
        + kickback_subset_justification(loaded.corner, loaded.temp_c)
        + ")"
    )
    a(
        f"- **Stimulus**: VINP/VINN biased at VCM={VCM}V +/- "
        f"{KICKBACK_VINDIFF_MV / 2:g}mV (a static {KICKBACK_VINDIFF_MV:g}mV "
        "differential step, sized to guarantee a clean decision -- matching "
        "the `regen` sweep's largest tested overdrive and the target-spec "
        "table's own \"Decision time vs. overdrive\" 50mV reference point); "
        f"single reset({RESET_NS}ns, CLK=0)->evaluate(CLK={VDD}V) edge, the "
        "same stimulus shape `regen`/`reset` already use"
    )
    a(
        "- **Variants**: `loaded` = VINP/VINN fed through an explicit "
        f"{KICKBACK_RS_OHM:g}ohm series resistor from an ideal DC source -- "
        "the target-spec Kickback row's own stated methodology assumption, "
        "and what lets an injected disturbance show up as a voltage instead "
        "of being absorbed. `ideal` = CONTROL, VINP/VINN driven directly by "
        "the ideal DC source (zero source impedance) -- must collapse to "
        "(numerically) zero by construction; anything else would mean the "
        "deck is not actually isolating the source-impedance-dependent "
        "effect the `loaded` variant measures."
    )
    a(
        f"- **Sensitivity criteria**: `loaded` peak disturbance must be >= "
        f"{KICKBACK_SENSITIVITY_MIN_V * 1e3:g}mV (a floor far below the "
        "measured signal, not a tuned threshold); `ideal` peak disturbance "
        f"must be <= {KICKBACK_IDEAL_TOL_V * 1e3:g}mV"
    )
    if note:
        a(f"- **Note**: {note}")
    a(
        f"- **Overall**: {'PASS' if not unexpected else 'FAIL'} "
        f"(loaded peak={loaded.peak_dev_v * 1e3:.4f}mV, "
        f"ideal peak={ideal.peak_dev_v * 1e3:.4f}mV)"
    )
    a("")
    a("## Peak input-node disturbance")
    a("")
    a(
        "| Variant | peak \\|VINP-quiescent\\| (mV) | peak \\|VINN-quiescent\\| "
        "(mV) | Result |"
    )
    a("|---|---|---|---|")
    for p in points:
        a(
            f"| {p.variant} | {p.peak_dev_vinp_v * 1e3:.4f} | "
            f"{p.peak_dev_vinn_v * 1e3:.4f} | {p.verdict} |"
        )
    a("")
    a("## Reading this record")
    a("")
    a(
        "Measured against the DR-004 static-preamp design (issue #34: a "
        "continuously-biased preamplifier ahead of the StrongARM latch, "
        "with DR-003's soft-clock shaper still on the clock port driving "
        "the latch tail and reset PMOS, tau ~ 250 ps). The raw mechanism "
        "the pre-DR-004 designs suffered -- a DYNAMIC input pair's own "
        "channel formation and internal-node collapse coupling back onto "
        "the VINP/VINN gate nodes through the input devices' "
        "gate parasitics -- is removed at the root in this class: the "
        "preamp's channels are always formed (Vgs constant, zero "
        "formation charge at the edge), and whatever the latch kicks "
        "back arrives at the preamp OUTPUT nodes, where the absorber "
        "caps (M_C1P/M_C1N) sink it before the pins. The residual "
        "`loaded` figure below is what survives that isolation, measured "
        "end to end through the target-spec row's own 1 kOhm source "
        "impedance. The `ideal` control still collapses to (numerically) "
        "zero by construction, so the deck continues to isolate a genuine "
        "source-impedance-dependent effect."
    )
    a("")
    a(
        f"- **Ratified bound comparison (DR-002)**: the Kickback row is "
        f"RATIFIED at <= {KICKBACK_TARGET_MV:g} mV disturbance into "
        f"1 kOhm source impedance (target, single decision edge) / "
        f"<= {KICKBACK_STRETCH_MV:g} mV (stretch). This record's "
        f"`loaded` peak figure of {loaded.peak_dev_v * 1000:.4f} mV "
        f"{'MEETS' if loaded.peak_dev_v * 1000 <= KICKBACK_TARGET_MV else 'DOES NOT yet meet'} "
        f"the target bound"
        + (
            f" and {'MEETS' if loaded.peak_dev_v * 1000 <= KICKBACK_STRETCH_MV else 'DOES NOT yet meet'} "
            f"the stretch bound."
            if loaded.peak_dev_v * 1000 <= KICKBACK_TARGET_MV else
            " -- the DR-002 non-compliance finding stands; this figure is "
            "honest partial-improvement information for the decision "
            "records to weigh, never silently superseding DR-002's "
            "disposition."
        )
        + f" The comparison holds for the single "
        f"{loaded.corner}/{loaded.temp_c:g}C PVT point this record runs (see "
        "Corner matrix run above) and for this record's DUT provenance alone "
        "-- see the corner-coverage table in "
        "`sim/comparator-decision/README.md` for which of the seven graded "
        "corners are measured at which provenance."
    )
    a("")
    lines.extend(post_layout_delta_lines(
        "kickback", loaded.corner, loaded.temp_c, loaded.peak_dev_v,
        unit_scale=1000.0))
    a("")
    return _finalize_record(
        lines, record_path, _resolve_pdk_line(info), toolchain._ngspice_version() or "unknown",
        netlist_sha, "kickback", supersedes=supersedes,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="comparator-decision standalone testbench driver (issue #9)")
    ap.add_argument(
        "mode", nargs="?", choices=["regen", "offset", "noise", "noise-tran", "reset", "kickback"],
        help="which characterization to run",
    )
    ap.add_argument("--check-env", action="store_true", help="check toolchain + PDK, print summary, exit")
    ap.add_argument("--corner", default="tt")
    ap.add_argument("--temp", type=float, default=27.0)
    ap.add_argument("--seed", type=int, default=1, help="offset: MC base seed")
    ap.add_argument("--n", type=int, default=16, help="offset / noise-tran: MC sample count")
    ap.add_argument("--record", action="store_true", help="write an evidence record under records/")
    ap.add_argument("--note", default="")
    ap.add_argument(
        "--supersedes", default="",
        help="prior <record-id> this run REPLACES for the same claim. Omit for a record making a different claim.",
    )
    ap.add_argument(
        "--jobs", type=int, default=1,
        help="parallel ngspice workers for independent single-shot decks "
        "(offset draws/negctrl, regen sweep points, kickback variants, "
        "noise-tran MC). Issue #41's campaign support.",
    )
    ap.add_argument(
        "--dut", choices=DUT_PROVENANCES, default="schematic",
        help="which DUT netlist to simulate: `schematic` (the default -- "
        "design/comparator.sch via testbench/comparator_core.spice) or "
        "`extracted` (post-layout, parasitics-included -- "
        "layout/comparator.pex.spice, generated by layout/extract_pex.py "
        "from layout/comparator.gds). Issue #57 / T1 item 7. `regen`, "
        "`offset`, `noise` and `kickback` support both; `reset` and "
        "`noise-tran` are schematic-only and say so rather than silently "
        "falling back.",
    )
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    set_dut_provenance(args.dut)
    if args.dut == "extracted" and args.mode in ("reset", "noise-tran"):
        _require_schematic_dut(args.mode)

    if args.check_env:
        result = toolchain.check_env()
        print(toolchain.summary())
        for w in result.warnings:
            print(f"  ! warning: {w}")
        for m in result.messages:
            print(f"  - {m}")
        return result.status

    if not args.mode:
        ap.print_help()
        return 2

    if args.mode == "regen":
        points = run_regen_sweep(corner=args.corner, temp_c=args.temp, quiet=args.quiet, jobs=args.jobs)
        if args.record:
            path = write_regen_evidence(points, args.corner, args.temp, note=args.note, supersedes=args.supersedes)
            print(f"wrote {path}")
        unresolved = [p for p in points if p.regen_time_ns is None]
        return 0 if not unresolved else 1

    if args.mode == "offset":
        result = run_offset_mc(
            corner=args.corner, temp_c=args.temp, seed=args.seed, n=args.n,
            quiet=args.quiet, jobs=args.jobs,
        )
        if args.record:
            path = write_offset_evidence(result, note=args.note, supersedes=args.supersedes)
            print(f"wrote {path}")
        negctrl_stdev = statistics.pstdev(result.negctrl_offset_v) if len(result.negctrl_offset_v) > 1 else 0.0
        draws_stdev = statistics.pstdev(result.draws_offset_v) if len(result.draws_offset_v) > 1 else 0.0
        return 0 if (negctrl_stdev == 0.0 and draws_stdev > 0) else 1

    if args.mode == "noise":
        result = run_noise(corner=args.corner, temp_c=args.temp, quiet=args.quiet)
        if args.record:
            path = write_noise_evidence(result, note=args.note, supersedes=args.supersedes)
            print(f"wrote {path}")
        return 0

    if args.mode == "noise-tran":
        result = run_noise_tran(
            corner=args.corner, temp_c=args.temp, n_pickoff=args.n,
            quiet=args.quiet, jobs=args.jobs,
        )
        if args.record:
            path = write_noise_tran_evidence(result, note=args.note, supersedes=args.supersedes)
            print(f"wrote {path}")
        return 0 if result.sigma_pickoff_mv == result.sigma_pickoff_mv else 1

    if args.mode == "reset":
        points = run_reset_check(quiet=args.quiet)
        if args.record:
            path = write_reset_evidence(points, note=args.note, supersedes=args.supersedes)
            print(f"wrote {path}")
        return 0 if all(p.ok for p in points) else 1

    if args.mode == "kickback":
        points = run_kickback(corner=args.corner, temp_c=args.temp, quiet=args.quiet, jobs=args.jobs)
        if args.record:
            path = write_kickback_evidence(points, note=args.note, supersedes=args.supersedes)
            print(f"wrote {path}")
        return 0 if all(p.ok for p in points) else 1

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
