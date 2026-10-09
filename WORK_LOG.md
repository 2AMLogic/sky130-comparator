# Work Log

Chronological record of merged pull requests and closed issues, maintained by the Loom Guide role. Newest entries appear first.

### 2026-10-09

- **PR #126**: feat: pin klt 0.7.0 and restore strict LVS evidence for T1 items 4/11
- **Issue #123** (closed): Upgrade klt to 0.7.0 and restore strict LVS evidence for T1 item 4

### 2026-10-04

- **PR #121**: docs: add erratum for kickback records' hardcoded tt/27C corner prose
- **Issue #75** (closed): Kickback evidence writer hardcodes 'tt/27C' corner prose into every non-tt record it writes

### 2026-10-03

- **PR #120**: chore(sim): remove dead ratified_oat_grid and unused measure.py surface
- **Issue #70** (closed): Remove port-ahead dead harness code: run_klt_yield(), ratified_oat_grid(), PROCESS_CORNERS

### 2026-10-02

- **PR #119**: feat: classify decision polarity and bisect decision-referred offset
- **PR #118**: docs: correct stale no-schematic claims in sim/harness docstrings
- **Issue #99** (closed): Two sim/harness docstrings still claim 'there is no comparator schematic yet' — design/comparator.sch landed in #25
- **Issue #66** (closed): sim: quantify the layout-induced systematic offset and the sub-20 mV decision-polarity asymmetry post-layout surfaced

### 2026-09-30

- **PR #117**: docs: embed fleet burndown chart in README
- **PR #62**: chore: retire the loom-workspace package.json stubs, alias to sim/selftest.sh
- **Issue #58** (closed): Retire the uncustomized loom-workspace package.json stubs: npm test/check:ci exit 0 without running the real gates
- **Issue #42** (closed): README: embed the fleet burndown chart (one line)

### 2026-09-27

- **PR #116**: docs: state integrator-view null-accepting rule as standing, not current-state
- **Issue #115** (closed): Three prose sites still say the integrator view's gds/measured_area are null because no layout exists — layout landed in #45
- **PR #114**: refactor: single-source the selftest fixture skeleton and star-leg assertion
- **PR #113**: refactor: single-source the --check-env reporting block in toolchain.py
- **PR #112**: refactor: replace hand-rolled probit bisection with statistics.NormalDist
- **PR #111**: ci: run full sim/tests unit suite instead of test_extract_pex.py filter
- **Issue #110** (closed): Deduplicate two copy-pasted test-support bodies that have already drifted
- **PR #109**: fix: widen T1 item 8's freshness guard to cover non-record row-table citations
- **Issue #108** (closed): Consolidate the duplicated --check-env reporting block: run.py's copy has already drifted from harness/cli.py's
- **PR #107**: docs: --chunk-decks counts campaign decks, not 'Monte Carlo decks' (#104)
- **Issue #106** (closed): Replace the hand-rolled probit bisection with statistics.NormalDist and drop its duplicated inline re-derivation
- **Issue #105** (closed): CI runs 22 of the 159 unit tests: the -p test_extract_pex.py filter narrows a suite that is already hermetic
- **Issue #104** (closed): noise-tran --chunk-decks counts every campaign deck, not the 'Monte Carlo decks' its help and README claim
- **Issue #102** (closed): T1 item 8's freshness guard claims to pin every row-table citation but only checks evidence records

### 2026-09-26

