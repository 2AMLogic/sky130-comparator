"""`kickback`: input-node disturbance from the comparator's own regeneration.

Measured through an explicit source impedance (issue #26).

One of the seven experiment modules `run.py` drives; see its docstring for the
experiment as a whole and `_shared.py` for the preamble they share. Moved here
verbatim from run.py by issue #224.
"""

from __future__ import annotations

import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

_EXPERIMENT_DIR = str(Path(__file__).resolve().parent)
if _EXPERIMENT_DIR not in sys.path:
    # Siblings of a path-loaded module under a hyphenated directory name: see
    # _shared.py's docstring for why this is how they reach each other.
    sys.path.insert(0, _EXPERIMENT_DIR)

import _shared  # noqa: E402  -- `_shared._run{,_many}` are patch seams
from _shared import (  # noqa: E402
    CLAIM_TEXT,
    RESET_NS,
    RESET_TR_NS,
    VCM,
    VDD,
    _begin_dut_record,
    _dut_lines,
    _finalize_record,
    kickback_subset_justification,
    netlist_provenance,
    post_layout_delta_lines,
)
from regen import (  # noqa: E402
    EVALUATE_NS,
)
from harness import evidence, pdk, toolchain  # noqa: E402


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
        kb_logs = _shared._run_many(kb_jobs, scratch_dir, jobs)
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
    info, record_id, netlist_sha, record_path, corners_dir = _begin_dut_record("corners")
    for p in points:
        evidence.write_new_text(corners_dir / f"kickback_{p.variant}.log", p.log_text)

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
        lines, record_path, info, netlist_sha, "kickback", supersedes=supersedes,
    )
