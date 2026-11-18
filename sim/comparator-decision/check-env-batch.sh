#!/usr/bin/env bash
#
# check-env-batch.sh — the strict toolchain/PDK check as a `repo-script` batch
# job (issue #127's supported route; see this directory's README.md, section
# "Supported execution route").
#
# What runs where: the `sim` image profile of the batch fleet bakes ngspice
# (the fleet's 47 artifact, at or above sim/toolchain.json's floor of 46),
# xschem 3.4.7 (the exact pin) and the sky130A PDK at the exact open_pdks pin
# of sim/pdk.json, unpacked under the baked PDK root (/opt/pdk), which
# batch-fleet-harness.sh exports as PDK_ROOT for every job. This script
# therefore installs nothing and fetches nothing — it records the provenance
# the submit side needs and runs the SAME check a local session runs. A
# missing tool or PDK here is a real exit 3, i.e. an image gap, never
# something to paper over by installing on the job.
#
# Submit, from a clean checkout at the commit to attribute (the runner ships
# `git archive` of one commit; the script runs from the extracted source
# root):
#
#   <2am-checkout>/infra/aws/repo-script-submit.py \
#       --source-dir <this checkout> \
#       --script sim/comparator-decision/check-env-batch.sh \
#       --issue <n> --image-profile sim \
#       --output sim/comparator-decision/route-check \
#       --wait-for-capacity 600 \
#       --out sim/comparator-decision/route-check/collected
#
# Declared output (collected to <out>/s00/files/... plus run.json, which
# carries image id, instance type, exit code and wall time):
#
#   sim/comparator-decision/route-check/env-check.log    human-readable
#   sim/comparator-decision/route-check/env-check.json   the same, structured
#
# Exit status is run.py --check-env's own, verbatim: 0 clean, 1 pinned
# version drifted, 3 tool/PDK missing. Nothing here transforms it.

set -uo pipefail

# Assert the source root before anything else: the harness runs this script
# from the extracted source root and every path below (OUT_DIR, run.py) is
# relative to it. A wrong CWD would otherwise die inside python with exit 2
# on the missing file, masquerading as a check status -- 0/1/3 are the
# check's own statuses, so fail here with a message instead.
[ -f sim/comparator-decision/run.py ] || {
    echo "check-env-batch.sh: not run from the source root" \
         "(sim/comparator-decision/run.py not found; cwd=$(pwd))" >&2
    exit 2
}

OUT_DIR="sim/comparator-decision/route-check"
mkdir -p "$OUT_DIR"

log_head() {
    echo "route-check (issue 127): strict toolchain check as a repo-script batch job"
    echo "utc_now:        $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "rs_commit:      ${RS_SOURCE_COMMIT:-<unset>}"
    echo "rs_src_sha256:  ${RS_SRC_SHA256:-<unset>}"
    echo "rs_synthetic:   ${RS_SYNTHETIC_HEAD:-<unset>}"
    echo "pdk_root:       ${PDK_ROOT:-<unset>}"
    echo "pdk:            ${PDK:-<unset>}  (pdk_variant env: ${PDK_VARIANT:-<unset>})"
    echo "hostname:       $(hostname)"
}

# The bake's own manifest: resolved tool/PDK versions, pin digest, base AMI
# (/etc/eda-batch-image.json; see 2am's batch-image.md). Absent is recorded
# as absent — it is evidence either way.
image_manifest() {
    if [ -r /etc/eda-batch-image.json ]; then
        echo "image_manifest (/etc/eda-batch-image.json):"
        cat /etc/eda-batch-image.json
    else
        echo "image_manifest: /etc/eda-batch-image.json not present"
    fi
}

tool_versions() {
    echo "python3: $(python3 --version 2>&1)"
    if command -v ngspice >/dev/null 2>&1; then
        echo "ngspice: $(ngspice --version 2>&1 | grep -m1 -E 'ngspice-[0-9]+' || echo PRESENT-unparsed)"
    else
        echo "ngspice: MISSING (not on PATH)"
    fi
    if command -v xschem >/dev/null 2>&1; then
        echo "xschem:  $(xschem -v 2>&1 | grep -m1 -E 'XSCHEM V[0-9.]+' || echo PRESENT-unparsed)"
    else
        echo "xschem:  MISSING (not on PATH)"
    fi
}

{
    log_head
    image_manifest
    tool_versions
} > "$OUT_DIR/env-check.log"

# The check itself: stdout and stderr preserved separately, then appended to
# the log, so the strict report the criterion quotes is byte-identical to
# what the tool printed. No errexit anywhere in this script: the exit status
# must be the check's own, never a later step's.
CHECK_STDOUT="$OUT_DIR/check-env.stdout"
CHECK_STDERR="$OUT_DIR/check-env.stderr"
set +e
python3 sim/comparator-decision/run.py --check-env >"$CHECK_STDOUT" 2>"$CHECK_STDERR"
CHECK_RC=$?

{
    echo "check-env exit status: $CHECK_RC"
    echo "--- stdout ---"
    cat "$CHECK_STDOUT"
    echo "--- stderr ---"
    cat "$CHECK_STDERR"
} >> "$OUT_DIR/env-check.log"

python3 - "$OUT_DIR" "$CHECK_RC" <<'PYEOF'
import json
import os
import sys
from pathlib import Path

out_dir = Path(sys.argv[1])
rc = int(sys.argv[2])


def read(name: str) -> str:
    p = out_dir / name
    return p.read_text(errors="replace") if p.is_file() else ""


def env_or(name: str) -> str:
    return os.environ.get(name, "") or "<unset>"


manifest = None
if Path("/etc/eda-batch-image.json").is_file():
    try:
        manifest = json.loads(Path("/etc/eda-batch-image.json").read_text())
    except json.JSONDecodeError:
        manifest = "<present but unparsable>"

doc = {
    "utc_now": os.popen("date -u +%Y-%m-%dT%H:%M:%SZ").read().strip(),
    "rs_commit": env_or("RS_SOURCE_COMMIT"),
    "rs_src_sha256": env_or("RS_SRC_SHA256"),
    "pdk_root": env_or("PDK_ROOT"),
    "pdk": env_or("PDK"),
    "pdk_variant_env": env_or("PDK_VARIANT"),
    "check_env_exit_status": rc,
    "check_env_stdout": read("check-env.stdout"),
    "check_env_stderr": read("check-env.stderr"),
    "image_manifest": manifest,
}
(out_dir / "env-check.json").write_text(json.dumps(doc, indent=2) + "\n")
PYEOF

rm -f "$CHECK_STDOUT" "$CHECK_STDERR"
exit "$CHECK_RC"
