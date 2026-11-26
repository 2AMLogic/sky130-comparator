# Work Log Archive — 2026-09

Sections moved byte-for-byte from [WORK_LOG.md](../WORK_LOG.md) by `loom-daemon work-docs archive`.

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

### 2026-09-06

- **PR #5**: docs: bootstrap target-spec table, porting plan, and gap-to-T1 tracker
- **Issue #4** (closed): Gap-to-T1 tracker: sky130-comparator bootstrap (T1/bronze design-evidence checklist)
- **Issue #2** (closed): Bootstrap the block: draft target-spec, porting/design plan, gap-to-T1 tracker (wave-5 standup completion)
