# Characterization report — sky130-comparator

The one aggregated, current artifact T1 item 8 names: every target-spec row,
its ratification status, its bounds, the measured figure at every condition
that has one, and the committed evidence record each figure rests on.

This document is the evidence cited for **T1 item 8** in
[`manifests/sky130-comparator.json`](../manifests/sky130-comparator.json). See
[`manifests/README.md`](../manifests/README.md) → "Item 8 — the characterization
report, and what its `met` row does not establish" for what that citation does
and does not prove.

**Rebuilt 2026-11-23 from the re-qualification campaign's records (issues
[#179](https://github.com/2AMLogic/sky130-comparator/issues/179) /
[#361](https://github.com/2AMLogic/sky130-comparator/issues/361)).** Every
figure below is copied from a record minted on the current pins — open_pdks
`f6eeac7dad08…`, ngspice-47, extracted on klt 0.8.0 / KLayout 0.30.12 at the
0.35 µm resistor geometry — and every superseded record this report used to
cite has been replaced by the terminal record of its `Supersedes` chain. The
28 schematic rows cite the direct successors; the 36 extracted rows cite the
corrected reissues at the end of their two-link chains.
[`check-requalify-plan.py`](comparator-decision/check-requalify-plan.py) gates
that discharge in `sim/selftest.sh`. The old/new movement itself — what moved,
by how much, and past which stated tolerance — is recorded in
[DR-012](../spec/decision-records/DR-012-requalification.md).

## How to read this report

- **It aggregates; it does not measure.** Every number below is copied from a
  committed, append-only record under
  [`sim/comparator-decision/records/`](comparator-decision/records/) (or, for
  the one row with no record, from the support deck named in the row). No
  simulation was run to produce this document, and none of its figures is new.
- **It does not set or interpret bounds.** Ratification status and bounds come
  from the [top-level `README.md`](../README.md) target-spec table and the
  decision records that dispose it (DR-002, DR-004, DR-005, DR-006). Per
  `CLAUDE.md`, nothing here relaxes a ratified bound, and no row is rendered
  compliant that the specs do not support.
- **One row is not compliant as read, and this report says so on its face.**
  The **Supply / power** row is still **DRAFT / OPEN**: it has no ratified
  bound at all, and the measurements it does have already exceed its DRAFT
  figure. The **Input-referred noise** row was the second such row until
  [#83](https://github.com/2AMLogic/sky130-comparator/issues/83): its bound is
  ratified, its *compliance basis* was **RE-OPENED** by
  [DR-006](../spec/decision-records/DR-006-post-layout-noise-headroom-reopened.md),
  and **DR-006 Amendment 1 has since re-closed the target-bound basis** on the
  regeneration-inclusive `fs`/125 °C measurement that record named as its own
  closure condition. Its ≤ 0.6 mV **stretch** figure is still recorded as
  breached at four of seven corners on the AC basis — recorded, not relaxed,
  and not a compliance requirement.
- **Freshness is enforced, not asserted.** See
  [Freshness enforcement](#freshness-enforcement) at the end: a drifted report
  or a drifted evidence record makes T1 item 8 grade non-`met`.

## Provenance and pinning

Every figure below was produced by
[`sim/comparator-decision/run.py`](comparator-decision/run.py) on the pins the
records themselves record:

| Axis | Pin |
|---|---|
| PDK | sky130A @ open_pdks `f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7` ([`sim/pdk.json`](pdk.json)) |
| Simulator | ngspice-47 (the campaign records' own environment; [`sim/toolchain.json`](toolchain.json) pins the ≥ 46 floor) |
| Harness | `sim/harness` 0.1.0 |
| Schematic DUT | `design/comparator.sch` → `./design/netlist.sh` → `sim/comparator-decision/testbench/comparator_core.spice` |
| Post-layout DUT | `layout/comparator.gds` → `klt extract --parasitics` → `layout/comparator.pex.spice`, extracted under **`klayout-tools==0.8.0` on `klayout==0.30.12`** at the **0.35 µm** `res_high_po` geometry (issue #123), on the `f6eeac7` PDK install — the pins `docs/environment-setup.md` records, CI installs, and `layout/extract_pex.py` asserts (extracted per-net series R is **not** stable across klt/klayout builds — up to 2.30× apart on this block) |
| Topology | DR-004 static preamplifier + StrongARM latch, with DR-003's soft-clock shaper on the clock port |

**The re-qualification campaign changed three things at once on the extracted
side** — geometry (0.42 µm → 0.35 µm resistors, issue #123), extraction pins
(klt 0.6.0/0.30.10 → 0.8.0/0.30.12) and the PDK/ngspice environment — so the
old→new post-layout movement is the bundle, not any one term. The schematic
side isolates the environment change alone, and there it is almost exactly
reproduced: every deterministic schematic figure this report carries
(`regen` times, `kickback` peaks, the `noise` AC estimate, the `reset`
currents) came out **identical to its superseded predecessor at displayed
precision**, while the mismatch-sampling rows (`offset`) moved — see row 1.

**Graded PVT corner set** (the seven `--dut extracted` rows below use it):
`tt`/27 °C, `ss`/−40 °C, `ff`/125 °C, `sf`/−40 °C, `sf`/125 °C, `fs`/−40 °C,
`fs`/125 °C. The Offset sigma row runs on the five `_mm` local-mismatch corners
at 27 °C instead (`tt_mm`, `ss_mm`, `ff_mm`, `sf_mm`, `fs_mm`) because mismatch
sampling is not a PVT axis; the reset-integrity screen behind the Supply/power
row's current column uses its own five-point set (`tt`/27 °C, `ss`/−40 °C,
`ss`/125 °C, `ff`/−40 °C, `ff`/125 °C). Each row states which set it used.

**Post-layout parasitic model, where it is coarse.** The extraction is a single
lumped star R per net. `GND` (6.56 kΩ) and `VDD` (2.13 kΩ) together carry 48.7 %
of the block's 17.81 kΩ total series R, where the real drawn supply is a wide
low-impedance shape. Every post-layout degradation below is therefore an **upper
bound on the supply-network contribution**, not a best estimate of it. See
[`sim/comparator-decision/README.md`](comparator-decision/README.md) →
"Parasitic model, and where it is coarse".

## Summary — the five target-spec rows

| # | Row | Status | Target | Stretch | Worst measured (post-layout unless noted) | Target met? | Stretch met? |
|---|---|---|---|---|---|---|---|
| 1 | Offset sigma | RATIFIED (DR-002; coverage by DR-005) | ≤ 15 mV, 3σ | ≤ 8 mV, 3σ | 7.5606 mV 3σ (`ff_mm`/27 °C, N=16) | **yes** (1.98×) | yes (1.06×) |
| 2 | Input-referred noise | RATIFIED (DR-002); compliance basis re-opened (DR-006), **RE-CLOSED** (DR-006 Amendment 1, #83) | ≤ 1.0 mV rms diff | ≤ 0.6 mV rms diff | 0.1951 mV rms regeneration-inclusive (`fs`/125 °C); 0.9372 mV rms on the AC **lower bound**, same corner | **yes** (5.13×; 4.21× at the CI's upper bound) — on the regeneration-inclusive basis; see row 2 | no (breached at 4 of 7 on the AC basis) |
| 3 | Decision time vs. overdrive | RATIFIED (DR-005) | ≤ 1.5 ns @ 50 mV | ≤ 0.8 ns @ 50 mV | 0.7575 ns (`fs`/125 °C) | **yes** (1.98×) | yes, but 1.06× |
| 4 | Kickback | RATIFIED (DR-002 bound; DR-004 first compliant design) | ≤ 5 mV into 1 kΩ | ≤ 2 mV | 2.7204 mV (`sf`/−40 °C) | **yes** (1.84×) | no (breached at 5 of 7 — down from 6 of 7; `ff`/125 °C now clears at 1.9604 mV) |
| 5 | Supply / power | **DRAFT / OPEN** (DR-002) | *(draft)* ≤ 50 µW avg at a TBD clock rate | *(draft)* ≤ 20 µW | ~95 µW static at 1.8 V | **no ratified bound exists** | — |

Row 2's "target met?" cell says "yes" only on the **regeneration-inclusive**
basis, and only since #83. Until then it deliberately did not: every measured
figure cleared the ratified target bound, but DR-006 had retired the argument
the ratification rested on. The measurement DR-006 named has now been made, so
the row's target compliance rests on a direct regeneration-inclusive figure at
the binding corner rather than on a lower bound plus a headroom argument. Two
qualifiers survive and both matter: a statement citing the **AC lower-bound**
figure instead still carries that figure's 1.07× worst-corner margin, and the
stretch column is still "no". The row's full disposition is in
[row 2](#2-input-referred-noise) and must be read before the row is cited.

---

## 1. Offset sigma

- **Status**: RATIFIED by [DR-002](../spec/decision-records/DR-002-target-spec-ratification.md) §1; the four remaining `_mm` corners and the large-N campaigns DR-002 left open were closed by [DR-005](../spec/decision-records/DR-005-full-corner-campaign.md).
- **Bounds**: target ≤ 15 mV 3σ, stretch ≤ 8 mV 3σ, input-referred, post-calibration-free.
- **Method**: `run.py offset` — a linearized pick-off statistic at a fixed early time after the evaluate edge, calibrated to an input-referred gain by an ideal-device Vindiff sweep, applied to N Monte Carlo draws at an `_mm` local-mismatch corner. Every run carries a same-seed, mismatch-disabled negative control at the plain corner, which must reproduce **stdev exactly 0**.

### Schematic-level, N=16, seed 1, 27 °C

| Corner | σ (mV) | 3σ (mV) | Negative control stdev | Record |
|---|---|---|---|---|
| `tt_mm` | 2.3027 | 6.9081 | 0 exactly | `sim/comparator-decision/records/20261121-073855-4d73da9.md` |
| `ss_mm` | 2.3962 | 7.1886 | 0 exactly | `sim/comparator-decision/records/20261121-074337-4d73da9.md` |
| `ff_mm` | 2.0463 | 6.1389 | 0 exactly | `sim/comparator-decision/records/20261121-074654-4d73da9.md` |
| `sf_mm` | 2.1357 | 6.4071 | 0 exactly | `sim/comparator-decision/records/20261121-075012-4d73da9.md` |
| `fs_mm` | 2.3863 | 7.1589 | 0 exactly | `sim/comparator-decision/records/20261121-075327-4d73da9.md` |

**The re-qualification moved every one of these figures up 27.8–31.3 %** —
`tt_mm` 1.7857 → 2.3027 mV, `ss_mm` 1.8244 → 2.3962 mV, `ff_mm` 1.5954 →
2.0463 mV, `sf_mm` 1.6706 → 2.1357 mV, `fs_mm` 1.8218 → 2.3863 mV — past the
N=16 relative standard error (≈ 18 % on a stdev) at every corner. This is the
one schematic quantity the PDK re-pin materially moved, and it moved it in the
direction the campaign was run to find: the `f6eeac7` open_pdks revision ships
different per-instance mismatch (AGAUSS) parameters than the retired
`c6d73a35` one, and the offset distribution those models produce is ~30 %
wider. DR-012 records the movement per corner. The corner ranking flips
accordingly: `ss_mm`/`fs_mm` were nominally binding pre-campaign, `ss_mm` still
is, and the ranking still does **not** survive layout (below).

### Schematic-level, N=200 (the yield-fraction campaigns)

| Corner | σ (mV) | 95 % CI on σ | 3σ (mV) | Record |
|---|---|---|---|---|
| `tt_mm` | 2.3197 | [2.0918, 2.5476] | 6.9592 | `sim/comparator-decision/records/20261121-082755-4d73da9.md` |
| `ss_mm` | 2.3782 | [2.1446, 2.6119] | 7.1346 | `sim/comparator-decision/records/20261121-085613-4d73da9.md` |

**The N=16/N=200 tightness gap DR-002 flagged is closed by the re-measurement.**
The superseded records put N=16 ≈ 22 % below N=200 at `tt_mm` (1.7857 vs
2.1854 mV); the re-qualified pair agrees to 0.7 % (`tt_mm`: 2.3027 vs
2.3197 mV) and 0.8 % (`ss_mm`: 2.3962 vs 2.3782 mV), with each N=16 figure
inside its N=200 counterpart's CI. The small-sample estimate happened to land
low on the old pin; the new-pin estimates do not.

### Post-layout (`--dut extracted`), N=16, seed 1, 27 °C — all five `_mm` corners

| Corner | Schematic σ | Post-layout σ | Ratio | 3σ post-layout | Negative-control **mean** | Record |
|---|---|---|---|---|---|---|
| `tt_mm`/27 °C | 2.3027 mV | 2.4932 mV | 1.083× | 7.4796 mV | 0.6539 mV | `sim/comparator-decision/records/20261122-123618-a22c816.md` |
| `ss_mm`/27 °C | 2.3962 mV | **2.4633 mV** | 1.028× | 7.3899 mV | **0.6610 mV** | `sim/comparator-decision/records/20261122-123619-a22c816.md` |
| **`ff_mm`/27 °C** | 2.0463 mV | **2.5202 mV** | **1.232×** | **7.5606 mV** | **0.6515 mV** | `sim/comparator-decision/records/20261122-123620-a22c816.md` |
| `sf_mm`/27 °C | 2.1357 mV | **2.5143 mV** | 1.177× | 7.5429 mV | **0.6535 mV** | `sim/comparator-decision/records/20261122-123621-a22c816.md` |
| `fs_mm`/27 °C | 2.3863 mV | **2.4651 mV** | 1.033× | 7.3953 mV | **0.6622 mV** | `sim/comparator-decision/records/20261122-123622-a22c816.md` |

Every 3σ column above is `3 ×` the σ each record reports for its own
mismatch-enabled positive control (`stdev = 2.4932 / 2.4633 / 2.5202 / 2.5143 /
2.4651 mV`), re-derived here from the records rather than carried over from any
other document. Every corner's same-seed, mismatch-disabled negative control
reproduced **stdev exactly 0**, so all five records are `Overall: PASS` and the
deck is still isolating mismatch rather than an artifact of the extracted
fragment. Against the superseded 0.42 µm-era post-layout set these σ figures
moved only +1.4 % to +2.4 % (e.g. `tt_mm` 2.4446 → 2.4932 mV) — the layout-term
of the offset budget is essentially unchanged by the geometry/pin bundle, and
the row's movement is dominated by the schematic-side mismatch-model change the
previous section records.

**The corner spread collapses post-layout, and nothing in it is resolved at
N=16.** Schematic-level the five σ figures span 2.0463–2.3962 mV (17.1 %, with
`ss_mm` nominally binding); post-layout they span 2.4633–2.5202 mV — **2.3 %**,
far inside this sample size's own ≈ 18.3 % relative standard error on a stdev.
So the schematic-level ranking does not survive layout (`ff_mm`, the *lowest*
schematic corner, is the highest post-layout; `ss_mm` is second-lowest), but the
honest reading is **not** "`ff_mm` binds" — it is that **this row has no
identifiable worst post-layout corner at N=16**. `ff_mm` is named as the worst
*measured* cell below because a bound comparison must be made against the largest
measured figure, not because the corner is distinguished. Separating the corners
needs the O(100s)-draw post-layout campaign, which does not exist.

**The post-layout penalty is corner-dependent, and largest where the schematic
figure was smallest**: 1.028×–1.232×, worst at `ff_mm` (schematic 2.0463 mV, the
lowest) and smallest at `ss_mm`/`fs_mm` (schematic 2.3962/2.3863 mV, the
highest). Unlike the σ figures themselves these ratios are **paired** — same seed
sequence, same draws, same deck template, only the DUT fragment differs — so
their ordering is better determined than an independent-sample reading of the
18.3 % SE would suggest. Scaling `tt_mm`'s 1.083× anchor onto `ff_mm` would have
under-predicted it by 12 %, which is why this row needed all five corners rather
than one.

**The systematic term is essentially process-independent.** The
mismatch-disabled negative control's stdev is exactly 0 post-layout, but its
**mean** is not: 0.0000 mV on the symmetric schematic fragment, and
**0.6515–0.6622 mV** (a 1.6 % span, mean 0.6564 mV) across all five `_mm`
corners post-layout. That is a **systematic, layout-induced** offset term —
measured at all five corners and barely moved by the re-qualification
(superseded range 0.6350–0.6874 mV) — and it is a quantity this row's σ-only
bounds do not cover at any corner. Because it is corner-robust it is also the
term that makes rows 2 and 3 read the way they do: it is the deterministic
offset that sits behind row 3's polarity-asymmetric sub-2 mV resolution loss
and row 2's all-one-way degenerate cross-checks, and the ~0.656 mV figure those
rows cite is representative of the whole `_mm` set.

### The decision-referred systematic offset ([#66](https://github.com/2AMLogic/sky130-comparator/issues/66), DR-007)

The `offset-bisect` sub-command measures the systematic term at the decision
itself, at the two corners both provenances share — the counterfactual DR-007
ratified as this row's decision-referred companion:

| Corner | Provenance | Decision flip | Reading | Record |
|---|---|---|---|---|
| `tt`/27 °C | schematic | **+0.0391 mV** | both edge brackets [+0.0000, +0.0781] | `sim/comparator-decision/records/20261121-080004-4d73da9.md` |
| `ss`/−40 °C | schematic | **no single flip** | measured NON-DECISION band [−0.8203, +0.8203] mV, width 1.6406 mV — an offset is not the right model at this corner | `sim/comparator-decision/records/20261121-080454-4d73da9.md` |
| `tt`/27 °C | post-layout | **−0.0391 mV** | both edge brackets [−0.0781, +0.0000] | `sim/comparator-decision/records/20261122-123623-a22c816.md` |
| `ss`/−40 °C | post-layout | **+1.9141 mV** | both edge brackets [+1.8750, +1.9531] | `sim/comparator-decision/records/20261122-123624-a22c816.md` |

The `tt`/27 °C pair is the sharp result: the schematic fragment's decision
offset is +0.0391 mV — effectively symmetric — while the extracted fragment's is
−0.0391 mV with the *sign flipped* and the same 0.0781 mV bracket width, so at
nominal the layout-induced systematic term nearly cancels the schematic-side
one and the ~0.656 mV pick-off-referred term above reads mostly as a
pick-off-artifact-plus-layout mix at this corner. At `ss`/−40 °C the schematic
side has no flip at all (a genuine non-decision band, the same floor its row-2
and row-3 counterparts record), while the extracted side flips at +1.9141 mV —
a 1.9 mV decision-referred systematic offset at the slow/cold corner, three
times the `tt`-corner pick-off figure and the largest systematic term this
report carries. DR-012 lists it among the movements past stated tolerance.

### Verdict and caveats

- **Target bound: met** at every measured corner and provenance — worst measured
  cell 7.5606 mV 3σ (`ff_mm`/27 °C, post-layout, N=16 → 3 × 2.5202 mV) against
  ≤ 15 mV, a **1.98×** margin. No other cell in this row is larger: the other
  four post-layout corners give 7.3899–7.5429 mV, and the largest
  schematic-level figure of either sample size is the N=200 `ss_mm` 7.1346 mV.
- **Stretch bound: met** at all five post-layout corners, worst case **1.06×**
  (8 mV / 7.5606 mV) — thinner than the superseded set's 1.08×, entirely because
  the mismatch-model change lifted σ on both provenances. Recorded, not relaxed:
  neither bound is breached, so **this row is not re-opened and no decision
  record is filed for a breach**; the movement itself is DR-012's subject.
- **Post-layout coverage is 5 of 5 `_mm` corners** (all at 27 °C, #80). What
  remains open on this row is **sample size, not corner count**: no post-layout
  large-N campaign exists, and at N=16 no corner-to-corner difference is
  resolved.
- **The systematic term is not bounded by this row.** It is measured at all
  five corners (0.6515–0.6622 mV pick-off-referred; −0.0391/+1.9141 mV
  decision-referred at the two bisected corners); quantifying and dispositioning
  it is [#66](https://github.com/2AMLogic/sky130-comparator/issues/66).
- The pick-off gain falls at every corner — 64.4571 → 35.9676 V/V (1.793×) at
  `tt_mm`, and 1.633×–1.968× across the five (`ff_mm` 64.6023 → 39.1475,
  `sf_mm` 66.0461 → 40.4416, `ss_mm` 53.9582 → 31.8486, `fs_mm` 61.0786 →
  31.0455). That is the common cause this row shares with rows 2 and 3, but it
  does **not** explain the ratio ordering above: the corner that retains the
  *least* gain (`fs_mm`) carries the *smallest* offset ratio, and layout
  *widens* the gain spread (1.224× → 1.303×) while *narrowing* the
  input-referred σ spread.

---

## 2. Input-referred noise

- **Status**: bounds RATIFIED by [DR-002](../spec/decision-records/DR-002-target-spec-ratification.md) §2. Compliance basis RE-OPENED by [DR-006](../spec/decision-records/DR-006-post-layout-noise-headroom-reopened.md) (2026-09-25), then **the target-bound basis RE-CLOSED by that record's Amendment 1** (2026-09-26, issue #83) on the regeneration-inclusive `fs`/125 °C measurement it named as its own closure condition. The ≤ 0.6 mV stretch figure's four-of-seven AC breach is unchanged.
- **Bounds**: target ≤ 1.0 mV rms differential, stretch ≤ 0.6 mV rms differential. **Unchanged** — DR-006 and its Amendment 1 both changed the disposition of the *claim*, not the numbers.
- **Two methods, deliberately**: `run.py noise` is an AC `.noise` analysis on a loop-broken sub-model and is a **lower bound by construction** (it excludes the regeneration phase's own noise). `run.py noise-tran` is the regeneration-inclusive transient-noise Monte Carlo (ngspice has no device-noise transient, so noise is injected as equivalent sources and propagated through the real clocked evaluate trajectory).

### AC loop-broken lower bound — all seven graded corners post-layout

| Corner | Schematic (AC) | Post-layout (AC) | Ratio | vs. ≤ 1.0 mV target | vs. ≤ 0.6 mV stretch | Post-layout record |
|---|---|---|---|---|---|---|
| `sf`/−40 °C | *(no AC counterpart)* | 0.4877 mV rms | — | 2.05× | clears | `sim/comparator-decision/records/20261122-123607-a22c816.md` |
| `ss`/−40 °C | *(no AC counterpart)* | 0.5409 mV rms | — | 1.85× | clears | `sim/comparator-decision/records/20261122-123605-a22c816.md` |
| `fs`/−40 °C | *(no AC counterpart)* | 0.5426 mV rms | — | 1.84× | clears | `sim/comparator-decision/records/20261122-123609-a22c816.md` |
| `tt`/27 °C | 0.5704 mV rms | 0.6553 mV rms | **1.149×** | 1.53× | **breached** | `sim/comparator-decision/records/20261122-123557-a22c816.md` |
| `ff`/125 °C | *(no AC counterpart)* | 0.8486 mV rms | — | 1.18× | **breached** | `sim/comparator-decision/records/20261122-123606-a22c816.md` |
| `sf`/125 °C | *(no AC counterpart)* | 0.8555 mV rms | — | 1.17× | **breached** | `sim/comparator-decision/records/20261122-123608-a22c816.md` |
| `fs`/125 °C | *(no AC counterpart)* | **0.9372 mV rms** | — | **1.07×** | **breached** | `sim/comparator-decision/records/20261122-123610-a22c816.md` |

The single schematic-level AC figure is `tt`/27 °C, 0.5704 mV rms
(`sim/comparator-decision/records/20261121-033551-4d73da9.md`) — **reproduced
exactly by the re-qualification**, like every other deterministic schematic
figure. The seven post-layout AC figures each moved −0.2 % to −0.5 % against
the superseded 0.42 µm-era set: the extraction/pin bundle moved this quantity
barely at all, and the row's shape — hot corners binding, ≈ 1.9× worse at
125 °C than −40 °C — is unchanged. **Six of the seven post-layout corners carry
no ratio, by construction**: DR-005's corner campaign measured `noise-tran` at
the non-`tt` corners, not this AC sub-model, so there is no committed
schematic-level AC counterpart to difference against. Each record states that
rather than inventing a ratio.

### Regeneration-inclusive (`noise-tran`), decision-referred

| Corner | Provenance | σ (mV) | 95 % CI | N (pick-off) | Decision-transition cross-check | Record |
|---|---|---|---|---|---|---|
| `tt`/27 °C | schematic | 0.1457 | [0.1322, 0.1585] | 128 | 0.1401 mV — agrees | `sim/comparator-decision/records/20261121-091933-4d73da9.md` |
| `ss`/−40 °C | schematic | 0.1292 | [0.1144, 0.1416] | 128 | not measurable (overdrives below the corner's resolvable floor) | `sim/comparator-decision/records/20261121-094511-4d73da9.md` |
| `ff`/125 °C | schematic | 0.1554 | [0.1410, 0.1688] | 128 | 0.1693 mV — agrees | `sim/comparator-decision/records/20261121-100659-4d73da9.md` |
| `tt`/27 °C | **post-layout** | **0.1420** | [0.1231, 0.1596] | 64 | 0.2496 mV — **disagrees** (1.8×; 4 seeds/point) | `sim/comparator-decision/records/20261122-123625-a22c816.md` |
| **`fs`/125 °C** | **post-layout** | **0.1951** | [0.1455, 0.2378] | 32 | 0.2409 mV — coarse agreement (1.2×) | `sim/comparator-decision/records/20261122-123628-a22c816.md` |
| **`ss`/−40 °C** | **post-layout** | **0.1051** | [0.0766, 0.1252] | 32 | not measurable (every pair degenerate — resolvable-overdrive floor) | `sim/comparator-decision/records/20261122-123626-a22c816.md` |
| **`ff`/125 °C** | **post-layout** | **0.1560** | [0.1205, 0.1810] | 32 | 0.3672 mV — **disagrees** (2.4×) | `sim/comparator-decision/records/20261122-123627-a22c816.md` |
| **`sf`/−40 °C** | **post-layout** | **0.1013** | [0.0797, 0.1166] | 32 | not measurable (every pair degenerate — all-one-way) | `sim/comparator-decision/records/20261122-123629-a22c816.md` |
| **`sf`/125 °C** | **post-layout** | **0.1852** | [0.1376, 0.2219] | 32 | 0.1244 mV — **disagrees** (0.67×) | `sim/comparator-decision/records/20261122-123630-a22c816.md` |
| **`fs`/−40 °C** | **post-layout** | **0.1119** | [0.0848, 0.1314] | 32 | 0.5266 mV — **disagrees** (4.7×) | `sim/comparator-decision/records/20261122-123631-a22c816.md` |

All seven graded corners carry a post-layout `noise-tran` record, as before.
The re-qualification moved this row's figures more than any other: two
post-layout values fell **past their superseded records' stated 95 % CIs**
(`fs`/125 °C 0.2540 → 0.1951 mV, old CI lower bound 0.1961; `ff`/125 °C
0.1956 → 0.1560 mV, old CI lower bound 0.1606), the two `sf` corners rose
9–10 % (`sf`/−40 °C 0.0929 → 0.1013 mV, +9.0 %; `sf`/125 °C 0.1682 →
0.1852 mV, +10.1 %; the other cold skew, `fs`/−40 °C, rose 3.2 %), and the
schematic figures at `tt`/27 °C and `ss`/−40 °C moved 6–7 % upward
(`tt`/27 °C 0.1362 → 0.1457 mV, +7.0 %; `ss`/−40 °C 0.1213 → 0.1292 mV,
+6.5 %; one schematic figure, `ff`/125 °C 0.1754 → 0.1554 mV, also fell
past its old CI).
DR-012 lists each. The pick-off statistic (a) remains the primary figure in
every record; the cross-check column (b) is stated at its own face below.

**The cross-check no longer corroborates the pick-off at the extracted
corners, and this report does not smooth that over.** The superseded
generation's extracted cross-checks either agreed with (a) (`tt`/27 °C,
`ff`/125 °C within 11 %) or were degenerate for a stated reason. The
re-qualified records' measurable cross-checks disagree with (a) by factors of
0.67×–4.7× at four of five corners, and only `fs`/125 °C (1.2×) is anywhere
near (a). The resolution is in the statistic's own construction: (b) is
estimated from 4 seeds per sign per point, where a single additional decision
flip moves the pair sigma by tens of percent — its resolution is far coarser
than (a)'s CI, and at `fs`/−40 °C the 0.5266 mV figure rests on a 1/4-vs-0/4
split. Two corners are degenerate for the reasons their records derive
(`ss`/−40 °C: the overdrives sit below the corner's resolvable floor;
`sf`/−40 °C: all 16 runs resolved and every one decided the same way — a
deterministic term larger than the sigma-scaled overdrives, row 1's systematic
offset, is setting the outcome). The honest state is: **the
regeneration-inclusive claim rests on the pick-off statistic; the
decision-transition cross-check, at its committed 4-seeds/point budget, no
longer independently corroborates it post-layout, and raising it to a sample
size that could is open work** (the same full-N/chunked-campaign track
[#100](https://github.com/2AMLogic/sky130-comparator/issues/100) blazed).

**Schematic→post-layout ratios, where both exist — now two of three below 1.**
`tt`/27 °C 0.974×, `ss`/−40 °C 0.814×, `ff`/125 °C 1.004×. At `tt` and `ff` the
schematic figure sits inside the post-layout CI; at `ss`/−40 °C it sits just
*above* the post-layout CI's upper bound (0.1292 vs 0.1252) — the first corner
where this report's basis establishes a *negative* schematic→layout change on
this row, in the direction of the layout being quieter. With two corners below
1 and one at 1, the old "suggestive positive penalty" reading is gone; what
replaces it is "unresolved, small in either direction", which is what these
sample sizes support.

**Corner-dependence on the regeneration-inclusive basis: no longer resolved.**
`fs`/125 °C (0.1951 mV) against `tt`/27 °C (0.1420 mV) is 1.374×, but their
95 % CIs **overlap** ([0.1455, 0.2378] vs [0.1231, 0.1596]) at these sample
sizes — the superseded records' non-overlapping-CI corner separation did not
survive the re-measurement, and the honest statement is that the worst-corner
ordering (`fs`/125 °C highest, the cold skews lowest) is suggestive, not
established. The basis still covers all seven graded corners: 0.1013 mV
(`sf`/−40 °C), 0.1051 mV (`ss`/−40 °C), 0.1119 mV (`fs`/−40 °C), 0.1420 mV
(`tt`/27 °C), 0.1560 mV (`ff`/125 °C), 0.1852 mV (`sf`/125 °C), 0.1951 mV
(`fs`/125 °C). The hot corners still bind this row on the regeneration-inclusive
basis exactly as they do on the AC one — that qualitative shape is the one part
of the old corner story that survived.

### Verdict — read this before citing the row

**Every measured figure clears the ratified ≤ 1.0 mV target bound, and the
row's target compliance rests on a direct regeneration-inclusive measurement at
the binding corner rather than on a lower bound plus a headroom argument.**
DR-006's disposition and its Amendment 1, restated against the current records:

1. The **bounds are unchanged** — target ≤ 1.0 mV rms differential, stretch
   ≤ 0.6 mV rms differential, exactly as DR-002 ratified them. Nothing here is
   relaxed, and nothing failed.
2. DR-006 moved the row's **compliance basis RATIFIED-and-clear → RATIFIED,
   basis OPEN**. The bound stayed ratified; what was re-opened is the claim
   that the measured evidence establishes compliance with it. DR-002 §2's
   headroom argument is **superseded by measurement** and must not be cited as
   current justification: it reasoned that the excluded regeneration-phase term
   would have to reach ~0.90 mV rms to threaten the target, and from the
   post-layout worst corner's 0.9372 mV rms it needs only
   `sqrt(1.0² − 0.9372²)` = **0.350 mV rms** in quadrature — 2.6× less headroom
   than the ratification reasoned from, on a figure the methodology states is a
   **lower** bound.
3. **The evidence DR-006 named as what would close it again** — a
   regeneration-inclusive input-referred noise measurement against the extracted
   netlist at **`fs`/125 °C**, the corner that binds the row — exists on the
   current pins
   ([#83](https://github.com/2AMLogic/sky130-comparator/issues/83) made the
   first one; the campaign re-minted it at `f6eeac7`). The current record,
   `sim/comparator-decision/records/20261122-123628-a22c816.md`, measures
   **0.1951 mV rms differential**, which clears the target with **5.13×**
   margin and **4.21×** at its 95 % CI's upper bound. Stated a second way so
   the closure does not rest on one arithmetic: even under a deliberately
   indefensible double-count — adding the *entire* measured figure in
   quadrature on top of the same corner's 0.9372 mV AC lower bound, which
   double-counts because both are dominated by the same preamp input-referred
   source — `sqrt(0.9372² + 0.1951²)` = 0.9573 mV rms is *still* inside the
   target (1.045×; 0.9669 mV / 1.034× at the CI's upper bound). DR-006's own
   0.350 mV allowance is not exceeded either (0.1951 mV is 0.56× of it).
   **The target-bound basis stays RATIFIED-and-clear on the re-qualified
   evidence.**
4. **The stretch figure is breached at four of seven corners** on the AC basis
   (`tt`/27 °C, `ff`/125 °C, `sf`/125 °C, `fs`/125 °C) and cleared at the three
   cold ones — the same four, with figures moved ≤ 0.5 %. **Unchanged, and
   explicitly not re-closed by the transient figures**: the transient basis
   clears the stretch figure at every corner (worst 0.1951 mV, 3.1× under),
   but the two bases disagree, and per `CLAUDE.md` a different method's number
   does not erase a recorded breach. Unchanged in kind; not a compliance
   requirement.

**What still needs a qualifier.** A bare "clears the noise target" *is*
supportable — provided it cites the regeneration-inclusive basis. What must
still carry the **1.07× worst-corner qualifier** is any statement that cites the
**AC lower-bound** figure as the row's basis: that figure is 0.9372 mV rms, and
what #83 changed is that it is not the row's *only* basis at that corner. The
cross-check caveat above is part of the row's honest state as of this rebuild
and must travel with any citation of the regeneration-inclusive basis.

---

## 3. Decision time vs. overdrive

- **Status**: RATIFIED by [DR-005](../spec/decision-records/DR-005-full-corner-campaign.md) (open since DR-002, anchored by DR-004).
- **Bounds**: target ≤ 1.5 ns at 50 mV overdrive, 1.8 V; stretch ≤ 0.8 ns at 50 mV.
- **Method**: `run.py regen` — a transient regeneration-time sweep vs. differential input, read off a `|v(outp)−v(outn)| > 0.5·VDD` threshold crossing. Both bounds are stated at the 50 mV point.

### All seven graded corners, both provenances

| Corner | Schematic @ 50 mV | Post-layout @ 50 mV | Ratio | Sweep points resolved (sch → PL) | Post-layout record |
|---|---|---|---|---|---|
| `tt`/27 °C | 0.4025 ns | 0.5825 ns | 1.447× | 8/8 → 8/8 | `sim/comparator-decision/records/20261122-123611-a22c816.md` |
| `ss`/−40 °C | 0.3575 ns | 0.5225 ns | 1.462× | 7/8 → 6/8 | `sim/comparator-decision/records/20261122-123612-a22c816.md` |
| `ff`/125 °C | 0.4975 ns | 0.6875 ns | 1.382× | 8/8 → 8/8 | `sim/comparator-decision/records/20261122-123614-a22c816.md` |
| `sf`/−40 °C | 0.3475 ns | 0.5125 ns | 1.475× | 8/8 → 8/8 | `sim/comparator-decision/records/20261122-123617-a22c816.md` |
| `sf`/125 °C | 0.4725 ns | 0.6625 ns | 1.402× | 8/8 → 8/8 | `sim/comparator-decision/records/20261122-123615-a22c816.md` |
| `fs`/−40 °C | 0.3725 ns | 0.5375 ns | 1.443× | 8/8 → 8/8 | `sim/comparator-decision/records/20261122-123616-a22c816.md` |
| `fs`/125 °C | 0.5375 ns | **0.7575 ns** | **1.409×** | 8/8 → 8/8 | `sim/comparator-decision/records/20261122-123613-a22c816.md` |

Schematic-level records, in the same corner order:
`sim/comparator-decision/records/20261121-033724-4d73da9.md`,
`sim/comparator-decision/records/20261121-033832-4d73da9.md`,
`sim/comparator-decision/records/20261121-033850-4d73da9.md`,
`sim/comparator-decision/records/20261121-033907-4d73da9.md`,
`sim/comparator-decision/records/20261121-033940-4d73da9.md`,
`sim/comparator-decision/records/20261121-033955-4d73da9.md`,
`sim/comparator-decision/records/20261121-034048-4d73da9.md`.

**The schematic column is byte-for-byte the superseded figures** — the
re-qualification reproduced every schematic `regen` time exactly, so this row's
movement is entirely a post-layout-side effect of the geometry/extraction/pin
bundle. That movement is not uniform: +3.9 % (`sf`/125 °C) to +15.8 %
(`sf`/−40 °C), with the worst corner `fs`/125 °C actually *improving* 2 % while
`tt`/27 °C worsens 9.4 %. The schematic→post-layout ratio band tightened from
1.273×–1.437× to **1.382×–1.475×** — the layout penalty is now more uniform
across corners, and its center of mass moved up.

### Verdict and caveats

- **Target bound: met at all seven corners.** Worst case `fs`/125 °C,
  0.7575 ns against ≤ 1.5 ns — 1.98×.
- **Stretch bound: also met at all seven corners — but at `fs`/125 °C with only
  1.06× margin (5.7 %).** Flagged, not smoothed over. It is the figure that
  would move first if the supply-net parasitic model were refined; the lumped
  star R on `GND`/`VDD` is expected to be *pessimistic*, so the true margin is
  plausibly better than 1.06× — an argument for re-measuring with
  `--distributed-rc`, not for assuming it.
- **Sub-2 mV resolution improved everywhere except `ss`/−40 °C.** Six of seven
  post-layout sweeps now resolve 8/8 (the superseded set resolved 8/8 at two
  corners only); `ss`/−40 °C resolves 6/8 with the +0.50 and +1.00 mV points
  classified **WRONG-POLARITY** — the sign-corrected criterion's bracket on the
  same sub-2 mV polarity asymmetry
  ([#66](https://github.com/2AMLogic/sky130-comparator/issues/66)) this row has
  always carried, now measurably worse at that one corner than the superseded
  set's 3/8 NON-DECISION reading only in *kind* (wrong-polarity decisions, not
  non-decisions). The schematic `ss`/−40 °C sweep keeps its one NON-DECISION
  point at +0.50 mV, as before. Neither bound is touched: both are stated at
  50 mV overdrive, which resolves at every corner and provenance.

---

## 4. Kickback

- **Status**: bound RATIFIED by [DR-002](../spec/decision-records/DR-002-target-spec-ratification.md) (as a bound the then-current design did **not** meet); design first measured compliant by [DR-004](../spec/decision-records/DR-004-comparator-preamp-supersession.md); PVT set completed by DR-005 and post-layout by the extracted-netlist campaign.
- **Bounds**: target ≤ 5 mV disturbance into a 1 kΩ source impedance at the input nodes on a single decision edge; stretch ≤ 2 mV.
- **Method**: `run.py kickback` — `VINP`/`VINN` biased at `VCM` through an explicit 1 kΩ series resistor each (`loaded`), 50 mV differential step, one reset→evaluate edge; peak absolute deviation from each node's own settled pre-edge value. A zero-impedance `ideal` control must collapse to (numerically) zero, or the measurement is not isolating a source-impedance-dependent effect at all.

### All seven graded corners, both provenances

| Corner | Schematic | Post-layout | Ratio | `ideal` control (PL) | Post-layout record |
|---|---|---|---|---|---|
| `tt`/27 °C | 1.8902 mV | 2.2931 mV | 1.213× | 0.0000 mV | `sim/comparator-decision/records/20261122-123556-a22c816.md` |
| `ss`/−40 °C | 1.8605 mV | 2.3602 mV | 1.269× | 0.0000 mV | `sim/comparator-decision/records/20261122-123602-a22c816.md` |
| `ff`/125 °C | 1.7677 mV | 1.9604 mV | 1.109× | 0.0000 mV | `sim/comparator-decision/records/20261122-123604-a22c816.md` |
| `sf`/−40 °C | 2.0208 mV | **2.7204 mV** | **1.346×** | 0.0000 mV | `sim/comparator-decision/records/20261122-123559-a22c816.md` |
| `sf`/125 °C | 1.7837 mV | 2.0079 mV | 1.126× | 0.0000 mV | `sim/comparator-decision/records/20261122-123600-a22c816.md` |
| `fs`/−40 °C | 1.8408 mV | 2.2898 mV | 1.244× | 0.0000 mV | `sim/comparator-decision/records/20261122-123601-a22c816.md` |
| `fs`/125 °C | 1.6091 mV | 1.6932 mV | 1.052× | 0.0000 mV | `sim/comparator-decision/records/20261122-123603-a22c816.md` |

Schematic-level records, in the same corner order:
`sim/comparator-decision/records/20261120-224448-059ee87.md`,
`sim/comparator-decision/records/20261121-034500-4d73da9.md`,
`sim/comparator-decision/records/20261121-033648-4d73da9.md`,
`sim/comparator-decision/records/20261121-034032-4d73da9.md`,
`sim/comparator-decision/records/20261121-034028-4d73da9.md`,
`sim/comparator-decision/records/20261121-034044-4d73da9.md`,
`sim/comparator-decision/records/20261121-034103-4d73da9.md`.

As with `regen`, the schematic column reproduces the superseded figures
exactly. The post-layout column **improved 13–15 % at every corner** — the
0.35 µm resistor re-draw plus the klt 0.8.0/`f6eeac7` extraction/pin bundle
reduced the extracted kickback peak at every corner of the graded set (e.g.
`sf`/−40 °C 3.1989 → 2.7204 mV, `tt`/27 °C 2.6767 → 2.2931 mV). This is the
largest deterministic movement of the campaign and DR-012's headline
improvement.

### Verdict and caveats

- **Target bound: met at all seven corners.** Worst case `sf`/−40 °C,
  2.7204 mV against ≤ 5 mV — 1.84×. The row is **not** re-opened.
- **Stretch figure: breached at five of seven corners, down from six** — the
  re-measurement brought `ff`/125 °C under the 2 mV figure (1.9604 mV, 2 %
  clear), leaving `tt`/27 °C (2.2931), `ss`/−40 °C (2.3602), `sf`/−40 °C
  (2.7204, worst, 36 % over), `sf`/125 °C (2.0079, over by 0.4 %) and
  `fs`/−40 °C (2.2898) breached and `fs`/125 °C (1.6932) clearing as before.
  Recorded, not legislated away — the stretch figure is unchanged and is not a
  compliance requirement. On the schematic side the single stretch breach is
  unchanged: `sf`/−40 °C at 2.0208 mV, over by 1 %.
- **The post-layout penalty is not a corner-independent constant.** It ranges
  1.052×–1.346× and is systematically larger at the **cold** corners
  (`sf`/−40 °C 1.346×, `ss`/−40 °C 1.269×, `fs`/−40 °C 1.244×) than the hot
  ones (`ff`/125 °C 1.109×, `sf`/125 °C 1.126×, `fs`/125 °C 1.052×). Layout
  penalty and schematic worst case therefore **reinforce rather than cancel**.
  Scaling the `tt`/27 °C ratio onto `sf`/−40 °C would have predicted ≈ 2.44 mV
  against the 2.7204 mV measured (10 % low) — which is why this row needed
  measuring at every corner rather than extrapolating from one.
- Historical note, for anyone reading an older claim: this row measured
  144.60 mV at `tt`/27 °C on the DR-001 single-tail design
  (`sim/comparator-decision/records/20260916-060139-f1eb978.md`) and 85.71 mV
  after [DR-003](../spec/decision-records/DR-003-kickback-slew-limited-clock.md)'s
  soft-clock shaper
  (`sim/comparator-decision/records/20260921-185208-bb32850.md`). DR-004's
  topology change is what made the row compliant; those two figures
  characterize superseded designs and are context, not evidence for any row
  above.

---

## 5. Supply / power

- **Status**: **DRAFT / OPEN** — [DR-002](../spec/decision-records/DR-002-target-spec-ratification.md) declined to ratify it because no measurement existed and the clock rate the bound assumes is TBD. It is the one row of the five that is still unratified.
- **DRAFT figures** (*not* bounds — nothing here is ratified, so nothing here can be met or breached): 1.8 V ±10 % core supply (`nfet_01v8`/`pfet_01v8`); ≤ 50 µW average at one decision per clock edge at a **TBD** clock rate; stretch ≤ 20 µW.
- **The supply-flavor half is settled**: sky130 ships no complementary 3.3 V enhancement device pair, so the 1.8 V core flavor is the only complementary-CMOS option at this node. That half of the row is not in question.

### What has actually been measured

| Quantity | Condition | Figure | Source |
|---|---|---|---|
| Static (reset-phase) supply current | `tt`/27 °C, `ss`/−40 °C, `ff`/125 °C | ~51–55 µA | `spec/dr-004-support/evaluate_idd_probe.spice` (DR-004 §Consequences) |
| Evaluate-phase supply current | same three corners | ~344–564 µA | `spec/dr-004-support/evaluate_idd_probe.spice` (DR-004 §Consequences) |
| Implied static power at 1.8 V | — | **~95 µW** | derived from the row above |
| Worst \|I(VDD)\| over the reset settle window, **schematic** | 5-corner reset set | 4.228e−05 … 6.756e−05 A | `sim/comparator-decision/records/20261121-033635-4d73da9.md` |
| Worst \|I(VDD)\| over the reset settle window, **post-layout** | same 5-corner set | 4.941e−05 … 6.728e−05 A | `sim/comparator-decision/records/20261122-123558-a22c816.md` |

The two `reset` records are the only committed evidence records that carry a
supply-current column at all, and they carry it as criterion (4) of a
**pass/fail reset-integrity screen**, not as a power measurement: what that
criterion rests on is the separation between the as-drawn figure and the
GND-tied positive control (8.376e−04 … 1.056e−03 A schematic,
6.292e−04 … 7.698e−04 A post-layout — corner by corner, 12–24× the as-drawn
figure schematically and 9–16× post-layout), not the absolute level. The
schematic→post-layout comparison on the as-drawn column is therefore reported
here as an overlap of ranges, not a ratio: the layout does not move it
materially, and the re-qualification reproduced the schematic column exactly.

### Measured average power and energy per decision (issue #134)

Schematic-derived, `run.py power` on the verified `repo-script` batch route
(`sim` image, ngspice 47, sky130A `f6eeac7dad08`), one record per point at
repository commit `353e129`, 10 ns period (100 MHz), 50 % evaluate duty,
+10 mV differential input about a common mode held at the nominal VCM = 0.9 V (it is not tracked to VDD/2 at the supply endpoints, so the 1.62 V point ran at 55.6 % and the 1.98 V point at 45.5 % of supply), 10 fF per output, first 3 of 8 periods excluded,
all nine points pass the sum (reset + evaluate = full period) and 1 %
convergence self-checks. **These are experiment conditions, not a ratified
clock rate or load**; average power scales as 1/period for a fixed energy per
decision, so the P column is only meaningful at the stated 100 MHz.

| Corner | Temp | Supply | E/period (pJ) | reset (pJ) | evaluate (pJ) | P_avg @ 10 ns (µW) | Convergence | Record |
|---|---|---|---|---|---|---|---|---|
| tt | 27 °C | 1.8 V | 3.7727 | 0.89111 | 2.8816 | 377.27 | 1.13e-05 | `sim/comparator-decision/records/20261124-014428-353e129.md` |
| ss | -40 °C | 1.8 V | 4.4926 | 0.88679 | 3.6059 | 449.26 | 7.99e-06 | `sim/comparator-decision/records/20261124-014445-353e129.md` |
| ff | 125 °C | 1.8 V | 3.263 | 0.88776 | 2.3752 | 326.3 | 1.78e-05 | `sim/comparator-decision/records/20261124-014507-353e129.md` |
| sf | -40 °C | 1.8 V | 3.3212 | 0.95557 | 2.3657 | 332.12 | 9.56e-06 | `sim/comparator-decision/records/20261124-014524-353e129.md` |
| sf | 125 °C | 1.8 V | 3.4619 | 0.8872 | 2.5747 | 346.19 | 1.33e-05 | `sim/comparator-decision/records/20261124-014540-353e129.md` |
| fs | -40 °C | 1.8 V | 4.3202 | 0.87473 | 3.4454 | 432.02 | 1.05e-05 | `sim/comparator-decision/records/20261124-014559-353e129.md` |
| fs | 125 °C | 1.8 V | 3.6186 | 0.81995 | 2.7986 | 361.86 | 1.41e-05 | `sim/comparator-decision/records/20261124-014619-353e129.md` |
| tt | 27 °C | 1.62 V | 2.4767 | 0.67201 | 1.8047 | 247.67 | 1.09e-05 | `sim/comparator-decision/records/20261124-014632-353e129.md` |
| tt | 27 °C | 1.98 V | 5.5066 | 1.1529 | 4.3536 | 550.66 | 1.12e-05 | `sim/comparator-decision/records/20261124-014653-353e129.md` |

Reading, without grading (no bound is ratified, so none is met or breached):

- Energy per decision spans 3.263–4.493 pJ across the seven graded PVT points at 1.8 V (highest `ss`/−40 °C 4.493 pJ; lowest `ff`/125 °C 3.263 pJ).
- Supply endpoints at `tt`/27 °C: 2.477 pJ at 1.62 V and 5.507 pJ at 1.98 V (3.773 pJ at 1.8 V), i.e. energy rises at roughly the fourth power of supply over this ±10 % range (fitted exponent ≈ 3.98: 1.62→1.80 V gives 3.99, 1.80→1.98 V gives 3.97), steeper than the square law of a dynamic-only CV²f expectation — a square law would under-predict the 1.98 V point by about 17 %. The DR-004 preamplifier's static term also scales with supply.
- The reset/evaluate split is ≈ 24 % / 76 % at `tt`/27 °C. The reset share includes clock-edge and node-recharge charge, so it is not directly comparable with the ~95 µW static (DC) figure above.
- Post-layout (`--dut extracted`) average power is **not** measured here; this campaign is schematic-derived only.

### Verdict

- **There is no ratified bound on this row, so there is nothing for the design
  to meet.** This report does not grade it, and no other artifact in this repo
  should either.
- **The DRAFT 50 µW figure is already exceeded by the static term alone**
  (~95 µW at 1.8 V), before any duty-cycle-dependent evaluate term. The DR-004
  preamplifier class costs static current by construction.
- **Schematic average-power and energy-per-decision figures now exist** (table
  above, at an experiment-only 100 MHz), but they cannot be graded: the row's
  "one decision per clock edge at a stated clock rate" framing has no ratified
  clock rate behind it — and that framing itself predates the preamplifier and is superseded in
  substance. Re-anchoring the row is an open ratification decision (DR-004 Open
  items); per `CLAUDE.md` the DRAFT figures are **not** changed to accommodate
  the measurement.
- **Open ratification questions** (stated, not decided; no spec bound or status
  changed): (1) what clock rate and per-output load does the power row assume
  — the measured 3.3–4.5 pJ/decision gives ≈ 330–450 µW at 100 MHz, ≈ 33–45 µW
  at 10 MHz, so the DRAFT 50 µW is met or exceeded depending entirely on that
  choice; (2) is the row defined on energy per decision (clock-rate
  independent) rather than average power; (3) should the row be graded on the
  ±10 % supply endpoints (2.48–5.51 pJ at `tt`/27 °C), and at which corner;
  (4) should the bound be evaluated post-layout.
- Post-layout coverage of this row is limited to the reset-phase current column
  above. No post-layout evaluate-phase or average-power measurement exists.

---

## Prior art — sky130-sar-adc (same-PDK context, not ported)

These three figures are **measurements of another repo's block**, carried here
so the target-spec table's Basis cells can link instead of restating campaign
history (DR-009). They are context on what the same PDK / supply rail can do at
an unoptimized sizing, **not** targets this repo inherited, **not** measurements
of this block, and they appear in no evidence record here. The citations point
at `sim/comparator-decision/records/` and `spec/decision-records/` in the
sky130-sar-adc repository, per that repo's own layout.

- **Offset (row 1 context)** — sky130-sar-adc's own embedded (non-standalone)
  comparator, at a first-pass `W = 4 µm` input-pair sizing with no
  offset-budget target, measured input-referred offset mean **35.24 mV** /
  stdev **97.08 mV** across N = 16 draws (`tt_mm`,
  `sim/comparator-decision/records/` in that repo) — same-PDK prior art on
  mismatch magnitude at an unoptimized sizing.
- **Input-referred noise (row 2 context)** — sky130-sar-adc's DR-004 measured
  **0.7064 mV rms** differential (estimated) for its own embedded-comparator
  sizing at `tt`, 27 °C — same-PDK, same-supply prior art, not a ported spec
  value.
- **Decision time (row 3 context)** — sky130-sar-adc's embedded comparator
  measured **0.5325–1.3975 ns** across a 0.5–50 mV differential sweep
  (`tt`, 27 °C) — same-PDK, same-rail prior art, not a ported number.

---

## Coverage — what is and is not measured post-layout

| Sub-command | Row(s) it feeds | Post-layout corner coverage | Gap |
|---|---|---|---|
| `kickback` | 4 | **7 of 7** graded corners | none |
| `regen` | 3 | **7 of 7** graded corners | none |
| `noise` (AC) | 2 | **7 of 7** graded corners | schematic→post-layout ratio available only at `tt`/27 °C (no AC counterpart elsewhere) |
| `offset` | 1 | **5 of 5** `_mm` corners (all at 27 °C; the four non-`tt_mm` ones by [#80](https://github.com/2AMLogic/sky130-comparator/issues/80)) | none at N=16; no post-layout large-N campaign, and at N=16 the 2.3 % post-layout corner spread is unresolved inside an 18.3 % relative SE |
| `offset-bisect` | 1 (systematic term) | 2 corners (`tt`/27 °C, `ss`/−40 °C), both provenances — the DR-007 row | not a PVT sweep; the other five graded corners carry no decision-referred offset |
| `noise-tran` | 2 | **7 of 7** graded corners | none at the coverage level. Only three of the seven (`tt`/27 °C, `ss`/−40 °C, `ff`/125 °C) have a schematic-level counterpart to form a ratio; the other four correctly report no ratio because no schematic-level record exists there. Separately open: post-layout pick-off N is 32–64 against the schematic side's N=128, the decision-transition cross-check runs at 4 seeds/point and no longer corroborates the pick-off post-layout (see row 2), and no individual ratio is resolved |
| `reset` | 5 (current column) | **5 of 5** of its own corner set | none |

Two coverage facts that apply to every row above:

- **The supply nets have not been re-extracted with `klt extract
  --distributed-rc`.** The single lumped star R on `GND`/`VDD` is 48.7 % of the
  block's total series R and is expected to be pessimistic, so every post-layout
  degradation in this report is an upper bound on the supply-network
  contribution.
- **Superseded post-layout sets.** Two superseded generations of extracted
  records remain in place unedited per the append-only rule and are **not** the
  figures any row above cites. The first (`20260925-065137-87f0013` …
  `20260925-072817-2e2ef84`) was extracted on an **off-pin** klt/klayout build
  whose per-net series resistances differ from the pinned build's by up to
  2.30×. The second (the set this report cited before the 2026-11-23 rebuild —
  `20260925-085247-4694692` through `20261002-004906-e2b808c`) was measured on
  the **0.42 µm** resistor layout at the retired `c6d73a35` PDK pin under
  ngspice-46. Each superseding record names its predecessor in `Supersedes`,
  and [`check-requalify-plan.py`](comparator-decision/check-requalify-plan.py)
  now gates that every plan entry's chain ends at a `f6eeac7` terminal.

## Open items this report carries

These are stated so a reader does not mistake an aggregated report for a closed
one:

- **The mismatch-model movement is recorded, not dispositioned.** The ~30 %
  schematic σ rise (row 1) is a property of the re-pinned PDK's mismatch
  models, measured by the campaign and recorded per corner in DR-012. It
  clears both ratified bounds with the margins stated in row 1; if the
  operator wants it investigated as a model change rather than accepted as a
  re-baseline, that is a new issue's call, not this report's.
- **Row 2's decision-transition cross-check no longer corroborates the pick-off
  statistic post-layout** (four of five measurable corners disagree by
  0.67×–4.7×, at 4 seeds/point). The regeneration-inclusive basis rests on the
  pick-off figure; raising the cross-check to a corroborating sample size is
  open work on the [#100](https://github.com/2AMLogic/sky130-comparator/issues/100)
  chunked-campaign track.
- **Row 2's sample sizes remain the binding open item on the ratios.** Every
  post-layout `noise-tran` figure is N=32–64 pick-off seeds against the
  schematic side's N=128; no individual schematic→layout ratio is resolved,
  and the `fs`/125 °C-vs-`tt`/27 °C corner separation no longer is either.
- **The ≤ 0.6 mV stretch figure on row 2** stays breached at four of seven
  corners on the AC basis. Not a compliance requirement, and deliberately not
  re-closed by the transient figures.
- [#66](https://github.com/2AMLogic/sky130-comparator/issues/66) — the
  layout-induced systematic offset (0.6515–0.6622 mV pick-off-referred across
  the `_mm` set; decision-referred −0.0391 mV at `tt`/27 °C and +1.9141 mV at
  `ss`/−40 °C post-layout) and the sub-2 mV decision-polarity asymmetry (now
  concentrated in `ss`/−40 °C's two WRONG-POLARITY points, row 3). Affects
  rows 1, 2 and 3 as a caveat; touches no bound, all of which are stated at
  50 mV overdrive or on σ alone.
- The Supply / power row's ratification decision (DR-004 Open items) — row 5 has
  no ratified bound and cannot acquire one without a clock-rate framing
  decision.
- **Row 1's post-layout sample size.** Every post-layout figure is N=16, whose
  ≈ 18.3 % relative SE on a stdev is eight times the 2.3 % spread the five
  corners actually show. No post-layout large-N (O(100s)-draw) campaign
  exists, and adding corners cannot substitute for one.
- `klt extract --distributed-rc` on the supply nets, for every row's
  post-layout figure.

## What T1 item 8 `met` establishes — and what it does not

A `"kind": "generic"` evidence envelope's `status: "pass"` is a **claimant
assertion**, not a tool verdict. Nothing in `klt` reads this document. A `met`
item 8 therefore asserts exactly two things:

1. **Aggregation** — one artifact exists that covers all five target-spec rows
   with the evidence record behind each figure named.
2. **Currency** — this document and every record it cites are byte-for-byte the
   ones the envelope was generated against (see below).

It asserts **nothing** about whether any bound is met. Two rows above are live
counter-examples: row 2's compliance basis is re-opened and row 5 has no
ratified bound at all. The full statement of what the citation does and does not
establish is in [`manifests/README.md`](../manifests/README.md).

## Freshness enforcement

T1 item 8's manifest entry is **command-backed**, not file-backed:

```json
"8": { "command": ["python3", "scripts/characterization-envelope.py"] }
```

`klt signoff` runs that script and grades item 8 against *that run's own*
stdout. The script
([`scripts/characterization-envelope.py`](../scripts/characterization-envelope.py)):

1. re-hashes this report and every artifact listed in the
   [Evidence index](#evidence-index) below,
2. compares each against the hash pinned in
   [`sim/characterization-envelope.json`](characterization-envelope.json),
3. checks that the pinned set and the indexed set agree, and that every
   `sim/comparator-decision/records/*.md` path mentioned anywhere in this report
   *and* every artifact cited from a table row inside the numbered measurement
   sections (§1–§5, i.e. any non-record artifact too, such as
   `spec/dr-004-support/evaluate_idd_probe.spice` in §5) appears in the index, and
4. emits the generic envelope with `status: "pass"` only when all of that holds,
   and `status: "fail"` otherwise.

The drift signal is carried by the envelope's **`status` field**, not by the
exit code: `klt signoff` parses a command-backed entry's stdout *before* it
inspects `exit_status`, so a guard that exited nonzero while still printing
`status: "pass"` would grade `met` anyway. Editing this report without running
`python3 scripts/characterization-envelope.py --update` makes item 8 grade
`unmet`/`check_failed`.

This is the reason the entry is command-backed rather than file-backed: `klt`
0.6.0 listed no input-artifact field for the `generic` kind, so a generic
citation always reports `input_verified: null` and its freshness cannot be
anchored by the grader itself (filed upstream as
[2AMLogic/klayout-tools#2403](https://github.com/2AMLogic/klayout-tools/issues/2403)).
Running the hash comparison live, in-repo, closes that gap here without pinning a
`content_hash` the grader would never re-hash.

### Regenerating

```sh
python3 scripts/characterization-envelope.py --update    # re-pin after editing this report
python3 scripts/characterization-envelope.py             # emit the envelope (what klt runs)
python3 scripts/characterization-envelope.py --selftest  # hermetic negative controls
```

Then regenerate the committed signoff record per
[`manifests/README.md`](../manifests/README.md) → "Regenerating the evidence
record".

## Evidence index

Every artifact cited from a table row inside the numbered measurement sections
(§1–§5) below, plus every `sim/comparator-decision/records/*.md` evidence
record this report mentions anywhere else (prose included). The script above
pins each one by SHA-256; adding such a citation without adding it here (or
vice versa) is a `status: "fail"`. Citations in the provenance table at the
top of this report, or in prose outside those sections, are process/tooling
mentions and are not covered by this check.

| Artifact | Row(s) | What it carries |
|---|---|---|
| `sim/comparator-decision/records/20261121-073855-4d73da9.md` | 1 | `offset` N=16 `tt_mm`/27 °C, schematic (re-qualified: σ 1.7857 → 2.3027 mV) |
| `sim/comparator-decision/records/20261121-074337-4d73da9.md` | 1 | `offset` N=16 `ss_mm`/27 °C, schematic (re-qualified) |
| `sim/comparator-decision/records/20261121-074654-4d73da9.md` | 1 | `offset` N=16 `ff_mm`/27 °C, schematic (re-qualified; the lowest schematic corner) |
| `sim/comparator-decision/records/20261121-075012-4d73da9.md` | 1 | `offset` N=16 `sf_mm`/27 °C, schematic (re-qualified) |
| `sim/comparator-decision/records/20261121-075327-4d73da9.md` | 1 | `offset` N=16 `fs_mm`/27 °C, schematic (re-qualified) |
| `sim/comparator-decision/records/20261121-082755-4d73da9.md` | 1 | `offset` N=200 `tt_mm`/27 °C, schematic (re-qualified; now agrees with N=16 to 0.7 %) |
| `sim/comparator-decision/records/20261121-085613-4d73da9.md` | 1 | `offset` N=200 `ss_mm`/27 °C, schematic (re-qualified) |
| `sim/comparator-decision/records/20261122-123618-a22c816.md` | 1 | `offset` N=16 `tt_mm`/27 °C, post-layout — corrected reissue (0.35 µm, `f6eeac7`) |
| `sim/comparator-decision/records/20261122-123619-a22c816.md` | 1 | `offset` N=16 **`ss_mm`/27 °C, post-layout** — corrected reissue |
| `sim/comparator-decision/records/20261122-123620-a22c816.md` | 1 | `offset` N=16 **`ff_mm`/27 °C, post-layout** — corrected reissue; the worst measured cell of this row (2.5202 mV σ → 7.5606 mV 3σ) and the largest post-layout ratio (1.232×) |
| `sim/comparator-decision/records/20261122-123621-a22c816.md` | 1 | `offset` N=16 **`sf_mm`/27 °C, post-layout** — corrected reissue |
| `sim/comparator-decision/records/20261122-123622-a22c816.md` | 1 | `offset` N=16 **`fs_mm`/27 °C, post-layout** — corrected reissue; carries the largest systematic term (0.6622 mV) |
| `sim/comparator-decision/records/20261121-080004-4d73da9.md` | 1 | `offset-bisect` `tt`/27 °C, schematic — decision flip +0.0391 mV (the DR-007 / #66 counterfactual) |
| `sim/comparator-decision/records/20261121-080454-4d73da9.md` | 1 | `offset-bisect` `ss`/−40 °C, schematic — no single flip; non-decision band [−0.8203, +0.8203] mV |
| `sim/comparator-decision/records/20261122-123623-a22c816.md` | 1 | `offset-bisect` `tt`/27 °C, post-layout — decision flip −0.0391 mV |
| `sim/comparator-decision/records/20261122-123624-a22c816.md` | 1 | `offset-bisect` `ss`/−40 °C, post-layout — decision flip +1.9141 mV, the largest systematic term this report carries |
| `sim/comparator-decision/records/20261121-033551-4d73da9.md` | 2 | `noise` AC `tt`/27 °C, schematic (re-qualified; reproduced exactly) |
| `sim/comparator-decision/records/20261122-123557-a22c816.md` | 2 | `noise` AC `tt`/27 °C, post-layout — corrected reissue |
| `sim/comparator-decision/records/20261122-123605-a22c816.md` | 2 | `noise` AC `ss`/−40 °C, post-layout — corrected reissue |
| `sim/comparator-decision/records/20261122-123606-a22c816.md` | 2 | `noise` AC `ff`/125 °C, post-layout — corrected reissue |
| `sim/comparator-decision/records/20261122-123607-a22c816.md` | 2 | `noise` AC `sf`/−40 °C, post-layout — corrected reissue |
| `sim/comparator-decision/records/20261122-123608-a22c816.md` | 2 | `noise` AC `sf`/125 °C, post-layout — corrected reissue |
| `sim/comparator-decision/records/20261122-123609-a22c816.md` | 2 | `noise` AC `fs`/−40 °C, post-layout — corrected reissue |
| `sim/comparator-decision/records/20261122-123610-a22c816.md` | 2 | `noise` AC `fs`/125 °C, post-layout — corrected reissue; the corner that binds the row |
| `sim/comparator-decision/records/20261121-091933-4d73da9.md` | 2 | `noise-tran` `tt`/27 °C, schematic (re-qualified) |
| `sim/comparator-decision/records/20261121-094511-4d73da9.md` | 2 | `noise-tran` `ss`/−40 °C, schematic (re-qualified) |
| `sim/comparator-decision/records/20261121-100659-4d73da9.md` | 2 | `noise-tran` `ff`/125 °C, schematic (re-qualified; fell past its superseded record's CI) |
| `sim/comparator-decision/records/20261122-123625-a22c816.md` | 2 | `noise-tran` `tt`/27 °C, post-layout — corrected reissue (N=64/4) |
| `sim/comparator-decision/records/20261122-123628-a22c816.md` | 2 | `noise-tran` **`fs`/125 °C, post-layout** — corrected reissue; DR-006's closure condition on the current pins |
| `sim/comparator-decision/records/20261122-123626-a22c816.md` | 2 | `noise-tran` **`ss`/−40 °C, post-layout** — corrected reissue (N=32/4); the schematic counterpart now sits above its CI |
| `sim/comparator-decision/records/20261122-123627-a22c816.md` | 2 | `noise-tran` **`ff`/125 °C, post-layout** — corrected reissue; fell past its superseded record's CI |
| `sim/comparator-decision/records/20261122-123629-a22c816.md` | 2 | `noise-tran` **`sf`/−40 °C, post-layout** — corrected reissue; no schematic-level counterpart exists |
| `sim/comparator-decision/records/20261122-123630-a22c816.md` | 2 | `noise-tran` **`sf`/125 °C, post-layout** — corrected reissue; no schematic-level counterpart exists |
| `sim/comparator-decision/records/20261122-123631-a22c816.md` | 2 | `noise-tran` **`fs`/−40 °C, post-layout** — corrected reissue; no schematic-level counterpart exists; its cross-check is the 0.5266 mV row-2 caveat's sharpest case |
| `sim/comparator-decision/records/20261121-033724-4d73da9.md` | 3 | `regen` `tt`/27 °C, schematic (re-qualified; reproduced exactly) |
| `sim/comparator-decision/records/20261121-033832-4d73da9.md` | 3 | `regen` `ss`/−40 °C, schematic (re-qualified; 7/8, the +0.50 mV point NON-DECISION) |
| `sim/comparator-decision/records/20261121-033850-4d73da9.md` | 3 | `regen` `ff`/125 °C, schematic (re-qualified) |
| `sim/comparator-decision/records/20261121-033907-4d73da9.md` | 3 | `regen` `sf`/−40 °C, schematic (re-qualified) |
| `sim/comparator-decision/records/20261121-033940-4d73da9.md` | 3 | `regen` `sf`/125 °C, schematic (re-qualified) |
| `sim/comparator-decision/records/20261121-033955-4d73da9.md` | 3 | `regen` `fs`/−40 °C, schematic (re-qualified) |
| `sim/comparator-decision/records/20261121-034048-4d73da9.md` | 3 | `regen` `fs`/125 °C, schematic (re-qualified) |
| `sim/comparator-decision/records/20261122-123611-a22c816.md` | 3 | `regen` `tt`/27 °C, post-layout — corrected reissue |
| `sim/comparator-decision/records/20261122-123612-a22c816.md` | 3 | `regen` `ss`/−40 °C, post-layout — corrected reissue; 6/8 with two WRONG-POLARITY points |
| `sim/comparator-decision/records/20261122-123613-a22c816.md` | 3 | `regen` `fs`/125 °C, post-layout — corrected reissue; the slowest corner |
| `sim/comparator-decision/records/20261122-123614-a22c816.md` | 3 | `regen` `ff`/125 °C, post-layout — corrected reissue |
| `sim/comparator-decision/records/20261122-123615-a22c816.md` | 3 | `regen` `sf`/125 °C, post-layout — corrected reissue |
| `sim/comparator-decision/records/20261122-123616-a22c816.md` | 3 | `regen` `fs`/−40 °C, post-layout — corrected reissue |
| `sim/comparator-decision/records/20261122-123617-a22c816.md` | 3 | `regen` `sf`/−40 °C, post-layout — corrected reissue |
| `sim/comparator-decision/records/20261120-224448-059ee87.md` | 4 | `kickback` `tt`/27 °C, schematic (re-qualified; reproduced exactly) |
| `sim/comparator-decision/records/20261121-034500-4d73da9.md` | 4 | `kickback` `ss`/−40 °C, schematic (re-qualified) |
| `sim/comparator-decision/records/20261121-033648-4d73da9.md` | 4 | `kickback` `ff`/125 °C, schematic (re-qualified) |
| `sim/comparator-decision/records/20261121-034032-4d73da9.md` | 4 | `kickback` `sf`/−40 °C, schematic (re-qualified; the only schematic stretch breach, by 1 %) |
| `sim/comparator-decision/records/20261121-034028-4d73da9.md` | 4 | `kickback` `sf`/125 °C, schematic (re-qualified) |
| `sim/comparator-decision/records/20261121-034044-4d73da9.md` | 4 | `kickback` `fs`/−40 °C, schematic (re-qualified) |
| `sim/comparator-decision/records/20261121-034103-4d73da9.md` | 4 | `kickback` `fs`/125 °C, schematic (re-qualified) |
| `sim/comparator-decision/records/20261122-123556-a22c816.md` | 4 | `kickback` `tt`/27 °C, post-layout — corrected reissue |
| `sim/comparator-decision/records/20261122-123559-a22c816.md` | 4 | `kickback` `sf`/−40 °C, post-layout — corrected reissue; the worst corner |
| `sim/comparator-decision/records/20261122-123600-a22c816.md` | 4 | `kickback` `sf`/125 °C, post-layout — corrected reissue; 0.4 % over the stretch figure |
| `sim/comparator-decision/records/20261122-123601-a22c816.md` | 4 | `kickback` `fs`/−40 °C, post-layout — corrected reissue |
| `sim/comparator-decision/records/20261122-123603-a22c816.md` | 4 | `kickback` `fs`/125 °C, post-layout — corrected reissue |
| `sim/comparator-decision/records/20261122-123602-a22c816.md` | 4 | `kickback` `ss`/−40 °C, post-layout — corrected reissue |
| `sim/comparator-decision/records/20261122-123604-a22c816.md` | 4 | `kickback` `ff`/125 °C, post-layout — corrected reissue; now clears the stretch figure (1.9604 mV) |
| `sim/comparator-decision/records/20260916-060139-f1eb978.md` | 4 | `kickback` `tt`/27 °C on the **superseded** DR-001 single-tail design (144.60 mV) — historical context only |
| `sim/comparator-decision/records/20260921-185208-bb32850.md` | 4 | `kickback` `tt`/27 °C after DR-003's soft-clock shaper (85.71 mV) — historical context only |
| `sim/comparator-decision/records/20261121-033635-4d73da9.md` | 5 | `reset` 5-corner screen, schematic (re-qualified) — the \|I(VDD)\| column |
| `sim/comparator-decision/records/20261122-123558-a22c816.md` | 5 | `reset` 5-corner screen, post-layout — corrected reissue; the \|I(VDD)\| column |
| `sim/comparator-decision/records/20261124-014428-353e129.md` | 5 | `power` `tt`/27 °C at 1.8 V, schematic — 3.7727 pJ per decision (batch route, issue #134) |
| `sim/comparator-decision/records/20261124-014445-353e129.md` | 5 | `power` `ss`/-40 °C at 1.8 V, schematic — 4.4926 pJ per decision (batch route, issue #134) |
| `sim/comparator-decision/records/20261124-014507-353e129.md` | 5 | `power` `ff`/125 °C at 1.8 V, schematic — 3.263 pJ per decision (batch route, issue #134) |
| `sim/comparator-decision/records/20261124-014524-353e129.md` | 5 | `power` `sf`/-40 °C at 1.8 V, schematic — 3.3212 pJ per decision (batch route, issue #134) |
| `sim/comparator-decision/records/20261124-014540-353e129.md` | 5 | `power` `sf`/125 °C at 1.8 V, schematic — 3.4619 pJ per decision (batch route, issue #134) |
| `sim/comparator-decision/records/20261124-014559-353e129.md` | 5 | `power` `fs`/-40 °C at 1.8 V, schematic — 4.3202 pJ per decision (batch route, issue #134) |
| `sim/comparator-decision/records/20261124-014619-353e129.md` | 5 | `power` `fs`/125 °C at 1.8 V, schematic — 3.6186 pJ per decision (batch route, issue #134) |
| `sim/comparator-decision/records/20261124-014632-353e129.md` | 5 | `power` `tt`/27 °C at 1.62 V, schematic — 2.4767 pJ per decision (batch route, issue #134) |
| `sim/comparator-decision/records/20261124-014653-353e129.md` | 5 | `power` `tt`/27 °C at 1.98 V, schematic — 5.5066 pJ per decision (batch route, issue #134) |
| `spec/dr-004-support/evaluate_idd_probe.spice` | 5 | the reset/evaluate supply-current probe deck behind DR-004's ~95 µW static figure |
| `spec/decision-records/DR-002-target-spec-ratification.md` | 1–5 | the ratification disposition every row's Status cell reports |
| `spec/decision-records/DR-004-comparator-preamp-supersession.md` | 1–5 | the topology supersession every figure above is measured at |
| `spec/decision-records/DR-003-kickback-slew-limited-clock.md` | 4 | the mitigation pass between the two superseded kickback figures above |
| `spec/decision-records/DR-005-full-corner-campaign.md` | 1–4 | the full-corner campaign; ratifies row 3 |
| `spec/decision-records/DR-006-post-layout-noise-headroom-reopened.md` | 2 | re-opens row 2's compliance basis; Amendment 1 re-closes it |
| `spec/decision-records/DR-007-systematic-decision-offset-row.md` | 1 | ratifies the decision-referred systematic-offset companion row (the `offset-bisect` records above) |
