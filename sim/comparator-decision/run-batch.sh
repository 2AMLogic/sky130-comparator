#!/usr/bin/env bash
#
# run-batch.sh — run.py on the repo-script batch route, with the campaign's
# documented per-deck ngspice budget (see this directory's README.md,
# "Supported execution route (issue #127)"; the campaign invocation forms
# mandate SIM_NGSPICE_TIMEOUT_S=900).
#
# Why a wrapper: the route's submitter passes a shard's arguments to ONE
# script and cannot inject environment variables, while
# sim/harness/toolchain.py's default per-ngspice budget is 120 s. That
# default was fine for the schematic decks step 2 (#359) ran, but the
# extracted decks this campaign measures are several times slower (up to
# ~285 s wall per deck measured on a loaded dispatch worker, issue #89), so
# the documented 900 s budget must ride along. The wrapper sets it and execs
# run.py verbatim; run.py's own exit status passes through unchanged
# (0 done · 1 unresolved-sweep-point or NaN-sigma, still a record ·
# 3 resumable-incomplete, no record).
#
# Submit, from a clean checkout at the commit to attribute:
#
#   <2am-checkout>/infra/aws/repo-script-submit.py \
#       --source-dir <this checkout> \
#       --script sim/comparator-decision/run-batch.sh \
#       --shard "<run.py mode and flags>" \
#       --output sim/comparator-decision/records \
#       --output sim/comparator-decision/corners \
#       --output sim/comparator-decision/mc-draws \
#       --output sim/comparator-decision/netlist-snapshots \
#       --issue <n> --image-profile sim \
#       --wait-for-capacity 600 \
#       --out <scratch>/collected

set -uo pipefail

# Assert the source root before anything else: the harness runs this script
# from the extracted source root and run.py's own path is relative to it. A
# wrong CWD would die inside python with an unrelated error instead.
[ -f sim/comparator-decision/run.py ] || {
    echo "run-batch.sh: not run from the source root" \
         "(sim/comparator-decision/run.py not found; cwd=$(pwd))" >&2
    exit 2
}

export SIM_NGSPICE_TIMEOUT_S="${SIM_NGSPICE_TIMEOUT_S:-900}"
exec python3 sim/comparator-decision/run.py "$@"