- **PR #103**: feat: add a chunked, resumable noise-tran runner for full-N campaigns
- **PR #101**: sim: post-layout noise-tran at sf/-40C, sf/125C and fs/-40C -- the last three graded corners (#95)
- **Issue #100** (closed): sim: build a resumable/chunked noise-tran runner so full-N post-layout re-runs fit the ~60-minute command ceiling
- **PR #98**: docs: aggregate #88's four post-layout offset corners into the characterization report (5 of 5 _mm)
- **PR #97**: chore: replace description=__doc__ with purpose-written one-liners at two CLI entry points
- **PR #96**: sim: post-layout noise-tran at ss/-40C and ff/125C, plus the SCHEMATIC_BASELINES entry gap that blocked both
- **Issue #95** (closed): sim: the three counterpart-less post-layout noise-tran corners, and the full-N re-runs the ~60-minute command ceiling blocks
- **Issue #94** (closed): Remove description=__doc__ from two entry points: --help reprints the whole module docstring as one re-wrapped paragraph
- **PR #93**: scripts: drop the unused Counter import from the device-count gate
- **Issue #92** (closed): Remove unused Counter import in scripts/check-layout-device-count.py
- **Issue #91** (closed): docs: sim/characterization-report.md is stale for #88's four post-layout offset records (row 1 still says 1 of 5)
- **PR #90**: sim: post-layout noise-tran at fs/125C closes DR-006's compliance basis
- **Issue #89** (closed): sim: post-layout noise-tran at the five remaining graded corners, plus the BASELINES entry gap #83 found
- **PR #88**: sim: post-layout offset campaign at the four remaining _mm mismatch corners
- **PR #87**: docs: aggregate the characterization report and cite it for T1 item 8 (generic evidence envelope)
- **Issue #86** (closed): docs: aggregate the characterization report and cite it for T1 item 8 (generic evidence envelope)
- **PR #85**: sim: consolidate the record-setup preamble in run.py's evidence writers
- **PR #84**: docs: correct sim/README.md's stale placeholder-DUT claim
- **Issue #83** (closed): sim: post-layout noise-tran at fs/125C (DR-006's closure condition) and the remaining graded corners
- **Issue #80** (closed): sim: post-layout offset campaign at the four remaining _mm mismatch corners
- **Issue #79** (closed): Consolidate duplicated record-setup preamble across the six write_*_evidence functions
- **Issue #78** (closed): sim/README.md still claims sim/comparator-decision/ exercises a placeholder DUT (superseded by issue #24)

### 2026-09-25

- **PR #82**: sim: give reset and noise-tran a post-layout deck form, and run both
- **PR #81**: sim: complete the post-layout PVT campaign across the graded corners
- **PR #77**: docs: drop stale bootstrap-era claims from sim/README.md
- **PR #76**: layout: klt erc supply-spec run for T1 item 11, committed and deliberately uncited
- **Issue #74** (closed): Remove stale bootstrap-era claims from sim/README.md (DRAFT spec, no schematic)
- **PR #73**: sim: qualify the ported sky130-sar-adc issue citations and drop two fictional call sites
- **PR #72**: scripts: finish the _gate_common extraction (selftest tally + main() dispatch tails)
- **Issue #71** (closed): Requalify the ported foreign issue citations in sim/: ten bare 'issue #N' refs point at another repo's tracker
- **Issue #69** (closed): Finish the _gate_common extraction: the selftest tally and main() dispatch tails are still duplicated across the gates
- **Issue #68** (closed): layout: klt erc supply-spec run + compound item-11 citation (T1 item 11, power delivery structural)
- **PR #67**: layout: post-layout (extracted-netlist) re-simulation for the comparator (T1 item 7)
- **Issue #65** (closed): sim: give reset and noise-tran a post-layout deck form (they currently refuse --dut extracted)
- **Issue #64** (closed): sim: complete the post-layout PVT campaign across the remaining graded corners (follow-on to T1 item 7)
- **PR #63**: tests: drop the shadowed duplicate test method in test_comparator_decision.py
- **PR #61**: manifests: make maturity_rung_basis checkable against the signoff report
- **PR #60**: scripts: extract the shared fail/ok/load_json CI-gate helpers into _gate_common.py
- **Issue #59** (closed): Remove the shadowed duplicate test method in sim/tests/test_comparator_decision.py: 1 of 34 tests never runs
- **Issue #57** (closed): layout: post-layout (extracted-netlist) re-simulation for the comparator (T1 item 7)
- **Issue #56** (closed): Extract shared fail/ok/load_json CI-gate helpers: check-integrator-view.py duplicates check-t1-signoff.py
- **PR #55**: layout: withdraw the T1 item-4 LVS citation — the match has the known delta in its blind spot
- **PR #54**: layout: commit the LVS signoff envelope and cite it for T1 item 4
- **PR #53**: sim: drop the never-called _run_ts_retry helper
- **Issue #52** (closed): Remove dead _run_ts_retry helper in comparator-decision/run.py
- **Issue #50** (closed): integrator-view: maturity_rung_basis still claims 0/11 T1 items met, and nothing checks it
- **Issue #49** (closed): layout: LVS-clean signoff citation for the comparator (T1 item 4)

### 2026-09-24

- **PR #51**: chore: bump the klt pin to 0.6.0 (+ klayout 0.30.10) and regrade the T1 record
- **PR #48**: layout: commit the DRC signoff envelope and cite it for T1 item 3
- **Issue #47** (closed): chore: bump the klt pin off 0.5.0 to pick up input_verified + citation.coverage
- **Issue #46** (closed): layout: DRC-clean signoff citation for the comparator (T1 item 3)

