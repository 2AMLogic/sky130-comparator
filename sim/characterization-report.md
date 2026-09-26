# Characterization report — sky130-comparator

The one aggregated, current artifact T1 item 8 names: every target-spec row,
its ratification status, its bounds, the measured figure at every condition
that has one, and the committed evidence record each figure rests on.

This document is the evidence cited for **T1 item 8** in
[`manifests/sky130-comparator.json`](../manifests/sky130-comparator.json). See
[`manifests/README.md`](../manifests/README.md) → "Item 8 — the characterization
report, and what its `met` row does not establish" for what that citation does
and does not prove.

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
| PDK | sky130A @ open_pdks `c6d73a35f524070e85faff4a6a9eef49553ebc2b` ([`sim/pdk.json`](pdk.json)) |
| Simulator | ngspice-46 ([`sim/toolchain.json`](toolchain.json)) |
| Harness | `sim/harness` 0.1.0 |
| Schematic DUT | `design/comparator.sch` → `./design/netlist.sh` → `sim/comparator-decision/testbench/comparator_core.spice` |
| Post-layout DUT | `layout/comparator.gds` → `klt extract --parasitics` → `layout/comparator.pex.spice`, extracted under **`klayout-tools==0.6.0` on `klayout==0.30.10`** (asserted by `layout/extract_pex.py`; extracted per-net series R is **not** stable across klt/klayout builds — up to 2.30× apart on this block) |
| Topology | DR-004 static preamplifier + StrongARM latch, with DR-003's soft-clock shaper on the clock port |

**Graded PVT corner set** (the seven `--dut extracted` rows below use it):
`tt`/27 °C, `ss`/−40 °C, `ff`/125 °C, `sf`/−40 °C, `sf`/125 °C, `fs`/−40 °C,
`fs`/125 °C. The Offset sigma row runs on the five `_mm` local-mismatch corners
at 27 °C instead (`tt_mm`, `ss_mm`, `ff_mm`, `sf_mm`, `fs_mm`) because mismatch
sampling is not a PVT axis; the reset-integrity screen behind the Supply/power
row's current column uses its own five-point set (`tt`/27 °C, `ss`/−40 °C,
`ss`/125 °C, `ff`/−40 °C, `ff`/125 °C). Each row states which set it used.

**Post-layout parasitic model, where it is coarse.** The extraction is a single
lumped star R per net. `GND` (6.76 kΩ) and `VDD` (2.36 kΩ) together carry 52.0 %
of the block's 17.52 kΩ total series R, where the real drawn supply is a wide
low-impedance shape. Every post-layout degradation below is therefore an **upper
bound on the supply-network contribution**, not a best estimate of it. See
[`sim/comparator-decision/README.md`](comparator-decision/README.md) →
"Parasitic model, and where it is coarse".

## Summary — the five target-spec rows

