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

| Parameter | Status | Target | Stretch | Basis |
|---|---|---|---|---|
| Offset sigma | **RATIFIED** (DR-002) | ≤ 15 mV, 3σ (input-referred, post-calibration-free) | ≤ 8 mV, 3σ | Monte Carlo via sky130's `_mm` local-mismatch corners (`tt_mm`/`ss_mm`/`ff_mm`/`sf_mm`/`fs_mm`, `AGAUSS()` per-instance terms — confirmed present in the installed `sky130.lib.spice`). Measured against this repo's own design: N=16 draws at `tt_mm`/27 °C, input-referred offset stdev 2.019 mV (3σ = 6.06 mV), same-seed mismatch-disabled negative control reproduces stdev = 0 exactly (`sim/comparator-decision/records/20260916-003531-52eb9b2.md`). Clears both the target and the stretch bound at this sample size. N=16 is sized for distribution-shape plumbing, not a tight yield-fraction claim (relative standard error on the stdev ≈ 18.3%); the other four `_mm` corners and an O(100s)-draw campaign remain open (DR-002 Open items). sky130-sar-adc's own embedded (non-standalone) comparator, at a first-pass `W = 4 µm` input-pair sizing with no offset-budget target, measured input-referred offset mean 35.24 mV / stdev 97.08 mV across N = 16 draws (`tt_mm`, `sim/comparator-decision/records/` in that repo) — same-PDK prior art on mismatch magnitude at an unoptimized sizing, not a target this repo inherited. |
| Input-referred noise | **RATIFIED** (DR-002) | ≤ 1.0 mV rms, differential | ≤ 0.6 mV rms, differential | ngspice `.noise` analysis on a reduced (loop-broken) sub-model of the latch's input pair + tail (methodology per sky130-sar-adc's `spec/decision-records/DR-004-comparator-topology-and-noise-budget.md`, documented there as excluding regeneration-phase noise — a lower bound, not a complete figure). Measured against this repo's own design: 0.4466 mV rms differential (estimated) at `tt`, 27 °C (`sim/comparator-decision/records/20260916-001416-52eb9b2.md`) — clears the 1.0 mV target with ~2.24× margin even as a lower bound; the 0.6 mV stretch bound has less margin (1.34×) and is the more likely candidate to be revisited once regeneration-inclusive noise is measured (DR-002 Open items). Full regeneration-inclusive noise and a PVT sweep remain open. sky130-sar-adc's DR-004 measured 0.7064 mV rms differential (estimated) for its own embedded-comparator sizing at `tt`, 27 °C — same-PDK, same-supply prior art, not a ported spec value. |
| Decision time vs. overdrive | **DRAFT / OPEN** (DR-002 — no full PVT sweep yet) | ≤ 1.5 ns at 50 mV overdrive, 1.8 V | ≤ 0.8 ns at 50 mV overdrive | Transient regeneration-time sweep vs. differential input, methodology mirroring sky130-sar-adc's `sim/comparator-decision/run.py` `regen` subcommand. Measured against this repo's own design at two points: 0.6775 ns at `tt`/27 °C and 0.6875 ns at `ss`/−40 °C (the corner this row's own basis, and DR-001's headroom probe, flagged as the expected binding case), both at 50 mV overdrive (`sim/comparator-decision/records/20260916-000727-52eb9b2.md`, `.../20260916-001345-52eb9b2.md`) — both points clear the stretch bound, not just the target, with almost no slow/cold penalty. [DR-002](spec/decision-records/DR-002-target-spec-ratification.md) leaves this row explicitly open rather than ratifying from two points: `ff`/`sf`/`fs` corners and the sub-50-mV overdrive shape off the `tt`/`ss` axis are unmeasured. sky130-sar-adc's embedded comparator measured 0.5325–1.3975 ns across a 0.5–50 mV differential sweep (`tt`, 27 °C) — same-PDK, same-rail prior art, not a ported number. |
| Kickback | **RATIFIED (bound); design non-compliant, mitigation pass 1 landed** (DR-002; pass 1: DR-003) | ≤ 5 mV disturbance into a 1 kΩ source impedance at the input nodes, single decision edge | ≤ 2 mV | No sky130 same-PDK comparator evidence existed for kickback specifically before this repo's own original testbench (issue #26, `python3 sim/comparator-decision/run.py kickback`, since sky130-sar-adc's `sim/comparator-decision/` does not include a kickback experiment either) — this bound was first-principles engineering judgment (comparable order-of-magnitude to sg13g2/gf180 twin bounds once those are drafted). That testbench's first nominal-corner (`tt`, 27 °C) measurement, at `design/comparator.sch`'s current sizing and the stated 1 kΩ source impedance, is 144.60 mV peak — ~29× the target and ~72× the stretch bound (`sim/comparator-decision/records/20260916-060139-f1eb978.md`). [DR-002](spec/decision-records/DR-002-target-spec-ratification.md) **ratifies this bound unchanged** rather than relaxing it to match the measurement (per `CLAUDE.md`: "agents do not relax the ratified spec to make results pass") and documents the current sizing as non-compliant against it; a mitigation design pass (candidate directions: reducing the offset-driven input-pair `Cgd`, dummy/compensation switches, bootstrapped/slew-limited clocking) is recommended as follow-on work, not performed by DR-002 itself. That pass has since happened: [DR-003](spec/decision-records/DR-003-kickback-slew-limited-clock.md) (issue #30) designs, measures, and lands a ~250 ps RC soft-clock shaper (`R_CLKS` + `M_CLKCAP` → internal node `CLKT` driving all five clocked gates, stretching the whole evaluate onset) — the measured candidate-mitigation series is recorded there with numbers, including why the input-isolation and charge-cancellation families were rejected (ratified-noise-row and decision-time regressions). Post-mitigation re-measurement at the same `tt`/27 °C, 1 kΩ, 50 mV overdrive point: **85.71 mV peak** (`sim/comparator-decision/records/20260921-185208-bb32850.md`, whose `ideal` negative control still collapses to 0.0000 mV) — a 40.7% reduction, still ~17× the target and ~43× the stretch bound, so the row's non-compliance annotation stands rather than being quietly flipped; full compliance is documented as requiring the preamplifier/double-tail topology class [DR-001](spec/decision-records/DR-001-comparator-topology.md) explicitly scoped out. |
| Supply / power | **DRAFT / OPEN** (DR-002 — no measurement exists) | 1.8 V ±10% core supply (`nfet_01v8`/`pfet_01v8`); ≤ 50 µW average, one decision per clock edge at a stated clock rate (TBD) | ≤ 20 µW average | sky130 ships no complementary 3.3 V enhancement device pair (only `nfet_03v3_nvt`, a native NMOS with no PMOS partner) — confirmed against the installed `sky130_fd_pr` model library, per sky130-sar-adc's `spec/decision-records/DR-001-supply-flavor-scope.md`. The 1.8 V core flavor is therefore the only complementary-CMOS option at this node, consistent with `CLAUDE.md`'s "1.8 V headroom is the design constraint" (this half of the row is not in question). Power figures are still first-principles engineering judgment with no current/power measurement behind them; the clock rate this bound assumes is TBD and downstream of the still-open Decision-time row above, so [DR-002](spec/decision-records/DR-002-target-spec-ratification.md) leaves this row open rather than ratifying a bound with no evidentiary basis. |

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
