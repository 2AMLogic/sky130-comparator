"""`noise-tran`: regeneration-inclusive input-referred noise.

Transient-noise Monte Carlo with equivalent-source injection (issue #41), plus
the chunked/resumable campaign driver that runs it inside a wall-clock budget
(issue #100). Both halves are in one module: the campaign exists only to drive
this experiment, and the two share its decks and constants.

One of the seven experiment modules `run.py` drives; see its docstring for the
experiment as a whole and `_shared.py` for the preamble they share. Moved here
verbatim from run.py by issue #224.
"""

from __future__ import annotations

import dataclasses
import json
import math
import os
import statistics
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

_EXPERIMENT_DIR = str(Path(__file__).resolve().parent)
if _EXPERIMENT_DIR not in sys.path:
    # Siblings of a path-loaded module under a hyphenated directory name: see
    # _shared.py's docstring for why this is how they reach each other.
    sys.path.insert(0, _EXPERIMENT_DIR)

import _shared  # noqa: E402  -- `_shared._run{,_many}` are patch seams
import noise  # noqa: E402  -- `noise.run_noise` is a patch seam
from _shared import (  # noqa: E402
    CLAIM_TEXT,
    EXPERIMENT_DIR,
    NOISE_FSTART_HZ,
    NOISE_FSTOP_HZ,
    PEX_LATCH_FRAGMENT,
    RESET_NS,
    RESET_TR_NS,
    STEERING_GATE_INJECTION,
    TERMINAL_GATE,
    VCM,
    VDD,
    _dut_device_line,
    _dut_fragment,
    _dut_lines,
    _finalize_record,
    _retie_star_legs,
    dut_provenance,
    netlist_provenance,
    post_layout_delta_lines,
)
from noise import (  # noqa: E402
    NOISE_STRETCH_MV,
    NOISE_TARGET_MV,
    NoiseResult,
)
from offset import (  # noqa: E402
    PICKOFF_TSTOP_NS,
    VINDIFF_GAIN_CAL_MV,
    _pickoff_deck,
    _pickoff_value,
)
from harness import evidence, pdk, toolchain  # noqa: E402


# WHY THIS EXISTS. The `noise` sub-command (noise.py) is, by its own statement, a
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
# and GST_P/GST_N with DC=0 (no bias disturbance). On the post-layout DUT
# (issue #65) the break is made one element further out -- the gate's own
# parasitic star leg is re-pointed onto GST_P/GST_N and the device line is
# not touched at all -- which is the SAME network by series commutation and
# leaves these two source lines textually identical in both provenances; see
# the POST-LAYOUT DECK SURGERY note in _shared.py, RULE 3.

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


def _decision_deck_name(k: float, sign: int, i: int) -> str:
    """The decision deck's name, which is also its persistence key in a
    resumable campaign's scratch directory -- so the build loop and the
    read-back loop MUST agree on it byte for byte. Single-sourced here."""
    return f"dec_{k:g}_{'+' if sign > 0 else '-'}_{i}".replace(".", "p")


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
                results[name] = _shared._run(build(NOISE_TRAN_TS), scratch_dir, name)
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
        results[name] = _shared._run(build(NOISE_TRAN_RETRY_TS), scratch_dir, name)
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
        log_text = _shared._run(_trnoise_calibration_deck(1e-3, NOISE_TRAN_TS), scratch_dir, "trncal")
    factor = float("nan")
    for line in log_text.splitlines():
        if line.strip().startswith("cal_std="):
            factor = float(line.split("=")[1].strip()) / 1e-3
    if not (factor > 0):
        raise RuntimeError(f"trnoise calibration failed to parse: {log_text[-400:]}")
    if not quiet:
        print(f"  trnoise calibration: std = {factor:.4f} x na (na in volts, ts={NOISE_TRAN_TS:g}s)")
    return factor


