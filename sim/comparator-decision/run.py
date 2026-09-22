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
    "RATIFIED while Decision time vs. overdrive and Supply/power stay "
    "DRAFT/OPEN. What this record characterizes is **this repo's own "
    "comparator**: `design/comparator.sch`, the DR-004 static-preamplifier + "
    "StrongARM-latch topology (superseding DR-001's no-preamp scoping) with "
    "the DR-003 soft-clock shaper still on the clock port, at a sizing "
    "derived from this PDK's own mismatch models (see the schematic's "
    "sizing-rationale block, DR-001 Amendment 1, DR-003, and DR-004). Any "
    "statement about a ratified row's compliance made below cites the bound "
    "and the number side by side."
)
NETLIST_PROVENANCE = (
    "- **Netlist provenance**: schematic-derived "
    "(`design/comparator.sch` -> `./design/netlist.sh` -> "
    "`sim/comparator-decision/testbench/comparator_core.spice`)"
)


def _dut_lines() -> str:
    return DUT_FRAGMENT.read_text()


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
    vindiff_sweep_mv: list[float] | None = None, quiet: bool = False,
) -> list[RegenPoint]:
    info = pdk.resolve_or_raise()
    vindiff_sweep_mv = vindiff_sweep_mv or DEFAULT_VINDIFF_SWEEP_MV
    evaluate_start_ns = RESET_NS + RESET_TR_NS
    points: list[RegenPoint] = []
    with tempfile.TemporaryDirectory(prefix="comparator-decision-regen-") as scratch:
        scratch_dir = Path(scratch)
        for vindiff_mv in vindiff_sweep_mv:
            log_name = f"regen_{vindiff_mv}mV".replace("-", "neg").replace(".", "p")
            deck = _regen_deck(info, corner, temp_c, vindiff_mv, log_name)
            log_text = _run(deck, scratch_dir, log_name)
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
    netlist_sha = evidence.sha256_file(DUT_FRAGMENT)
    record_path = evidence.write_netlist_snapshot(EXPERIMENT_DIR, record_id, DUT_FRAGMENT)
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
    a(NETLIST_PROVENANCE)
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
    logs: dict[str, str] = field(default_factory=dict)


def run_offset_mc(
    corner: str = "tt", temp_c: float = 27.0, seed: int = 1, n: int = 16, quiet: bool = False,
) -> OffsetResult:
    info = pdk.resolve_or_raise()
    mismatch_corner = corners_mod.mismatch_corner_for(corner)
    logs: dict[str, str] = {}

    with tempfile.TemporaryDirectory(prefix="comparator-decision-offset-") as scratch:
        scratch_dir = Path(scratch)

        # 1. Gain calibration (ideal devices, plain corner).
        cal_points: list[tuple[float, float]] = []
        for vindiff_mv in VINDIFF_GAIN_CAL_MV:
            log_name = f"gaincal_{vindiff_mv}mV"
            deck = _pickoff_deck(info, corner, temp_c, vindiff_mv, log_name)
            log_text = _run(deck, scratch_dir, log_name)
            logs[log_name] = log_text
            diff = _pickoff_value(scratch_dir / f"{log_name}.csv")
            cal_points.append((vindiff_mv / 1000.0, diff))
            if not quiet:
                print(f"  gain-cal vindiff={vindiff_mv}mV -> pickoff_diff={diff:.6g}")
        sxy = sum(x * y for x, y in cal_points)
        sxx = sum(x * x for x, y in cal_points)
        gain = sxy / sxx if sxx else float("nan")
        if not quiet:
            print(f"  gain = {gain:.4f} V/V (from {len(cal_points)} calibration points)")

        # 2. Mismatch-enabled draws at Vindiff=0.
        draws_pickoff: list[float] = []
        for i in range(n):
            this_seed = seed + i
            log_name = f"draw_{i}"
            deck = _pickoff_deck(info, mismatch_corner, temp_c, 0.0, log_name, rndseed=this_seed)
            log_text = _run(deck, scratch_dir, log_name)
            logs[log_name] = log_text
            diff = _pickoff_value(scratch_dir / f"{log_name}.csv")
            draws_pickoff.append(diff)
            if not quiet:
                print(f"  draw {i} (seed={this_seed}, {mismatch_corner}): pickoff_diff={diff:.6g}")

        # 3. Negative control at the plain corner, same seed sequence.
        negctrl_pickoff: list[float] = []
        for i in range(n):
            this_seed = seed + i
            log_name = f"negctrl_{i}"
            deck = _pickoff_deck(info, corner, temp_c, 0.0, log_name, rndseed=this_seed)
            log_text = _run(deck, scratch_dir, log_name)
            logs[log_name] = log_text
            diff = _pickoff_value(scratch_dir / f"{log_name}.csv")
            negctrl_pickoff.append(diff)
            if not quiet:
                print(f"  negctrl {i} (seed={this_seed}, {corner}): pickoff_diff={diff:.6g}")

    draws_offset_v = [d / gain for d in draws_pickoff]
    negctrl_offset_v = [d / gain for d in negctrl_pickoff]

    return OffsetResult(
        gain_v_per_v=gain, gain_cal_points=cal_points,
        draws_pickoff=draws_pickoff, draws_offset_v=draws_offset_v,
        negctrl_pickoff=negctrl_pickoff, negctrl_offset_v=negctrl_offset_v,
        seed=seed, n=n, corner=corner, mismatch_corner=mismatch_corner, logs=logs,
    )


