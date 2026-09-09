#!/usr/bin/env python3
"""Standalone driver for the comparator-decision experiment (issue #9).

Exercises the placeholder DUT fragment at
sim/comparator-decision/testbench/comparator_core.spice for its decision
behavior in isolation: mismatch-driven offset, input-referred noise, and
regeneration time vs. differential input. No CDAC array or SAR sequencer is
involved -- every source here is an ideal differential DC/pulse stimulus,
because this repo has no SAR ADC (spec/porting-plan.md "Next steps" item 3).

    python3 sim/comparator-decision/run.py --check-env
    python3 sim/comparator-decision/run.py regen  --record
    python3 sim/comparator-decision/run.py offset --record --n 16 --seed 1
    python3 sim/comparator-decision/run.py noise  --record

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
PICKOFF_NS = 0.3  # time after evaluate-start used as the offset pick-off
# point -- see the `offset` subcommand's methodology comment below.
NOISE_FSTART_HZ = 1e3
NOISE_FSTOP_HZ = 1e9

PROCESS_CORNERS = ["tt", "ss", "ff", "sf", "fs"]


def _dut_lines() -> str:
    return DUT_FRAGMENT.read_text()


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
    a(
        "- **Claim**: None -- top-level README's target-spec table is DRAFT "
        "(spec/README.md) and design/comparator.sch does not exist yet "
        "(spec/porting-plan.md 'Next steps' item 1). This record characterizes "
        "the placeholder DUT (see testbench/comparator_core.spice's header) "
        "purely to prove the regen/offset/noise driver plumbing ported from "
        "2AMLogic/sky130-sar-adc works end to end against a real dynamic latch "
        "on this PDK -- it substantiates NO spec row and must not be quoted as "
        "if it characterized this repo's own comparator."
    )
    a(f"- **Netlist provenance**: schematic, placeholder (`{DUT_FRAGMENT.relative_to(evidence.REPO_ROOT)}`)")
    a(
        f"- **Corner matrix run**: process=['{corner}'], temperature_c=[{temp_c}], "
        f"supply_v=[{VDD}] (1 PVT point -- **subset-corner justification**: "
        "plumbing proof at the nominal corner only, per issue #9's acceptance "
        "criteria; a full PVT sweep is deferred to when a real "
        "design/comparator.sch exists to characterize)"
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
PICKOFF_TSTOP_NS = RESET_NS + RESET_TR_NS + 1.5


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
    a(
        "- **Claim**: None -- see the `regen` record's Claim field for why "
        "(placeholder DUT, DRAFT spec, no design/comparator.sch yet). This "
        "record's purpose is to prove the offset-extraction methodology "
        "(linearized pick-off + mismatch-corner Monte Carlo + negative "
        "control) ported from 2AMLogic/sky130-sar-adc works end to end on "
        "this PDK -- distribution shape only, not a spec claim."
    )
    a(f"- **Netlist provenance**: schematic, placeholder (`{DUT_FRAGMENT.relative_to(evidence.REPO_ROOT)}`)")
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
# latch has no stable small-signal operating point once regeneration begins
# (the cross-coupled pair is a positive-feedback loop), so a direct `.noise`
# analysis on the full comparator_core.spice fragment is not meaningful.
# Instead this uses a REDUCED sub-model: the tail + input pair, with the
# devices on the input pair's own drain nodes (DIP/DIN) DIODE-CONNECTED
# (self-biased) so the stage finds its own DC bias point, and with the
# positive-feedback cross-coupling removed entirely. This is a standard
# "break the loop for small-signal analysis" technique (generic
# circuit-analysis practice, not specific to any implementation) -- it
# measures the INTEGRATION phase only (tail on, input pair saturated,
# discharging DIP/DIN) and, per the port source's own DR-004, is a
# deliberate LOWER BOUND: it excludes the cross-coupled latch pair's own
# regenerative-phase noise contribution.
#
# The AC stimulus is single-ended (Vinp gets AC=1, Vinn stays pure DC), and
# ngspice's `inoise_total` (referred back through Vinp) is reported as a
# single-ended input-referred rms noise voltage. For a symmetric
# differential pair with uncorrelated per-side noise contributions, the
# standard diff-pair noise-doubling result gives differential-input-referred
# variance = 2x the single-ended value, i.e.
# rms_differential = sqrt(2) * rms_single_ended -- applied here as a named,
# flagged approximation, not re-derived from scratch.

VBIAS_NOTE = (
    "reduced sub-model of the INTEGRATION phase: tail + input pair, with the "
    "DI-node precharge PMOS pair diode-connected (self-biased) as the loads "
    "on the input pair's own drain nodes DIP/DIN, and the cross-coupled latch "
    "pairs omitted because they are off (Vgs ~ 0) until regeneration begins; "
    "CLK held at VDD (steady evaluate bias, tail on); noise taken at v(DIP,DIN)"
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
        "Vclkfix CLK 0 dc {vdd_val}",
        f"Vinp VINP 0 dc {VCM} AC 1",
        f"Vinn VINN 0 dc {VCM}",
        "",
        "XM_TAIL TAIL CLK GND GND sky130_fd_pr__nfet_01v8 L=0.5 W=8 nf=1",
        "XM_INN DIP VINN TAIL GND sky130_fd_pr__nfet_01v8 L=0.5 W=4 nf=1",
        "XM_INP DIN VINP TAIL GND sky130_fd_pr__nfet_01v8 L=0.5 W=4 nf=1",
        "XM_RST_DIP DIP DIP VDD VDD sky130_fd_pr__pfet_01v8 L=0.5 W=4 nf=1",
        "XM_RST_DIN DIN DIN VDD VDD sky130_fd_pr__pfet_01v8 L=0.5 W=4 nf=1",
        "",
        ".control",
        # sim/spiceinit sets 'option klu' repo-wide for corner-sweep speed,
        # but ngspice's KLU solver does not support .noise analysis. Switch
        # to SPARSE for this invocation only.
        "option sparse",
        "op",
        "print v(TAIL) v(DIP) v(DIN)",
        f"noise v(dip,din) Vinp dec 20 {NOISE_FSTART_HZ:g} {NOISE_FSTOP_HZ:g} 20",
        "print inoise_total onoise_total",
        ".endc",
        ".end",
    ]
    return "\n".join(lines) + "\n"


@dataclass
class NoiseResult:
    single_ended_rms_v: float
    differential_rms_v: float
    op_tail_v: float
    op_dip_v: float
    op_din_v: float
    log_text: str
    corner: str
    temp_c: float


def run_noise(corner: str = "tt", temp_c: float = 27.0, quiet: bool = False) -> NoiseResult:
    info = pdk.resolve_or_raise()
    with tempfile.TemporaryDirectory(prefix="comparator-decision-noise-") as scratch:
        scratch_dir = Path(scratch)
        deck = _noise_deck(info, corner, temp_c)
        log_text = _run(deck, scratch_dir, "noise")

    op_tail = op_dip = op_din = float("nan")
    single_ended = float("nan")
    for line in log_text.splitlines():
        s = line.strip()
        if s.startswith("v(tail)"):
            op_tail = float(s.split("=")[1])
        elif s.startswith("v(dip)"):
            op_dip = float(s.split("=")[1])
        elif s.startswith("v(din)"):
            op_din = float(s.split("=")[1])
        elif s.startswith("inoise_total"):
            single_ended = float(s.split("=")[1])
    differential = single_ended * (2 ** 0.5)
    if not quiet:
        print(f"  op: TAIL={op_tail:.4f}V DIP={op_dip:.4f}V DIN={op_din:.4f}V")
        print(f"  inoise_total (single-ended) = {single_ended * 1000:.4f} mV rms")
        print(f"  differential estimate (x sqrt(2)) = {differential * 1000:.4f} mV rms")
    return NoiseResult(
        single_ended_rms_v=single_ended, differential_rms_v=differential,
        op_tail_v=op_tail, op_dip_v=op_dip, op_din_v=op_din,
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
    a(
        "- **Claim**: None -- see the `regen` record's Claim field for why "
        "(placeholder DUT, DRAFT spec, no design/comparator.sch yet). This "
        "record proves the reduced-sub-model `.noise` methodology ported "
        "from 2AMLogic/sky130-sar-adc runs end to end on this PDK; the "
        "measured value is not compared against any budget because no "
        "noise-budget row exists in this repo's target-spec table yet."
    )
    a("- **Netlist provenance**: schematic, placeholder, reduced sub-model (see Methodology)")
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
    a(f"| Op point: v(TAIL) | {result.op_tail_v:.4f} V | {result.corner}/{result.temp_c}C/{VDD}V |")
    a(f"| Op point: v(DIP)=v(DIN) | {result.op_dip_v:.4f} V | {result.corner}/{result.temp_c}C/{VDD}V |")
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
    a("")
    return _finalize_record(
        lines, record_path, _resolve_pdk_line(info), toolchain._ngspice_version() or "unknown",
        netlist_sha, "noise", supersedes=supersedes,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="comparator-decision standalone testbench driver (issue #9)")
    ap.add_argument(
        "mode", nargs="?", choices=["regen", "offset", "noise"],
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

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
