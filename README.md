# sky130-comparator

A dynamic latched comparator on SkyWater sky130 on
[SkyWater sky130](https://github.com/google/skywater-pdk), a 130 nm open CMOS PDK — designed by AI agents driving
[klayout-tools](https://github.com/2AMLogic/klayout-tools) and the
open-source xschem + ngspice flow.

**Status: just opened.** Nothing is designed yet. The first work is
the offset methodology at 1.8 V — sky130's Monte-Carlo mismatch support decides whether the strong or fallback statistical story applies.

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
mismatch; establishing that (and committing the answer) is the first
result, same as on SG13G2.

## Target specification

No sibling has a ratified comparator spec to port yet — sg13g2-comparator
and gf180-comparator are simultaneous wave-5 standups at the identical
bootstrap stage as this repo (each carries its own open "bootstrap the
block" issue, neither has a target-spec table). These bounds are therefore
original engineering judgment for the sky130 1.8 V core flavor, not a
ported number; each row states its basis rather than asserting a bare
figure. See [`spec/porting-plan.md`](spec/porting-plan.md) for what *does*
transfer (testbench structure and methodology, not spec numbers) from
[`sky130-sar-adc`](https://github.com/2AMLogic/sky130-sar-adc)'s embedded
comparator work.

As of
[DR-002](spec/decision-records/DR-002-target-spec-ratification.md)
(2026-09-16), three of the five rows below are **RATIFIED** against a real
measurement of this repo's own `design/comparator.sch`; two remain
**DRAFT / OPEN**, explicitly, pending further evidence. No row's numeric
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

| Parameter | Status | Target | Stretch | Basis |
|---|---|---|---|---|
| Offset sigma | **RATIFIED** (DR-002) | ≤ 15 mV, 3σ (input-referred, post-calibration-free) | ≤ 8 mV, 3σ | Monte Carlo via sky130's `_mm` local-mismatch corners (`tt_mm`/`ss_mm`/`ff_mm`/`sf_mm`/`fs_mm`, `AGAUSS()` per-instance terms — confirmed present in the installed `sky130.lib.spice`). Measured against this repo's own design: N=16 draws at `tt_mm`/27 °C, input-referred offset stdev 2.019 mV (3σ = 6.06 mV), same-seed mismatch-disabled negative control reproduces stdev = 0 exactly (`sim/comparator-decision/records/20260916-003531-52eb9b2.md`). Clears both the target and the stretch bound at this sample size. N=16 is sized for distribution-shape plumbing, not a tight yield-fraction claim (relative standard error on the stdev ≈ 18.3%); the other four `_mm` corners and an O(100s)-draw campaign remain open (DR-002 Open items). Re-measured against the DR-004 topology (issue #34, input pair widened 10 → 13 µm as the noise lever, pick-off re-anchored 1.0 → 0.65 ns for the preamp design's faster separation): stdev **1.7857 mV** (3σ = 5.36 mV), same-seed negative control still exactly 0 (`sim/comparator-decision/records/20260922-065300-e084b55.md`) — both bounds still cleared. sky130-sar-adc's own embedded (non-standalone) comparator, at a first-pass `W = 4 µm` input-pair sizing with no offset-budget target, measured input-referred offset mean 35.24 mV / stdev 97.08 mV across N = 16 draws (`tt_mm`, `sim/comparator-decision/records/` in that repo) — same-PDK prior art on mismatch magnitude at an unoptimized sizing, not a target this repo inherited. The four-corner + large-N coverage DR-002 left open has since landed ([DR-005](spec/decision-records/DR-005-full-corner-campaign.md), issue #41), all at the same seed-1/27 °C methodology with stdev-exactly-0 same-seed negative controls: `ss_mm` **1.8244 mV**, `ff_mm` **1.5954 mV**, `sf_mm` **1.6706 mV**, `fs_mm` **1.8218 mV** (N=16; records `sim/comparator-decision/records/20260922-173622-e23c509.md` … `.../20260922-175152-e23c509.md`) — the corner ranking is within the N=16 relative SE, with `ss_mm` nominally binding, and every corner clears both bounds at 3σ ≈ 4.8–5.5 mV. N=200 campaigns at both `tt_mm` and `ss_mm` (seed 1) replace the relative-SE caveat with a stated 95% CI: `tt_mm` **σ = 2.1854 mV, CI [1.9707, 2.4001]** (`sim/comparator-decision/records/20260922-191034-e23c509.md`), `ss_mm` **σ = 2.2353 mV, CI [2.0157, 2.4549]** (`.../20260922-202434-e026012.md`) — both give 3σ ≈ 6.6–6.7 mV, clearing the stretch bound with the implied yield against it > 99.96% (8 mV / σ ≈ 3.6σ per side). Note the N=200 estimates sit ~22% above the N=16 figure the row previously quoted — the small-sample estimate happened to land low, which is precisely the tightness gap DR-002's Open items flagged. |
| Input-referred noise | **RATIFIED** (DR-002) | ≤ 1.0 mV rms, differential | ≤ 0.6 mV rms, differential | ngspice `.noise` analysis on a reduced (loop-broken) sub-model of the latch's input pair + tail (methodology per sky130-sar-adc's `spec/decision-records/DR-004-comparator-topology-and-noise-budget.md`, documented there as excluding regeneration-phase noise — a lower bound, not a complete figure). Measured against this repo's own design: 0.4466 mV rms differential (estimated) at `tt`, 27 °C (`sim/comparator-decision/records/20260916-001416-52eb9b2.md`) — clears the 1.0 mV target with ~2.24× margin even as a lower bound; the 0.6 mV stretch bound has less margin (1.34×) and is the more likely candidate to be revisited once regeneration-inclusive noise is measured (DR-002 Open items). Full regeneration-inclusive noise and a PVT sweep remain open. Re-measured against the DR-004 topology (issue #34) on a re-derived sub-model that is the REAL static preamp stage verbatim (not the pre-DR-004 integration-phase proxy): **0.5704 mV rms differential** at `tt`/27 °C (`sim/comparator-decision/records/20260922-065534-e084b55.md`) — target cleared with 1.75× margin and the 0.6 mV stretch bound now cleared with 1.05× margin (the first-cut preamp sizing measured 0.72 mV, over stretch; the widened input pair and raised bias closed it, with the coupling of the noise/speed/kickback levers through the preamp bias recorded as a DR-004 consequence). sky130-sar-adc's DR-004 measured 0.7064 mV rms differential (estimated) for its own embedded-comparator sizing at `tt`, 27 °C — same-PDK, same-supply prior art, not a ported spec value. The regeneration-inclusive measurement DR-002 left open has since landed ([DR-005](spec/decision-records/DR-005-full-corner-campaign.md), issue #41, `run.py noise-tran` — transient-noise Monte Carlo with equivalent-source injection, since ngspice-46 has no device-noise transient): decision-referred input sigma **0.1362 mV** at `tt`/27 °C (95% CI [0.1216, 0.1493]; `sim/comparator-decision/records/20260922-192722-e23c509.md`), **0.1213 mV** at `ss`/−40 °C (CI [0.1084, 0.1335]; `.../20260922-205857-ebea4e2.md`), and **0.1754 mV** at `ff`/125 °C (CI [0.1594, 0.1905]; `.../20260923-010427-ebea4e2.md`). At `tt` and `ff` an independent decision-transition cross-check agrees with the pick-off figure within its coarser CI (0.1342 / 0.1515 mV) — the evidence that the regenerative phase adds no material noise term beyond the injected device noise; at `ss`/−40 the cross-check is honestly not measurable (the sigma-scaled overdrives sit below that corner's resolvable-overdrive floor, the same floor DR-004 recorded) — itself the statement that noise does not bound decisions at that corner. The decision-referred figures sit ~3–4× below the 1 kHz–1 GHz band-integrated AC figures because the decision sees the circuit's own bandwidth, not the integration band; the AC numbers remain the row's conservative reported basis and no bound changes. |
| Decision time vs. overdrive | **RATIFIED** (DR-005; open since DR-002, anchored by DR-004) | ≤ 1.5 ns at 50 mV overdrive, 1.8 V | ≤ 0.8 ns at 50 mV overdrive | Transient regeneration-time sweep vs. differential input, methodology mirroring sky130-sar-adc's `sim/comparator-decision/run.py` `regen` subcommand. Measured against this repo's own design at two points: 0.6775 ns at `tt`/27 °C and 0.6875 ns at `ss`/−40 °C (the corner this row's own basis, and DR-001's headroom probe, flagged as the expected binding case), both at 50 mV overdrive (`sim/comparator-decision/records/20260916-000727-52eb9b2.md`, `.../20260916-001345-52eb9b2.md`) — both points clear the stretch bound, not just the target, with almost no slow/cold penalty. [DR-002](spec/decision-records/DR-002-target-spec-ratification.md) leaves this row explicitly open rather than ratifying from two points: `ff`/`sf`/`fs` corners and the sub-50-mV overdrive shape off the `tt`/`ss` axis are unmeasured. Re-anchored at the DR-004 topology's numbers (issue #34): **0.4025 ns @ 50 mV at `tt`/27 °C** (8/8 sweep points resolved, down to 1.1375 ns @ 0.5 mV; `sim/comparator-decision/records/20260922-070800-e084b55.md`) and **0.3575 ns @ 50 mV at `ss`/−40 °C** (`.../20260922-071313-e084b55.md`) — ~2.9× faster than the DR-003 design at the same point. That ss/−40 °C record is honestly 7/8: the 0.5 mV point no longer resolves there (a 400 ns probe confirms it never regenerates, vs 2.5575 ns for the DR-001 design) — sub-mV decisions sit below the design's own ~1.8 mV offset floor in practice, and the row's bounds are stated at 50 mV, but the regression is recorded in DR-004's Consequences and Open items rather than hidden. sky130-sar-adc's embedded comparator measured 0.5325–1.3975 ns across a 0.5–50 mV differential sweep (`tt`, 27 °C) — same-PDK, same-rail prior art, not a ported number. The full PVT sweep DR-002 left open has since landed ([DR-005](spec/decision-records/DR-005-full-corner-campaign.md), issue #41): **`ff`/125 °C 0.4975 ns, `sf`/−40 °C 0.3475 ns, `sf`/125 °C 0.4725 ns, `fs`/−40 °C 0.3725 ns, `fs`/125 °C 0.5375 ns** at 50 mV overdrive (records `sim/comparator-decision/records/20260922-175252-e23c509.md`, `.../20260922-175425-e23c509.md`, `.../20260922-175554-e23c509.md`, `.../20260922-175734-e23c509.md`, `.../20260922-175918-e23c509.md`; 8/8 sweep points resolve at every new corner). Seven PVT points now span the set; the slowest (`fs`/125 °C, 0.5375 ns) clears the stretch bound with 1.49× margin and the target with 2.8× — DR-005 **ratifies this row** at the DR-002-stated bounds unchanged, with the one non-resolving point in the whole set still the `ss`/−40 °C 0.5 mV point DR-004 recorded. |
| Kickback | **RATIFIED (bound); design COMPLIANT at all three graded PVT anchors** (DR-002; pass 1: DR-003; topology pass: DR-004) | ≤ 5 mV disturbance into a 1 kΩ source impedance at the input nodes, single decision edge | ≤ 2 mV | No sky130 same-PDK comparator evidence existed for kickback specifically before this repo's own original testbench (issue #26, `python3 sim/comparator-decision/run.py kickback`, since sky130-sar-adc's `sim/comparator-decision/` does not include a kickback experiment either) — this bound was first-principles engineering judgment (comparable order-of-magnitude to sg13g2/gf180 twin bounds once those are drafted). That testbench's first nominal-corner (`tt`, 27 °C) measurement, at `design/comparator.sch`'s current sizing and the stated 1 kΩ source impedance, is 144.60 mV peak — ~29× the target and ~72× the stretch bound (`sim/comparator-decision/records/20260916-060139-f1eb978.md`). [DR-002](spec/decision-records/DR-002-target-spec-ratification.md) **ratifies this bound unchanged** rather than relaxing it to match the measurement (per `CLAUDE.md`: "agents do not relax the ratified spec to make results pass") and documents the current sizing as non-compliant against it; a mitigation design pass (candidate directions: reducing the offset-driven input-pair `Cgd`, dummy/compensation switches, bootstrapped/slew-limited clocking) is recommended as follow-on work, not performed by DR-002 itself. That pass has since happened: [DR-003](spec/decision-records/DR-003-kickback-slew-limited-clock.md) (issue #30) designs, measures, and lands a ~250 ps RC soft-clock shaper (`R_CLKS` + `M_CLKCAP` → internal node `CLKT` driving all five clocked gates, stretching the whole evaluate onset) — the measured candidate-mitigation series is recorded there with numbers, including why the input-isolation and charge-cancellation families were rejected (ratified-noise-row and decision-time regressions). Post-mitigation re-measurement at the same `tt`/27 °C, 1 kΩ, 50 mV overdrive point: **85.71 mV peak** (`sim/comparator-decision/records/20260921-185208-bb32850.md`, whose `ideal` negative control still collapses to 0.0000 mV) — a 40.7% reduction, still ~17× the target and ~43× the stretch bound, so the row's non-compliance annotation stands rather than being quietly flipped; full compliance is documented as requiring the preamplifier/double-tail topology class [DR-001](spec/decision-records/DR-001-comparator-topology.md) explicitly scoped out. That topology pass has since landed: [DR-004](spec/decision-records/DR-004-comparator-preamp-supersession.md) (issue #34) supersedes DR-001's no-preamp clause with a static resistive-load preamplifier ahead of the StrongARM latch (the double-tail route was evaluated first and measured still ~1:1 elastic — 7.5 mV @ 0.77 ns, probe deck committed under `spec/dr-004-support/`). Re-measurement at the identical tt/27 °C methodology point: **1.8902 mV peak** (`sim/comparator-decision/records/20260922-070119-e084b55.md`), with the PVT anchors ss/−40 °C at **1.8605 mV** (`.../20260922-070212-e084b55.md`) and ff/125 °C — the corner where the DR-003-era isolation candidate breached — at **1.7677 mV** (`.../20260922-070307-e084b55.md`); every `ideal` control still collapses to 0.0000 mV. All three anchors clear both the target (2.65–2.83× margin) and the stretch bound (1.06–1.13×); the stretch margin is thin and PVT-bracketed, and DR-002's standing layout-stage re-verification requirement remains the gate before any silicon claim. The `sf`/`fs` skew corners at both temperature extremes complete the row's PVT set ([DR-005](spec/decision-records/DR-005-full-corner-campaign.md), issue #41): **`sf`/−40 °C 2.0208 mV, `sf`/125 °C 1.7837 mV, `fs`/−40 °C 1.8408 mV, `fs`/125 °C 1.6091 mV** (records `sim/comparator-decision/records/20260922-180026-e23c509.md` … `.../20260922-180425-e23c509.md`; every `ideal` control still collapses to 0.0000 mV). All seven graded corners clear the ≤ 5 mV target with 2.5–3.1× margin; the ≤ 2 mV **stretch** bound is breached by 1% at exactly one corner — `sf`/−40 °C, 2.0208 mV — recorded by DR-005 rather than legislated away (the stretch figure is not a compliance requirement and is unchanged). |
| Supply / power | **DRAFT / OPEN** (DR-002 — no measurement exists) | 1.8 V ±10% core supply (`nfet_01v8`/`pfet_01v8`); ≤ 50 µW average, one decision per clock edge at a stated clock rate (TBD) | ≤ 20 µW average | sky130 ships no complementary 3.3 V enhancement device pair (only `nfet_03v3_nvt`, a native NMOS with no PMOS partner) — confirmed against the installed `sky130_fd_pr` model library, per sky130-sar-adc's `spec/decision-records/DR-001-supply-flavor-scope.md`. The 1.8 V core flavor is therefore the only complementary-CMOS option at this node, consistent with `CLAUDE.md`'s "1.8 V headroom is the design constraint" (this half of the row is not in question). Power figures are still first-principles engineering judgment with no current/power measurement behind them; the clock rate this bound assumes is TBD and downstream of the still-open Decision-time row above, so [DR-002](spec/decision-records/DR-002-target-spec-ratification.md) leaves this row open rather than ratifying a bound with no evidentiary basis. First-ever current measurements landed with [DR-004](spec/decision-records/DR-004-comparator-preamp-supersession.md) (issue #34), whose preamplifier class costs static current by construction: ~51–55 µA in reset and ~344–564 µA during evaluate (tt/27 °C, ss/−40 °C, ff/125 °C; `spec/dr-004-support/evaluate_idd_probe.spice`) — i.e. ~95 µW static at 1.8 V, above this row's DRAFT 50 µW figure, plus a duty-cycle-dependent evaluate term. The row's "one decision per clock edge" framing predates any preamp and is superseded in substance; its re-anchoring is deliberately left as an open ratification decision (DR-004 Open items) — the DRAFT figures above are NOT changed by that record. |

**Statistical basis, stated once for the table.** sky130's `_mm` local-mismatch
corners enable real per-instance `AGAUSS()` device-mismatch terms (not a
global-process-only fallback) — the "strong" statistical story named in
`CLAUDE.md`'s "Statistical basis first" principle is available on this PDK,
and is now exercised (not merely planned) against this repo's own design,
per the ratified Offset sigma row above.

**Ratification status.** As of
[DR-002](spec/decision-records/DR-002-target-spec-ratification.md)
(2026-09-16, status: proposed pending PR merge), the Offset sigma,
Input-referred noise, and Kickback rows are **RATIFIED**; Decision time vs.
overdrive and Supply/power stay **DRAFT / OPEN**, explicitly, pending
further evidence (see DR-002's per-row disposition and Open items). No
row's numeric bound changed from the original DRAFT figures. `spec/README.md`
documents when a DR is required (whenever this table is set, changed, or
scoped) and how to write one. See issue #3 for the honest gap-to-T1
checklist this table's ratification status feeds (item 5, full PVT corner
sim vs. a *ratified* spec, remains open for the two DRAFT/OPEN rows and for
full-corner coverage on the ratified ones too — DR-002 is a first pass, not
a campaign-complete characterization).

## License

Apache-2.0.
