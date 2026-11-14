"""`reset`: reset-integrity negative control (issue #24).

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
    RESET_GND_TIE_MOVES,
    RESET_SCHEMATIC_COUNTERPART,
    VCM,
    VDD,
    _begin_dut_record,
    _dut_device_line,
    _dut_devices,
    _dut_lines,
    _finalize_record,
    _retie_star_legs,
    netlist_provenance,
)
from harness import evidence, pdk, toolchain  # noqa: E402


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

    On the POST-LAYOUT fragment (issue #65) the same counterfactual is made
    by RULE 2 of _shared.py's POST-LAYOUT DECK SURGERY note: each steering
    device's source star leg is re-pointed from the TAIL2 hub to GND, the
    device lines and every parasitic value left exactly as extracted. The
    schematic branch below is untouched, so the schematic-level deck text
    stays byte-identical to the one that produced the committed
    schematic-level reset records.
    """
    if variant == "as-drawn":
        return _dut_lines()
    if variant != "gnd-tied":
        raise ValueError(f"unknown reset variant {variant!r}")
    if _shared.dut_provenance() == "extracted":
        return _retie_star_legs(_dut_lines(), RESET_GND_TIE_MOVES)
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
                log_text = _shared._run(deck, scratch_dir, log_name)
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
    info, record_id, netlist_sha, record_path, corners_dir = _begin_dut_record("corners")
    for p in points:
        safe = f"{p.variant.replace('-', '_')}_{p.corner}_{str(p.temp_c).replace('-', 'neg').replace('.', 'p')}c"
        evidence.write_new_text(corners_dir / f"reset_{safe}.log", p.log_text)

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
    if _shared.dut_provenance() == "extracted":
        a(
            "- **How the counterfactual is made post-layout** (issue #65): on "
            "the extracted netlist no terminal sits on the logical node -- "
            "each steering device's source sits on its own parasitic star leg "
            "(`TAIL2__t1`, `TAIL2__t2`) tied to the `TAIL2` hub through that "
            "terminal's share of the net's series resistance. The "
            "counterfactual therefore RE-POINTS each of those two star-leg "
            "resistors from `TAIL2` to `GND` (310.07 ohm each, value "
            "unchanged) and edits nothing else: the device lines, every other "
            "parasitic R and C, and every extracted parameter are byte-"
            "identical to the `as-drawn` fragment, so the two decks differ by "
            "exactly two tokens. The leg travels WITH the terminal, which is "
            "what keeps the moved terminal's own extracted resistance in the "
            "circuit instead of deleting it and leaves no star leg stranded "
            "on a one-connection node. Convention for split devices (a "
            "schematic device the layout draws as several parallel fingers): "
            "all of its fingers are moved together. It is not exercised here "
            "-- the steering pair is drawn as ONE W=8 device each "
            "(`XM_STN_P`/`XM_STN_N`, no `__a`/`__b` split); the split devices "
            "on this layout are the W=13 input pair, which this "
            "counterfactual does not touch."
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
    if _shared.dut_provenance() == "extracted":
        a("## Post-layout delta vs. the schematic-level record")
        a("")
        a(
            f"- **Schematic-level counterpart record**: "
            f"`sim/comparator-decision/records/{RESET_SCHEMATIC_COUNTERPART}.md` "
            "(same five corners, same two variants, same four criteria)."
        )
        a(
            "- **What differs between the two runs**: the DUT fragment, and "
            "nothing else. Same sub-command, same corner matrix, same "
            "stimulus and initial conditions, same tolerances, same deck "
            "template -- the schematic-side deck text is byte-identical to "
            "the one that produced the counterpart record."
        )
        a(
            "- **Why this record has no numeric delta table**: `reset` is a "
            "four-criterion pass/fail screen with a paired positive control, "
            "not a scalar measurement. The delta that matters is whether the "
            "VERDICTS survive the parasitics, so it is stated as verdicts "
            "below, with the one genuinely continuous column (supply "
            "current) quoted alongside its schematic-level range."
        )
        a("")
        a("| Variant | Post-layout verdict | Schematic-level verdict |")
        a("|---|---|---|")
        a(
            f"| `as-drawn` (negative control) | "
            f"{sum(1 for p in as_drawn if p.holds_reset)}/{len(as_drawn)} "
            f"corners hold reset | 5/5 corners hold reset |"
        )
        a(
            f"| `gnd-tied` (positive control) | "
            f"{sum(1 for p in control if not p.holds_reset)}/{len(control)} "
            f"corners break reset | 5/5 corners break reset |"
        )
        a("")
        if as_drawn and control:
            a(
                f"- **Supply current**: worst |I(VDD)| over the settle window "
                f"is {min(p.max_abs_idd_a for p in as_drawn):.4g}-"
                f"{max(p.max_abs_idd_a for p in as_drawn):.4g} A as-drawn "
                f"(schematic-level 4.228e-05-6.756e-05 A) against "
                f"{min(p.max_abs_idd_a for p in control):.4g}-"
                f"{max(p.max_abs_idd_a for p in control):.4g} A for the "
                f"positive control (schematic-level 8.376e-04-1.056e-03 A). "
                f"The separation between the two variants, not the absolute "
                f"level, is what criterion (4) rests on."
            )
        a(
            "- **The point of running this post-layout at all**: `reset` is "
            "the screen for a latch whose reset state is not a stable, "
            "non-conducting equilibrium, and layout parasitics are exactly "
            "the class of asymmetry such a screen exists to catch. Until "
            "this record it had only ever been run against a netlist that is "
            "symmetric by construction."
        )
        a("")
    return _finalize_record(
        lines, record_path, info, netlist_sha, "reset", supersedes=supersedes,
    )
