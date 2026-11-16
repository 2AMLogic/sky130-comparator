# sky130-comparator

A dynamic latched comparator on SkyWater sky130 on
[SkyWater sky130](https://github.com/google/skywater-pdk), a 130 nm open CMOS PDK — designed by AI agents driving
[klayout-tools](https://github.com/2AMLogic/klayout-tools) and the
open-source xschem + ngspice flow.

![fleet burndown](https://raw.githubusercontent.com/2AMLogic/2am/main/fleet-metrics/charts/sky130-comparator.svg)

**Status:** designed (`design/comparator.sch`), laid out
(`layout/comparator.gds`) with DRC/LVS evidence, and four of the five spec rows
are ratified; Supply / power remains DRAFT / OPEN. The current frontier is the
post-layout re-measurement campaign
[#125](https://github.com/2AMLogic/sky130-comparator/issues/125), blocked on
the execution route [#127](https://github.com/2AMLogic/sky130-comparator/issues/127).
See the [decision records](spec/decision-records/) (latest ratified:
[DR-006](spec/decision-records/DR-006-post-layout-noise-headroom-reopened.md)),
[`manifests/design-evidence-tiers.md`](manifests/design-evidence-tiers.md), and
[`WORK_PLAN.md`](WORK_PLAN.md); figures live there, not here.

**For integrators:** [`spec/consumers.md`](spec/consumers.md) is the dated
consumer-compatibility record (last refreshed 2026-10-10 against the
DR-004 static-preamp topology and DR-005 ratifications). It distinguishes
ratified bounds, schematic results, and historical post-layout results; no
compatibility claim there covers the current layout geometry, whose
re-measurement is #125.

**Built agent-native.** Every specification, decision record, testbench, and
line of documentation here is produced by AI agents working from a ratified
spec and an append-only evidence trail — not human-authored work that agents
merely assisted with. Verification is the product: every claim traces to a
recorded result under PVT corners. Where the agents hit friction with the
open-source tooling — most often
[klayout-tools](https://github.com/2AMLogic/klayout-tools) — that friction is
filed as a public issue against the tool itself, so the fix benefits everyone
using this PDK, not just this repo.

## Why this block, on this PDK

The sky130 leg of the comparator twin set (see sg13g2-comparator for the
program). sky130-sar-adc embeds a comparator this repo characterizes
standalone; at 1.8 V the StrongARM's stacked devices are headroom-tight,
and the regeneration-speed vs offset trade lands differently than at
3.3 V — which is the comparative result the twins exist to surface.

The statistical story depends on what sky130's models actually ship for
mismatch; establishing that (and committing the answer) was the first
result, same as on SG13G2.

## Target specification

The bounds below are original engineering judgment for the sky130 1.8 V
core flavor, not ported numbers; each row states its basis rather than
asserting a bare figure. See [`spec/porting-plan.md`](spec/porting-plan.md) for what *does*
transfer (testbench structure and methodology, not spec numbers) from
[`sky130-sar-adc`](https://github.com/2AMLogic/sky130-sar-adc)'s embedded
comparator work.

History: [DR-002](spec/decision-records/DR-002-target-spec-ratification.md)
(2026-09-16) ratified three of the five rows below (Offset sigma,
Input-referred noise, Kickback) against a real measurement of this repo's
own `design/comparator.sch`, leaving two **DRAFT / OPEN** at that date; that
count is superseded by the DR-003/004/005 chronology below, and the
current per-row status is the table. No row's numeric
value changed from the original DRAFT figures — DR-002 disposes each row's
*status*, not its bound. See DR-002 for the full per-row reasoning,
including why the Kickback row is ratified as a bound the current design
does **not** meet. [DR-003](spec/decision-records/DR-003-kickback-slew-limited-clock.md)
(2026-09-21, issue #30) is the first kickback-mitigation pass against that
row: a partial improvement (144.60 → 85.71 mV peak at the same measurement
point), with the bound still unmet and the measured alternatives recorded.
[DR-004](spec/decision-records/DR-004-comparator-preamp-supersession.md)
(2026-09-22, issue #34) is the topology-class supersession that closes it: a
static preamplifier ahead of the StrongARM latch, measured **compliant with
the Kickback row at all three graded PVT anchors (1.89 / 1.86 / 1.77 mV at
tt/27 °C, ss/−40 °C, ff/125 °C)** while clearing every other ratified row
and re-anchoring the two DRAFT rows at measured numbers.
[DR-005](spec/decision-records/DR-005-full-corner-campaign.md)
(2026-09-22, issue #41) is the full-corner campaign those records left
open: the remaining four `_mm` mismatch corners plus N=200 offset
campaigns, a regeneration-inclusive noise measurement at three PVT
anchors, the `ff`/`sf`/`fs` decision-time corners, and the `sf`/`fs`
kickback skews — **ratifying the Decision-time row** (four of five rows
now ratified) and recording one new fact against a stretch figure: the
kickback stretch bound (≤ 2 mV) is breached by 1% at `sf`/−40 °C
(2.0208 mV), with the ≤ 5 mV target still cleared at every graded corner.
Only Supply/power remains DRAFT/OPEN.

Every figure above is measured against `design/comparator.sch`'s netlist.
[Issue #57](https://github.com/2AMLogic/sky130-comparator/issues/57) (T1 item
7) is the first pass that re-measures four of them against the
**parasitics-annotated extraction of the committed layout**, at the `tt`/27 °C
anchor plus `ss`/−40 °C for decision time — the standing layout-stage
re-verification gate DR-002's Open items named. **No ratified target bound is
breached, so no row is re-opened or re-ratified by it.** Two rows now sit over
their *stretch* figures, which the per-row notes below state in full rather
than adjust: **Kickback 1.8902 → 2.6767 mV** (≤ 2 mV stretch; ≤ 5 mV target
cleared 1.87×) and **Input-referred noise 0.5704 → 0.6576 mV rms** (≤ 0.6 mV
stretch; ≤ 1.0 mV target cleared 1.52×). Offset sigma degrades 1.7857 →
2.4446 mV (3σ = 7.33 mV, stretch bound still cleared) and decision time 0.4025
→ 0.5325 ns at `tt`/27 °C (both bounds cleared). A single mechanism — a 2.12×
loss of pick-off gain, from parasitic loading on the preamp outputs plus
PR #55's disclosed load-resistor width delta — drives most of it, and two
genuinely new post-layout facts appear: a 0.6547 mV **systematic**
layout-induced offset (exactly 0 on the symmetric schematic netlist) and a
polarity asymmetry in the sub-20 mV decision. That first pass' coverage was
deliberately narrow — two corners, four of the six sub-commands — and
[#64](https://github.com/2AMLogic/sky130-comparator/issues/64),
[#65](https://github.com/2AMLogic/sky130-comparator/issues/65) and
[#80](https://github.com/2AMLogic/sky130-comparator/issues/80) have since
widened it to every graded corner of `kickback`, `regen` and `noise`, all
five `_mm` corners of `offset`, and a post-layout deck form for `reset` and
`noise-tran`; the notes below say which corners remain unmeasured. The
systematic offset term above is now known to be essentially
process-independent (0.6350–0.6874 mV across all five `_mm` corners, #80),
so it is a property of the layout rather than of the `tt_mm` corner. The extraction is pinned to
`klayout-tools==0.8.0` / `klayout==0.30.12` (the pin every other committed
layout envelope carries; this paragraph's figures were measured under
0.6.0 / 0.30.10 on the earlier 0.42 µm-resistor layout and are historical, see
`layout/README.md`), asserted by `layout/extract_pex.py` and gated in CI),
because extracted per-net series resistances are **not** stable across
klt/klayout builds — up to 2.30× apart on this block.

| Parameter | Status | Target | Stretch | Basis |
|---|---|---|---|---|
| Offset sigma | **RATIFIED** (DR-002) | ≤ 15 mV, 3σ (input-referred, post-calibration-free) | ≤ 8 mV, 3σ | Monte Carlo on sky130's `_mm` local-mismatch corners (`AGAUSS()` per-instance terms) via `run.py offset` — a pick-off statistic calibrated to an input-referred gain by an ideal-device Vindiff sweep — N=16 seed-1/27 °C per corner plus N=200 campaigns at `tt_mm`/`ss_mm`, every run carrying a same-seed mismatch-disabled negative control that must reproduce stdev exactly 0; re-verified post-layout on the extracted netlist (#57, #80), with the layout-induced systematic term quantified by `run.py offset-bisect` (#66). All figures, per-corner tables, schematic→post-layout ratios and caveats: [sim/characterization-report.md §1](sim/characterization-report.md#1-offset-sigma). Owning records: [DR-002](spec/decision-records/DR-002-target-spec-ratification.md) (ratification), [DR-004](spec/decision-records/DR-004-comparator-preamp-supersession.md) (topology re-anchor), [DR-005](spec/decision-records/DR-005-full-corner-campaign.md) (corners + N=200), [DR-007](spec/decision-records/DR-007-systematic-decision-offset-row.md) (**proposed** companion systematic-offset row; disposes the #66 finding this σ-only row does not cover). |
| Input-referred noise | **RATIFIED** (DR-002); target-bound compliance basis **RE-OPENED** post-layout by [DR-006](spec/decision-records/DR-006-post-layout-noise-headroom-reopened.md) and **RE-CLOSED** by that record's **Amendment 1** (issue #83) on the regeneration-inclusive `fs`/125 °C measurement. The ≤ 0.6 mV stretch figure stays recorded as breached at four of seven corners on the AC basis (DR-006 Decision 4, unchanged) | ≤ 1.0 mV rms, differential | ≤ 0.6 mV rms, differential | Two bases. AC: ngspice `.noise` on a reduced, loop-broken preamp sub-model — a stated **lower bound**, excluding regeneration-phase noise (methodology per sky130-sar-adc's noise-budget DR). Regeneration-inclusive: `run.py noise-tran`, transient-noise Monte Carlo with equivalent-source injection, decision-referred (ngspice-46 has no device-noise transient). Since [DR-006 Amendment 1](spec/decision-records/DR-006-post-layout-noise-headroom-reopened.md) (#83) the row's target-bound compliance rests on the regeneration-inclusive `fs`/125 °C run — the binding corner — not on the AC lower bound. All corner figures, CIs and the two-basis caveat: [sim/characterization-report.md §2](sim/characterization-report.md#2-input-referred-noise). Owning records: [DR-002](spec/decision-records/DR-002-target-spec-ratification.md) (ratification), [DR-006](spec/decision-records/DR-006-post-layout-noise-headroom-reopened.md) (compliance-basis re-open + Amendment 1 re-close). |
| Decision time vs. overdrive | **RATIFIED** (DR-005; open since DR-002, anchored by DR-004) | ≤ 1.5 ns at 50 mV overdrive, 1.8 V | ≤ 0.8 ns at 50 mV overdrive | Transient regeneration-time sweep vs. differential input (`run.py regen`, methodology mirroring sky130-sar-adc's `run.py regen`): an 8-point 0.5–50 mV overdrive ladder at every graded corner, measured schematic-level and re-verified post-layout on the extracted netlist (#57, #64). The sub-20 mV post-layout resolution loss and its polarity-asymmetry mechanism are quantified by `run.py offset-bisect` (#66) and disposed in [DR-007](spec/decision-records/DR-007-systematic-decision-offset-row.md) (**proposed**); the bounds are stated at 50 mV overdrive, which resolves at every corner, and the `fs`/125 °C stretch margin is thin (1.04×). All corner figures, ratios and the sweep-resolution record: [sim/characterization-report.md §3](sim/characterization-report.md#3-decision-time-vs-overdrive). Owning records: [DR-002](spec/decision-records/DR-002-target-spec-ratification.md) (left open), [DR-004](spec/decision-records/DR-004-comparator-preamp-supersession.md) (topology re-anchor), [DR-005](spec/decision-records/DR-005-full-corner-campaign.md) (ratification). |
| Kickback | **RATIFIED (bound); design COMPLIANT at all three graded PVT anchors** (DR-002; pass 1: DR-003; topology pass: DR-004) | ≤ 5 mV disturbance into a 1 kΩ source impedance at the input nodes, single decision edge | ≤ 2 mV | Original testbench (`run.py kickback`) — no same-PDK comparator evidence existed for kickback, so the ≤ 5 mV bound is first-principles engineering judgment, measured as peak disturbance into a 1 kΩ source impedance at the input nodes on a single decision edge, every run carrying a zero-impedance `ideal` negative control that must collapse to exactly 0. Design history: non-compliant first sizing ([DR-002](spec/decision-records/DR-002-target-spec-ratification.md) ratified the bound unchanged), the [DR-003](spec/decision-records/DR-003-kickback-slew-limited-clock.md) soft-clock mitigation pass, then the [DR-004](spec/decision-records/DR-004-comparator-preamp-supersession.md) preamplifier topology that brought the design compliant; PVT and post-layout corner campaigns by [DR-005](spec/decision-records/DR-005-full-corner-campaign.md) and #64. All figures, margins and the stretch-breach record: [sim/characterization-report.md §4](sim/characterization-report.md#4-kickback). |
| Supply / power | **DRAFT / OPEN** (DR-002 — no measurement exists) | 1.8 V ±10% core supply (`nfet_01v8`/`pfet_01v8`); ≤ 50 µW average, one decision per clock edge at a stated clock rate (TBD) | ≤ 20 µW average | sky130 ships no complementary 3.3 V enhancement device pair (only `nfet_03v3_nvt`, a native NMOS with no PMOS partner) — confirmed against the installed `sky130_fd_pr` model library, per sky130-sar-adc's `spec/decision-records/DR-001-supply-flavor-scope.md`. The 1.8 V core flavor is therefore the only complementary-CMOS option at this node, consistent with `CLAUDE.md`'s "1.8 V headroom is the design constraint" (this half of the row is not in question). Power figures are still first-principles engineering judgment with no current/power measurement behind them; the clock rate this bound assumes is TBD and downstream of the still-open Decision-time row above, so [DR-002](spec/decision-records/DR-002-target-spec-ratification.md) leaves this row open rather than ratifying a bound with no evidentiary basis. First-ever current measurements landed with [DR-004](spec/decision-records/DR-004-comparator-preamp-supersession.md) (issue #34), whose preamplifier class costs static current by construction: ~51–55 µA in reset and ~344–564 µA during evaluate (tt/27 °C, ss/−40 °C, ff/125 °C; `spec/dr-004-support/evaluate_idd_probe.spice`) — i.e. ~95 µW static at 1.8 V, above this row's DRAFT 50 µW figure, plus a duty-cycle-dependent evaluate term. The row's "one decision per clock edge" framing predates any preamp and is superseded in substance; its re-anchoring is deliberately left as an open ratification decision (DR-004 Open items) — the DRAFT figures above are NOT changed by that record. |

**Statistical basis, stated once for the table.** sky130's `_mm` local-mismatch
corners enable real per-instance `AGAUSS()` device-mismatch terms (not a
global-process-only fallback) — the "strong" statistical story named in
`CLAUDE.md`'s "Statistical basis first" principle is available on this PDK,
and is now exercised (not merely planned) against this repo's own design,
per the ratified Offset sigma row above.

**Ratification status.** Per-row status lives in the table above and is not
restated here. The rows were ratified by decision record:
[DR-002](spec/decision-records/DR-002-target-spec-ratification.md) (Offset
sigma, Input-referred noise, Kickback) and
[DR-005](spec/decision-records/DR-005-full-corner-campaign.md) (Decision time
vs. overdrive); Supply / power is the only row still **DRAFT / OPEN**
(tracked by [#134](https://github.com/2AMLogic/sky130-comparator/issues/134)).
No row's numeric bound changed from the original DRAFT figures.
`spec/README.md` documents when a DR is required (whenever this table is set,
changed, or scoped) and how to write one. See issue
[#3](https://github.com/2AMLogic/sky130-comparator/issues/3) for the honest
gap-to-T1 checklist this table's ratification status feeds.

## License

Apache-2.0.