| # | Row | Status | Target | Stretch | Worst measured (post-layout unless noted) | Target met? | Stretch met? |
|---|---|---|---|---|---|---|---|
| 1 | Offset sigma | RATIFIED (DR-002; coverage by DR-005) | ≤ 15 mV, 3σ | ≤ 8 mV, 3σ | 7.4388 mV 3σ (`ff_mm`/27 °C, N=16) | **yes** (2.02×) | yes (1.08×) |
| 2 | Input-referred noise | RATIFIED (DR-002); compliance basis re-opened (DR-006), **RE-CLOSED** (DR-006 Amendment 1, #83) | ≤ 1.0 mV rms diff | ≤ 0.6 mV rms diff | 0.2540 mV rms regeneration-inclusive (`fs`/125 °C); 0.9423 mV rms on the AC **lower bound**, same corner | **yes** (3.94×; 3.32× at the CI's upper bound) — on the regeneration-inclusive basis; see row 2 | no (breached at 4 of 7 on the AC basis) |
| 3 | Decision time vs. overdrive | RATIFIED (DR-005) | ≤ 1.5 ns @ 50 mV | ≤ 0.8 ns @ 50 mV | 0.7725 ns (`fs`/125 °C) | **yes** (1.94×) | yes, but 1.04× |
| 4 | Kickback | RATIFIED (DR-002 bound; DR-004 first compliant design) | ≤ 5 mV into 1 kΩ | ≤ 2 mV | 3.1989 mV (`sf`/−40 °C) | **yes** (1.56×) | no (breached at 6 of 7) |
| 5 | Supply / power | **DRAFT / OPEN** (DR-002) | *(draft)* ≤ 50 µW avg at a TBD clock rate | *(draft)* ≤ 20 µW | ~95 µW static at 1.8 V | **no ratified bound exists** | — |

Row 2's "target met?" cell says "yes" only on the **regeneration-inclusive**
basis, and only since #83. Until then it deliberately did not: every measured
figure cleared the ratified target bound, but DR-006 had retired the argument
the ratification rested on. The measurement DR-006 named has now been made, so
the row's target compliance rests on a direct regeneration-inclusive figure at
the binding corner rather than on a lower bound plus a headroom argument. Two
qualifiers survive and both matter: a statement citing the **AC lower-bound**
figure instead still carries that figure's 1.06× worst-corner margin, and the
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
| `tt_mm` | 1.7857 | 5.3571 | 0 exactly | `sim/comparator-decision/records/20260922-065300-e084b55.md` |
| `ss_mm` | 1.8244 | 5.4732 | 0 exactly | `sim/comparator-decision/records/20260922-173622-e23c509.md` |
| `ff_mm` | 1.5954 | 4.7862 | 0 exactly | `sim/comparator-decision/records/20260922-174326-e23c509.md` |
| `sf_mm` | 1.6706 | 5.0118 | 0 exactly | `sim/comparator-decision/records/20260922-174831-e23c509.md` |
| `fs_mm` | 1.8218 | 5.4654 | 0 exactly | `sim/comparator-decision/records/20260922-175152-e23c509.md` |

The corner ranking sits inside the N=16 relative standard error (≈ 18 % on a
stdev); `ss_mm` is nominally binding. That ranking does **not** survive layout —
see the post-layout table below, where `ss_mm` is second-lowest.

### Schematic-level, N=200 (the yield-fraction campaigns)

| Corner | σ (mV) | 95 % CI on σ | 3σ (mV) | Record |
|---|---|---|---|---|
| `tt_mm` | 2.1854 | [1.9707, 2.4001] | 6.5562 | `sim/comparator-decision/records/20260922-191034-e23c509.md` |
| `ss_mm` | 2.2353 | [2.0157, 2.4549] | 6.7059 | `sim/comparator-decision/records/20260922-202434-e026012.md` |

The N=200 estimates sit ≈ 22 % above the N=16 figures — the small-sample
estimate happened to land low, which is the tightness gap DR-002's Open items
flagged.

### Post-layout (`--dut extracted`), N=16, seed 1, 27 °C — all five `_mm` corners

| Corner | Schematic σ | Post-layout σ | Ratio | 3σ post-layout | Negative-control **mean** | Record |
|---|---|---|---|---|---|---|
| `tt_mm`/27 °C | 1.7857 mV | 2.4446 mV | 1.369× | 7.3338 mV | 0.6547 mV | `sim/comparator-decision/records/20260925-112809-4694692.md` |
| `ss_mm`/27 °C | 1.8244 mV | **2.4133 mV** | 1.323× | 7.2400 mV | **0.6780 mV** | `sim/comparator-decision/records/20260926-022304-5b02508.md` |
| **`ff_mm`/27 °C** | 1.5954 mV | **2.4796 mV** | **1.554×** | **7.4388 mV** | **0.6355 mV** | `sim/comparator-decision/records/20260926-032735-85c288e.md` |
| `sf_mm`/27 °C | 1.6706 mV | **2.4794 mV** | 1.484× | 7.4381 mV | **0.6350 mV** | `sim/comparator-decision/records/20260926-034704-dfaee77.md` |
| `fs_mm`/27 °C | 1.8218 mV | **2.4078 mV** | 1.322× | 7.2235 mV | **0.6874 mV** | `sim/comparator-decision/records/20260926-041419-38f6227.md` |

The four non-`tt_mm` rows landed with
[#80](https://github.com/2AMLogic/sky130-comparator/issues/80) and close the
coverage gap DR-005 and issue #64 left open. Every 3σ column above is `3 ×` the
σ each record reports for its own mismatch-enabled positive control
(`stdev = 2.44462 / 2.41332 / 2.47959 / 2.47938 / 2.40783 mV`), re-derived here
from the records rather than carried over from any other document. Every corner's
same-seed, mismatch-disabled negative control reproduced **stdev exactly 0**, so
all five records are `Overall: PASS` and the deck is still isolating mismatch
rather than an artifact of the extracted fragment.

**The corner spread collapses post-layout, and nothing in it is resolved at
N=16.** Schematic-level the five σ figures span 1.5954–1.8244 mV (14.4 %, with
`ss_mm` nominally binding); post-layout they span 2.4078–2.4796 mV — **3.0 %**,
far inside this sample size's own ≈ 18.3 % relative standard error on a stdev. So
the schematic-level ranking does not survive layout (`ff_mm`, the *lowest*
schematic corner, is the highest post-layout; `ss_mm` is second-lowest), but the
honest reading is **not** "`ff_mm` binds" — it is that **this row has no
identifiable worst post-layout corner at N=16**. `ff_mm` is named as the worst
*measured* cell below because a bound comparison must be made against the largest
measured figure, not because the corner is distinguished. Separating the corners
needs the O(100s)-draw post-layout campaign, which does not exist.

**The post-layout penalty is corner-dependent, and largest where the schematic
figure was smallest**: 1.322×–1.554×, worst at `ff_mm` (schematic 1.5954 mV, the
lowest) and smallest at `fs_mm`/`ss_mm` (schematic 1.8218/1.8244 mV, the
highest). Unlike the σ figures themselves these ratios are **paired** — same seed
sequence, same draws, same deck template, only the DUT fragment differs — so
their ordering is better determined than an independent-sample reading of the
18.3 % SE would suggest. Scaling `tt_mm`'s 1.369× anchor onto `ff_mm` would have
under-predicted it by 12 %, which is why this row needed all five corners rather
than one.

**The systematic term is essentially process-independent.** The
mismatch-disabled negative control's stdev is exactly 0 post-layout, but its
**mean** is not: 0.0000 mV on the symmetric schematic fragment, and
**0.6350–0.6874 mV** (an 8.3 % span, mean 0.6581 mV) across all five `_mm`
corners post-layout. That is a **systematic, layout-induced** offset term — first
measured at `tt_mm` (0.6547 mV) and now shown to barely move with process — and
it is a quantity this row's σ-only bounds do not cover at any corner. Because it
is corner-robust it is also the term that makes rows 2 and 3 read the way they
do: it is the deterministic offset that swamps the sub-mV overdrives in row 2's
degenerate post-layout `noise-tran` cross-checks and sits behind row 3's
polarity-asymmetric sub-20 mV resolution loss, and the 0.6547 mV figure those
rows cite is representative of the whole `_mm` set rather than of `tt_mm` alone.

### Verdict and caveats

- **Target bound: met** at every measured corner and provenance — worst measured
  cell 7.4388 mV 3σ (`ff_mm`/27 °C, post-layout, N=16 → 3 × 2.47959 mV) against
  ≤ 15 mV, a **2.02×** margin. No other cell in this row is larger: the other
  four post-layout corners give 7.2235–7.4381 mV, the post-layout `tt_mm` anchor
  7.3338 mV, and the largest schematic-level figure of either sample size is the
  N=200 `ss_mm` 6.7059 mV.
- **Stretch bound: met** at all five post-layout corners, worst case **1.08×**
  (8 mV / 7.4388 mV) — down from 1.09× when `tt_mm` was the only post-layout
  corner, and from 1.49× schematic-level. Recorded, not relaxed: neither bound is
  breached, so **this row is not re-opened and no decision record is filed**.
- **Post-layout coverage is now 5 of 5 `_mm` corners** (all at 27 °C, #80),
  closing the four-corner skip DR-005/#64 recorded as a deliberate cost decision
  (`offset` is the campaign's most expensive sub-command — ~37 decks and, as #80
  measured, 19–64 min per corner serially on a contended shared dispatch host).
  What remains open on this row is **sample size, not corner count**: no
  post-layout large-N campaign exists, and at N=16 no corner-to-corner difference
  is resolved.
- **The systematic term is not bounded by this row.** It is now measured at all
  five corners (0.6350–0.6874 mV) rather than one; quantifying and dispositioning
  it is [#66](https://github.com/2AMLogic/sky130-comparator/issues/66).
- The pick-off gain falls at every corner — 64.4571 → 30.4600 V/V (2.116×) at
  `tt_mm`, and 1.808×–2.373× across the five (`ff_mm` 64.6023 → 35.7356,
  `sf_mm` 66.0461 → 35.9542, `ss_mm` 53.9582 → 26.0386, `fs_mm` 61.0786 →
  25.7414). That is the common cause this row shares with rows 2 and 3, but it
  does **not** explain the ratio ordering above: the two corners that retain the
  most gain (`ff_mm`, `sf_mm`) carry the *largest* offset ratios, and layout
  *widens* the gain spread (1.224× → 1.397×) while *narrowing* the
  input-referred σ spread.

---

## 2. Input-referred noise

- **Status**: bounds RATIFIED by [DR-002](../spec/decision-records/DR-002-target-spec-ratification.md) §2. Compliance basis RE-OPENED by [DR-006](../spec/decision-records/DR-006-post-layout-noise-headroom-reopened.md) (2026-09-25), then **the target-bound basis RE-CLOSED by that record's Amendment 1** (2026-09-26, issue #83) on the regeneration-inclusive `fs`/125 °C measurement it named as its own closure condition. The ≤ 0.6 mV stretch figure's four-of-seven AC breach is unchanged.
- **Bounds**: target ≤ 1.0 mV rms differential, stretch ≤ 0.6 mV rms differential. **Unchanged** — DR-006 and its Amendment 1 both changed the disposition of the *claim*, not the numbers.
- **Two methods, deliberately**: `run.py noise` is an AC `.noise` analysis on a loop-broken sub-model and is a **lower bound by construction** (it excludes the regeneration phase's own noise). `run.py noise-tran` is the regeneration-inclusive transient-noise Monte Carlo (ngspice-46 has no device-noise transient, so noise is injected as equivalent sources and propagated through the real clocked evaluate trajectory).

### AC loop-broken lower bound — all seven graded corners post-layout

| Corner | Schematic (AC) | Post-layout (AC) | Ratio | vs. ≤ 1.0 mV target | vs. ≤ 0.6 mV stretch | Post-layout record |
|---|---|---|---|---|---|---|
| `sf`/−40 °C | *(no AC counterpart)* | 0.4886 mV rms | — | 2.05× | clears | `sim/comparator-decision/records/20260925-192745-bec714a.md` |
| `ss`/−40 °C | *(no AC counterpart)* | 0.5429 mV rms | — | 1.84× | clears | `sim/comparator-decision/records/20260925-192710-bec714a.md` |
| `fs`/−40 °C | *(no AC counterpart)* | 0.5447 mV rms | — | 1.84× | clears | `sim/comparator-decision/records/20260925-192818-bec714a.md` |
| `tt`/27 °C | 0.5704 mV rms | 0.6576 mV rms | **1.153×** | 1.52× | **breached** | `sim/comparator-decision/records/20260925-112827-4694692.md` |
| `ff`/125 °C | *(no AC counterpart)* | 0.8521 mV rms | — | 1.17× | **breached** | `sim/comparator-decision/records/20260925-192728-bec714a.md` |
| `sf`/125 °C | *(no AC counterpart)* | 0.8590 mV rms | — | 1.16× | **breached** | `sim/comparator-decision/records/20260925-192801-bec714a.md` |
| `fs`/125 °C | *(no AC counterpart)* | **0.9423 mV rms** | — | **1.06×** | **breached** | `sim/comparator-decision/records/20260925-192836-bec714a.md` |

The single schematic-level AC figure is `tt`/27 °C, 0.5704 mV rms
(`sim/comparator-decision/records/20260922-065534-e084b55.md`). **Six of the
seven post-layout corners carry no ratio, by construction**: DR-005's corner
campaign measured `noise-tran` at the non-`tt` corners, not this AC sub-model,
so there is no committed schematic-level AC counterpart to difference against.
Each record states that rather than inventing a ratio.

The hot corners bind this row — the post-layout AC figure is ≈ 1.9× worse at
125 °C than at −40 °C, which a `tt`/27 °C-only basis could not have revealed.

### Regeneration-inclusive (`noise-tran`), decision-referred

| Corner | Provenance | σ (mV) | 95 % CI | N (pick-off) | Decision-transition cross-check | Record |
|---|---|---|---|---|---|---|
| `tt`/27 °C | schematic | 0.1362 | [0.1216, 0.1493] | 128 | 0.1342 mV — agrees | `sim/comparator-decision/records/20260922-192722-e23c509.md` |
| `ss`/−40 °C | schematic | 0.1213 | [0.1084, 0.1335] | 128 | not measurable (overdrives below the corner's resolvable floor) | `sim/comparator-decision/records/20260922-205857-ebea4e2.md` |
| `ff`/125 °C | schematic | 0.1754 | [0.1594, 0.1905] | 128 | 0.1515 mV — agrees | `sim/comparator-decision/records/20260923-010427-ebea4e2.md` |
| `tt`/27 °C | **post-layout** | **0.1448** | [0.1224, 0.1641] | 64 | degenerate — a *deterministic* term sets the outcome | `sim/comparator-decision/records/20260925-214740-81f594b.md` |
| **`fs`/125 °C** | **post-layout** | **0.2540** | [0.1961, 0.3009] | 32 | degenerate — same all-one-way cause | `sim/comparator-decision/records/20260926-055806-3034c41.md` |
| **`ss`/−40 °C** | **post-layout** | **0.1382** | [0.1046, 0.1666] | 32 | degenerate — resolvable-overdrive floor, as on the schematic side | `sim/comparator-decision/records/20260926-110218-b64004b.md` |
| **`ff`/125 °C** | **post-layout** | **0.1956** | [0.1606, 0.2212] | 32 | **0.2175 mV — measurable, and agrees** | `sim/comparator-decision/records/20260926-102605-b64004b.md` |

**Three corners now carry a schematic→post-layout ratio, none of them resolved,
and all three pointing the same way**: 1.063× (`tt`/27 °C), 1.139× (`ss`/−40 °C,
[#89](https://github.com/2AMLogic/sky130-comparator/issues/89)) and 1.115×
(`ff`/125 °C, #89). At every one of the three the schematic figure sits
**inside** the post-layout 95 % CI, so no corner on its own establishes that this
quantity moved with the layout — each record establishes the post-layout figure
*and its uncertainty*. What the three together add is a **sign**: three
independent corners, all above 1, in a 1.06–1.14× band (one-sided sign-test
p = 0.125). Read that as suggestive corroboration that the post-layout penalty
on this row is small and positive, not as a measurement of it. Resolving it
needs N, not more corners. Post-layout sample sizes are smaller than the
schematic side's N=128 for wall-clock reasons stated on each record's own face.

The `ss`/−40 °C and `ff`/125 °C rows exist at all only because #89 also fixed
`run.py`'s `SCHEMATIC_BASELINES`, which carried a `noise-tran` anchor at
`tt`/27 °C alone: before that fix a post-layout run at either corner printed "no
committed schematic-level record exists" while the counterpart sat in
`records/`.

**`ff`/125 °C is the first post-layout corner whose decision-transition
cross-check is measurable**, and it changes how the degenerate ones read. At
+/−0.1467 mV the pair splits 2/4 against 0/4 and yields **0.2175 mV**, against
the same record's 0.1956 mV pick-off figure — two independent statistics on the
same extracted fragment agreeing to 11 %. The `tt`/27 °C and `fs`/125 °C
degeneracies are therefore not "the cross-check does not work post-layout"; they
are the all-one-way branch, with a deterministic term (row 1's 0.6547 mV
post-layout systematic) swamping the overdrives. That explanation is not
`tt_mm`-specific: since #80 the same term is measured at **0.6350–0.6874 mV
across all five `_mm` corners**, i.e. essentially process-independent, so it is
available as the cause at the skewed corners too and not only where it was first
measured. `ss`/−40 °C is degenerate for
the third, distinct reason its schematic-level counterpart already recorded — the
overdrives sit below that corner's resolvable-overdrive floor.

**`fs`/125 °C carries no ratio at all**, and says so instead of inventing one:
no committed schematic-level `noise-tran` record exists at that corner (the
three that do are `tt`/27 °C, `ss`/−40 °C and `ff`/125 °C) — the same convention
the AC table above uses at its six counterpart-less corners. Its N=32 and
4 seeds/sign/point are likewise stated on the record's face, with the measured
reason: this dispatch host budgets each agent a **one-core cgroup CPU quota**
(so `--jobs 2` buys no parallel throughput), and extracted decks at `fs`/125 °C
cost ~350–500 s of CPU each — roughly **3×** the `tt`/27 °C cost the #65 budget
was extrapolated from. Every disposition drawn from it below is therefore read
against the **conservative end of its 95 % CI**, not the point estimate.

**A resolved corner-dependence, unlike the schematic→layout ratio.** 0.2540 mV
at `fs`/125 °C against 0.1448 mV at `tt`/27 °C is **1.754×** with
**non-overlapping** 95 % CIs, so this difference *is* resolved at these sample
sizes. It degrades faster with corner than the AC sub-model's own 1.433×
(0.9423 / 0.6576), and the AC-to-transient gap at `fs`/125 °C is 3.71× —
squarely inside the ~3–4× gap the other corners show, so the closing figure is
not a method outlier at the corner where it matters most. #89's two corners
extend that scaling to four points, monotone in temperature: 0.1382 mV
(`ss`/−40 °C), 0.1448 mV (`tt`/27 °C), 0.1956 mV (`ff`/125 °C), 0.2540 mV
(`fs`/125 °C). The hot corners bind this row on the regeneration-inclusive basis
exactly as they do on the AC one.

Three of the four post-layout cross-checks are degenerate, and the two
*all-one-way* ones are independent evidence for the sub-20 mV polarity asymmetry
([#66](https://github.com/2AMLogic/sky130-comparator/issues/66)): at `tt`/27 °C
all 64 runs resolved and all decided the same way at both signs of a
±0.109 / ±0.217 mV overdrive, and at `fs`/125 °C all 16 did the same at
±0.191 / ±0.381 mV — the all-one-way branch, not the resolvable-overdrive
floor, and consistent with the 0.6547 mV systematic offset measured on row 1.
`ss`/−40 °C is degenerate for the *other* reason, the one its own schematic-level
counterpart recorded: the overdrives sit below that corner's
resolvable-overdrive floor. And `ff`/125 °C is **not** degenerate — the branch
that makes the two all-one-way readings interpretable rather than a suspected
method failure.

### Verdict — read this before citing the row

**Every measured figure clears the ratified ≤ 1.0 mV target bound, and since
#83 the row's target compliance rests on a direct regeneration-inclusive
measurement at the binding corner rather than on a lower bound plus a headroom
argument.** DR-006's disposition and its Amendment 1, reproduced in substance:

1. The **bounds are unchanged** — target ≤ 1.0 mV rms differential, stretch
   ≤ 0.6 mV rms differential, exactly as DR-002 ratified them. Nothing here is
   relaxed, and nothing failed.
2. DR-006 moved the row's **compliance basis RATIFIED-and-clear → RATIFIED,
   basis OPEN**. The bound stayed ratified; what was re-opened is the claim that
   the measured evidence establishes compliance with it. DR-002 §2's headroom
   argument is **superseded by measurement** and must not be cited as current
   justification: it reasoned that the excluded regeneration-phase term would
   have to reach ~0.90 mV rms to threaten the target, and from the post-layout
   worst corner's 0.9423 mV rms it needs only
   `sqrt(1.0² − 0.9423²)` = **0.335 mV rms** in quadrature — 2.7× less headroom
   than the ratification reasoned from, on a figure the methodology states is a
   **lower** bound.
3. **The evidence DR-006 named as what would close it again** — a
   regeneration-inclusive input-referred noise measurement against the extracted
   netlist at **`fs`/125 °C**, the corner that binds the row — **has now been
   made** ([#83](https://github.com/2AMLogic/sky130-comparator/issues/83),
   `sim/comparator-decision/records/20260926-055806-3034c41.md`, built on the
   post-layout deck form [#65](https://github.com/2AMLogic/sky130-comparator/issues/65)
   added). It measures **0.2540 mV rms differential**, which clears the target
   with **3.94×** margin and **3.32×** at its 95 % CI's upper bound. Stated a
   second way so the closure does not rest on one arithmetic: even under a
   deliberately indefensible double-count — adding the *entire* measured figure
   in quadrature on top of the same corner's 0.9423 mV AC lower bound, which
   double-counts because both are dominated by the same preamp input-referred
   source — `sqrt(0.9423² + 0.2540²)` = 0.9759 mV rms is *still* inside the
   target (1.025×; 0.9892 mV / 1.011× at the CI's upper bound). DR-006's own
   0.335 mV allowance is not exceeded either (0.2540 mV is 0.76× of it).
   **DR-006 Amendment 1 therefore moves the target-bound basis back to
   RATIFIED-and-clear and discharges its own §3 closure condition.**
4. **The stretch figure is breached at four of seven corners** on the AC basis
   (`tt`/27 °C, `ff`/125 °C, `sf`/125 °C, `fs`/125 °C) and cleared at the three
   cold ones. **Unchanged, and explicitly not re-closed by #83 or #89**: the
   transient basis clears the stretch figure at all four of its corners, but the
   two bases disagree, the transient basis has 4 of 7 corners, and per
   `CLAUDE.md` a different method's number does not erase a recorded breach.
   Unchanged in value; not a compliance requirement. Note that #89's two new
   corners include `ff`/125 °C, one of the four the AC basis records as
   breached — and the transient figure there (0.1956 mV) clears the stretch
   figure by 3.07×. That widens the disagreement between the two bases at a
   *breached* corner rather than resolving it, which is precisely why the AC
   breach record is left standing.

**What still needs a qualifier.** A bare "clears the noise target" *is* now
supportable — provided it cites the regeneration-inclusive basis. What must
still carry the **1.06× worst-corner qualifier** is any statement that cites the
**AC lower-bound** figure as the row's basis: that figure is unchanged at
0.9423 mV rms, and what #83 changed is that it is no longer the row's *only*
basis at that corner. Three graded corners (`sf`/−40 °C, `sf`/125 °C,
`fs`/−40 °C) also remain unmeasured post-layout for `noise-tran`, so the
regeneration-inclusive basis covers the binding corner, `tt`/27 °C, `ss`/−40 °C
and `ff`/125 °C — not the full seven.

---

## 3. Decision time vs. overdrive

- **Status**: RATIFIED by [DR-005](../spec/decision-records/DR-005-full-corner-campaign.md) (open since DR-002, anchored by DR-004).
- **Bounds**: target ≤ 1.5 ns at 50 mV overdrive, 1.8 V; stretch ≤ 0.8 ns at 50 mV.
- **Method**: `run.py regen` — a transient regeneration-time sweep vs. differential input, read off a `|v(outp)−v(outn)| > 0.5·VDD` threshold crossing. Both bounds are stated at the 50 mV point.

### All seven graded corners, both provenances

| Corner | Schematic @ 50 mV | Post-layout @ 50 mV | Ratio | Sweep points resolved (sch → PL) | Post-layout record |
|---|---|---|---|---|---|
| `tt`/27 °C | 0.4025 ns | 0.5325 ns | 1.323× | 8/8 → 6/8 | `sim/comparator-decision/records/20260925-085247-4694692.md` |
| `ss`/−40 °C | 0.3575 ns | 0.4725 ns | 1.322× | 7/8 → 3/8 | `sim/comparator-decision/records/20260925-093624-4694692.md` |
| `ff`/125 °C | 0.4975 ns | 0.6475 ns | 1.302× | 8/8 → 8/8 | `sim/comparator-decision/records/20260925-175622-bec714a.md` |
| `sf`/−40 °C | 0.3475 ns | 0.4425 ns | 1.273× | 8/8 → 5/8 | `sim/comparator-decision/records/20260925-192610-bec714a.md` |
| `sf`/125 °C | 0.4725 ns | 0.6375 ns | 1.349× | 8/8 → 7/8 | `sim/comparator-decision/records/20260925-182949-bec714a.md` |
| `fs`/−40 °C | 0.3725 ns | 0.4875 ns | 1.309× | 8/8 → 5/8 | `sim/comparator-decision/records/20260925-185950-bec714a.md` |
| `fs`/125 °C | 0.5375 ns | **0.7725 ns** | **1.437×** | 8/8 → 7/8 | `sim/comparator-decision/records/20260925-173228-bec714a.md` |

Schematic-level records, in the same corner order:
`sim/comparator-decision/records/20260922-070800-e084b55.md`,
`sim/comparator-decision/records/20260922-071313-e084b55.md`,
`sim/comparator-decision/records/20260922-175252-e23c509.md`,
`sim/comparator-decision/records/20260922-175425-e23c509.md`,
`sim/comparator-decision/records/20260922-175554-e23c509.md`,
`sim/comparator-decision/records/20260922-175734-e23c509.md`,
`sim/comparator-decision/records/20260922-175918-e23c509.md`.

### Verdict and caveats

- **Target bound: met at all seven corners.** Worst case `fs`/125 °C,
  0.7725 ns against ≤ 1.5 ns — 1.94×.
- **Stretch bound: also met at all seven corners — but at `fs`/125 °C with only
  1.04× margin (3.4 %).** Flagged, not smoothed over. It is the figure that
  would move first if the supply-net parasitic model were refined; the lumped
  star R on `GND`/`VDD` is expected to be *pessimistic*, so the true margin is
  plausibly better than 1.04× — an argument for re-measuring with
  `--distributed-rc`, not for assuming it.
- **The post-layout penalty is corner-dependent** (1.273×–1.437×) and largest at
  the **hot** corner, the opposite of row 4. Neither row's PVT shape can be
  inferred from the other's.
- **Sub-20 mV resolution degrades post-layout, asymmetrically in polarity.**
  8/8 resolve at `ff`/125 °C, 7/8 at the 125 °C skews, 5/8 at both −40 °C skews,
  3/8 at `ss`/−40 °C. `regen`'s criterion is sign-corrected, so a
  wrong-polarity decision and a genuine non-decision both read `UNRESOLVED` —
  the sweeps *bracket* the asymmetry (between 2 and 5 mV at the cold skews)
  rather than measuring it. Neither bound is touched: both are stated at 50 mV
  overdrive, which resolves at every corner. Tracked as
  [#66](https://github.com/2AMLogic/sky130-comparator/issues/66).

---

## 4. Kickback

- **Status**: bound RATIFIED by [DR-002](../spec/decision-records/DR-002-target-spec-ratification.md) (as a bound the then-current design did **not** meet); design first measured compliant by [DR-004](../spec/decision-records/DR-004-comparator-preamp-supersession.md); PVT set completed by DR-005 and post-layout by the extracted-netlist campaign.
- **Bounds**: target ≤ 5 mV disturbance into a 1 kΩ source impedance at the input nodes on a single decision edge; stretch ≤ 2 mV.
- **Method**: `run.py kickback` — `VINP`/`VINN` biased at `VCM` through an explicit 1 kΩ series resistor each (`loaded`), 50 mV differential step, one reset→evaluate edge; peak absolute deviation from each node's own settled pre-edge value. A zero-impedance `ideal` control must collapse to (numerically) zero, or the measurement is not isolating a source-impedance-dependent effect at all.

### All seven graded corners, both provenances

| Corner | Schematic | Post-layout | Ratio | `ideal` control (PL) | Post-layout record |
|---|---|---|---|---|---|
| `tt`/27 °C | 1.8902 mV | 2.6767 mV | 1.416× | 0.0000 mV | `sim/comparator-decision/records/20260925-094700-4694692.md` |
| `ss`/−40 °C | 1.8605 mV | 2.7564 mV | 1.482× | 0.0000 mV | `sim/comparator-decision/records/20260925-165936-45f0767.md` |
| `ff`/125 °C | 1.7677 mV | 2.2985 mV | 1.300× | 0.0000 mV | `sim/comparator-decision/records/20260925-170317-45f0767.md` |
| `sf`/−40 °C | 2.0208 mV | **3.1989 mV** | **1.583×** | 0.0000 mV | `sim/comparator-decision/records/20260925-165719-45f0767.md` |
| `sf`/125 °C | 1.7837 mV | 2.3443 mV | 1.314× | 0.0000 mV | `sim/comparator-decision/records/20260925-165748-45f0767.md` |
| `fs`/−40 °C | 1.8408 mV | 2.6795 mV | 1.456× | 0.0000 mV | `sim/comparator-decision/records/20260925-165825-45f0767.md` |
| `fs`/125 °C | 1.6091 mV | 1.9558 mV | 1.215× | 0.0000 mV | `sim/comparator-decision/records/20260925-165858-45f0767.md` |

Schematic-level records, in the same corner order:
`sim/comparator-decision/records/20260922-070119-e084b55.md`,
`sim/comparator-decision/records/20260922-070212-e084b55.md`,
`sim/comparator-decision/records/20260922-070307-e084b55.md`,
`sim/comparator-decision/records/20260922-180026-e23c509.md`,
`sim/comparator-decision/records/20260922-180157-e23c509.md`,
`sim/comparator-decision/records/20260922-180319-e23c509.md`,
`sim/comparator-decision/records/20260922-180425-e23c509.md`.

### Verdict and caveats

- **Target bound: met at all seven corners.** Worst case `sf`/−40 °C,
  3.1989 mV against ≤ 5 mV — 1.56×. The row is **not** re-opened.
- **Stretch figure: breached at six of seven corners** (by 60 % at `sf`/−40 °C);
  `fs`/125 °C at 1.9558 mV is the only corner that still meets it. Recorded, not
  legislated away — the stretch figure is unchanged and is not a compliance
  requirement.
- **The post-layout penalty is not a corner-independent constant.** It ranges
  1.215×–1.583× and is systematically larger at the **cold** corners
  (`sf`/−40 °C 1.583×, `ss`/−40 °C 1.482×, `fs`/−40 °C 1.456×) than the hot ones
  (`fs`/125 °C 1.215×, `ff`/125 °C 1.300×, `sf`/125 °C 1.314×). Layout penalty
  and schematic worst case therefore **reinforce rather than cancel**. Scaling
  the `tt`/27 °C ratio onto `sf`/−40 °C would have predicted ≈ 2.7 mV against
  the 3.1989 mV measured (18 % low) — which is why this row needed measuring at
  every corner rather than extrapolating from one.
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
| Worst \|I(VDD)\| over the reset settle window, **schematic** | 5-corner reset set | 4.228e−05 … 6.756e−05 A | `sim/comparator-decision/records/20260922-070024-e084b55.md` |
| Worst \|I(VDD)\| over the reset settle window, **post-layout** | same 5-corner set | 4.789e−05 … 6.642e−05 A | `sim/comparator-decision/records/20260925-165718-8ea399d.md` |

The two `reset` records are the only committed evidence records that carry a
supply-current column at all, and they carry it as criterion (4) of a
**pass/fail reset-integrity screen**, not as a power measurement: what that
criterion rests on is the separation between the as-drawn figure and the
GND-tied positive control (8.376e−04 … 1.056e−03 A schematic,
7.856e−04 … 8.306e−04 A post-layout — corner by corner, 12–24× the as-drawn
figure schematically and 12–17× post-layout), not the absolute level. The schematic→post-layout comparison on the as-drawn column
is therefore reported here as an overlap of ranges, not a ratio: the layout does
not move it materially.

### Verdict

- **There is no ratified bound on this row, so there is nothing for the design
  to meet.** This report does not grade it, and no other artifact in this repo
  should either.
- **The DRAFT 50 µW figure is already exceeded by the static term alone**
  (~95 µW at 1.8 V), before any duty-cycle-dependent evaluate term. The DR-004
  preamplifier class costs static current by construction.
- **No average-power figure exists at all**, because the row's "one decision per
  clock edge at a stated clock rate" framing has no ratified clock rate behind
  it — and that framing itself predates the preamplifier and is superseded in
  substance. Re-anchoring the row is an open ratification decision (DR-004 Open
  items); per `CLAUDE.md` the DRAFT figures are **not** changed to accommodate
  the measurement.
- Post-layout coverage of this row is limited to the reset-phase current column
  above. No post-layout evaluate-phase or average-power measurement exists.

---

## Coverage — what is and is not measured post-layout

| Sub-command | Row(s) it feeds | Post-layout corner coverage | Gap |
|---|---|---|---|
| `kickback` | 4 | **7 of 7** graded corners | none |
| `regen` | 3 | **7 of 7** graded corners | none |
| `noise` (AC) | 2 | **7 of 7** graded corners | schematic→post-layout ratio available only at `tt`/27 °C (no AC counterpart elsewhere) |
| `offset` | 1 | **5 of 5** `_mm` corners (all at 27 °C; the four non-`tt_mm` ones by [#80](https://github.com/2AMLogic/sky130-comparator/issues/80)) | none at N=16; no post-layout large-N campaign, and at N=16 the 3.0 % post-layout corner spread is unresolved inside an 18.3 % relative SE |
| `noise-tran` | 2 | **4 of 7** graded corners (`tt`/27 °C; `fs`/125 °C, [#83](https://github.com/2AMLogic/sky130-comparator/issues/83); **`ss`/−40 °C and `ff`/125 °C**, [#89](https://github.com/2AMLogic/sky130-comparator/issues/89)) | 3 corners (`sf`/−40 °C, `sf`/125 °C, `fs`/−40 °C) — but **not** `fs`/125 °C, the corner DR-006 closes on: that one is measured, and DR-006 Amendment 1 closes row 2's target-bound basis on it. None of the three remaining corners has a schematic-level counterpart, so none can yield a ratio; the only two that could, #89 ran. Separately open: every post-layout figure is N=32–64 against the schematic side's N=128, so no individual ratio is resolved |
| `reset` | 5 (current column) | **5 of 5** of its own corner set | none |

Two coverage facts that apply to every row above:

- **The supply nets have not been re-extracted with `klt extract
  --distributed-rc`.** The single lumped star R on `GND`/`VDD` is 52.0 % of the
  block's total series R and is expected to be pessimistic, so every post-layout
  degradation in this report is an upper bound on the supply-network
  contribution.
- **Superseded post-layout set.** An earlier post-layout set
  (`20260925-065137-87f0013` … `20260925-072817-2e2ef84`) was extracted on an
  **off-pin** klt/klayout build whose per-net series resistances differ from the
  pinned build's by up to 2.30×. Those records remain in place unedited per the
  append-only rule and are **not** the figures any row above cites; each
  superseding record names them in its `Supersedes` field.

## Open items this report carries

These are stated so a reader does not mistake an aggregated report for a closed
one:

- **Row 2's remaining three post-layout `noise-tran` corners** (`sf`/−40 °C,
  `sf`/125 °C, `fs`/−40 °C). DR-006's closure condition — `fs`/125 °C — **has
  landed** ([#83](https://github.com/2AMLogic/sky130-comparator/issues/83)) and
  Amendment 1 closes the target-bound basis on it, so what is open here is
  *coverage*, not the basis. The two corners that had committed schematic-level
  counterparts (`ss`/−40 °C, `ff`/125 °C) **have since been run**
  ([#89](https://github.com/2AMLogic/sky130-comparator/issues/89)), together with
  the `run.py` `SCHEMATIC_BASELINES` fix they needed in order to difference
  against those counterparts at all. None of the three remaining corners has a
  counterpart, so each will correctly report no ratio.
- **Row 2's sample sizes are the binding open item, not its corner count.** Every
  post-layout `noise-tran` figure is N=32–64 pick-off seeds against the schematic
  side's N=128, and at all three corners where a ratio exists the schematic value
  sits inside the post-layout CI — so the schematic→layout change on this row is
  *unresolved* at every corner, and adding the last three corners will not
  resolve it. A full-N re-run would: `tt`/27 °C (N=64/16),
  `fs`/125 °C (N=32/4), `ss`/−40 °C and `ff`/125 °C (N=32/4 each), each
  `--supersedes`-ing the record it replaces. **This cannot be done on the present
  dispatch host as a single command**: #89 measured a hard ~60-minute wall-clock
  ceiling on any one agent command (on top of the one-core cgroup quota #83
  measured), and a full-N corner is 388 decks — an order of magnitude over it. A
  resumable/chunked runner or a different execution host is a prerequisite, not a
  scheduling preference.
- **The ≤ 0.6 mV stretch figure on row 2** stays breached at four of seven
  corners on the AC basis. Not a compliance requirement, and deliberately not
  re-closed by #83's transient figure.
- [#66](https://github.com/2AMLogic/sky130-comparator/issues/66) — the
  layout-induced systematic offset (0.6547 mV at `tt_mm`, and 0.6350–0.6874 mV
  across all five `_mm` corners since #80, so essentially process-independent)
  and the sub-20 mV decision-polarity asymmetry. Affects rows 1, 2 and 3 as a
  caveat; touches no bound, all of which are stated at 50 mV overdrive or on σ
  alone.
- The Supply / power row's ratification decision (DR-004 Open items) — row 5 has
  no ratified bound and cannot acquire one without a clock-rate framing
  decision.
- **Row 1's post-layout sample size.** Its four missing `_mm` corners **have
  since been run** ([#80](https://github.com/2AMLogic/sky130-comparator/issues/80)),
  so coverage is 5 of 5; what is still open is that every post-layout figure is
  N=16, whose ≈ 18.3 % relative SE on a stdev is six times the 3.0 % spread the
  five corners actually show. No post-layout large-N (O(100s)-draw) campaign
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
   appears in the index, and
4. emits the generic envelope with `status: "pass"` only when all of that holds,
   and `status: "fail"` otherwise.

The drift signal is carried by the envelope's **`status` field**, not by the
exit code: `klt signoff` parses a command-backed entry's stdout *before* it
inspects `exit_status`, so a guard that exited nonzero while still printing
`status: "pass"` would grade `met` anyway. Editing this report without running
`python3 scripts/characterization-envelope.py --update` makes item 8 grade
`unmet`/`check_failed`.

This is the reason the entry is command-backed rather than file-backed: `klt`
0.6.0 lists no input-artifact field for the `generic` kind, so a generic
citation always reports `input_verified: null` and its freshness cannot be
anchored by the grader itself (filed upstream as
[2AMLogic/klayout-tools#2403](https://github.com/2AMLogic/klayout-tools/issues/2403)).
Running the hash comparison live, in-repo, closes that gap here without pinning
a `content_hash` the grader would never re-hash.

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

Every artifact this report draws a figure from. The script above pins each one
by SHA-256; adding a citation to a row table without adding it here (or vice
versa) is a `status: "fail"`.

| Artifact | Row(s) | What it carries |
|---|---|---|
| `sim/comparator-decision/records/20260922-065300-e084b55.md` | 1 | `offset` N=16 `tt_mm`/27 °C, schematic |
| `sim/comparator-decision/records/20260922-173622-e23c509.md` | 1 | `offset` N=16 `ss_mm`/27 °C, schematic |
| `sim/comparator-decision/records/20260922-174326-e23c509.md` | 1 | `offset` N=16 `ff_mm`/27 °C, schematic |
| `sim/comparator-decision/records/20260922-174831-e23c509.md` | 1 | `offset` N=16 `sf_mm`/27 °C, schematic |
| `sim/comparator-decision/records/20260922-175152-e23c509.md` | 1 | `offset` N=16 `fs_mm`/27 °C, schematic |
| `sim/comparator-decision/records/20260922-191034-e23c509.md` | 1 | `offset` N=200 `tt_mm`/27 °C, schematic |
| `sim/comparator-decision/records/20260922-202434-e026012.md` | 1 | `offset` N=200 `ss_mm`/27 °C, schematic |
| `sim/comparator-decision/records/20260925-112809-4694692.md` | 1 | `offset` N=16 `tt_mm`/27 °C, post-layout (+ 0.6547 mV systematic term) |
| `sim/comparator-decision/records/20260926-022304-5b02508.md` | 1 | `offset` N=16 **`ss_mm`/27 °C, post-layout** (#80) — the nominally binding schematic corner, second-lowest post-layout |
| `sim/comparator-decision/records/20260926-032735-85c288e.md` | 1 | `offset` N=16 **`ff_mm`/27 °C, post-layout** (#80) — the worst measured cell of this row (2.4796 mV σ → 7.4388 mV 3σ) and the largest post-layout ratio (1.554×) |
| `sim/comparator-decision/records/20260926-034704-dfaee77.md` | 1 | `offset` N=16 **`sf_mm`/27 °C, post-layout** (#80) |
| `sim/comparator-decision/records/20260926-041419-38f6227.md` | 1 | `offset` N=16 **`fs_mm`/27 °C, post-layout** (#80) — the fifth and last `_mm` corner; carries the largest systematic term (0.6874 mV) |
| `sim/comparator-decision/records/20260922-065534-e084b55.md` | 2 | `noise` AC `tt`/27 °C, schematic |
| `sim/comparator-decision/records/20260925-112827-4694692.md` | 2 | `noise` AC `tt`/27 °C, post-layout |
| `sim/comparator-decision/records/20260925-192710-bec714a.md` | 2 | `noise` AC `ss`/−40 °C, post-layout |
| `sim/comparator-decision/records/20260925-192728-bec714a.md` | 2 | `noise` AC `ff`/125 °C, post-layout |
| `sim/comparator-decision/records/20260925-192745-bec714a.md` | 2 | `noise` AC `sf`/−40 °C, post-layout |
| `sim/comparator-decision/records/20260925-192801-bec714a.md` | 2 | `noise` AC `sf`/125 °C, post-layout |
| `sim/comparator-decision/records/20260925-192818-bec714a.md` | 2 | `noise` AC `fs`/−40 °C, post-layout |
| `sim/comparator-decision/records/20260925-192836-bec714a.md` | 2 | `noise` AC `fs`/125 °C, post-layout — the corner that binds the row |
| `sim/comparator-decision/records/20260922-192722-e23c509.md` | 2 | `noise-tran` `tt`/27 °C, schematic |
| `sim/comparator-decision/records/20260922-205857-ebea4e2.md` | 2 | `noise-tran` `ss`/−40 °C, schematic |
| `sim/comparator-decision/records/20260923-010427-ebea4e2.md` | 2 | `noise-tran` `ff`/125 °C, schematic |
| `sim/comparator-decision/records/20260925-214740-81f594b.md` | 2 | `noise-tran` `tt`/27 °C, post-layout |
| `sim/comparator-decision/records/20260926-055806-3034c41.md` | 2 | `noise-tran` **`fs`/125 °C, post-layout** — DR-006's closure condition |
| `sim/comparator-decision/records/20260926-110218-b64004b.md` | 2 | `noise-tran` **`ss`/−40 °C, post-layout** (N=32/4) — the cited figure at this corner |
| `sim/comparator-decision/records/20260926-100015-b64004b.md` | 2 | `noise-tran` `ss`/−40 °C, post-layout at N=16/2 — **superseded** by the row above; kept because the N=16→N=32 move at one fixed corner is itself the evidence that N=16 is below this statistic's useful floor |
| `sim/comparator-decision/records/20260926-102605-b64004b.md` | 2 | `noise-tran` **`ff`/125 °C, post-layout** (N=32/4) — the only post-layout corner whose decision-transition cross-check is measurable |
| `sim/comparator-decision/records/20260922-070800-e084b55.md` | 3 | `regen` `tt`/27 °C, schematic |
| `sim/comparator-decision/records/20260922-071313-e084b55.md` | 3 | `regen` `ss`/−40 °C, schematic |
| `sim/comparator-decision/records/20260922-175252-e23c509.md` | 3 | `regen` `ff`/125 °C, schematic |
| `sim/comparator-decision/records/20260922-175425-e23c509.md` | 3 | `regen` `sf`/−40 °C, schematic |
| `sim/comparator-decision/records/20260922-175554-e23c509.md` | 3 | `regen` `sf`/125 °C, schematic |
| `sim/comparator-decision/records/20260922-175734-e23c509.md` | 3 | `regen` `fs`/−40 °C, schematic |
| `sim/comparator-decision/records/20260922-175918-e23c509.md` | 3 | `regen` `fs`/125 °C, schematic |
| `sim/comparator-decision/records/20260925-085247-4694692.md` | 3 | `regen` `tt`/27 °C, post-layout |
| `sim/comparator-decision/records/20260925-093624-4694692.md` | 3 | `regen` `ss`/−40 °C, post-layout |
| `sim/comparator-decision/records/20260925-173228-bec714a.md` | 3 | `regen` `fs`/125 °C, post-layout — the slowest corner |
| `sim/comparator-decision/records/20260925-175622-bec714a.md` | 3 | `regen` `ff`/125 °C, post-layout |
| `sim/comparator-decision/records/20260925-182949-bec714a.md` | 3 | `regen` `sf`/125 °C, post-layout |
| `sim/comparator-decision/records/20260925-185950-bec714a.md` | 3 | `regen` `fs`/−40 °C, post-layout |
| `sim/comparator-decision/records/20260925-192610-bec714a.md` | 3 | `regen` `sf`/−40 °C, post-layout |
| `sim/comparator-decision/records/20260922-070119-e084b55.md` | 4 | `kickback` `tt`/27 °C, schematic |
| `sim/comparator-decision/records/20260922-070212-e084b55.md` | 4 | `kickback` `ss`/−40 °C, schematic |
| `sim/comparator-decision/records/20260922-070307-e084b55.md` | 4 | `kickback` `ff`/125 °C, schematic |
| `sim/comparator-decision/records/20260922-180026-e23c509.md` | 4 | `kickback` `sf`/−40 °C, schematic |
| `sim/comparator-decision/records/20260922-180157-e23c509.md` | 4 | `kickback` `sf`/125 °C, schematic |
| `sim/comparator-decision/records/20260922-180319-e23c509.md` | 4 | `kickback` `fs`/−40 °C, schematic |
| `sim/comparator-decision/records/20260922-180425-e23c509.md` | 4 | `kickback` `fs`/125 °C, schematic |
| `sim/comparator-decision/records/20260925-094700-4694692.md` | 4 | `kickback` `tt`/27 °C, post-layout |
| `sim/comparator-decision/records/20260925-165719-45f0767.md` | 4 | `kickback` `sf`/−40 °C, post-layout — the worst corner |
| `sim/comparator-decision/records/20260925-165748-45f0767.md` | 4 | `kickback` `sf`/125 °C, post-layout |
| `sim/comparator-decision/records/20260925-165825-45f0767.md` | 4 | `kickback` `fs`/−40 °C, post-layout |
| `sim/comparator-decision/records/20260925-165858-45f0767.md` | 4 | `kickback` `fs`/125 °C, post-layout |
| `sim/comparator-decision/records/20260925-165936-45f0767.md` | 4 | `kickback` `ss`/−40 °C, post-layout |
| `sim/comparator-decision/records/20260925-170317-45f0767.md` | 4 | `kickback` `ff`/125 °C, post-layout |
| `sim/comparator-decision/records/20260916-060139-f1eb978.md` | 4 | `kickback` `tt`/27 °C on the **superseded** DR-001 single-tail design (144.60 mV) — historical context only |
| `sim/comparator-decision/records/20260921-185208-bb32850.md` | 4 | `kickback` `tt`/27 °C after DR-003's soft-clock shaper (85.71 mV) — historical context only |
| `sim/comparator-decision/records/20260922-070024-e084b55.md` | 5 | `reset` 5-corner screen, schematic — the \|I(VDD)\| column |
| `sim/comparator-decision/records/20260925-165718-8ea399d.md` | 5 | `reset` 5-corner screen, post-layout — the \|I(VDD)\| column |
| `spec/dr-004-support/evaluate_idd_probe.spice` | 5 | the reset/evaluate supply-current probe deck behind DR-004's ~95 µW static figure |
| `spec/decision-records/DR-002-target-spec-ratification.md` | 1–5 | the ratification disposition every row's Status cell reports |
| `spec/decision-records/DR-004-comparator-preamp-supersession.md` | 1–5 | the topology supersession every figure above is measured at |
| `spec/decision-records/DR-003-kickback-slew-limited-clock.md` | 4 | the mitigation pass between the two superseded kickback figures above |
| `spec/decision-records/DR-005-full-corner-campaign.md` | 1–4 | the full-corner campaign; ratifies row 3 |
| `spec/decision-records/DR-006-post-layout-noise-headroom-reopened.md` | 2 | re-opens row 2's compliance basis |
