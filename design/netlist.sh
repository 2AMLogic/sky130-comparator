#!/usr/bin/env bash
#
# design/netlist.sh -- regenerate the simulation DUT fragment from the schematic.
#
#   design/comparator.sch  --(xschem netlister)-->
#       sim/comparator-decision/testbench/comparator_core.spice
#
# This is the documented, reproducible derivation command issue #24's
# acceptance criteria ask for: the committed .spice fragment is a build
# product of the committed .sch, never hand-edited. Re-run it after ANY
# change to design/comparator.sch and commit both together.
#
# Usage (from the repository root):
#   ./design/netlist.sh          # rewrite the fragment in place
#   ./design/netlist.sh --check  # regenerate to a temp file and diff; non-zero
#                                # exit means the committed fragment is stale
#
# Why the xschem output needs post-processing at all: xschem wraps a
# top-level "-x" netlist target in "**.subckt <name>" / "**.ends" marker
# lines and prepends a "** sch_path:" provenance line. Every one of those is
# "**"-prefixed -- a SPICE comment, not a real directive (xschem netlists a
# top-level target FLAT, never inside a real .subckt), so stripping them
# plus the trailing ".end" leaves exactly the flat device lines this repo's
# testbench harness includes as a fragment. No device line is modified.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCH="${REPO_ROOT}/design/comparator.sch"
OUT="${REPO_ROOT}/sim/comparator-decision/testbench/comparator_core.spice"

CHECK=0
[[ "${1:-}" == "--check" ]] && CHECK=1

if [[ -z "${PDK_ROOT:-}" || -z "${PDK:-}" ]]; then
  # shellcheck disable=SC1091
  source "${REPO_ROOT}/sim/env.sh" >/dev/null
fi
: "${PDK_ROOT:?PDK_ROOT not set -- run 'source sim/env.sh' first}"
: "${PDK:?PDK not set -- run 'source sim/env.sh' first}"

SCRATCH="$(mktemp -d)"
trap 'rm -rf "${SCRATCH}"' EXIT

# NOTE: xschem 3.4.7 exits 10 on a SUCCESSFUL batch netlist-and-quit run
# (-q), not 0, so its status is not usable as a success signal here. The
# checks below (netlist exists, and has exactly the 11 device lines the
# DR-001 device set calls for) are what actually gate this script.
xschem -n -q -x \
  --rcfile "${PDK_ROOT}/${PDK}/libs.tech/xschem/xschemrc" \
  "${SCH}" -o "${SCRATCH}" >/dev/null || true

RAW="${SCRATCH}/comparator.spice"
[[ -s "${RAW}" ]] || { echo "netlist.sh: xschem produced no netlist" >&2; exit 1; }

DEVICES="${SCRATCH}/devices.spice"
# Drop xschem's "**"-prefixed wrapper comments and the trailing .end; keep
# every remaining line byte-for-byte as the netlister emitted it.
grep -v '^\*\*' "${RAW}" | grep -v '^\.end[[:space:]]*$' \
  | sed -e '/./,$!d' > "${DEVICES}"

N_DEV="$(grep -c '^XM_' "${DEVICES}" || true)"
if [[ "${N_DEV}" -ne 11 ]]; then
  echo "netlist.sh: expected 11 device lines (DR-001 device set), got ${N_DEV}" >&2
  exit 1
fi

NEW="${SCRATCH}/comparator_core.spice"
cat > "${NEW}" <<'HEADER'
* comparator_core.spice -- THIS REPO'S OWN comparator design.
*
* GENERATED FILE -- do not hand-edit. Regenerate with ./design/netlist.sh
* (see that script for the exact xschem invocation and the post-processing
* it applies). The source of truth is design/comparator.sch.
*
* This file is no longer the sky130-sar-adc-ported PLACEHOLDER DUT it was
* under issue #9. It is this repo's own design/comparator.sch (issue #24),
* implementing the topology and reset scheme decided in
* spec/decision-records/DR-001-comparator-topology.md (issue #21 / PR #22)
* at a sizing derived first-principles against this repo's own installed
* sky130 device models. The prior placeholder content remains in git
* history; records under sim/comparator-decision/records/ written before
* this change characterize that placeholder, not this design, and say so in
* their own Claim fields (they are append-only evidence and are never
* edited -- they simply stop being the freshest evidence).
*
* Topology: single-tail, bottom-tail NMOS-input dynamic latch, no static
* preamp. 11 devices: 1 tail switch NMOS + 2 input-pair NMOS + 2
* cross-coupled latch NMOS + 2 cross-coupled latch PMOS + 2 output-node PMOS
* reset/precharge + 2 internal-node PMOS reset/precharge. CLK-gated PMOS
* precharge of BOTH the differential output nodes (OUTP/OUTN) AND the
* cross-coupled latch NMOS pair's own source nodes (DIP/DIN) to VDD, per
* DR-001 Decision 3 -- every latch NMOS is at Vgs = 0 during reset, so the
* positive-feedback loop is dead and the reset state is a stable,
* non-conducting equilibrium.
*
* Sizing (all L=0.5um; full derivation in design/comparator.sch's own
* sizing-rationale text block and in DR-001 Amendment 1):
*   M_TAIL                W=20um   headroom: CLK-gated switch, Ron drop
*   M_INN, M_INP          W=10um   offset budget: 2*AVT_n^2/(W*L) at 70% of
*                                  the DRAFT stretch row's variance
*   M_LATN_P, M_LATN_N    W= 8um   offset budget: remaining 30%
*   M_LATP_P, M_LATP_N    W=16um   2x latch NMOS -> trip point near VDD/2
*   M_RST_P,  M_RST_N     W= 8um   reset tau << reset window, min C_out
*   M_RST_DIP, M_RST_DIN  W= 6um   reset tau << reset window, min C_DI
*
* Ports: VDD, GND (auto-tied to node 0 by ngspice's built-in gnd-name
* recognition), CLK, VINP, VINN, OUTP, OUTN. Internal nodes: TAIL, DIP, DIN.
* Vin,diff = VINP - VINN > 0 => OUTP settles high.
*
* Every device is sky130_fd_pr__{n,p}fet_01v8 (1.8V core flavour, matching
* this repo's own 1.8V headroom constraint per CLAUDE.md) -- no
* _g5v0d10v5 or other non-core flavour instances.

HEADER
cat "${DEVICES}" >> "${NEW}"

if [[ "${CHECK}" -eq 1 ]]; then
  if diff -u "${OUT}" "${NEW}"; then
    echo "netlist.sh --check: ${OUT#"${REPO_ROOT}/"} is up to date with design/comparator.sch"
  else
    echo "netlist.sh --check: STALE -- re-run ./design/netlist.sh" >&2
    exit 1
  fi
else
  cp "${NEW}" "${OUT}"
  echo "netlist.sh: wrote ${OUT#"${REPO_ROOT}/"} from design/comparator.sch"
fi
