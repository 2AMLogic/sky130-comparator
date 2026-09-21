# DR-003: Kickback mitigation pass 1 — soft-clocked evaluate onset, chosen over measured alternatives

- **Status**: **proposed** — a recommendation for two-key ratification via
  this PR (Judge review + Champion/operator merge), per the 2026-08-19
  ratification-via-PR ruling DR-002 was filed under. Nothing here is
  binding until this PR merges. Upon merge, the Decision below takes effect
  exactly as stated: this is a **partial-improvement** record by design —
  it lands a measured mitigation that does **not** reach the ratified
  Kickback bound, documents why the 17× remaining gap is not closable
  inside DR-001's topology + port set with the candidates measured, and
  defers full compliance to the topology-class work it names.
- **Date**: 2026-09-21
- **Decided by**: Builder agent, issue #30
- **Supersedes**: none — third decision record in this repo. It does not
  supersed DR-001 (all 11 DR-001 MOSFETs, their sizings, the reset scheme,
  and the port list are byte-identical before and after this record's
  change; the shaper hangs off the existing `CLK` port as new work) and it
  does not supersede DR-002 (its dispositions stand; this record *executes*
  DR-002 Decision §4's recommendation rather than amending it).
- **Superseded by**: (none while this record stands)
- **Related**: #30 (this issue), #26/PR #27 (kickback testbench),
  #24/PR #25 (the schematic this pass modifies), #28/PR #29 (DR-002),
  #3 (gap-to-T1 tracker — **not edited by this PR**, per the convention
  PRs #25/#27/#29 already followed; a Curator pass updates it separately),
  [DR-001](DR-001-comparator-topology.md) and its Amendment 1 (topology,
  reset scheme, and the offset-budget sizing pass this record preserves),
  [DR-002](DR-002-target-spec-ratification.md) Decision §4 (the candidate
  directions and the non-compliance finding this record works),
  `sim/comparator-decision/run.py` (`kickback` subcommand — the graded
  testbench every figure below cites), #34 (the follow-on issue this
  record's Consequences name), and the same-PDK cross-pollination filing
  2AMLogic/sky130-sar-adc#346 (per this repo's CLAUDE.md protocol — the
  measured option table transfers to that repo's embedded comparator).

## Context

DR-002 Decision §4 ratified the Kickback row at **≤ 5 mV disturbance into
a 1 kΩ source impedance (target) / ≤ 2 mV (stretch), single decision
edge** — unchanged — and measured this design at **144.60 mV peak**
(`tt`/27 °C, 50 mV overdrive; record
`sim/comparator-decision/records/20260916-060139-f1eb978.md`), ~29× the
target. It named three candidate mitigation directions (input-pair `Cgd`
reduction; dummy/compensation switches; bootstrapped or slew-limited
clocking), sized none of them, and recommended exactly this design pass as
follow-on work. Issue #30 is that pass; its acceptance criteria require the
same testbench, the same corner for before/after comparison, regression
checks on the **ratified** Offset sigma and Input-referred-noise rows, and
**an explicit statement of whether the new measurement meets the ratified
bound — with partial improvement and an honest deferral rationale an
acceptable outcome.**

All candidate measurements below were made with scratch decks against this
exact netlist (identical stimulus shape to the graded `kickback` bench),
then the chosen design was regenerated through `./design/netlist.sh` and
re-measured through the graded harness; probe figures are labelled as
such, and every graded figure cites its committed record.

### What the 144.60 mV actually is (waveform decomposition)

The graded pre-mitigation record's disturbance decomposes into two lobes
(probe-traced on the same deck):

- a **+38 mV common-mode lobe** during the CLK ramp: the tail switch's own
  gate capacitance kicks `TAIL` upward (0.705 → 1.045 V) and couples to
  both pins through the input pair's Cgs;
- a dominant **−144.6 mV (VINP) / −131.1 mV (VINN) negative spike** peaking
  at the END of the 100 ps CLK ramp: `DIP`/`DIN` — precharged to VDD and
  momentarily driven ~+0.5 V above it by the reset PMOS's turn-off channel
  charge — collapse through the input pair, and the fast first phase of
  that collapse drives a −145 µA displacement spike into each pin through
  the input device's own Cgd and channel-charge release.

Two structural facts fall out of that decomposition and drive everything
below. **First, the dominant charge keeps flowing *past the end of the
ramp*** — no clock-edge-correlated compensation capacitance can time-match
it. **Second, the collapse rate is set by the tail-switch + input-pair
conductance** — the same conductance that sets regeneration — so any
rate-based reduction trades roughly 1:1 into decision time.

## Decision

### 1. Adopt a soft-clocked evaluate onset — two devices on the clock port

The schematic lands a 2-device slew shaper: **`R_CLKS`** (a
`sky130_fd_pr__res_high_po_0p35` poly resistor, L = 1.75 µm, ≈ 2.4 kΩ)
from `CLK` to a new internal node **`CLKT`**, and **`M_CLKCAP`** (an
`nfet_01v8`, W = 20 µm, L = 0.5 µm ≈ 100 fF, gate on `CLKT`, all other
terminals at `GND`), giving τ = R·C ≈ **250 ps**. **All five clocked
gates** — the tail switch `M_TAIL` and the four precharge PMOS
(`M_RST_DIP`, `M_RST_DIN`, `M_RST_P`, `M_RST_N`) — moved from `CLK` to
`CLKT`, so the whole evaluate onset together (precharge release *and* tail
turn-on) is slew-limited by that RC rather than by the testbench's 100 ps
edge. Softening both halves of the onset also removes the reset-PMOS
channel-charge overshoot of `DIP`/`DIN` and slows the collapse that
follows it.

**The reset state is untouched, not traded**: during `CLK = 0`, `CLKT`
discharges to `GND` through `R_CLKS`, so every gate sits exactly where the
DR-001 design put it — only the *transition* is shaped. The reset
subcommand's reset-integrity record re-verified this after the change:
5/5 as-drawn corners hold reset, 5/5 `gnd-tied` positive controls correctly
break it (record `sim/comparator-decision/records/20260921-191043-bb32850.md`).

**Why this candidate (DR-002's direction 3) and not the others**: it is the
only measured direction that reduces the disturbance *at its source*
without adding ports, touching DR-001's signal path or device set, or
regressing a ratified row. The measured rejections are Decision §2; the
decision to stop at τ ≈ 250 ps is Decision §3.

### 2. The other candidate directions, measured and rejected

Each row was measured against this exact netlist (`tt`/27 °C scratch
decks unless noted; graded figures cite records):

| Candidate | Measured outcome | Why rejected |
|---|---|---|
| **Reset-device resizing** (`M_RST_DIP`/`M_RST_DIN` 6 µm and `M_RST_P`/`M_RST_N` 8 µm, all → 1 µm) | spike unchanged: −145.6 mV (positive lobe shrank +37.8 → +30.5 mV) | The reset PMOS channel-injection sharpens the `DIP`/`DIN` overshoot but is **not** the pin-disturbance mechanism — the input-pair-mediated collapse is. No mitigation lever here. |
| **Input-pair shrink** (`W_in` 10 → 5 µm) | kickback tracks ≈ ∝ W: −92.5 mV | A 29× reduction would need `W_in` ≈ 0.35 µm; the offset row's own Pelgrom basis (σ ∝ 1/√(W·L)) collapses first — DR-002 Decision §1's ratified offset budget is the directly-conflicting commitment. |
| **Feedthrough-cancellation caps `CLK`→pin** (4 fF and 8 fF per side) | 4 fF leaves a −104 mV spike; 8 fF overshoots to +166 mV positive lobe | The dominant charge flows **past the ramp's end**, so every value either under-cancels the trailing spike or overshoots the leading lobe — no sizing flattens both. It would also re-inject on every falling edge of every later cycle. |
| **Input isolation switches** (always-on min-width NMOS stacks, W = 0.42 µm, one to four per side) | pin **meets the bound**: 2-stack −5.88 mV, 3-stack −3.81 mV, 4-stack −2.71 mV @ `tt` (−3.66 @ `ff`/125 °C, −1.65 @ `ss`/−40 °C; `ideal` control still 0.0000 mV) | **Two measured regressions. (a) Decision time: the chain's R·C hangover suppresses the input pair's Vov through the decision edge — regeneration inflates 0.68 → 3.80 ns @ 50 mV (4-deep); a chain short enough not to hangover cannot be long enough to attenuate ~29× into a 1 kΩ source. A 3-deep chain also breaches the bound at a probed corner (−5.10 mV @ `ff`/125 °C). (b) The ratified Noise row: any input-referred-noise methodology that refers through an ideal source over a wide band (this repo's: loop-broken sub-model, 1 kHz–1 GHz) measures the chain's input pole (~0.45 → 17.53 mV differential against a ratified ≤ 1.0 mV) — a regression of a *ratified* row, which issue #30's no-regression acceptance criterion excludes outright.** |
| **Shunt capacitance at the pins** (not measured, reasoned) | would need ≈ 1.5 pF per pin for a 29× capacitive division | Not a mitigation: the injected charge is unchanged, the metric passes by brute swamping, and 1.5 pF of input capacitance dwarfs a real SAR's CDAC. Rejected as metric-gaming rather than design. |
| **Slew-limited clocking**, the ladder itself (τ 0.25 / 0.5 / 1 / 2 / 4 ns) | probe: 85.2 / 64.1 / 43.4 / 26.2 / 14.2 mV at regen 1.18 / 1.58 / 2.43 / 3.84 / 6.55 ns | The **~1:1 kickback/decision-time elasticity is the fundamental limit** of rate-based mitigation under this topology: the collapse rate and the regeneration share the same conductance. The ladder is the trade curve issue #30's own guidance anticipated for this direction ("bootstrapped or slew-limited clocking … trades off against decision speed"). |

### 3. Where on the ladder to stop, and why

τ ≈ 250 ps was chosen because it is the knee that keeps decision time
inside the **DRAFT** Decision-time row's own target at *every* probed
corner while buying the largest honest fraction of the elastic trade:

| Quantity | pre (records) | post (records) | bound status |
|---|---|---|---|
| Kickback peak, `tt`/27 °C, 1 kΩ, 50 mV (`loaded`) | 144.5980 mV (`20260916-060139-f1eb978`) | **85.7071 mV** (`20260921-185208-bb32850`) | **still misses the RATIFIED ≤ 5 mV target ~17×; stretch ~43×** |
| Decision time @ 50 mV, `tt`/27 °C | 0.6775 ns (`20260916-000727-52eb9b2`) | 1.0975 ns (`20260921-190636-bb32850`) | inside the DRAFT ≤ 1.5 ns target |
| Decision time @ 50 mV, `ss`/−40 °C | 0.6875 ns (`20260916-001345-52eb9b2`) | 1.0825 ns (`20260921-190824-bb32850`) | inside the DRAFT ≤ 1.5 ns target |
| Input-referred noise, `tt`/27 °C | 0.4466 mV rms diff. (`20260916-001416-52eb9b2`) | 0.4466 mV rms diff. — identical (`20260921-190837-bb32850`), same sub-model op point | clears the RATIFIED ≤ 1.0 mV target and ≤ 0.6 mV stretch |
| Offset sigma, `tt_mm`/27 °C, N=16/seed=1 | 2.019 mV stdev (`20260916-003531-52eb9b2`) | 2.3399 mV stdev (`20260921-193443-bb32850`) | clears the RATIFIED ≤ 15 mV target and ≤ 8 mV stretch (3σ = 7.02 mV), with the pick-off re-anchor of Decision §4 in the audit trail |

τ = 0.5 ns would buy 64 mV (−56%) but pay 1.58 ns/1.60 ns decision time at
`tt`/`ss` — *outside* the draft target at both graded points. τ ≈ 250 ps
buys −41% with draft-row compliance preserved, and the probe matrix
brackets the PVT spread of the RC itself (R and C each ±15–20%; kickback
spans ~80–86 mV and regen ≤ ~1.3 ns across `tt`/`ss`/`ff` probed points).

### 4. The offset regression audit trail (what it is and is not)

The first post-mitigation offset re-run minted
`sim/comparator-decision/records/20260921-192020-bb32850.md`: **343×
degenerate** — not an offset regression of the comparator, but the offset
*statistic* sampling the wrong place. Its own fields show it: the
calibration gain collapsed **5.8156 → 0.0021 V/V**, because the run.py
pick-off constant (0.3 ns after evaluate-start) was frozen against the
pre-DR-003 design's ~100 ps onset and now lands inside the shaper's
shaped-onset dead zone, where `|OUTP − OUTN|` is essentially zero for every
calibration stimulus. A statistic whose calibration gain is ~0.002 V/V
divides its (µV-scale, mismatch-timing-flavored) separations by ~0.002 and
reports ~245 mV of "offset" that is really onset-latency dispersion. The
record states its own non-compliance honestly (its Ratified-bound
comparison line) and is **kept, superseded, as evidence** — deleting
non-useful evidence is not this repo's discipline.

The superseding record re-anchors the pick-off constant to **1.0 ns** —
back inside the post-shaper separation's linear, gain-calibrated window
(ideal-device gains: 0.3 ns → 0.0021, 0.8 → 9.4, 1.0 → 13.2, 1.2 → 26.8
V/V), the same statistic *meaning* the pre-mitigation 0.3 ns sample had on
the fast onset. The record's Methodology line prints the pick-off
constant, so every record states which measurement point produced it.
The re-anchored figure:
**sim/comparator-decision/records/20260921-193443-bb32850.md** —
input-referred offset stdev **2.3399 mV** under
gain **13.2206 V/V**, negative control exact-zero as required.

**The pick-off re-anchor is a harness-methodology data point, not a spec
rescope**: the Offset row's bounds and their meaning ("input-referred
offset, post-calibration-free, 3σ") are untouched; what changed is which
sample of the transient represents that meaning on a design whose evaluate
onset this PR itself reshaped.

### 5. Compliance statement, plain

**The RATIFIED Kickback bound is NOT met.** The landed design measures
85.7071 mV peak at the like-for-like graded point — a 40.7% reduction
against 144.60 mV, still ~17× the 5 mV target and ~43× the 2 mV stretch.
Per issue #30's acceptance criteria this is an honest partial improvement
with the remaining gap explained: the measured candidates that reach ≤ 5 mV
(the isolation-stack family) regress a **ratified** row outright, and
rate-based mitigation (this record's own choice) is ~1:1 elastic against
decision time — τ large enough for 17× would put decision time at many
times the draft row's target. **Full compliance requires the topology class
DR-001 explicitly scoped out** — a static preamplifier or double-tail-style
isolation in front of the latch — which changes the port/timing story and
all four other rows together. That work is deliberately not smuggled in
here; it is filed as its own issue (#34) for a DR-001-supersession-grade
pass, per "agents do not relax the ratified spec" and per scope discipline
alike: the Kickback row's annotation stays **non-compliant**, and this
record recommends the README Basis row carry the new figure **alongside**
(not replacing) DR-002's citation.

## Alternatives considered

Beyond the candidate table in Decision §2 (each measured and rejected
there), the structural alternatives at the record level:

- **Declare full compliance out of reach and file nothing.** Rejected:
  DR-002 explicitly recommended this design pass, issue #30 exists for it,
  and the honest outcome — the option table and the elasticity
  measurement — is exactly the reusable engineering evidence, for this
  repo's layout stage, for the T1 ladder, and (cross-filed) for
  sky130-sar-adc's embedded comparator.
- **Land the isolation stack anyway** — it meets the pin bound — and
  re-scope the noise row's input plane (refer at the gate nodes) to dodge
  the 17.5 mV regression. Rejected twice over: it would be relaxing the
  measurement basis of a *ratified* row to admit a design, which is the
  laundering `CLAUDE.md` rules out; and its 5.6× decision-time cost wrecks
  the draft row without any honest margin story. The noise/isolation
  interaction is recorded here (and cross-filed) as prior art for any
  future design that adopts isolation.
- **Stretch τ further (≥ 0.5 ns) for a bigger headline cut.** Rejected:
  64 mV at 1.58/1.60 ns graded points exits the draft decision-time target
  at both graded corners. The delivered knee keeps every draft aspiration
  reachable while banking the honest fraction — and τ remains a one-device
  resize (R or C) away if a future decision record re-weighs that trade
  deliberately.

## Spec lines affected

- **`README.md` target-spec table, Kickback row**: Status annotation
  changes "design non-compliant, mitigation open" → "design non-compliant,
  mitigation pass 1 landed (DR-003)"; Basis gains the post-mitigation
  record citation **alongside** (not replacing) DR-002's; **values
  unchanged** — no row's numeric bound changes in this record, and none is
  relaxed.
- **`design/comparator.sch` / `design/README.md` / `design/netlist.sh`**:
  re-document the 13-device design (12 MOSFETs + one poly resistor), the
  `CLKT` node, and the shaper's sizing — the schematic's own text blocks
  carry the full option table with the probe numbers.
- **`sim/comparator-decision/run.py`**: the noise sub-model biases the
  tail's `CLKT` gate at the same steady evaluate level `Vclkfix` gives
  `CLK` (one source line; the loop-broken sub-model is otherwise
  structurally identical, and the noise record re-measured 0.4466 mV
  unchanged); the kickback/offset/noise record writers state each row's
  DR-002-ratified bound comparison explicitly; the offset pick-off
  constant is re-anchored per Decision §4 with its provenance in comments.
- **No changes** to the Decision-time or Supply/power rows' values or
  status (both stay DRAFT/OPEN; the two fresh regen records re-anchor
  their evidence at the new design).

## Consequences

1. **Kickback improves 144.60 → 85.71 mV at the like-for-like graded
   point** (−40.7%); the row's non-compliance annotation stands, with the
   new Basis citation, until the work #34 tracks lands.
2. **Decision time pays the measured trade**: +0.42 ns @ `tt`, +0.39 ns @
   `ss`/−40 °C at 50 mV — 1.10 ns / 1.08 ns graded points, both inside the
   draft 1.5 ns target; the sub-50-mV shape is re-anchored by the two fresh
   regen records (small-overdrive points now span ~1.46–2.11 ns; the row
   was and remains DRAFT/OPEN pending a full PVT sweep).
3. **Offset and noise hold** within their methodologies — the offset
   record's caveat chain (Decision §4) is the audit trail, and the noise
   record is bit-for-bit methodology-identical (0.4466 mV differential,
   same op point).
4. **Reset-integrity is verified unchanged** (5/5 hold + 5/5 positive
   control breaks, `20260921-191043-bb32850`) — because `CLKT` rests at
   `GND` whenever `CLK` does, DR-001 Decision 3's property was never
   traded.
5. **The shaped onset opens a brief contention window** (~250 ps where the
   tail sinks while the precharge PMOS are not yet fully off). The
   Supply/power row is DRAFT/OPEN with no measurement at any corner — the
   one consequence this record can state qualitatively but deliberately
   does not quantify; a future power record should capture it.
6. **τ drifts with PVT** (R and C each ±15–20%): the probe matrix brackets
   the trade at `tt`/`ss`/`ff`; the graded kickback evidence remains a
   single-corner like-for-like figure (kickback PVT coverage stays open
   exactly as DR-002 already flags).
7. **The cross-pollination finding is filed** on 2AMLogic/sky130-sar-adc
   (#346): the decomposition, the option table, and especially the
   noise-row/isolation-switch input-plane interaction are directly
   reusable prior art for that repo's embedded comparator, per this
   repo's CLAUDE.md protocol.
8. **The TEMPLATE.md question `spec/README.md` deferred ("a template
   remains future work if a third decision record makes the shape worth
   codifying") has its trigger now**: this record is the third DR. It is
   deliberately *not* created inside this PR (scope discipline; the
   follow-up exists as issue #33).
9. **Evidence-record corrections while this PR was assembled** minted
   supersede chains rather than edits, per the append-only discipline:
   kickback `20260921-185034` → `…-185118` → `…-185208` (claim-preamble
   wording corrections; the measurement was identical in all three) and
   offset `20260921-192020` → the re-anchored record (Decision §4). The
   chain is itself evidence of both failure modes — a wording fix and a
   statistic re-anchor — kept visible on purpose.

## Open items

- **Kickback full compliance** — the preamp/double-tail topology-class
  pass DR-001 scoped out; tracked as #34 with this record's option table
  as its evidence base. The ≤ 2 mV stretch bound has no measured route at
  all inside the current topology.
- **Kickback PVT coverage**, unchanged from DR-002 — `tt`/27 °C graded
  figures only; a full-corner kickback sweep remains open work.
- **Offset MC breadth** — the re-anchored record is still N=16/seed=1
  distribution-shape evidence (~18% relative SE on the stdev), exactly as
  DR-002 recorded; O(100s)-draw campaigns and the four other `_mm` corners
  remain open.
- **Decision-time full PVT** (`ff`/`sf`/`fs`) and the sub-50-mV shape off
  the `tt`/`ss` axis — unchanged open items, now re-anchored at the
  post-DR-003 design by this PR's two records.
- **Supply/power**, including the contention window this design added —
  no measurement exists at any corner; unchanged open.
- **Layout-stage re-verification** — DR-002's open item, now applying to
  the 13-device design: every figure this record cites is schematic-level.