def _latch_front_end_block() -> tuple[str, tuple[str, str]]:
    """The three-device steering+tail sub-model, plus the pair of nodes its
    gate drives attach to.

    Schematic: the three named device lines, re-emitted verbatim from the
    committed fragment with their gates on GST_P/GST_N -- byte-identical to
    what this deck has always inlined, driven at GST_P/GST_N.

    Post-layout (issue #65): the committed LATCH FRONT-END PARTITION
    (`layout/comparator.pex-latch.spice`, emitted by `layout/extract_pex.py`
    alongside the preamp partition it already emitted, and selected there by
    the same kind of connectivity rule -- "every device on the latch tail
    node TAIL2" -- rather than by a name list), verbatim, driven at OUTP1 /
    OUTN1.

    NOTE this deck needs no terminal move at all, and deliberately makes
    none. GST_P/GST_N exist on the schematic side only because the three
    device lines are lifted out of a fragment where their gates name the
    preamp outputs; in this sub-model there IS no preamp, so "the gate net"
    is the drive point. On the extracted side that net is already present as
    a hub (`OUTP1`/`OUTN1`) with nothing but the gate's own star leg on it,
    so the ideal drive attaches there directly -- which also keeps the
    gates' extracted leg resistance between the drive and the gate, where
    the layout puts it. (Re-pointing the gate legs onto fresh GST_* nodes
    here would strand `OUTP1`/`OUTN1` as a capacitor-only island with no DC
    path, which is the tell that the terminal-move rules are for the FULL
    fragment's decks, not for a partition that already ends at that net.)
    """
    if _shared.dut_provenance() == "extracted":
        return PEX_LATCH_FRAGMENT.read_text(), ("OUTP1", "OUTN1")
    return "\n".join([
        _dut_device_line("XM_STN_P", nodes=["OUTP", "GST_P", "TAIL2", "GND"]),
        _dut_device_line("XM_STN_N", nodes=["OUTN", "GST_N", "TAIL2", "GND"]),
        _dut_device_line("XM_TAIL2"),
    ]), ("GST_P", "GST_N")


def _noise_tran_dut_block() -> list[str]:
    """The FULL DUT fragment with the steering pair's gates driven from the
    injected nodes GST_P/GST_N, as deck lines.

    The series TRNOISE sources the callers place are always
    `V<x> GST_<s> <gate net> dc 0 TRNOISE(...)` -- the same two lines in both
    provenances -- because _shared.py's RULE 3 inserts on the hub side of the star
    leg, where the gate NET (not a leg node) is what the source's far side
    attaches to.
    """
    if _shared.dut_provenance() == "extracted":
        return _retie_star_legs(
            _dut_lines(),
            [(base, TERMINAL_GATE, node) for base, node, _d, _g in STEERING_GATE_INJECTION],
        ).splitlines()
    injected = {base: (node, drain) for base, node, drain, _g in STEERING_GATE_INJECTION}
    out: list[str] = []
    for raw in _dut_lines().splitlines():
        stripped = raw.strip()
        name = stripped.split()[0] if stripped else ""
        if name in injected:
            gate_node, out_node = injected[name]
            out.append(_dut_device_line(name, nodes=[out_node, gate_node, "TAIL2", "GND"]))
        else:
            out.append(raw)
    return out


