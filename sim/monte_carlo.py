#!/usr/bin/env python3
"""Monte Carlo runner for sky130-comparator.

    python3 sim/monte_carlo.py --list
    python3 sim/monte_carlo.py mc-smoke --seed 1 --n 8
    python3 sim/monte_carlo.py mc-smoke --seed 1 --n 8 --record

Stdlib only, no virtualenv required. See sim/harness/mc_cli.py for the
full CLI and sim/README.md for the evidence-record format (recorded seed,
N, and the deterministic negative control) this writes.

This is the piece the comparator's offset-sigma target-spec row needs
(see the top-level README's target-spec table, DRAFT) -- offset is a
statistical row, not a corner point (spec/porting-plan.md). This pass
(issue #8) proves the mechanism against a harness-proof circuit
(sim/mc-smoke/); a future comparator testbench manifest reuses this
exact runner.

Provenance: ported (issue #8) from 2AMLogic/sky130-sar-adc's
sim/monte_carlo.py (commit b80c144efbf467a586f728726cabb25c1eb5a1f2).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness.mc_cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
