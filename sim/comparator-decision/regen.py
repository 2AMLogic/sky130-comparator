"""`regen`: regeneration time vs. differential input (deterministic sweep).

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
    DECIDE_THRESHOLD_V,
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
from harness import evidence, pdk, toolchain  # noqa: E402


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
    # Issue #66: the three-way outcome the sign-corrected criterion used to
    # collapse into one "UNRESOLVED". "resolved" keeps regen_time_ns's old
    # meaning exactly; the two new labels carry the crossing time of the
    # opposite-sign crossing ("wrong-polarity") or None ("non-decision").
    outcome: str = "resolved"


def _classify_decision(
    t: list[float], outp: list[float], outn: list[float],
    evaluate_start_ns: float, expected_sign: float,
) -> tuple[str, float | None]:
    """Classify one reset->evaluate transient's decision by checking BOTH
    signs of the output difference (issue #66).

    `regen`'s original criterion was sign-corrected -- `sign*(outp-outn) >
    DECIDE_THRESHOLD_V` -- so a decision that settled the WRONG way and a
    decision that never settled both read `UNRESOLVED`, and nothing could
    tell them apart. This helper keeps that crossing test as the
    "resolved" outcome (so every pre-#66 record's numbers keep their
    meaning) and adds the opposite-sign crossing as "wrong-polarity",
    leaving "non-decision" for a window in which neither sign crossed.

    Returns `(outcome, crossing_ns)` where `crossing_ns` is the
    evaluate-relative time at which the classified crossing occurred (for
    "wrong-polarity" that is the wrong-way crossing -- the evidence for
    the label), or None for a non-decision. Samples before
    `evaluate_start_ns` (the reset phase) are ignored, exactly as the old
    inline loop ignored them.
    """
    outcome = "non-decision"
    crossing_ns: float | None = None
    for i, tt in enumerate(t):
        if tt < evaluate_start_ns * 1e-9:
            continue
        diff = expected_sign * (outp[i] - outn[i])
        if diff > DECIDE_THRESHOLD_V:
            outcome = "resolved"
            crossing_ns = (tt - evaluate_start_ns * 1e-9) * 1e9
            break
        if -diff > DECIDE_THRESHOLD_V:
            outcome = "wrong-polarity"
            crossing_ns = (tt - evaluate_start_ns * 1e-9) * 1e9
            break
    return outcome, crossing_ns


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
        sweep_logs = _shared._run_many(sweep_jobs, scratch_dir, jobs)
        for vindiff_mv in vindiff_sweep_mv:
            log_name = f"regen_{vindiff_mv}mV".replace("-", "neg").replace(".", "p")
            log_text = sweep_logs[log_name]
            csv_path = scratch_dir / f"{log_name}.csv"
            t, clk, outp, outn = toolchain.read_wrdata_csv(csv_path, 3)
            sign = 1.0 if vindiff_mv >= 0 else -1.0
            outcome, regen_ns = _classify_decision(
                t, outp, outn, evaluate_start_ns, expected_sign=sign,
            )
            points.append(RegenPoint(
                vindiff_mv=vindiff_mv, regen_time_ns=regen_ns,
                log_text=log_text, outcome=outcome,
            ))
            if not quiet:
                if outcome == "resolved":
                    shown = f"regen_time={regen_ns:.4f}ns"
                elif outcome == "wrong-polarity":
                    shown = f"WRONG-POLARITY (opposite-sign crossing at {regen_ns:.4f}ns)"
                else:
                    shown = "NON-DECISION (no crossing within the evaluate window)"
                print(f"  vindiff={vindiff_mv:+.4f}mV -> {shown}")
    return points


def write_regen_evidence(
    points: list[RegenPoint], corner: str, temp_c: float,
    note: str = "", supersedes: str = "",
) -> Path:
    info, record_id, netlist_sha, record_path, corners_dir = _begin_dut_record("corners")
    for p in points:
        safe = f"{p.vindiff_mv}mV".replace("-", "neg").replace(".", "p")
        evidence.write_new_text(corners_dir / f"vindiff_{safe}.log", p.log_text)

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
        f"|v(outp)-v(outn)| > {DECIDE_THRESHOLD_V}V (0.5*VDD), BOTH signs "
        "classified (issue #66): `resolved` / `WRONG-POLARITY` (the "
        "opposite-sign crossing) / `NON-DECISION` (no crossing); "
        f"Vcm={VCM}V"
    )
    if note:
        a(f"- **Note**: {note}")
    unresolved = [p for p in points if p.outcome != "resolved"]
    wrong = [p for p in points if p.outcome == "wrong-polarity"]
    nondec = [p for p in points if p.outcome == "non-decision"]
    a(f"- **Overall**: {'PASS' if not unresolved else 'INCOMPLETE'} "
      f"({len(points) - len(unresolved)}/{len(points)} points resolved within the "
      f"{EVALUATE_NS}ns evaluate window; {len(wrong)} WRONG-POLARITY, "
      f"{len(nondec)} NON-DECISION)")
    a("")
    a("## Regeneration time vs. differential input")
    a("")
    a("| Vindiff (mV) | regen time (ns) | decision |")
    a("|---|---|---|")
    for p in sorted(points, key=lambda p: p.vindiff_mv):
        if p.outcome == "resolved":
            shown, label = f"{p.regen_time_ns:.4f}", "OK"
        elif p.outcome == "wrong-polarity":
            shown = f"{p.regen_time_ns:.4f} (opposite-sign crossing)"
            label = "WRONG-POLARITY"
        else:
            shown, label = "--", "NON-DECISION (no crossing within window)"
        a(f"| {p.vindiff_mv:+.2f} | {shown} | {label} |")
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
        lines, record_path, info, netlist_sha, "regen", supersedes=supersedes,
    )
