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
regen/offset/noise MEASUREMENT METHODOLOGY (in the sibling modules listed
below) is ported from
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
loop-broken sub-model (see noise.py). This driver still
follows sim/README.md's directory convention (testbench/, netlist-snapshots/,
corners/, mc-draws/, records/) and reuses sim/harness/{pdk,toolchain,
evidence,corners}.py directly for PDK resolution, the ngspice invocation +
timeout, and the evidence-record scaffolding (record IDs, netlist SHA-256,
git/environment block) -- so records from this experiment are directly
comparable in format to every other record under sim/.

Module layout (issue #224 split this driver into sibling modules; this module
is the CLI over them):

    _shared.py     DUT-provenance switch, fragment parsing, testbench
                   constants, record preamble/baselines, the ngspice seams
                   and the evidence-record head/tail
    regen.py       `regen`
    offset.py      `offset` and `offset-bisect`
    noise.py       `noise`
    noise_tran.py  `noise-tran`, and its chunked/resumable campaign driver
    reset.py       `reset`
    kickback.py    `kickback`

They are reached through sys.path, not as a package -- this directory's
hyphenated name is not a legal package name, so this file is loaded by path.
_shared.py's docstring documents that convention and the one monkeypatch seam
it establishes.
"""

from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

_EXPERIMENT_DIR = str(Path(__file__).resolve().parent)
if _EXPERIMENT_DIR not in sys.path:
    # Siblings of a path-loaded module under a hyphenated directory name: see
    # _shared.py's docstring for why this is how they reach each other.
    sys.path.insert(0, _EXPERIMENT_DIR)

import _shared  # noqa: E402
import regen  # noqa: E402
import offset  # noqa: E402
import noise  # noqa: E402
import noise_tran  # noqa: E402
import reset  # noqa: E402
import kickback  # noqa: E402
# `pdk` is not used in this module: it is here for the re-export surface
# below. Every module in this directory resolves the PDK through this one
# module object, so patching `run.py`'s `pdk` attribute does reach them all.
from harness import pdk, toolchain  # noqa: E402,F401

# --- Compatibility re-exports (issue #224).
#
# The sibling modules above own this driver's implementation. Every name the
# unit suite reads off this module is re-bound here, so `run.py` keeps the flat
# attribute surface it had before the split and
# sim/tests/test_comparator_decision.py's assertions carry over unchanged.
#
# THIS IS A READ-ONLY SURFACE. Assigning to a name here rebinds it on THIS
# module only and does NOT reach the sibling that owns it, so a monkeypatch
# must target `<module>.<name>` -- which is why the ngspice seams
# (`_shared._run`, `_shared._run_many`) and the runners `noise.run_noise` /
# `noise_tran.run_latch_noise` / `noise_tran.run_trnoise_calibration` are
# deliberately absent below, rather than re-exported as traps. `main()` below
# likewise dispatches through the owning module, not through these names, so
# one patch of a sibling reaches both the CLI and the sibling's own callers.
from _shared import (  # noqa: E402,F401
    DECIDE_THRESHOLD_V,
    DUT_FRAGMENT,
    EXPERIMENT_DIR,
    GRADED_CORNERS,
    NOISE_FSTART_HZ,
    NOISE_FSTOP_HZ,
    OFFSET_GRADED_CORNERS,
    PEX_FRAGMENT,
    PEX_LATCH_FRAGMENT,
    PEX_PREAMP_FRAGMENT,
    PICKOFF_NS,
    RESET_GND_TIE_MOVES,
    RESET_NS,
    RESET_TR_NS,
    SCHEMATIC_BASELINES,
    STEERING_GATE_INJECTION,
    VCM,
    _dut_device_line,
    _dut_devices,
    _dut_fragment,
    _dut_lines,
    _instance_names,
    _parse_devices,
    _retie_star_legs,
    baseline_for,
    dut_provenance,
    kickback_subset_justification,
    post_layout_delta_lines,
    set_dut_provenance,
)
from regen import (  # noqa: E402,F401
    EVALUATE_NS,
    _classify_decision,
    _regen_deck,
    run_regen_sweep,
)
from offset import (  # noqa: E402,F401
    BISECT_EVALUATE_NS,
    BISECT_TOL_MV,
    PICKOFF_TSTOP_NS,
    VINDIFF_GAIN_CAL_MV,
    _bisect_probe_mv,
    _bisect_probe_name,
    _offset_bisect_deck,
    _pickoff_deck,
    run_offset_bisect,
)
from noise import (  # noqa: E402,F401
    NoiseResult,
    _noise_deck,
)
from noise_tran import (  # noqa: E402,F401
    LATCH_NOISE_CL_FF,
    LatchNoiseResult,
    NOISE_TRAN_DECIDE_PAIRS,
    NOISE_TRAN_EVALUATE_NS,
    NOISE_TRAN_INCOMPLETE_EXIT,
    NoiseTranCampaignIncomplete,
    NoiseTranResult,
    _latch_noise_deck,
    _noise_tran_decision_deck,
    _noise_tran_dut_block,
    _noise_tran_pickoff_deck,
    degenerate_cross_check_reason,
    pair_sigma_mv,
    run_noise_tran,
    two_statistics_line,
)
from reset import (  # noqa: E402,F401
    _reset_device_block,
)
from kickback import (  # noqa: E402,F401
    KICKBACK_RS_OHM,
    KickbackPoint,
    _kickback_deck,
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="comparator-decision standalone testbench driver (issue #9)")
    ap.add_argument(
        "mode", nargs="?", choices=["regen", "offset", "offset-bisect", "noise", "noise-tran", "reset", "kickback"],
        help="which characterization to run",
    )
    ap.add_argument("--check-env", action="store_true", help="check toolchain + PDK, print summary, exit")
    ap.add_argument("--corner", default="tt")
    ap.add_argument("--temp", type=float, default=27.0)
    ap.add_argument("--seed", type=int, default=1, help="offset: MC base seed")
    ap.add_argument("--n", type=int, default=16, help="offset / noise-tran: MC sample count")
    ap.add_argument(
        "--seeds-per-point", type=int, default=noise_tran.NOISE_TRAN_SEEDS_PER_POINT,
        help="noise-tran: seeds per sign per decision-transition point "
        "(statistic (b)). The record states the value used, so a run that "
        "trades cross-check precision for wall clock says so on its face.",
    )
    ap.add_argument(
        "--resume-dir", default="",
        help="noise-tran: scratch directory for a CHUNKED, RESUMABLE campaign "
        "(issue #100). Each deck's derived value is persisted under it as that "
        "deck completes, and a re-invocation of the IDENTICAL command runs only "
        "the decks still missing. The record is written by whichever invocation "
        "completes the last deck; an incomplete campaign writes none. Required "
        "for --chunk-decks / --chunk-seconds.",
    )
    ap.add_argument(
        "--chunk-decks", type=int, default=None,
        help="noise-tran: stop this invocation cleanly after N campaign decks "
        "(needs --resume-dir). N counts EVERY deck this invocation dispatches -- "
        "the same all-deck 'campaign decks' count the stop message reports -- so "
        "the four gain-calibration decks are included: on a fresh campaign a "
        "budget of N reaches N-4 Monte Carlo decks, and any N<=4 reaches none. "
        "Use it to keep each command inside this host's "
        "~60-minute wall-clock ceiling; exit status "
        f"{noise_tran.NOISE_TRAN_INCOMPLETE_EXIT} means 'incomplete, resumable, no record'.",
    )
    ap.add_argument(
        "--chunk-seconds", type=float, default=None,
        help="noise-tran: stop this invocation cleanly once it has been running "
        "this long, checked between decks (needs --resume-dir). The wall-clock "
        "form of --chunk-decks, and the one that actually matches the ceiling "
        "given the measured 35-285 s per-deck spread; the clock starts at "
        "campaign setup, so it covers the AC/calibration preamble too.",
    )
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
        "--dut", choices=_shared.DUT_PROVENANCES, default="schematic",
        help="which DUT netlist to simulate: `schematic` (the default -- "
        "design/comparator.sch via testbench/comparator_core.spice) or "
        "`extracted` (post-layout, parasitics-included -- "
        "layout/comparator.pex.spice, generated by layout/extract_pex.py "
        "from layout/comparator.gds). Issue #57 / T1 item 7; `reset` and "
        "`noise-tran` gained their post-layout deck form in issue #65 and "
        "`offset-bisect` was added with one in issue #66, so all seven "
        "sub-commands support both provenances.",
    )
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    _shared.set_dut_provenance(args.dut)

    if args.check_env:
        # allow_drift=False deliberately: this driver writes evidence records,
        # so a drifted pin must stay fatal here. It has no
        # --allow-toolchain-drift flag (issue #108, out of scope).
        return toolchain.report_env()

    if not args.mode:
        ap.print_help()
        return 2

    chunk_flags = [
        name for name, given in (
            ("--resume-dir", bool(args.resume_dir)),
            ("--chunk-decks", args.chunk_decks is not None),
            ("--chunk-seconds", args.chunk_seconds is not None),
        ) if given
    ]
    if chunk_flags and args.mode != "noise-tran":
        # Refused rather than ignored: silently dropping a resume flag would
        # make a long campaign look resumable when nothing was persisted.
        ap.error(
            f"{', '.join(chunk_flags)} only appl{'y' if len(chunk_flags) > 1 else 'ies'} "
            f"to `noise-tran` (issue #100), not `{args.mode}`"
        )
    if (args.chunk_decks is not None or args.chunk_seconds is not None) and not args.resume_dir:
        ap.error("--chunk-decks / --chunk-seconds need --resume-dir to persist into")

    if args.mode == "regen":
        points = regen.run_regen_sweep(corner=args.corner, temp_c=args.temp, quiet=args.quiet, jobs=args.jobs)
        if args.record:
            path = regen.write_regen_evidence(points, args.corner, args.temp, note=args.note, supersedes=args.supersedes)
            print(f"wrote {path}")
        unresolved = [p for p in points if p.regen_time_ns is None]
        return 0 if not unresolved else 1

    if args.mode == "offset":
        result = offset.run_offset_mc(
            corner=args.corner, temp_c=args.temp, seed=args.seed, n=args.n,
            quiet=args.quiet, jobs=args.jobs,
        )
        if args.record:
            path = offset.write_offset_evidence(result, note=args.note, supersedes=args.supersedes)
            print(f"wrote {path}")
        negctrl_stdev = statistics.pstdev(result.negctrl_offset_v) if len(result.negctrl_offset_v) > 1 else 0.0
        draws_stdev = statistics.pstdev(result.draws_offset_v) if len(result.draws_offset_v) > 1 else 0.0
        return 0 if (negctrl_stdev == 0.0 and draws_stdev > 0) else 1

    if args.mode == "offset-bisect":
        result = offset.run_offset_bisect(corner=args.corner, temp_c=args.temp, quiet=args.quiet)
        if args.record:
            path = offset.write_offset_bisect_evidence(result, note=args.note, supersedes=args.supersedes)
            print(f"wrote {path}")
        return 0 if result.converged else 1

    if args.mode == "noise":
        result = noise.run_noise(corner=args.corner, temp_c=args.temp, quiet=args.quiet)
        if args.record:
            path = noise.write_noise_evidence(result, note=args.note, supersedes=args.supersedes)
            print(f"wrote {path}")
        return 0

    if args.mode == "noise-tran":
        try:
            result = noise_tran.run_noise_tran(
                corner=args.corner, temp_c=args.temp, n_pickoff=args.n,
                seeds_per_point=args.seeds_per_point,
                quiet=args.quiet, jobs=args.jobs,
                resume_dir=Path(args.resume_dir) if args.resume_dir else None,
                chunk_decks=args.chunk_decks, chunk_seconds=args.chunk_seconds,
            )
        except noise_tran.NoiseTranCampaignIncomplete as incomplete:
            # Deliberately NOT a failure: the chunk did exactly what it was
            # asked to. Nothing is written, so `--record` cannot have fired.
            print(str(incomplete))
            return noise_tran.NOISE_TRAN_INCOMPLETE_EXIT
        if args.record:
            path = noise_tran.write_noise_tran_evidence(result, note=args.note, supersedes=args.supersedes)
            print(f"wrote {path}")
        return 0 if result.sigma_pickoff_mv == result.sigma_pickoff_mv else 1

    if args.mode == "reset":
        points = reset.run_reset_check(quiet=args.quiet)
        if args.record:
            path = reset.write_reset_evidence(points, note=args.note, supersedes=args.supersedes)
            print(f"wrote {path}")
        return 0 if all(p.ok for p in points) else 1

    if args.mode == "kickback":
        points = kickback.run_kickback(corner=args.corner, temp_c=args.temp, quiet=args.quiet, jobs=args.jobs)
        if args.record:
            path = kickback.write_kickback_evidence(points, note=args.note, supersedes=args.supersedes)
            print(f"wrote {path}")
        return 0 if all(p.ok for p in points) else 1

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