def _latch_noise_deck(
    info: pdk.PdkInfo, corner: str, temp_c: float, gate_cm_v: float, cl_ff: float,
) -> str:
    """AC `.noise` deck for the latch front-end's gate-referred noise (stage
    2 above): steering pair + strong tail re-emitted verbatim from the
    committed fragment (gates moved to driven nodes), linearized at the
    preamp's own static output common mode with CLKT at VDD."""
    block, (gate_p, gate_n) = _latch_front_end_block()
    return "\n".join([
        f"* comparator-decision latch front-end gate-referred noise -- "
        f"corner={corner} temp={temp_c}C gate_cm={gate_cm_v:.4f}V (issue #41)",
        f".lib {info.ngspice_lib} {corner}",
        f".temp {temp_c}",
        f".param vdd_val = {VDD} vcmo = {gate_cm_v:.6f}",
        "",
        "Vdd VDD 0 dc {vdd_val}",
        "Vclkfix CLKT 0 dc {vdd_val}",
        f"Vstp {gate_p} 0 dc {{vcmo}} AC 1",
        f"Vstn {gate_n} 0 dc {{vcmo}}",
        "",
        "* steering pair + strong tail, verbatim device lines (gates on the",
        "* driven GST_* nodes -- the same node-replacement helper the reset",
        "* counterfactual uses)"
        + (
            ""
            if _shared.dut_provenance() != "extracted" else
            f"\n* POST-LAYOUT: the committed latch front-end partition, and the\n"
            f"* gate drive attaches at {gate_p}/{gate_n} -- see "
            "`_latch_front_end_block`"
        ),
        block,
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
        log_text = _shared._run(deck, scratch_dir, "latch_noise")
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
    lines += _noise_tran_dut_block()
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
    lines += _noise_tran_dut_block()
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


_NORMAL_DIST = statistics.NormalDist()


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
    denom = _NORMAL_DIST.inv_cdf(arg)
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


# ---------------------------------------------------------------------------
# Chunked / resumable noise-tran campaigns (issue #100)
# ---------------------------------------------------------------------------
#
# WHY THIS EXISTS. A full-N post-layout `noise-tran` corner is
# `4 gaincal + N + 4 x seeds-per-point` decks -- 388 of them at N=128/64 --
# and this host kills any single agent command at ~60 minutes (measured by
# issue #89; see README "A second host cost"). At the measured ~35-285 s per
# deck that is an order of magnitude over the ceiling, so a full-N corner
# CANNOT run as one command here, and a run killed by the ceiling wrote no
# record at all: issue #89 spent 59.5 minutes and committed nothing.
#
# Issue #95 chose between the three ways out (a resumable/chunked runner, a
# different execution host, or redefining "full N" below 128) and picked the
# runner. This is it: `--resume-dir` persists each deck's DERIVED SCALAR as
# soon as that deck completes, and `--chunk-decks` / `--chunk-seconds` stop
# an invocation cleanly while it is still inside the ceiling. A full-N corner
# then becomes a documented SEQUENCE of identical sub-ceiling commands.
#
# TWO PROPERTIES THIS IS BUILT AROUND, because the campaign's value depends
# on them and neither is self-evident from the flags:
#
#  1. THE RESULT MUST NOT DEPEND ON THE CHUNKING. Every deck already pins its
#     own `.option rndseed=<stable seed derived from its index>`, and the
#     decision points' overdrives are a deterministic function of the
#     completed pick-off set, so a deck's contribution is a pure function of
#     its key. The chunked and unchunked paths therefore run the SAME
#     downstream arithmetic over the SAME per-deck values -- structurally,
#     not by a parallel re-implementation: `NoiseTranCampaign.resolve()` is
#     the only thing that differs between them, and in ephemeral mode
#     (`root is None`) it dispatches exactly the batch `_run_many*` call the
#     un-chunked runner always made.
#  2. AN INCOMPLETE CAMPAIGN MUST WRITE NO RECORD. The "a killed run produces
#     no record" property is a safety property, not an accident: a partial
#     record would state an N on its face that its own statistics were not
#     computed at. So an invocation that stops on its own budget raises
#     `NoiseTranCampaignIncomplete` INSTEAD of returning a result, which
#     means `--record` cannot fire; the CLI turns that into exit status
#     `NOISE_TRAN_INCOMPLETE_EXIT` and a progress line.
#
# WHAT IS PERSISTED, and what deliberately is not. Per deck: the one derived
# scalar the statistics consume (`_pickoff_value()`'s pick-off difference, or
# `_decision_from_csv()`'s latched decision), written atomically to
# `<resume-dir>/decks/<key>.json`. NOT the deck's raw ngspice log or csv:
# those are scratch, no record has ever cited a per-seed Monte Carlo log, and
# keeping 388 of them would make the scratch dir the campaign's largest
# artifact for no evidentiary gain. The three logs a record DOES embed
# (`latch_noise`, `injcal_input`, `injcal_gate`) belong to the AC/calibration
# preamble, which is persisted whole in `<resume-dir>/preamble.json` -- so a
# resumed chunk reuses the identical injection amplitudes rather than
# re-deriving them, and the record's netlist snapshot (built from `na_input`
# / `na_gate`) is bit-identical to the unchunked one's.
NOISE_TRAN_CAMPAIGN_SCHEMA = 1
NOISE_TRAN_INCOMPLETE_EXIT = 3

_MISSING = object()


class NoiseTranCampaignIncomplete(RuntimeError):
    """A chunked invocation stopped on its own budget with decks outstanding.

    Raised INSTEAD of returning a `NoiseTranResult`, so no caller can write a
    record from a partial campaign. The scratch directory is left valid and
    resumable: re-running the identical command continues from here.
    """

    def __init__(
        self, message: str, *, stage: str, resume_dir: Path,
        completed: int, total: int,
    ) -> None:
        super().__init__(message)
        self.stage = stage
        self.resume_dir = resume_dir
        self.completed = completed
        self.total = total


class NoiseTranCampaign:
    """Per-deck result store for one `noise-tran` campaign.

    Two modes behind one interface, so the statistics downstream are computed
    by exactly the same code either way:

      * EPHEMERAL (`root=None`) -- the un-chunked behaviour this bench has
        always had: every deck runs, in ONE batch at the caller's `--jobs`
        width, its derived value is used immediately, nothing is persisted.
      * RESUMABLE (`root=<dir>`) -- each deck's derived value is written to
        `<root>/decks/<key>.json` as soon as that deck completes, and a deck
        whose file is already there is not re-run. Decks are dispatched in
        batches of `--jobs` so persistence keeps up with completion; at the
        `--jobs 1` this host is limited to (one-core cgroup quota, #83) that
        is one deck at a time.

    The campaign KEY is what makes a scratch directory safe to point a second
    command at: corner, temperature, N, seeds/point, DUT provenance and the
    DUT fragment's own sha256 are recorded in `<root>/campaign.json`, and a
    mismatch is refused loudly rather than silently mixing two campaigns'
    decks into one record. The fragment hash is in there for the same reason
    every record carries it: a resumed campaign whose netlist changed
    underneath it is not one campaign.
    """

    def __init__(
        self, root: Path | None = None, key: dict | None = None,
        chunk_decks: int | None = None, chunk_seconds: float | None = None,
        quiet: bool = False,
    ) -> None:
        if root is None and (chunk_decks is not None or chunk_seconds is not None):
            raise ValueError(
                "--chunk-decks / --chunk-seconds need --resume-dir: a chunk "
                "budget without a scratch directory to persist into would "
                "throw away every deck it ran"
            )
        self.root = Path(root) if root is not None else None
        self.key = dict(key or {})
        self.chunk_decks = chunk_decks
        self.chunk_seconds = chunk_seconds
        self.quiet = quiet
        self._ran = 0
        self._started = time.monotonic()
        if self.root is not None:
            self._open()

    # --- scratch-directory layout -----------------------------------------

    @property
    def manifest_path(self) -> Path:
        return self.root / "campaign.json"

    @property
    def decks_dir(self) -> Path:
        return self.root / "decks"

    @property
    def preamble_path(self) -> Path:
        return self.root / "preamble.json"

    def _manifest(self) -> dict:
        return dict(self.key, schema=NOISE_TRAN_CAMPAIGN_SCHEMA)

    def _open(self) -> None:
        self.decks_dir.mkdir(parents=True, exist_ok=True)
        want = self._manifest()
        if self.manifest_path.exists():
            try:
                have = json.loads(self.manifest_path.read_text())
            except ValueError as exc:
                raise RuntimeError(
                    f"{self.manifest_path} is not readable JSON ({exc}) -- "
                    "point --resume-dir at a fresh directory"
                ) from exc
            if have != want:
                differing = sorted(
                    k for k in set(have) | set(want) if have.get(k) != want.get(k)
                )
                raise RuntimeError(
                    f"--resume-dir {self.root} holds a DIFFERENT campaign: "
                    + ", ".join(
                        f"{k}={have.get(k)!r} on disk vs {want.get(k)!r} requested"
                        for k in differing
                    )
                    + ". Resuming across a changed campaign key would mix two "
                    "campaigns' decks into one record -- use a fresh "
                    "--resume-dir for the new configuration."
                )
        else:
            self.manifest_path.write_text(
                json.dumps(want, indent=2, sort_keys=True) + "\n"
            )

    @staticmethod
    def _file_key(name: str) -> str:
        """Deck name -> filename stem. The decision decks' names carry the
        overdrive SIGN as a literal `+`/`-`; both are spelled out so the
        stem is portable and a `+` can never be read as a `-`."""
        return name.replace("+", "plus").replace("-", "minus")

    def _deck_path(self, name: str) -> Path:
        return self.decks_dir / f"{self._file_key(name)}.json"

    # --- reading / writing one deck's derived value -----------------------

    def _load_json(self, path: Path):
        """A truncated or unreadable file is reported MISSING, not fatal: a
        kill can land mid-write, and re-running one deck is always cheaper
        and safer than trusting a partial one. (The writes below are atomic
        via `os.replace`, so this should not happen -- but "should not" is
        not the bar for a file the ceiling is expected to interrupt.)"""
        if not path.exists():
            return _MISSING
        try:
            return json.loads(path.read_text())
        except (ValueError, OSError):
            return _MISSING

    @staticmethod
    def _store_json(path: Path, payload: dict) -> None:
        tmp = path.parent / (path.name + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        os.replace(tmp, path)

    def load_deck(self, name: str):
        if self.root is None:
            return _MISSING
        blob = self._load_json(self._deck_path(name))
        if blob is _MISSING or "value" not in blob:
            return _MISSING
        return blob["value"]

    def store_deck(self, name: str, value) -> None:
        if self.root is None:
            return
        self._store_json(self._deck_path(name), {"deck": name, "value": value})

    def load_preamble(self):
        if self.root is None:
            return _MISSING
        return self._load_json(self.preamble_path)

    def store_preamble(self, payload: dict) -> None:
        if self.root is None:
            return
        self._store_json(self.preamble_path, payload)

    # --- progress and the chunk budget ------------------------------------

    def total_decks(self) -> int:
        """Every deck this campaign will ever run: the gain calibration, the
        pick-off MC, and both signs of both decision points."""
        return (
            len(VINDIFF_GAIN_CAL_MV)
            + int(self.key.get("n_pickoff", 0))
            + 2 * len(NOISE_TRAN_DECIDE_PAIRS) * int(self.key.get("seeds_per_point", 0))
        )

    def completed_decks(self) -> int:
        if self.root is None:
            return 0
        return len(list(self.decks_dir.glob("*.json")))

    def _budget_spent(self) -> bool:
        if self.chunk_decks is not None and self._ran >= self.chunk_decks:
            return True
        if self.chunk_seconds is not None:
            return (time.monotonic() - self._started) >= self.chunk_seconds
        return False

    def _stop(self, stage: str) -> None:
        completed = self.completed_decks()
        total = self.total_decks()
        elapsed = time.monotonic() - self._started
        raise NoiseTranCampaignIncomplete(
            f"noise-tran campaign INCOMPLETE and RESUMABLE -- stopped in stage "
            f"'{stage}' on this invocation's chunk budget after {self._ran} deck(s) "
            f"/ {elapsed / 60:.1f} min. {completed} of {total} campaign decks are "
            f"complete in {self.root}. NO record was written (a partial campaign "
            f"must never produce one). Re-run the IDENTICAL command to continue "
            f"from here; the campaign emits its record on the invocation that "
            f"completes the last deck.",
            stage=stage, resume_dir=self.root, completed=completed, total=total,
        )

    # --- the one place decks are dispatched -------------------------------

    def resolve(
        self, stage: str, builds: list, extract, run_batch, jobs: int = 1,
        logs: dict[str, str] | None = None,
    ) -> dict:
        """Return `{deck name: derived value}` for every `(name, build)` in
        `builds`, running only the decks not already persisted.

        `run_batch(batch)` runs one batch of `(name, build)` pairs and returns
        their ngspice logs; `extract(name)` reads that deck's derived value
        out of the scratch directory right after it ran. Raises
        `NoiseTranCampaignIncomplete` if the chunk budget runs out with decks
        still pending.
        """
        values: dict = {}
        pending: list = []
        for name, build in builds:
            cached = self.load_deck(name)
            if cached is _MISSING:
                pending.append((name, build))
            else:
                values[name] = cached
        if self.root is not None and not self.quiet:
            print(
                f"  [{stage}] {len(values)} of {len(builds)} decks already in "
                f"{self.root}, {len(pending)} to run"
            )
        # Ephemeral mode dispatches the whole stage as ONE batch -- byte-for-
        # byte the call the un-chunked runner always made, including its
        # `--jobs`-wide parallelism across the entire stage.
        width = len(pending) if self.root is None else max(1, jobs)
        index = 0
        while index < len(pending):
            if self._budget_spent():
                self._stop(stage)
            batch = pending[index:index + width]
            batch_logs = run_batch(batch)
            if logs is not None:
                logs.update(batch_logs)
            for name, _build in batch:
                value = extract(name)
                self.store_deck(name, value)
                values[name] = value
            self._ran += len(batch)
            index += len(batch)
        return values


def run_noise_tran(
    corner: str = "tt", temp_c: float = 27.0, n_pickoff: int = 128,
    seeds_per_point: int = NOISE_TRAN_SEEDS_PER_POINT, quiet: bool = False,
    jobs: int = 1, resume_dir: Path | None = None,
    chunk_decks: int | None = None, chunk_seconds: float | None = None,
) -> NoiseTranResult:
    info = pdk.resolve_or_raise()
    campaign = NoiseTranCampaign(
        root=resume_dir,
        key={
            "corner": corner,
            "temp_c": float(temp_c),
            "n_pickoff": int(n_pickoff),
            "seeds_per_point": int(seeds_per_point),
            "dut": dut_provenance(),
            "netlist_sha256": evidence.sha256_file(_dut_fragment()),
        },
        chunk_decks=chunk_decks, chunk_seconds=chunk_seconds, quiet=quiet,
    )
    logs: dict[str, str] = {}

    with tempfile.TemporaryDirectory(prefix="comparator-decision-noisetran-") as scratch:
        scratch_dir = Path(scratch)

        # --- AC / calibration preamble (stages 1-3 + the injection-rms
        # verification decks). Persisted as ONE unit: it is what fixes the
        # injected amplitudes, so a resumed chunk MUST reuse it verbatim
        # rather than re-derive it, and the three logs a record embeds come
        # from here.
        preamble = campaign.load_preamble()
        if preamble is _MISSING:
            # Stage 1: preamp input-referred rms + its op point (gate CM for stage 2).
            preamp = noise.run_noise(corner=corner, temp_c=temp_c, quiet=quiet)
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
            # Injection-rms verification decks: the same trnoise sources into a
            # 1-ohm load, one for each amplitude, so the record can state
            # achieved-vs-target injection rms directly.
            for tag, na in (("input", na_input), ("gate", na_gate)):
                cal_log = _trnoise_calibration_deck(na, NOISE_TRAN_TS)
                vlog = _shared._run(cal_log, scratch_dir, f"injcal_{tag}")
                logs[f"injcal_{tag}"] = vlog
            achieved = {}
            for tag in ("input", "gate"):
                for line in logs[f"injcal_{tag}"].splitlines():
                    if line.strip().startswith("cal_std="):
                        achieved[tag] = float(line.split("=")[1].strip())
            campaign.store_preamble({
                "preamp": dataclasses.asdict(preamp),
                "latch": dataclasses.asdict(latch),
                "trnoise_factor": factor,
                "na_input": na_input,
                "na_gate": na_gate,
                "achieved": achieved,
                "logs": {k: v for k, v in logs.items()},
            })
        else:
            preamp = NoiseResult(**preamble["preamp"])
            latch = LatchNoiseResult(**preamble["latch"])
            factor = preamble["trnoise_factor"]
            na_input = preamble["na_input"]
            na_gate = preamble["na_gate"]
            achieved = preamble["achieved"]
            logs.update(preamble["logs"])
            if not quiet:
                print(
                    f"  resumed the AC/calibration preamble from {campaign.root} "
                    f"(input na={na_input:g}V, gate na={na_gate:g}V) -- the "
                    f"injected amplitudes are the first invocation's, verbatim"
                )

        # Gain calibration: ideal devices, plain corner, NO noise -- the
        # same calibration the `offset` sub-command performs, so the
        # pick-off statistic is referred back through the identical gain.
        def _cal_build(vindiff_mv: float):
            def build(ts: float) -> str:
                return _pickoff_deck(
                    info, corner, temp_c, vindiff_mv, f"gaincal_{vindiff_mv}mV",
                )
            return build

        cal_values = campaign.resolve(
            "gain calibration",
            [(f"gaincal_{v}mV", _cal_build(v)) for v in VINDIFF_GAIN_CAL_MV],
            extract=lambda name: _pickoff_value(scratch_dir / f"{name}.csv"),
            run_batch=lambda batch: _shared._run_many(
                [(name, build(NOISE_TRAN_TS)) for name, build in batch],
                scratch_dir, jobs,
            ),
            jobs=jobs, logs=logs,
        )
        gain_cal_points = [
            (v / 1000.0, cal_values[f"gaincal_{v}mV"]) for v in VINDIFF_GAIN_CAL_MV
        ]
        sxy = sum(x * y for x, y in gain_cal_points)
        sxx = sum(x * x for x, y in gain_cal_points)
        gain = sxy / sxx if sxx else float("nan")
        if not quiet:
            print(f"  gain = {gain:.4f} V/V (from {len(gain_cal_points)} calibration points)")

        def _mc_batch(batch):
            return _run_many_ts_retry(batch, scratch_dir, jobs)

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
        po_values = campaign.resolve(
            "pick-off MC", po_builds,
            extract=lambda name: _pickoff_value(scratch_dir / f"{name}.csv"),
            run_batch=_mc_batch, jobs=jobs, logs=logs,
        )
        pickoff_diffs = [po_values[f"po_{i}"] for i in range(n_pickoff)]
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
                    name = _decision_deck_name(k, sign, i)
                    dseed = (dseed_base + int(k * 1000) * 10_000
                             + (seeds_per_point if sign > 0 else 0) + i)
                    d_builds.append((name, _dec_build(name, sign * v_mv, dseed)))
            # The decision points' overdrives are a function of the COMPLETED
            # pick-off set (sigma_hat above), so these deck keys cannot exist
            # -- and this stage cannot start -- until statistic (a) is whole.
            # That is the resume order, not an extra constraint: a chunk that
            # stops inside the pick-off stage simply never names these.
            d_values = campaign.resolve(
                f"decision pair k={k:g}", d_builds,
                extract=lambda name: _decision_from_csv(scratch_dir / f"{name}.csv"),
                run_batch=_mc_batch, jobs=jobs, logs=logs,
            )
            for sign in (1, -1):
                ones = 0
                unresolved = 0
                for i in range(seeds_per_point):
                    name = _decision_deck_name(k, sign, i)
                    dec = d_values[name]
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
        darg = point["v_mv"] / sigma_i
        # var(sigma_i)/sigma_i^2 ~ (dPhi^-1/darg)^2 * var(arg) / darg^2
        dprobit = math.sqrt(2 * math.pi) * math.exp(0.5 * darg * darg)
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


def degenerate_cross_check_reason(points: list[dict]) -> str:
    """Why every decision pair came out degenerate, READ OFF THE COUNTS.

    A degenerate pair (p+ == p-, or p+ - p- == 1) carries no sigma
    information, but the three ways of getting there are three different
    physical statements and a record must not assert the wrong one. This
    classifies from the data instead:

      UNRESOLVED   most runs never separated inside the decision window --
                   the overdrive sits under the corner's own
                   resolvable-overdrive floor. (The schematic-level
                   `ss`/-40C record's case.)
      ALL-ONE-WAY  every run decided, and decided the SAME way at BOTH
                   signs -- so a DETERMINISTIC term bigger than the
                   sigma-scaled overdrive (a systematic offset) is setting
                   the outcome, not noise. Noise would have to be comparable
                   to that term to flip anything. This is the post-layout
                   case: issue #65's `tt`/27C run sat entirely inside the
                   layout-induced systematic offset the post-layout `offset`
                   record measured.
      ALL-CORRECT  every run decided, correctly, at both signs -- the
                   overdrive is far ABOVE what noise can flip.

    Issue #65: before this was derived, the record asserted the UNRESOLVED
    wording unconditionally, which was simply untrue of an all-one-way run
    sitting two lines below its own 0-unresolved counts.
    """
    if not points:
        return "no decision pairs were run"
    total = sum(2 * p["m"] for p in points)
    unresolved = sum(p.get("unresolved", 0) for p in points)
    if unresolved * 2 >= total:
        return (
            f"{unresolved} of {total} runs never separated inside the "
            "decision window: the sigma-scaled overdrives sit below this "
            "corner's own resolvable-overdrive floor, so the pairs carry no "
            "sigma information"
        )
    one_way = all(
        p["plus_ones"] == p["minus_ones"] and p["plus_ones"] in (0, p["m"])
        for p in points
    )
    if one_way:
        side = "negative" if all(p["plus_ones"] == 0 for p in points) else "positive"
        return (
            f"every one of the {total} runs RESOLVED ({unresolved} unresolved) "
            f"and every one of them decided the SAME way -- {side} -- at BOTH "
            "signs of the overdrive, so p+ = p- exactly and the pairs carry no "
            "sigma information. That is not a noise statement and must not be "
            "read as one: it says a DETERMINISTIC term larger than these "
            "sigma-scaled overdrives (tens to hundreds of uV) is setting the "
            "outcome. Compare the systematic input offset the `offset` "
            "sub-command measures at this same corner and provenance before "
            "reading anything else into it"
        )
    all_correct = all(
        p["plus_ones"] == p["m"] and p["minus_ones"] == 0 for p in points
    )
    if all_correct:
        return (
            f"every one of the {total} runs decided CORRECTLY at both signs "
            "(p+ = 1, p- = 0), so the overdrives sit far above anything this "
            "noise can flip and the pairs carry no sigma information"
        )
    return (
        f"the pair counts below ({unresolved} of {total} runs unresolved) "
        "leave p+ - p- outside the range the probit estimator can invert"
    )


def two_statistics_line(result: NoiseTranResult) -> str:
    """The record's headline bullet: the pick-off sigma, and either the
    decision cross-check that corroborates it or the data-derived reason
    there is none. Split out of the record writer so the degenerate branch
    can be tested against synthetic counts without an ngspice run."""
    head = (
        f"- **Two statistics, one claim**: (a) pick-off MC at Vindiff=0, "
        f"N={len(result.pickoff_diffs)} seeds, gain "
        f"{result.gain_v_per_v:.4f} V/V -> input-referred sigma "
        f"**{result.sigma_pickoff_mv:.4f} mV** (95% CI "
        f"[{result.sigma_pickoff_ci95_mv[0]:.4f}, "
        f"{result.sigma_pickoff_ci95_mv[1]:.4f}] mV)"
    )
    if result.sigma_decision_mv == result.sigma_decision_mv:
        seeds = result.decision_points[0]["m"] if result.decision_points else 0
        return (
            f"{head}; (b) decision-transition cross-check at "
            f"+/-{NOISE_TRAN_DECIDE_PAIRS} sigma_hat, {seeds} "
            f"seeds/point -> sigma **{result.sigma_decision_mv:.4f} mV**. "
            f"(b)'s agreeing with (a) within (b)'s coarser CI is the evidence "
            f"that the regenerative phase adds no material noise term beyond "
            f"the injected device noise -- the regeneration-inclusiveness this "
            f"record exists to establish."
        )
    return (
        f"{head}. (b) The decision-transition cross-check is NOT MEASURABLE at "
        f"this corner: every pair was degenerate, and the reason is read off "
        f"the counts in the table below rather than asserted from a canned "
        f"string -- {degenerate_cross_check_reason(result.decision_points)}. "
        f"Either way the consequence for THIS record is the same: at this "
        f"corner the decision statistics are not noise-bound, so the pick-off "
        f"figure stands alone and the cross-check is deferred to the corners "
        f"where it is measurable."
    )


def write_noise_tran_evidence(
    result: NoiseTranResult, note: str = "", supersedes: str = "",
) -> Path:
    info = pdk.resolve()
    netlist_text = _noise_tran_pickoff_deck(
        info, result.corner, result.temp_c, 0.0, 10000,
        result.na_input, result.na_gate, "noise_tran_pickoff",
    )
    resv = evidence.reserve_record(EXPERIMENT_DIR, ("corners",))
    record_id = resv.record_id
    netlist_sha = evidence.sha256_text(netlist_text)
    evidence.write_netlist_snapshot_text(EXPERIMENT_DIR, record_id, netlist_text)
    record_path = resv.record_path
    runs_dir = resv.log_dirs["corners"]
    for name in ("latch_noise", "injcal_input", "injcal_gate"):
        if name in result.logs:
            evidence.write_new_text(runs_dir / f"{name}.log", result.logs[name])

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
    a(two_statistics_line(result))
    if _shared.dut_provenance() == "extracted":
        a(
            "- **How the injection is made post-layout** (issue #65): on the "
            "extracted netlist each steering device's gate sits on its own "
            "parasitic star leg (`OUTP1__t4`, `OUTN1__t4`) tied to the "
            "preamp-output hub through that terminal's share of the net's "
            "series resistance (75.87 / 97.49 ohm), so there is no node "
            "on which to insert a series source by naming the gate net. The "
            "deck therefore RE-POINTS those two star-leg resistors from "
            "`OUTP1`/`OUTN1` onto the injected nodes `GST_P`/`GST_N` (values "
            "unchanged) and places the sources `Vstp GST_P OUTP1` / "
            "`Vstn GST_N OUTN1` exactly as the schematic-level deck does; "
            "the device lines and every other extracted element are "
            "byte-identical to the committed fragment, so the whole "
            "injection is two changed tokens. Inserting on this side of the "
            "leg rather than between the gate terminal and its leg is not a "
            "judgement call: a star-leg node carries exactly one device "
            "terminal and exactly one star resistor (asserted by the deck "
            "builder, not assumed), so the leg resistor and an ideal source "
            "are two-terminal elements in series and the two placements are "
            "the same network. Convention for split devices (a schematic "
            "device the layout draws as several parallel fingers): all "
            "fingers are driven from the one injected node, each keeping its "
            "own re-pointed leg. It is not exercised here -- the steering "
            "pair is drawn as ONE W=8 device each, and the split devices on "
            "this layout are the W=13 input pair, whose injection is at the "
            "comparator PINS and needs no surgery at all."
        )
        a(
            "- **Where the stage-2 AC anchor comes from post-layout**: the "
            "latch front-end gate-referred rms is measured on the committed "
            "LATCH FRONT-END PARTITION of the extracted netlist "
            "(`layout/comparator.pex-latch.spice` -- steering pair + latch "
            "tail with their extracted parasitics, selected by connectivity "
            "as `every device on the TAIL2 node`), the exact counterpart of "
            "the schematic side's three named device lines, and the "
            "counterpart of the preamp partition the AC `noise` sub-command "
            "already used post-layout."
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
            # Deliberately does NOT restate a cause. The cause is derived
            # from these same counts in the "Two statistics" bullet above,
            # and a second, independently-worded copy of it is exactly how
            # this record grew a wrong one (issue #65).
            "**not measurable at this corner** (every pair degenerate -- the "
            "reason is derived from these counts in the **Two statistics** "
            "bullet above, and is not restated here so the two cannot drift "
            "apart)"
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
    lines.extend(post_layout_delta_lines(
        "noise-tran", result.corner, result.temp_c, result.sigma_pickoff_mv,
    ))
    a("")
    seeds = result.decision_points[0]["m"] if result.decision_points else 0
    return _finalize_record(
        lines, record_path, info, netlist_sha, "noise-tran",
        extra={
            "noise-tran N pickoff": str(len(result.pickoff_diffs)),
            "noise-tran seeds/sign/decision point": str(seeds),
        },
        supersedes=supersedes,
    )
