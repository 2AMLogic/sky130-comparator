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
# checks below (netlist exists, and has exactly the 13 MOSFET device
# lines the DR-004 preamp+latch device set (preamp tail + input pair +
# latch tail + steering pair + cross-coupled PMOS + two output reset
# PMOS + the two OUT1 absorber caps + the DR-003 soft-clock shaper cap)
# calls for, and three XR_ resistor lines: the shaper plus the two
# preamp poly loads) are what actually gate this script.
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
if [[ "${N_DEV}" -ne 13 ]]; then
  echo "netlist.sh: expected 13 MOSFET device lines (DR-004 preamp+latch set + OUT1 caps incl. DR-003 clock shaper cap), got ${N_DEV}" >&2
  exit 1
fi
N_RES="$(grep -c '^XR_' "${DEVICES}" || true)"
if [[ "${N_RES}" -ne 3 ]]; then
  echo "netlist.sh: expected 3 resistor lines (DR-003 clock shaper + two preamp poly loads), got ${N_RES}" >&2
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
* Topology: static preamplifier + dynamic StrongARM-class latch per
* DR-004 (issue #34) -- the DR-001-supersession topology-class change
* that closes the kickback gap DR-003 documented. 16 devices: a
* continuously-biased preamp (M_PTAIL, a gate-at-VDD NMOS current source;
* input pair M_PINN/M_PINP; poly loads R_LP/R_LN ~30kohm) whose outputs
* OUTP1/OUTN1 sit at a static ~1.1-1.25 V common mode and carry the
* differential with ~13-18x gain, ahead of a clocked latch (strong tail
* switch M_TAIL2 + steering pair M_STN_P/M_STN_N gated by the preamp
* outputs + cross-coupled PMOS M_LATP_P/M_LATP_N + output reset PMOS
* M_RST_P/M_RST_N), plus the OUT1 absorber caps M_C1P/M_C1N (nfet MOS
* caps at the preamp outputs, absorbing the steering pair's gate kick).
* CLK-gated PMOS precharge of the differential output
* nodes to VDD: during reset every latch PMOS sits at Vgs = 0 exactly, so
* the cross-coupled loop is dead and the reset state is a stable,
* non-conducting equilibrium -- DR-001 Decision 3's property on the latch
* stage. The steering pair's gates sit at the static preamp common mode
* and M_TAIL2 is off in reset, so no supply path exists. The DR-003
* shaper (R_CLKS x M_CLKCAP, tau ~ 250 ps) drives the latch tail and both
* reset PMOS from CLKT: the evaluate onset stays slew-limited. The
* preamp's channels are ALWAYS formed (static bias) -- the input-pin
* channel-formation transient that dominated the dynamic-input variants
* (single-tail AND double-tail; measured ladder in DR-004) does not exist
* in this class, and the latch's kickback arrives at the preamp outputs,
* divided by the preamp's gain and absorbed by the OUTx1 node before the
* pins.
*
* Sizing (all L=0.5um; full derivation in design/comparator.sch's own
* sizing-rationale text block and in DR-004):
*   M_PTAIL               W=0.8um  static current ~44uA total (supply row)
*   M_PINN, M_PINP        W=13um   offset budget + noise lever (DR-004)
*   R_LP, R_LN            L=22um   gain A~13-18, output CM ~1.1-1.25V
*   M_C1P, M_C1N          W=40um   kickback: absorb the steering gate kick
*   M_TAIL2               W= 8um   output descent + regeneration speed
*   M_STN_P, M_STN_N      W= 8um   steer strength / offset (2nd, /A)
*   M_LATP_P, M_LATP_N    W=16um   trip point near VDD/2 (as DR-001 Amd 1)
*   M_RST_P,  M_RST_N     W= 8um   reset tau << reset window, min C_out
*   R_CLKS (res_high_po_0p35, L=1.75um, ~2.4kohm) + M_CLKCAP (W=20um):
*                             DR-003 soft-clock shaper, tau ~ 0.25 ns
*
* Ports: VDD, GND (auto-tied to node 0 by ngspice's built-in gnd-name
* recognition), CLK, VINP, VINN, OUTP, OUTN -- UNCHANGED from every prior
* revision (the preamp is internally biased; no new port).
* Internal nodes: TAILP, OUTP1, OUTN1, TAIL2, CLKT.
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
