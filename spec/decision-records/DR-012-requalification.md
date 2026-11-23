# DR-012: Re-qualification of the characterization basis to open_pdks `f6eeac7` — old/new comparison record

- **Status**: proposed — this record ratifies nothing and changes no
  ratified row, bound, tolerance or status. It is the comparison record the
  re-qualification campaign's final step owes: the measured old/new movement
  per metric per corner, every result that moved past its stated tolerance,
  and the statement that no ratified bound is newly breached. Per `CLAUDE.md`
  and `spec/README.md`, a breach recorded here would get its own bounded
  design-iteration issue; there is none to file (see Consequences).
- **Date**: 2026-11-23
- **Decided by**: issue [#179](https://github.com/2AMLogic/sky130-comparator/issues/179)
  re-qualification campaign, final step (issue
  [#361](https://github.com/2AMLogic/sky130-comparator/issues/361));
  executed by builder agent against `main` at `92cea9e3`

## Context

The workspace's sky130 canaries re-pinned the PDK from open_pdks
`c6d73a35f5…` to `f6eeac7dad0…` (`sim/pdk.json`), the fleet's ngspice moved
46 → 47, and this repo's layout had already re-drawn its poly resistors from
0.42 µm to the schematic's 0.35 µm at the klt 0.7.0 pin (issue #123). Every
committed characterization record predated at least one of those changes, so
the whole live record set — 64 entries, enumerated by the machine-readable
plan `sim/comparator-decision/requalify-plan.json` (issue #358) — was
re-measured by the campaign's steps 1–5 (issues #358, #359, #360, #125;
PRs #363, #366, #369, #371, #388), on the supported `repo-script` batch
route (issue #127).

This record is the campaign's closing artifact: it freezes the old/new
comparison so that (a) a reader can tell what moved and by how much without
diffing 64 append-only records, and (b) any future claim about "the"
characterization figures names which pin it rests on. The aggregated report
(`sim/characterization-report.md`) now cites only `f6eeac7` terminals; the
plan-discharge gate in `sim/selftest.sh` keeps it that way.

**What the "new" column bundles.** On the extracted side the movement is the
*bundle* of geometry (0.42 → 0.35 µm resistors), extraction pins (klt
0.6.0/klayout 0.30.10 → klt 0.8.0/klayout 0.30.12) and environment (PDK
`c6d73a35`/ngspice-46 → `f6eeac7`/ngspice-47) — the superseded extracted
records are the 0.42 µm-era set this report's predecessor cited. On the
schematic side only the environment changed, which is what makes the
schematic column the campaign's control: **every deterministic schematic
figure reproduced exactly** (`regen` times, `kickback` peaks, the `noise`
AC estimate, the `reset` currents — identical at displayed precision at all
corners), while the mismatch-sampled quantities moved (row 1 below). The
environment change alone is therefore benign for deterministic small-signal
and transient behavior, and material for the mismatch models.

## Decision

1. The repo's characterization basis — the figures
   `sim/characterization-report.md` aggregates and the records its Evidence
   index pins — moves to the re-qualified `f6eeac7` terminals: the 28
   schematic entries' direct successors and the 36 extracted entries'
   corrected reissues (the terminal records of each entry's `Supersedes`
   chain; `check-requalify-plan.py` gates this).
2. The old/new movement is recorded below, per metric per corner, with
   schematic (new-pin), old post-layout (0.42 µm, `c6d73a35`, superseded)
   and new post-layout (0.35 µm, `f6eeac7`) columns. Every result that
   moved past its superseded record's **stated tolerance** (a 95 % CI or a
   stated relative SE — the only tolerances the records themselves carry)
   is listed in its own section; deterministic records state no tolerance,
   and their movements are recorded as measured, not tested.
3. **No ratified row, bound, tolerance or ratification status changes.**
   Every ratified target bound is still met on the new figures, and no
   stretch figure that was met is now breached. The two standing
   recorded stretch-breach dispositions (Input-referred noise, AC basis,
   4 of 7 corners; Kickback, 5 of 7 corners — down from 6 of 7) carry over
   unchanged in kind, per DR-005's and DR-006 Amendment 1's own "recorded,
   not legislated away" framing.

## The old/new tables

Records: old post-layout = the superseded set the pre-campaign report cited;
schematic and new post-layout = the re-qualified terminals. Ratios in the
last column are new-post-layout ÷ schematic, both on the current pins (a
same-environment layout penalty).

### Row 1 — Offset sigma (`offset`, `_mm` corners, 27 °C, N=16, seed 1; σ in mV)

| Corner | Schematic (old) | Schematic (new) | Old post-layout | New post-layout | New PL/sch |
|---|---|---|---|---|---|
| `tt_mm` | 1.7857 | 2.3027 | 2.4446 | 2.4932 | 1.083× |
| `ss_mm` | 1.8244 | 2.3962 | 2.4133 | 2.4633 | 1.028× |
| `ff_mm` | 1.5954 | 2.0463 | 2.4796 | 2.5202 | 1.232× |
| `sf_mm` | 1.6706 | 2.1357 | 2.4794 | 2.5143 | 1.177× |
| `fs_mm` | 1.8218 | 2.3863 | 2.4078 | 2.4651 | 1.033× |

N=200 schematic: `tt_mm` 2.1854 → 2.3197 (old CI [1.9707, 2.4001] — new
inside), `ss_mm` 2.2353 → 2.3782 (old CI [2.0157, 2.4549] — new inside).
The N=16/N=200 discrepancy DR-002 flagged (22 % at `tt_mm`) is gone: the
new-pin N=16 and N=200 estimates agree to < 1 % at both corners.

Decision-referred systematic offset (`offset-bisect`, tolerance 0.1 mV):

| Corner | Schematic (old) | Schematic (new) | Old post-layout | New post-layout |
|---|---|---|---|---|
| `tt`/27 °C | −0.0391 mV | +0.0391 mV | **+1.8359 mV** | **−0.0391 mV** |
| `ss`/−40 °C | non-decision band [−0.8203, +0.8203] mV | identical band | non-decision band [−8.2715, +19.9707] mV (width 28.24) | **clean flip +1.9141 mV** |

### Row 2 — Input-referred noise (`noise` AC, mV rms differential)

| Corner | Schematic (old) | Schematic (new) | Old post-layout | New post-layout |
|---|---|---|---|---|
| `tt`/27 °C | 0.5704 | 0.5704 | 0.6576 | 0.6553 |
| `ss`/−40 °C | — | — | 0.5429 | 0.5409 |
| `ff`/125 °C | — | — | 0.8521 | 0.8486 |
| `sf`/−40 °C | — | — | 0.4886 | 0.4877 |
| `sf`/125 °C | — | — | 0.8590 | 0.8555 |
| `fs`/−40 °C | — | — | 0.5447 | 0.5426 |
| `fs`/125 °C | — | — | 0.9423 | 0.9372 |

Regeneration-inclusive (`noise-tran`, σ in mV, 95 % CI; N = pick-off seeds):

| Corner | Schematic (old) | Schematic (new) | Old post-layout | New post-layout |
|---|---|---|---|---|
| `tt`/27 °C | 0.1362 [0.1216, 0.1493] | 0.1457 [0.1322, 0.1585] | 0.1448 [0.1224, 0.1641] (N=64) | 0.1420 [0.1231, 0.1596] (N=64) |
| `ss`/−40 °C | 0.1213 [0.1084, 0.1335] | 0.1292 [0.1144, 0.1416] | 0.1382 [0.1046, 0.1666] | 0.1051 [0.0766, 0.1252] |
| `ff`/125 °C | 0.1754 [0.1594, 0.1905] | **0.1554 [0.1410, 0.1688]** | 0.1956 [0.1606, 0.2212] | **0.1560 [0.1205, 0.1810]** |
| `sf`/−40 °C | — | — | 0.0929 [0.0718, 0.1094] | 0.1013 [0.0797, 0.1166] |
| `sf`/125 °C | — | — | 0.1682 [0.1362, 0.1903] | 0.1852 [0.1376, 0.2219] |
| `fs`/−40 °C | — | — | 0.1084 [0.0838, 0.1282] | 0.1119 [0.0848, 0.1314] |
| `fs`/125 °C | — | — | 0.2540 [0.1961, 0.3009] | **0.1951 [0.1455, 0.2378]** |

### Row 3 — Decision time at 50 mV overdrive (`regen`, ns)

| Corner | Schematic (old) | Schematic (new) | Old post-layout | New post-layout | New PL/sch |
|---|---|---|---|---|---|
| `tt`/27 °C | 0.4025 | 0.4025 | 0.5325 | 0.5825 | 1.447× |
| `ss`/−40 °C | 0.3575 | 0.3575 | 0.4725 | 0.5225 | 1.462× |
| `ff`/125 °C | 0.4975 | 0.4975 | 0.6475 | 0.6875 | 1.382× |
| `sf`/−40 °C | 0.3475 | 0.3475 | 0.4425 | 0.5125 | 1.475× |
| `sf`/125 °C | 0.4725 | 0.4725 | 0.6375 | 0.6625 | 1.402× |
| `fs`/−40 °C | 0.3725 | 0.3725 | 0.4875 | 0.5375 | 1.443× |
| `fs`/125 °C | 0.5375 | 0.5375 | 0.7725 | 0.7575 | 1.409× |

Sweep-point resolution (schematic → old PL → new PL): all corners 8/8
except `ss`/−40 °C, which goes 7/8 (one NON-DECISION) → 3/8 → **6/8 with
the +0.50 and +1.00 mV points WRONG-POLARITY** — the sub-2 mV polarity
asymmetry (#66) is now concentrated there as wrong-polarity decisions
rather than non-decisions, while the other six corners improve to full
resolution.

### Row 4 — Kickback (`kickback`, `loaded` peak in mV)

| Corner | Schematic (old) | Schematic (new) | Old post-layout | New post-layout | New PL/sch |
|---|---|---|---|---|---|
| `tt`/27 °C | 1.8902 | 1.8902 | 2.6767 | 2.2931 | 1.213× |
| `ss`/−40 °C | 1.8605 | 1.8605 | 2.7564 | 2.3602 | 1.269× |
| `ff`/125 °C | 1.7677 | 1.7677 | 2.2985 | 1.9604 | 1.109× |
| `sf`/−40 °C | 2.0208 | 2.0208 | 3.1989 | 2.7204 | 1.346× |
| `sf`/125 °C | 1.7837 | 1.7837 | 2.3443 | 2.0079 | 1.126× |
| `fs`/−40 °C | 1.8408 | 1.8408 | 2.6795 | 2.2898 | 1.244× |
| `fs`/125 °C | 1.6091 | 1.6091 | 1.9558 | 1.6932 | 1.052× |

### Row 5 — reset-screen supply current (`reset`, worst |I(VDD)| over the reset settle window, A)

| Provenance | Old | New |
|---|---|---|
| Schematic, 5-corner range | 4.228e−05 … 6.756e−05 | identical |
| Post-layout, 5-corner range | 4.789e−05 … 6.642e−05 | 4.941e−05 … 6.728e−05 |
| Post-layout GND-tied control range | 7.856e−04 … 8.306e−04 | 6.292e−04 … 7.698e−04 |

The screen's separation (as-drawn vs GND-tied) stays 9–16× post-layout;
the row remains DRAFT/OPEN with no ratified bound, so no comparison is
graded.

## Results that moved past their stated tolerance

The superseded records' own stated uncertainties are the tolerances tested
here. Deterministic records (`regen`, `kickback`, `noise` AC, `reset`)
state none; their movements are recorded above as measured.

1. **Schematic `offset` σ, N=16, all five `_mm` corners — past the stated
   18.3 % relative SE.** +27.8 % (`sf_mm`) to +31.3 % (`ss_mm`). This is
   the mismatch-model change (`f6eeac7` AGAUSS parameters), the single
   largest schematic-side effect of the re-pin, and the reason the campaign
   existed. Both ratified bounds still clear (below).
2. **Schematic `noise-tran` `ff`/125 °C — below the old record's 95 % CI.**
   0.1754 → 0.1554 mV against CI lower bound 0.1594 (−11.4 %).
3. **Post-layout `noise-tran` `fs`/125 °C — below the old record's 95 % CI.**
   0.2540 → 0.1951 mV against CI lower bound 0.1961. This is the DR-006
   Amendment-1 closure corner; the closure arithmetic is restated on the new
   figure in the report (margin improves from 3.94× to 5.13×).
4. **Post-layout `noise-tran` `ff`/125 °C — below the old record's 95 % CI.**
   0.1956 → 0.1560 mV against CI lower bound 0.1606 (−20.2 %).
5. **Post-layout `offset-bisect` `tt`/27 °C — moved 1.875 mV, past the 0.1 mV
   bisection tolerance.** The extracted systematic decision offset goes from
   +1.8359 mV to −0.0391 mV: at the new geometry/pins the `tt`-corner
   extracted systematic essentially vanishes.
6. **Post-layout `offset-bisect` `ss`/−40 °C — qualitative change.** The old
   record's 28.24 mV non-decision band is gone; the new record has a clean
   flip at +1.9141 mV. The systematic offset did not disappear — it moved
   corners, and the worst decision-referred term is now measured where the
   old netlist could not decide at all. Recorded under #66's scope.

Additionally recorded (no stated tolerance to test against): the post-layout
`kickback` peak fell 13–15 % at every corner and the post-layout `regen`
time moved −2 % to +15.8 % per corner — both the geometry/extraction/pin
bundle's effect on the extracted parasitics, not environment drift (the
schematic controls for that and reproduce exactly).

## Alternatives considered

- **Keeping the superseded records as the cited basis** — rejected: a
  report built from a mix of old-pin and new-pin records is worse than
  none (issue #361's own framing); the pin change is exactly the class of
  environment drift `sim/toolchain.json`'s check exists to catch.
- **Treating the movement as drift and re-opening the ratified rows** —
  rejected: DR-002/DR-005/DR-006 ratified bounds against *this repo's own
  comparator*, not against a PDK revision. Every target bound still clears
  on the new figures; re-opening rows on a re-baseline that changes no
  verdict would be spec churn, not verification.
- **Waiving or adjusting the stretch figures the new measurements move**
  — rejected: per `CLAUDE.md`, agents do not relax the ratified spec to
  make results pass. The stretch-breach counts are recorded as they are
  (Kickback improves from 6/7 to 5/7 breached; noise AC is unchanged at
  4/7), and any re-scoping stays a future DR's call, as DR-005 already
  recorded for its own breach.

## Spec lines affected

**None.** No row of the `README.md` target-spec table changes — not its
bounds, tolerances, statuses or Basis cells' measured figures' *status*
(meaning: the ratified Target/Stretch numbers and every row's
RATIFIED/DRAFT status stand exactly as DR-002/DR-005 disposed them). What
changes is which records substantiate them: the report, its envelope and
the Evidence index now pin the `f6eeac7` terminals, and
`manifests/integrator-view.json`'s GDS note records the verified
byte-identity of the layout under the same pins.

## Consequences

- **No ratified-bound breach, so no design-iteration issue is filed from
  this record.** Worst new figures against their bounds: Offset sigma
  7.5606 mV 3σ vs ≤ 15 mV target (1.98×) and ≤ 8 mV stretch (1.06×, met);
  noise 0.9372 mV rms AC vs ≤ 1.0 mV target (1.07×) — regeneration-inclusive
  basis 0.1951 mV (5.13×), DR-006 Amendment 1's closure restated on the new
  figure; decision time 0.7575 ns vs ≤ 1.5 ns target (1.98×) and ≤ 0.8 ns
  stretch (1.06×, met); kickback 2.7204 mV vs ≤ 5 mV target (1.84×). The
  standing *stretch-figure* breach records carry over unchanged in kind
  (noise AC 4 of 7 corners; kickback 5 of 7, down from 6 — `ff`/125 °C now
  clears at 1.9604 mV) and remain, per DR-005/DR-006, recorded rather than
  compliance-blocking.
- **The offset basis is ~30 % wider at fixed N** — every future
  offset-margin statement must quote the new-pin σ. The stretch margin on
  row 1 thins from 1.08× to 1.06× while staying met.
- **The `noise-tran` decision-transition cross-check no longer corroborates
  the pick-off statistic post-layout** (0.67×–4.7× disagreement at 4
  seeds/point, at four of five measurable corners). The row's
  regeneration-inclusive claim rests on the pick-off statistic; raising the
  cross-check to a corroborating sample size is open work on the #100
  chunked-campaign track, and the report says so on its face.
- **The extracted systematic-offset picture changed corners** (#66): the
  `tt`-corner pick-off-referred term is stable (~0.65 mV) but the
  decision-referred term moved from +1.8359 mV to −0.0391 mV at `tt` and
  from a 28.24 mV non-decision band to a clean +1.9141 mV flip at `ss`/−40 °C.
  #66's disposition work should start from the new records.
- Downstream: T1 items 5/6 (#188) and item 7 (#187) can now build on a
  same-pin record set; the item-9 attestation inventory's stale PDK revision
  is corrected in the same change (issue #361 step 7).
- The superseded records stay byte-identical under the append-only rule;
  every one is named in its successor's `Supersedes` field, and
  `check-requalify-plan.py`'s discharge check fails if any entry's chain
  stops short of a `f6eeac7` terminal.