def write_offset_evidence(
    result: OffsetResult, note: str = "", supersedes: str = "",
) -> Path:
    info = pdk.resolve()
    record_id = evidence.new_record_id()
    netlist_sha = evidence.sha256_file(DUT_FRAGMENT)
    record_path = evidence.write_netlist_snapshot(EXPERIMENT_DIR, record_id, DUT_FRAGMENT)
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
    a(NETLIST_PROVENANCE)
    rel_se_pct = 100.0 / (2 * (result.n - 1)) ** 0.5 if result.n > 1 else float("inf")
    a(
        f"- **Statistical convention**: mismatch corner `{result.mismatch_corner}`, "
        f"N={result.n}, seed={result.seed} (draws use seed, seed+1, ..., "
        f"seed+N-1), PVT point process={result.corner} temp=27.0C supply={VDD}V. "
        f"Relative standard error on the estimated offset stdev, "
        f"SE(s)/s ~= 1/sqrt(2(N-1)): N={result.n} gives {rel_se_pct:.1f}% -- a "
        "distribution-shape-adequate sample for this plumbing proof, not a "
        "sample sized for a tight yield-fraction claim (that needs O(100s))."
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
        + " N=16 is sized for distribution shape, not a yield-fraction claim "
        "(see the Statistical convention above)."
    )
    a("")
    a("## Negative control (mismatch-disabled, same seed sequence)")
    a("")
    negctrl_mean = statistics.fmean(result.negctrl_offset_v) if result.negctrl_offset_v else float("nan")
    a("| N | mean (mV) | stdev (mV, must be 0) |")
    a("|---|---|---|")
    a(f"| {len(result.negctrl_offset_v)} | {negctrl_mean * 1000:.4f} | {negctrl_stdev * 1000:.6g} |")
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


