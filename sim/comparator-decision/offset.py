"""`offset` and `offset-bisect`: mismatch-induced and systematic offset.

`offset` is a Monte Carlo campaign read through a linearized pick-off statistic
calibrated against an ideal-device Vindiff sweep; `offset-bisect` bisects the
differential input at which the decision flips POLARITY (issue #66). They live
in one module because they share the `_pickoff_*` machinery.

One of the seven experiment modules `run.py` drives; see its docstring for the
experiment as a whole and `_shared.py` for the preamble they share. Moved here
verbatim from run.py by issue #224.
"""

from __future__ import annotations

import statistics
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

_EXPERIMENT_DIR = str(Path(__file__).resolve().parent)
if _EXPERIMENT_DIR not in sys.path:
    # Siblings of a path-loaded module under a hyphenated directory name: see
    # _shared.py's docstring for why this is how they reach each other.
    sys.path.insert(0, _EXPERIMENT_DIR)

import _shared  # noqa: E402  -- `_shared._run{,_many}` are patch seams
from _shared import (  # noqa: E402
    CLAIM_TEXT,
    DECIDE_THRESHOLD_V,
    OFFSET_STRETCH_MV,
    OFFSET_TARGET_MV,
    PICKOFF_NS,
    RESET_NS,
    RESET_TR_NS,
    VCM,
    VDD,
    _begin_dut_record,
    _dut_lines,
    _finalize_record,
    netlist_provenance,
    post_layout_delta_lines,
)
from regen import (  # noqa: E402
    _classify_decision,
)
from harness import corners as corners_mod, evidence, pdk, toolchain  # noqa: E402


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
        cal_logs = _shared._run_many(cal_jobs, scratch_dir, jobs)
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
        draw_logs = _shared._run_many(draw_jobs, scratch_dir, jobs)
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
        negctrl_logs = _shared._run_many(negctrl_jobs, scratch_dir, jobs)
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
    info, record_id, netlist_sha, record_path, draws_dir = _begin_dut_record("mc-draws")
    for name, text in result.logs.items():
        evidence.write_new_text(draws_dir / f"{name}.log", text)

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
        lines, record_path, info, netlist_sha, "offset",
        extra={"MC seed": str(result.seed), "MC N": str(result.n)},
        supersedes=supersedes,
    )


# ---------------------------------------------------------------------------
# offset-bisect: decision-referred systematic offset -- bisect the
# differential input at which the decision flips POLARITY (issue #66)
# ---------------------------------------------------------------------------
#
# Why a second offset measurement exists (the `offset` sub-command above
# measures sigma only, and its negative-control mean is a PICK-OFF-referred
# quantity, read at PICKOFF_NS before the latch regenerates): #57's
# post-layout records showed the laid-out comparator has a systematic,
# deterministic input-referred offset whose sub-20 mV decision polarity is
# asymmetric, and the pick-off term could neither be compared against a
# decision outcome nor explain the `ss`/-40C magnitude. The decision-referred
# quantity is measured directly here:
#
#  1. Probe the DUT with single reset->evaluate transients at a series of
#     differential inputs, classifying each decision by BOTH signs of the
#     output crossing (`_classify_decision`, the same three-way split the
#     `regen` sub-command now reports). The evaluate window is
#     BISECT_EVALUATE_NS -- deliberately longer than `regen`'s
#     EVALUATE_NS, because a probe just past the flip regenerates from a
#     vanishing overdrive and must not be misread as a non-decision by a
#     window too short for it.
#  2. Find anchors: `lo` deciding WRONG-POLARITY for a positive probe and
#     `hi` deciding resolved (expanding geometrically from
#     BISECT_BRACKET_START_MV up to BISECT_BRACKET_MAX_MV).
#  3. Bisect TWO boundaries against those anchors: the wrong-polarity edge
#     (last vindiff that still decides the wrong way) and the resolved
#     edge (first vindiff that decides correctly). Every probe outcome
#     moves exactly one bracket edge -- a probe that decides resolves
#     moves the resolved edge down, one that decides wrong-polarity moves
#     the wrong-polarity edge up, and a NON-DECISION probe (neither sign
#     crosses within the window) moves both edges toward itself, because
#     it is "not wrong-polarity" for the lower boundary and "not resolved"
#     for the upper one. The two boundaries coincide (within tolerance) at
#     a single decision flip -- the input-referred systematic offset, with
#     the sign convention stated in the record: the comparator decides
#     correctly for a positive input only when that input exceeds the
#     flip, i.e. it behaves as though an error of -V_flip were added to
#     the applied differential input. Where they do NOT coincide, the gap
#     between them is a measured NON-DECISION BAND -- vindiffs for which
#     no decision occurs at all inside the window (the shape the
#     `ss`/-40C post-layout `regen` re-run found: its +0.5..+10 mV points
#     cross neither sign within 40 ns), and the record reports the band
#     instead of pretending a single flip exists.
#
# The symmetric schematic fragment's flip sits at ~0 by construction --
# the negative control for the measurement itself. There the probe at
# exactly vindiff=0 is ideally metastable (a non-decision), which the
# two-edge bisection handles as just another non-decision probe: both
# edges converge to it from either side and the band collapses to ~0.

