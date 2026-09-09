#!/usr/bin/env python3
"""PVT corner runner for sky130-comparator.

    python3 sim/run_corners.py --check-env
    python3 sim/run_corners.py --list
    python3 sim/run_corners.py harness-corner-smoke

Stdlib only, no virtualenv required. See sim/harness/cli.py for the full
CLI and sim/README.md for the evidence-record format it writes.

Provenance: ported (issue #8) from 2AMLogic/sky130-sar-adc's
sim/run_corners.py (commit b80c144efbf467a586f728726cabb25c1eb5a1f2),
per spec/porting-plan.md's "Next steps" item 2. That file itself follows
the pattern of 2AMLogic/gf180-sar-adc's sim/run_corners.py (commit
f613571aee5b80eff1eea37bdce9dfc88c5cf396), per CLAUDE.md's "Harness
bootstrap" instruction.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
