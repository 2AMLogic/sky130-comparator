#!/usr/bin/env bash
#
# pex-batch.sh — the issue #187 `klt pex --measure-command` run on the
# repo-script batch route (the same "Supported execution route (issue #127)"
# run-batch.sh documents: a repo-script job on the fleet's `sim` image
# profile, the operator ruling of 2026-11-17).
#
# Why klt is pip-installed by the SUBMITTER, not baked and not installed here:
# the `sim` image has ngspice but no klt, and the extraction must run at the
# repo's own pin (klayout-tools 0.8.0 / klayout 0.30.12, `layout/
# gen_comparator.py`'s constants) because extracted resistances are not
# stable across klt/klayout builds (`layout/extract_pex.py` refuses an
# off-pin extraction for exactly that reason). The submitter's first-class
# `--pip klayout-tools==0.8.0 --pip klayout==0.30.12` installs exactly that
# pin into the job, so this script installs nothing itself — the route's
# "fetches nothing and installs nothing" rule is honoured by the submitter,
# not worked around in-job.
#
# What this runs: one `klt pex` invocation over the committed
# layout/comparator.gds with the issue #409 adapter
# (scripts/pex-measure-command.py) as --measure-command. klt pex extracts
# with `klt extract --parasitics` (same flags `layout/extract_pex.py` uses,
# so the fresh extraction is byte-identical to the committed
# layout/comparator.extract.spice — the adapter refuses anything else), then
# measures both legs over the seven graded corners (2 ngspice decks per
# corner per leg, 28 transients total, serial: the one-core cgroup quota
# (#83) applies) and writes the delta[] report to layout/pex-report.json.
#
# SIM_NGSPICE_TIMEOUT_S rides along for the same reason run-batch.sh sets
# it: the harness default is 120 s and extracted decks run several times
# longer. --measure-timeout-s 5400 (90 min per leg) bounds the whole
# 14-transient leg with margin over the worst measured per-deck time, while
# staying inside the route's per-job ceiling.
#
# The envelope's path fields are normalised to repo-relative before the run
# exits: klt writes the job tree's absolute source root into
# layout/reference_netlist/measurement.sides paths, and a committed evidence
# artifact carries no home dir (`layout/extract_pex.py` normalises the same
# way, the rule `klt env-provenance --lint` enforces).
#
# Submit, from a clean checkout at the commit to attribute:
#
#   <2am-checkout>/infra/aws/repo-script-submit.py \
#       --source-dir <this checkout> \
#       --script sim/comparator-decision/pex-batch.sh \
#       --output layout/pex-report.json \
#       --issue <n> --image-profile sim \
#       --pip klayout-tools==0.8.0 --pip klayout==0.30.12 \
#       --wait-for-capacity 600 \
#       --out <scratch>/collected
#
# Exit status: klt pex's own (0 pass · 1 error envelope, including any
# adapter refusal or measurement failure · 4 not-checked conditions), after
# the path normalisation step. A failed run still leaves its error envelope
# at layout/pex-report.json for collection.

set -uo pipefail

# Assert the source root before anything else: the harness runs this script
# from the extracted source root and every path below is relative to it.
[ -f scripts/pex-measure-command.py ] || {
    echo "pex-batch.sh: not run from the source root" \
         "(scripts/pex-measure-command.py not found; cwd=$(pwd))" >&2
    exit 2
}
command -v klt >/dev/null 2>&1 || {
    echo "pex-batch.sh: klt not on PATH -- submit with" \
         "--pip klayout-tools==0.8.0 --pip klayout==0.30.12" \
         "(the repo pin; the sim image bakes no klt)" >&2
    exit 2
}
KLT_VERSION="$(klt --version 2>/dev/null | awk '{print $2}')"
[ "${KLT_VERSION:-}" = "0.8.0" ] || {
    echo "pex-batch.sh: klt ${KLT_VERSION:-unknown} is off the repo pin 0.8.0" \
         "(layout/gen_comparator.py); extracted resistances differ across" \
         "builds, so this would be a different measurement" >&2
    exit 2
}

export SIM_NGSPICE_TIMEOUT_S="${SIM_NGSPICE_TIMEOUT_S:-900}"

# Scratch inside the job tree, never committed: klt pex's own generated
# artifacts (per-side measurement dirs, the extracted netlist copy) and the
# stdout envelope dump. The collected deliverable is layout/pex-report.json.
SCRATCH=layout/.klt/pex
mkdir -p "$SCRATCH"

# The envelope is `--format json`'s stdout, redirected to the deliverable:
# the pinned klt 0.8.0 predates `--envelope-out` (#4692), and on a failed
# run the redirect simply leaves a partial/empty file behind a non-zero
# exit status (the error envelope of that klt vintage goes to stderr, which
# the harness log keeps).
status=0
klt pex layout/comparator.gds \
    --deck sky130 --top gen_compose_0 --pdk sky130A \
    --measure-command 'python3 scripts/pex-measure-command.py --corners all' \
    --reference-netlist sim/comparator-decision/testbench/comparator_core.spice \
    --measure-timeout-s 5400 \
    --outdir "$SCRATCH" -o "$SCRATCH/extracted.spice" \
    --format json >layout/pex-report.json || status=$?

# Normalise the job tree's absolute source root out of the envelope's path
# fields (see header). Textual prefix replacement only: the source root is a
# directory prefix, so it cannot collide with a value klt meant to keep.
python3 - "$PWD" <<'EOF' || status=$?
import sys
from pathlib import Path

root = sys.argv[1]
report = Path("layout/pex-report.json")
if not report.is_file():
    print("pex-batch.sh: no envelope at layout/pex-report.json to normalise",
          file=sys.stderr)
    raise SystemExit(1)
text = report.read_text()
prefix = root.rstrip("/") + "/"
count = text.count(prefix)
if count:
    report.write_text(text.replace(prefix, ""))
print(f"pex-batch.sh: normalised {count} absolute source-root path(s) "
      "to repo-relative in layout/pex-report.json")
EOF

exit "$status"