BISECT_EVALUATE_NS = 200.0
BISECT_BRACKET_START_MV = 10.0
BISECT_BRACKET_MAX_MV = 160.0  # VCM +/- 0.08 V stays well inside the supply
BISECT_TOL_MV = 0.1
BISECT_MAX_MIDPOINT_PROBES = 16


def _bisect_probe_name(vindiff_mv: float) -> str:
    """Unique, minus-sign-free job/log name for one bisection probe.

    Microvolt resolution keeps every distinct probe name distinct (the
    bisection's own midpoints differ by at least half the tolerance), and
    encoding the value in the name lets a batched/faked `_run_many`
    recover the probe's vindiff without parsing deck text."""
    return f"bisect_{round(vindiff_mv * 1000)}uV".replace("-", "neg")


def _bisect_probe_mv(name: str) -> float:
    """Recover the probe vindiff (mV) from a `_bisect_probe_name` name."""
    body = name.removeprefix("bisect_").removesuffix("uV")
    sign = 1.0
    if body.startswith("neg"):
        sign, body = -1.0, body[3:]
    return sign * int(body) / 1000.0


def _offset_bisect_deck(
    info: pdk.PdkInfo, corner: str, temp_c: float, vindiff_mv: float,
    log_name: str,
) -> str:
    """Single reset->evaluate transient for one bisection probe at the
    nominal supply. Same stimulus shape as `_regen_deck`, with the longer
    BISECT_EVALUATE_NS window and OUTP/OUTN only (no CLK vector needed --
    the classification never looks at the clock)."""
    vindiff_v = vindiff_mv / 1000.0
    period_ns = RESET_NS + RESET_TR_NS + BISECT_EVALUATE_NS + 10.0
    lines = [
        f"* comparator-decision decision-flip offset bisection -- "
        f"vindiff={vindiff_mv}mV corner={corner} temp={temp_c}C (issue #66)",
        f".lib {info.ngspice_lib} {corner}",
        f".temp {temp_c}",
        f".param vdd_val = {VDD}",
        "",
        "Vdd VDD 0 dc {vdd_val}",
        f"Vclk CLK 0 PULSE(0 {{vdd_val}} {RESET_NS}n {RESET_TR_NS}n {RESET_TR_NS}n "
        f"{BISECT_EVALUATE_NS}n {period_ns}n)",
        f"Vinp VINP 0 dc {VCM + vindiff_v / 2}",
        f"Vinn VINN 0 dc {VCM - vindiff_v / 2}",
        "",
        _dut_lines(),
        "",
        ".control",
        f"tran 0.005n {RESET_NS + RESET_TR_NS + BISECT_EVALUATE_NS}n",
        f"wrdata {log_name}.csv v(OUTP) v(OUTN)",
        ".endc",
        ".end",
    ]
    return "\n".join(lines) + "\n"