### 2026-09-23

- **PR #45**: feat: add klt-generated comparator GDS layout with device-count CI gate
- **Issue #44** (closed): layout: create GDS/OASIS for the comparator (T1 item 2)
- **PR #43**: feat: full-corner Monte Carlo + PVT campaign (DR-005) -- ratify Decision-time, complete every row's corner set
- **Issue #41** (closed): Run the full-corner Monte Carlo and PVT campaigns the ratified target-spec rows still lack

### 2026-09-22

- **PR #40**: feat: static preamp ahead of StrongARM latch, closing the kickback gap (DR-004)
- **PR #39**: docs: add decision-record TEMPLATE.md and point spec/README at it
- **PR #38**: feat: add rule-9 consumers record and gated integrator view
- **Issue #36** (closed): 2am: reuse rule 9 — name this block's consumers in the spec, carry their requirement rows, publish the integrator view as data
- **Issue #34** (closed): design: kickback full compliance needs the topology class DR-001 scoped out (preamp/double-tail) — DR-001-supersession-grade follow-on
- **Issue #33** (closed): spec: codify decision-records/TEMPLATE.md now that DR-003 is the third record

### 2026-09-21

- **PR #35**: feat: add ~250ps soft-clock shaper, cutting comparator kickback 41%
- **PR #32**: feat: grade T1 state via klt signoff manifest + CI re-run gate
- **Issue #31** (closed): Commit a klt signoff block manifest so this block's T1 state is graded, not hand-read
- **Issue #30** (closed): design: kickback mitigation for comparator input stage (DR-002 non-compliance, 144.60 mV vs. ≤5 mV/≤2 mV)

### 2026-09-16

- **PR #29**: spec: DR-002 target-spec ratification pass (porting-plan next step 5)
- **Issue #28** (closed): spec: target-spec ratification decision record, informed by real measurements (porting-plan next step 5)
- **PR #27**: feat: add kickback input-node disturbance experiment
- **Issue #26** (closed): sim: design an original kickback experiment for design/comparator.sch (porting-plan next step 4)
- **PR #25**: design: draft design/comparator.sch + derived netlist per DR-001
- **Issue #24** (closed): design: draft design/comparator.sch schematic + derived netlist per DR-001 (porting-plan next step 1)

### 2026-09-15

- **Issue #23** (closed): design: comparator schematic (design/comparator.sch), sized against DR-001 (porting-plan next step 2)
- **PR #22**: spec: comparator topology decision record (DR-001)
- **Issue #21** (closed): design: comparator topology decision record (porting-plan next step 1)

### 2026-09-09

- **PR #20**: sim: stand up sim/comparator-decision/ regen/offset/noise experiments
- **PR #19**: docs: add missing provenance docstring to measure.py
- **PR #18**: sim: remove dead resolve_provenance()/ProvenanceInfo from evidence.py
- **Issue #17** (closed): Dead code: resolve_provenance()/ProvenanceInfo in sim/harness/evidence.py have zero callers
- **Issue #16** (closed): Simplify mc_runner._draw_n: drop speculative callback generality (no second caller in this repo)
- **PR #15**: sim: simplify _draw_n in mc_runner.py, drop unused callback abstraction
- **Issue #14** (closed): Simplify _draw_n in sim/harness/mc_runner.py: drop unused generic callback abstraction
- **PR #13**: docs: add docs/environment-setup.md for the sim/ harness toolchain pins
- **Issue #12** (closed): sim/harness/measure.py missing per-file provenance docstring
- **Issue #11** (closed): docs: add docs/environment-setup.md for the sim/ harness toolchain pins
- **PR #10**: sim: port sky130-sar-adc's harness plumbing + sim/pdk.json pin
- **Issue #9** (closed): sim: stand up sim/comparator-decision/ regen/offset/noise experiments with standalone stimuli (porting-plan next step 3)
- **Issue #8** (closed): sim: port sky130-sar-adc's sim/harness/ plumbing + sim/pdk.json pin (porting-plan next step 2)
- **Issue #7** (closed): sim: port sky130-sar-adc harness + pdk.json pin and stand up comparator-decision experiments with standalone stimuli (porting-plan next steps 2-3)

### 2026-09-07

- **Issue #1** (closed): Champion: Merge-Risk Hold Digest


