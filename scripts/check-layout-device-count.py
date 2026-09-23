#!/usr/bin/env python3
"""layout device-count CI gate (issue #44, T1 checklist item 2's evidence).

Re-runs the independent `klt extract` device-count assertion over the
committed `layout/comparator.gds`: the extraction must re-derive the
schematic's 16 devices counted by model from the *extracted netlist*
(9 `nfet_01v8` + 4 `pfet_01v8` + 3 `res_high_po`) -- never from the
generator's own parameters.  This is the CI-side twin of
`layout/gen_comparator.py` step 7 (which writes
`layout/extract-device-count.json` when regenerating); the two share one
parser/count logic by importing it from the generator, so they cannot drift.

Needs `klt` (klayout-tools, pinned in .github/workflows/t1-signoff.yml) and
a resolvable sky130A PDK install at the sim/pdk.json pin:

    python3 scripts/check-layout-device-count.py gate [--pdk-root ~/.volare]

`selftest` is hermetic (no klt, no PDK): it proves the counter accepts a
known-good fixture netlist and rejects two corrupted ones (a missing device
and an extra one) -- a count gate means nothing until "wrong count fails"
has been shown reachable on the same code path.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "layout"))

from gen_comparator import count_check, parse_extract_devices  # noqa: E402

GDS = "layout/comparator.gds"
TOP_CELL = "gen_compose_0"
PDK_VARIANT = "sky130A"

FIXTURE_GOOD = """
.SUBCKT t a b c
* two cross-quad legs per input device (parallel pairs), then 7 single-gate
* nfets, each on its own net set -- 9 logical nfet devices from 11 lines
X$1 n1 g1 s1 b1 sky130_fd_pr__nfet_01v8 L=0.5 W=6.5
X$7 n1 g1 s1 b1 sky130_fd_pr__nfet_01v8 L=0.5 W=6.5
X$2 n2 g2 s1 b1 sky130_fd_pr__nfet_01v8 L=0.5 W=6.5
X$8 n2 g2 s1 b1 sky130_fd_pr__nfet_01v8 L=0.5 W=6.5
X$3 n3 g2 s2 b1 sky130_fd_pr__nfet_01v8 L=0.5 W=8
X$4 n4 g2 b1 b1 sky130_fd_pr__nfet_01v8 L=0.5 W=40
X$5 n5 vdd b1 b1 sky130_fd_pr__nfet_01v8 L=0.5 W=0.8
X$6 n6 g3 b1 b1 sky130_fd_pr__nfet_01v8 L=0.5 W=8
X$9 n7 g1 s2 b1 sky130_fd_pr__nfet_01v8 L=0.5 W=8
X$10 n8 g3 b1 b1 sky130_fd_pr__nfet_01v8 L=0.5 W=20
X$11 n9 g1 b1 b1 sky130_fd_pr__nfet_01v8 L=0.5 W=40
X$12 p1 p2 vdd vdd sky130_fd_pr__pfet_01v8 L=0.5 W=16
X$13 p1 g3 vdd vdd sky130_fd_pr__pfet_01v8 L=0.5 W=8
X$14 p3 g3 vdd vdd sky130_fd_pr__pfet_01v8 L=0.5 W=8
X$15 p3 p1 vdd vdd sky130_fd_pr__pfet_01v8 L=0.5 W=16
X$16 g3 clk b1 sky130_fd_pr__res_high_po l=1.75 w=0.42
X$17 n1 vdd b1 sky130_fd_pr__res_high_po l=22 w=0.42
X$18 vdd n2 b1 sky130_fd_pr__res_high_po l=22 w=0.42
.ENDS
"""


def selftest() -> int:
    """The counter must accept the fixture and reject corrupted variants."""
    ok = True

    def verdict(text: str, expect_pass: bool, label: str) -> None:
        nonlocal ok
        _raw, merged = parse_extract_devices(text)
        passed, _tally = count_check(merged)
        if passed != expect_pass:
            print(f"selftest: FAIL: {label} (expected "
                  f"{'pass' if expect_pass else 'reject'}, got "
                  f"{'pass' if passed else 'reject'})")
            ok = False
        else:
            print(f"selftest: ok: {label}")

    verdict(FIXTURE_GOOD, True, "known-good 16-device netlist passes")
    verdict(FIXTURE_GOOD.replace("X$9 n7 g1 s2 b1", "X$9 n3 g2 s2 b1", 1),
            False, "a topologically-distinct device absorbed into another "
            "net set is hidden by the parallel merge (8 nfet groups rejects)")
    verdict(FIXTURE_GOOD
            + "X$19 n10 g4 b1 b1 sky130_fd_pr__nfet_01v8 L=0.5 W=1\n",
            False, "an extra 17th device rejects")
    print("gate: selftest: PASS" if ok else "gate: selftest: FAIL")
    return 0 if ok else 1


def gate(klt: str, pdk_root: Path) -> int:
    gds = REPO_ROOT / GDS
    if not gds.exists():
        print(f"gate: FAIL: {GDS} does not exist", file=sys.stderr)
        return 1
    with tempfile.TemporaryDirectory(prefix="layout-device-count-") as tmp:
        out = Path(tmp) / "extract.spice"
        cmd = [klt, "extract", str(gds), "--deck", "sky130", "--top", TOP_CELL,
               "--pdk", PDK_VARIANT, "--pdk-root", str(pdk_root),
               "-o", str(out), "--format", "json"]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            print(f"gate: FAIL: klt extract failed (rc={r.returncode}):\n"
                  f"{r.stdout}\n{r.stderr}", file=sys.stderr)
            return 1
        raw, merged = parse_extract_devices(out.read_text())
        passed, tally = count_check(merged)
        evidence = {
            "command": "scripts/check-layout-device-count.py gate",
            "raw_counts": dict(sorted(raw.items())),
            "merged_counts": dict(sorted(merged.items())),
            "check": tally,
            "pass": passed,
        }
        print("gate: " + json.dumps(evidence["merged_counts"]))
        if not passed:
            print(f"gate: FAIL: device count check failed:\n"
                  f"{json.dumps(tally, indent=2)}", file=sys.stderr)
            return 1
    print(f"gate: ok: {GDS} re-derives 16 devices by model "
          f"(9 nfet_01v8, 4 pfet_01v8, 3 res_high_po)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["gate", "selftest"])
    parser.add_argument("--klt", default="klt")
    parser.add_argument("--pdk-root", default="~/.volare")
    args = parser.parse_args()
    if args.mode == "selftest":
        return selftest()
    return gate(args.klt, Path(args.pdk_root).expanduser())


if __name__ == "__main__":
    raise SystemExit(main())