@dataclass
class OffsetBisectResult:
    corner: str
    temp_c: float
    wrong_edge_bracket: tuple[float, float]  # (last wrong-polarity probe, first probe past it)
    resolved_edge_bracket: tuple[float, float]  # (last probe below it, first resolved probe)
    converged: bool
    probes: list[tuple[float, str]]  # every probe, in order: (vindiff, outcome)
    solver_floor_hit: bool = False  # an edge stopped at the solver-budget metastability floor
    logs: dict[str, str] = field(default_factory=dict)

    @property
    def wrong_edge_mv(self) -> float:
        lo, hi = self.wrong_edge_bracket
        return (lo + hi) / 2

    @property
    def resolved_edge_mv(self) -> float:
        lo, hi = self.resolved_edge_bracket
        return (lo + hi) / 2

    @property
    def band_mv(self) -> float:
        """The measured NON-DECISION band width: the gap between the
        wrong-polarity edge and the resolved edge. ~0 (<= tolerance) means
        a single decision flip; a larger value means vindiffs in between
        produce no decision at all inside the evaluate window."""
        return self.resolved_edge_mv - self.wrong_edge_mv

    @property
    def flip_mv(self) -> float:
        """The decision-flip vindiff when `band_mv` is ~0 (the
        wrong-polarity/resolved edges coincide); otherwise the midpoint of
        the non-decision band, which is NOT a flip -- see `band_mv`."""
        return (self.wrong_edge_mv + self.resolved_edge_mv) / 2


