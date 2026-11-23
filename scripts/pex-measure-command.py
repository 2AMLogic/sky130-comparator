#!/usr/bin/env python3
"""`klt pex --measure-command` adapter for sim/comparator-decision (issue #187).

`klt pex` runs this command twice, appending the netlist under measurement as
the final argument and exporting KLT_PEX_SIDE=schematic|extracted. It prints
one measurement document on stdout:

    {"corners": [{"corner_id": ..., "measurements": [{name, value, status}]}]}

This wrapper measures nothing itself; it calls the existing
`sim/comparator-decision` runners (`regen`, `kickback`) and reshapes their
results. Rows emitted per graded corner (see `_shared.GRADED_CORNERS`):

  decision_time_50mV_ns   regen time at +50 mV overdrive (ns); null if the
                          point did not resolve (klt renders that `error`)
  kickback_loaded_peak_mV peak input-node disturbance, `loaded` variant (mV)

Offset sigma and regeneration-inclusive noise are NOT emitted: they are
Monte Carlo / chunked campaigns that cannot fit one `--measure-timeout-s`
invocation and belong on the batch route (sim/comparator-decision/README.md
-> "Supported execution route"). See manifests/README.md, item 7.

Netlist handling. The decision runners simulate committed flat fragments, not
an arbitrary file. So the netlist argument is checked, never silently ignored:
  * extracted side: must be byte-identical to `layout/comparator.extract.spice`
    (the extractor output the committed `comparator.pex*.spice` derive from);
    otherwise exit 3 -- run `layout/extract_pex.py` and commit first.
  * schematic side: must be byte-identical to
    `sim/comparator-decision/testbench/comparator_core.spice` (the flat device-card
    fragment the runners measure; it has no `.subckt`); otherwise exit 3, so
    the report's `reference_netlist` always describes the measured schematic leg.

Invoke as `python3 scripts/pex-measure-command.py` (klt runs the command
without a shell; the file is also executable).

Never launch this over many corners on a dispatch worker: use a single
`--corners` for a probe, and the batch route for the full set.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
EXPERIMENT_DIR = REPO_ROOT / "sim" / "comparator-decision"
RAW_EXTRACT = REPO_ROOT / "layout" / "comparator.extract.spice"
SCHEMATIC_FRAGMENT = EXPERIMENT_DIR / "testbench" / "comparator_core.spice"
OVERDRIVE_MV = 50.0

ROW_DECISION = "decision_time_50mV_ns"
ROW_KICKBACK = "kickback_loaded_peak_mV"


def corner_id(corner: str, temp_c: float, vdd: float) -> str:
    return f"{corner}/{vdd:.3f}V/{temp_c:g}C"


def parse_corners(spec: str, graded: tuple) -> list[tuple[str, float]]:
    if spec == "all":
        return list(graded)
    out = []
    for item in spec.split(","):
        name, _, temp = item.partition(":")
        if not name or not temp:
            raise ValueError(f"bad corner {item!r}; want <process>:<tempC> (e.g. tt:27)")
        out.append((name, float(temp)))
    if graded:
        bad = [c for c in out if c not in set(graded)]
        if bad:
            raise ValueError(f"corner(s) {bad} not in the graded set {list(graded)}")
    return out


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_netlist(side: str, netlist: Path) -> str | None:
    """Return an error message, or None when the netlist argument is acceptable."""
    if not netlist.is_file():
        return f"netlist {netlist} does not exist"
    if side == "extracted":
        if sha256(netlist) != sha256(RAW_EXTRACT):
            return (
                f"extracted netlist {netlist} differs from the committed "
                f"layout/comparator.extract.spice; the runners simulate the committed "
                f"comparator.pex*.spice fragments, so measuring would not describe this "
                f"extraction. Run `python3 layout/extract_pex.py` and commit, then retry."
            )
    elif side == "schematic":
        if sha256(netlist) != sha256(SCHEMATIC_FRAGMENT):
            return (
                f"schematic netlist {netlist} differs from the committed "
                f"sim/comparator-decision/testbench/comparator_core.spice that the "
                f"runners measure; the report's reference_netlist would not describe "
                f"the measured schematic leg. Pass that file as --reference-netlist."
            )
    else:
        return f"unknown KLT_PEX_SIDE {side!r}"
    return None


def load_driver():
    for p in (EXPERIMENT_DIR, REPO_ROOT / "sim"):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    import _shared  # noqa: E402
    import kickback  # noqa: E402
    import regen  # noqa: E402

    return _shared, regen, kickback


def measure_corner(regen, kickback, corner: str, temp_c: float) -> list[dict]:
    pts = regen.run_regen_sweep(
        corner=corner, temp_c=temp_c, vindiff_sweep_mv=[OVERDRIVE_MV], quiet=True
    )
    pt = pts[0]
    if pt.outcome == "resolved" and pt.regen_time_ns is not None:
        decision = {"name": ROW_DECISION, "value": pt.regen_time_ns}
    else:
        decision = {
            "name": ROW_DECISION,
            "value": None,
            "message": f"decision {pt.outcome} at {OVERDRIVE_MV:g} mV",
        }
    loaded = next(
        (p for p in kickback.run_kickback(corner=corner, temp_c=temp_c, quiet=True)
         if p.variant == "loaded"),
        None,
    )
    if loaded is None:
        raise RuntimeError(f"kickback returned no 'loaded' point at {corner}/{temp_c:g}C")
    kick = {"name": ROW_KICKBACK, "value": loaded.peak_dev_v * 1e3}
    return [decision, kick]


def build_document(measure, corners: list[tuple[str, float]], vdd: float) -> dict:
    return {
        "corners": [
            {"corner_id": corner_id(c, t, vdd), "measurements": measure(c, t)}
            for c, t in corners
        ]
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--corners", default="all",
                    help="'all' (the seven graded corners) or comma list like tt:27,ss:-40")
    ap.add_argument("netlist", type=Path)
    args = ap.parse_args(argv)

    side = os.environ.get("KLT_PEX_SIDE", "")
    err = check_netlist(side, args.netlist)
    if err:
        print(f"pex-measure-command: {err}", file=sys.stderr)
        return 3

    shared, regen, kickback = load_driver()
    try:
        corners = parse_corners(args.corners, shared.GRADED_CORNERS)
    except ValueError as e:
        print(f"pex-measure-command: {e}", file=sys.stderr)
        return 2
    shared.set_dut_provenance(side)
    doc = build_document(
        lambda c, t: measure_corner(regen, kickback, c, t), corners, shared.VDD)
    json.dump(doc, sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