def _noise_deck(info: pdk.PdkInfo, corner: str, temp_c: float) -> str:
    lines = [
        f"* comparator-decision input-referred noise ({VBIAS_NOTE}) "
        f"corner={corner} temp={temp_c}C supply={VDD}V (issue #9)",
        f".lib {info.ngspice_lib} {corner}",
        f".temp {temp_c}",
        f".param vdd_val = {VDD}",
        "",
        "Vdd VDD 0 dc {vdd_val}",
        f"Vinp VINP 0 dc {VCM} AC 1",
        f"Vinn VINN 0 dc {VCM}",
        "",
        # Built from the committed DUT fragment's OWN device lines (issue
        # #24): the DR-004 preamp stage verbatim -- tail, input pair, poly
        # loads, absorber caps -- with everything past the preamp outputs
        # omitted (the loop break; see the methodology note above). Sizing
        # therefore tracks design/comparator.sch automatically; it is not
        # transcribed here. The preamp contains no clocked device, so no
        # CLK/CLKT steady-bias source is needed (the pre-DR-004 sub-model's
        # Vclkfix/Vclkfixt lines existed to bias the omitted-from-latch
        # tail's soft-clock gate; that device is no longer in the sub-model).
        _dut_device_line("XM_PTAIL"),
        _dut_device_line("XM_PINN"),
        _dut_device_line("XM_PINP"),
        _dut_device_line("XR_LP"),
        _dut_device_line("XR_LN"),
        _dut_device_line("XM_C1P"),
        _dut_device_line("XM_C1N"),
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
        "- **Netlist provenance**: schematic-derived, reduced sub-model -- the "
        "DR-004 preamplifier stage's device lines (tail, input pair, poly "
        "loads, OUT1 absorber caps) are taken "
        "verbatim from `sim/comparator-decision/testbench/comparator_core.spice` "
        "(itself generated from `design/comparator.sch` by `./design/netlist.sh`); "
        "everything past the preamp outputs is the loop break; "
        "see Methodology for what that omits."
    )
    a(f"- **Corner matrix run**: process=['{result.corner}'], temperature_c=[{result.temp_c}], supply_v=[{VDD}] (1 point)")
    a(
        f"- **Noise methodology**: `ac-based`, integration bandwidth "
        f"{NOISE_FSTART_HZ:g}Hz-{NOISE_FSTOP_HZ:g}Hz. REDUCED SUB-MODEL, not "
        f"the full comparator_core.spice fragment: {VBIAS_NOTE}. This is a "
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
    return _finalize_record(
        lines, record_path, _resolve_pdk_line(info), toolchain._ngspice_version() or "unknown",
        netlist_sha, "noise", supersedes=supersedes,
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
    netlist_sha = evidence.sha256_file(DUT_FRAGMENT)
    record_path = evidence.write_netlist_snapshot(EXPERIMENT_DIR, record_id, DUT_FRAGMENT)
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
    a(NETLIST_PROVENANCE)
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
    corner: str = "tt", temp_c: float = 27.0, quiet: bool = False,
) -> list[KickbackPoint]:
    info = pdk.resolve_or_raise()
    results: list[KickbackPoint] = []
    with tempfile.TemporaryDirectory(prefix="comparator-decision-kickback-") as scratch:
        scratch_dir = Path(scratch)
        for variant in KICKBACK_VARIANTS:
            log_name = f"kickback_{variant}"
            deck = _kickback_deck(info, corner, temp_c, variant, log_name)
            log_text = _run(deck, scratch_dir, log_name)
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
    netlist_sha = evidence.sha256_file(DUT_FRAGMENT)
    record_path = evidence.write_netlist_snapshot(EXPERIMENT_DIR, record_id, DUT_FRAGMENT)
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
    a(NETLIST_PROVENANCE)
    a(
        f"- **Corner matrix run**: process=['{loaded.corner}'], "
        f"temperature_c=[{loaded.temp_c}], supply_v=[{VDD}] (1 PVT point, "
        "both variants -- **subset-corner justification**: this record "
        "re-measures the SAME single nominal corner (tt/27C, 1 kOhm, "
        "50 mV overdrive) issue #26's kickback record "
        "(20260916-060139-f1eb978, the pre-mitigation measurement DR-002's "
        "Kickback disposition cites) used, so the before/after comparison "
        "DR-002 asked for is direct and like-for-like per issue #30's "
        "acceptance criteria -- a full-corner kickback sweep remains open "
        "work exactly as DR-002 already flags it)"
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
        + " The comparison holds for the single tt/27C PVT point this "
        "record runs (see Corner matrix run above); kickback PVT coverage "
        "remains open work per DR-002."
    )
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
        "mode", nargs="?", choices=["regen", "offset", "noise", "reset", "kickback"],
        help="which characterization to run",
    )
    ap.add_argument("--check-env", action="store_true", help="check toolchain + PDK, print summary, exit")
    ap.add_argument("--corner", default="tt")
    ap.add_argument("--temp", type=float, default=27.0)
    ap.add_argument("--seed", type=int, default=1, help="offset: MC base seed")
    ap.add_argument("--n", type=int, default=16, help="offset: MC sample count")
    ap.add_argument("--record", action="store_true", help="write an evidence record under records/")
    ap.add_argument("--note", default="")
    ap.add_argument(
        "--supersedes", default="",
        help="prior <record-id> this run REPLACES for the same claim. Omit for a record making a different claim.",
    )
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

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
        points = run_regen_sweep(corner=args.corner, temp_c=args.temp, quiet=args.quiet)
        if args.record:
            path = write_regen_evidence(points, args.corner, args.temp, note=args.note, supersedes=args.supersedes)
            print(f"wrote {path}")
        unresolved = [p for p in points if p.regen_time_ns is None]
        return 0 if not unresolved else 1

    if args.mode == "offset":
        result = run_offset_mc(corner=args.corner, temp_c=args.temp, seed=args.seed, n=args.n, quiet=args.quiet)
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

    if args.mode == "reset":
        points = run_reset_check(quiet=args.quiet)
        if args.record:
            path = write_reset_evidence(points, note=args.note, supersedes=args.supersedes)
            print(f"wrote {path}")
        return 0 if all(p.ok for p in points) else 1

    if args.mode == "kickback":
        points = run_kickback(corner=args.corner, temp_c=args.temp, quiet=args.quiet)
        if args.record:
            path = write_kickback_evidence(points, note=args.note, supersedes=args.supersedes)
            print(f"wrote {path}")
        return 0 if all(p.ok for p in points) else 1

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