def run_offset_bisect(
    corner: str = "tt", temp_c: float = 27.0, quiet: bool = False,
    bracket_start_mv: float = BISECT_BRACKET_START_MV,
) -> OffsetBisectResult:
    """Bisect the wrong-polarity and resolved decision boundaries.

    Probes are strictly sequential (each midpoint depends on the previous
    classification), so unlike `regen` there is no `jobs` parameter -- a
    parallel batch here would be a different (gradient/interpolation)
    measurement, not a bisection."""
    info = pdk.resolve_or_raise()
    evaluate_start_ns = RESET_NS + RESET_TR_NS
    probes: list[tuple[float, str]] = []
    logs: dict[str, str] = {}

    def classify(vindiff_mv: float) -> str:
        name = _bisect_probe_name(vindiff_mv)
        deck = _offset_bisect_deck(info, corner, temp_c, vindiff_mv, name)
        try:
            probe_logs = _shared._run_many([(name, deck)], scratch_dir, 1)
        except RuntimeError as exc:
            # A solver BUDGET timeout is not a circuit outcome -- it means
            # this probe sits so close to the decision boundary that the
            # numerically metastable latch makes ngspice's step control
            # crawl (the same probes decide in ~5 ns of simulated time
            # when they decide at all). Surface it as its own outcome so
            # the edge bisection can stop at the measured floor instead of
            # fabricating a crossing. Any other failure (nonzero ngspice
            # exit, missing PDK) is a real error and propagates.
            if "timed out" in str(exc):
                outcome = "timeout"
                probes.append((vindiff_mv, outcome))
                if not quiet:
                    print(
                        f"  probe vindiff={vindiff_mv:+.4f}mV -> TIMEOUT "
                        f"(solver budget exhausted; near-boundary "
                        f"metastability)"
                    )
                return outcome
            raise
        logs.update(probe_logs)
        t, outp, outn = toolchain.read_wrdata_csv(scratch_dir / f"{name}.csv", 2)
        outcome, cross_ns = _classify_decision(
            t, outp, outn, evaluate_start_ns, expected_sign=+1.0,
        )
        probes.append((vindiff_mv, outcome))
        if not quiet:
            if outcome == "resolved":
                shown = f"RESOLVED (crossing at {cross_ns:.4f}ns)"
            elif outcome == "wrong-polarity":
                shown = f"WRONG-POLARITY (opposite-sign crossing at {cross_ns:.4f}ns)"
            else:
                shown = "NON-DECISION (no crossing within the window)"
            print(f"  probe vindiff={vindiff_mv:+.4f}mV -> {shown}")
        return outcome

    def bisect_edge(
        lo: float, hi: float, boundary_outcome: str, outcome_owns_low: bool,
    ) -> tuple[float, float]:
        """Bisect one decision boundary. `outcome_owns_low=True` names the
        outcome owning the LOW side of the boundary (probes classifying it
        move `lo` up; every other outcome -- resolved or a non-decision --
        moves `hi` down): the wrong-polarity edge. `outcome_owns_low=False`
        names the outcome owning the HIGH side (probes classifying it move
        `hi` down; every other outcome moves `lo` up): the resolved edge.
        Either way every probe moves exactly one bracket edge, so the loop
        terminates regardless of which three-way outcomes the DUT
        produces -- except a solver-budget TIMEOUT, which stops the edge
        where it stands: such a probe is by construction essentially at
        the boundary, and pushing finer would only burn the budget again."""
        guard = 0
        timed_out = False
        while (hi - lo) > BISECT_TOL_MV:
            guard += 1
            if guard > BISECT_MAX_MIDPOINT_PROBES:
                raise RuntimeError(
                    f"offset-bisect exceeded {BISECT_MAX_MIDPOINT_PROBES} "
                    f"midpoint probes on one edge without closing the "
                    f"bracket to {BISECT_TOL_MV}mV -- outcomes are not "
                    f"monotone in vindiff, which a deterministic "
                    f"comparator cannot produce"
                )
            mid = (lo + hi) / 2
            outcome = classify(mid)
            if outcome == "timeout":
                timed_out = True
                break
            if (outcome == boundary_outcome) == outcome_owns_low:
                lo = mid
            else:
                hi = mid
        return (lo, hi), timed_out

    with tempfile.TemporaryDirectory(prefix="comparator-decision-bisect-") as scratch:
        scratch_dir = Path(scratch)

        lo_anchor, hi_anchor = -bracket_start_mv, bracket_start_mv
        lo_out = classify(lo_anchor)
        while lo_out != "wrong-polarity":
            if -lo_anchor >= BISECT_BRACKET_MAX_MV:
                raise RuntimeError(
                    f"offset-bisect could not bracket the decision flip at "
                    f"{corner}/{temp_c}C: vindiff={lo_anchor}mV still "
                    f"decides {lo_out!r} at the bracket ceiling "
                    f"-{BISECT_BRACKET_MAX_MV}mV"
                )
            lo_anchor *= 2
            lo_out = classify(lo_anchor)
        hi_out = classify(hi_anchor)
        while hi_out != "resolved":
            if hi_anchor >= BISECT_BRACKET_MAX_MV:
                raise RuntimeError(
                    f"offset-bisect could not bracket the decision flip at "
                    f"{corner}/{temp_c}C: vindiff={hi_anchor}mV still "
                    f"decides {hi_out!r} at the bracket ceiling "
                    f"+{BISECT_BRACKET_MAX_MV}mV"
                )
            hi_anchor *= 2
            hi_out = classify(hi_anchor)

        wrong_edge, wrong_stopped = bisect_edge(
            lo_anchor, hi_anchor, "wrong-polarity", outcome_owns_low=True
        )
        resolved_edge, resolved_stopped = bisect_edge(
            lo_anchor, hi_anchor, "resolved", outcome_owns_low=False
        )

    return OffsetBisectResult(
        corner=corner, temp_c=temp_c,
        wrong_edge_bracket=wrong_edge, resolved_edge_bracket=resolved_edge,
        converged=(
            (wrong_edge[1] - wrong_edge[0]) <= BISECT_TOL_MV
            and (resolved_edge[1] - resolved_edge[0]) <= BISECT_TOL_MV
            and not (wrong_stopped or resolved_stopped)
        ),
        solver_floor_hit=bool(wrong_stopped or resolved_stopped),
        probes=probes, logs=logs,
    )


def write_offset_bisect_evidence(
    result: OffsetBisectResult, note: str = "", supersedes: str = "",
) -> Path:
    info, record_id, netlist_sha, record_path, corners_dir = _begin_dut_record("corners")
    for name, log_text in result.logs.items():
        evidence.write_new_text(corners_dir / f"{name}.log", log_text)

    lines: list[str] = []
    a = lines.append
    a(f"# Record {record_id}")
    a("")
    a(f"- **Record ID**: {record_id}")
    a(CLAIM_TEXT)
    a(netlist_provenance())
    a(
        f"- **Corner matrix run**: process=['{result.corner}'], "
        f"temperature_c=[{result.temp_c}], supply_v=[{VDD}] (1 PVT point -- "
        "**subset-corner justification**: single-point characterization of "
        "this repo's own design at the stated corner, per issue #24's "
        "acceptance criteria; a full ratified PVT corner sweep and Monte "
        "Carlo campaign remain open work, blocked on the top-level README "
        "target-spec table's ratification -- see issue #3 item 5 and "
        "DR-001's 'A full PVT sweep' open item)"
    )
    a(
        f"- **Stimulus**: single reset({RESET_NS}ns, CLK=0)->evaluate"
        f"(CLK={VDD}V) edge per probe (not a repeating clock); decision "
        f"threshold |v(outp)-v(outn)| > {DECIDE_THRESHOLD_V}V (0.5*VDD), "
        "BOTH signs classified; evaluate window "
        f"{BISECT_EVALUATE_NS}ns; Vcm={VCM}V; bisection tolerance "
        f"{BISECT_TOL_MV} mV"
    )
    if note:
        a(f"- **Note**: {note}")
    if result.band_mv <= BISECT_TOL_MV:
        a(
            f"- **Overall**: decision flip at vindiff = **{result.flip_mv:+.4f} mV** "
            f"(wrong-polarity edge bracket "
            f"[{result.wrong_edge_bracket[0]:+.4f}, {result.wrong_edge_bracket[1]:+.4f}], "
            f"resolved edge bracket "
            f"[{result.resolved_edge_bracket[0]:+.4f}, {result.resolved_edge_bracket[1]:+.4f}], "
            f"{len(result.probes)} probes, tolerance {BISECT_TOL_MV} mV). Sign "
            "convention: the comparator decides correctly for a POSITIVE "
            "differential input only when that input exceeds the flip -- it "
            "behaves as though an error of -(flip) were added to the applied "
            "differential input. This is the DECISION-REFERRED systematic "
            "input offset (issue #66): a quantity the pick-off `offset` "
            "sub-command's sigma statistic does not express, measured at "
            f"the decision itself rather than read off a {PICKOFF_NS}ns "
            "pick-off."
        )
    else:
        a(
            f"- **Overall**: **no single decision flip exists at this corner** "
            f"-- a measured NON-DECISION band "
            f"**[{result.wrong_edge_mv:+.4f}, {result.resolved_edge_mv:+.4f}] mV** "
            f"(width {result.band_mv:.4f} mV) separates the wrong-polarity "
            f"region below it from the correctly-resolved region above it: "
            f"for any vindiff inside the band, NEITHER output sign crosses "
            f"the {DECIDE_THRESHOLD_V}V threshold within the "
            f"{BISECT_EVALUATE_NS}ns evaluate window. The wrong-polarity "
            f"edge brackets to "
            f"[{result.wrong_edge_bracket[0]:+.4f}, {result.wrong_edge_bracket[1]:+.4f}] "
            f"and the resolved edge to "
            f"[{result.resolved_edge_bracket[0]:+.4f}, {result.resolved_edge_bracket[1]:+.4f}] "
            f"({len(result.probes)} probes, tolerance {BISECT_TOL_MV} mV). "
            "A decision-referred OFFSET is therefore not the right model "
            "for this corner's sub-band behavior: an offset predicts "
            "wrong-polarity decisions, and those stop "
            f"{result.wrong_edge_mv:+.4f} mV below the first vindiff that "
            "decides anything at all."
        )
    if result.solver_floor_hit:
        a(
            f"- **Solver metastability floor**: at least one probe exhausted "
            f"the ngspice wall-clock budget without finishing the window "
            f"(a numerically balanced latch makes the solver's step "
            f"control crawl). The edge bisection(s) stopped at the floor "
            f"rather than fabricating a crossing for that probe, so the "
            f"bracket widths above -- not the {BISECT_TOL_MV} mV tolerance "
            f"-- are this record's actual resolution. Raising "
            f"SIM_NGSPICE_TIMEOUT_S tightens it at wall-clock cost."
        )
    a("")
    a("## Bisection probe trace")
    a("")
    a("| vindiff (mV) | decision |")
    a("|---|---|")
    for vindiff_mv, outcome in result.probes:
        a(f"| {vindiff_mv:+.4f} | {outcome} |")
    a("")
    lines.extend(post_layout_delta_lines(
        "offset-bisect", result.corner, result.temp_c, result.flip_mv))
    a("")
    return _finalize_record(
        lines, record_path, info, netlist_sha, "offset-bisect",
        supersedes=supersedes,
    )
