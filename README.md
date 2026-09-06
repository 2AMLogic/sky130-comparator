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

## Target specification (DRAFT — engineering to ratify)

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

| Parameter | Target | Stretch | Basis |
|---|---|---|---|
| Offset sigma | ≤ 15 mV, 3σ (input-referred, post-calibration-free) | ≤ 8 mV, 3σ | Monte Carlo via sky130's `_mm` local-mismatch corners (`tt_mm`/`ss_mm`/`ff_mm`/`sf_mm`/`fs_mm`, `AGAUSS()` per-instance terms — confirmed present in the installed `sky130.lib.spice`; see sky130-sar-adc's `spec/decision-records/DR-001-supply-flavor-scope.md`), N ≥ 200 draws per corner once a comparator schematic exists. This repo has no schematic yet, so no measurement exists; the bound is a placeholder pending design. sky130-sar-adc's own embedded (non-standalone) comparator, at a first-pass `W = 4 µm` input-pair sizing with no offset-budget target, measured input-referred offset mean 35.24 mV / stdev 97.08 mV across N = 16 draws (`tt_mm`, `sim/comparator-decision/records/` in that repo) — informative prior art on the same PDK's mismatch magnitude at that (unoptimized) sizing, not a target this repo inherits; a standalone design here re-derives its own sizing and re-measures. |
| Input-referred noise | ≤ 1.0 mV rms, differential | ≤ 0.6 mV rms, differential | ngspice `.noise` analysis on a reduced (loop-broken) sub-model of the latch's input pair + tail, the same methodology sky130-sar-adc's `spec/decision-records/DR-004-comparator-topology-and-noise-budget.md` used and documented as excluding regeneration-phase noise (a lower bound, not a complete figure). That record measured 0.7064 mV rms differential (estimated) for its own embedded-comparator sizing at `tt`, 27 °C — cited here as same-PDK, same-supply prior art informing this row's initial bound, not a ported spec value; this repo's own testbench (once built, per the porting plan) re-measures against its own sizing. |
| Decision time vs. overdrive | ≤ 1.5 ns at 50 mV overdrive, 1.8 V | ≤ 0.8 ns at 50 mV overdrive | Transient regeneration-time sweep vs. differential input, methodology mirroring sky130-sar-adc's `sim/comparator-decision/run.py` `regen` subcommand. That repo's embedded comparator measured 0.5325–1.3975 ns across a 0.5–50 mV differential sweep (`tt`, 27 °C) — same-PDK, same-rail prior art, not a ported number. No sensitivity-vs-corner data exists yet; the slow/cold (`ss`, −40 °C) corner is expected to be the binding case per sky130-sar-adc's own DR-003/DR-004 headroom analysis, and is explicitly open work here too. |
| Kickback | ≤ 5 mV disturbance into a 1 kΩ source impedance at the input nodes, single decision edge | ≤ 2 mV | No sky130 same-PDK comparator evidence exists yet for kickback specifically (sky130-sar-adc's `sim/comparator-decision/` does not currently include a kickback experiment) — this bound is first-principles engineering judgment (comparable order-of-magnitude to sg13g2/gf180 twin bounds once those are drafted), to be superseded by a measured value once this repo's own testbench exists. Source impedance (1 kΩ) is a stated planning assumption, not yet tied to any driving stage. |
| Supply / power | 1.8 V ±10% core supply (`nfet_01v8`/`pfet_01v8`); ≤ 50 µW average, one decision per clock edge at a stated clock rate (TBD) | ≤ 20 µW average | sky130 ships no complementary 3.3 V enhancement device pair (only `nfet_03v3_nvt`, a native NMOS with no PMOS partner) — confirmed against the installed `sky130_fd_pr` model library, per sky130-sar-adc's `spec/decision-records/DR-001-supply-flavor-scope.md`. The 1.8 V core flavor is therefore the only complementary-CMOS option at this node, consistent with `CLAUDE.md`'s "1.8 V headroom is the design constraint." Power figures are first-principles engineering judgment (no dynamic-latch design exists yet to measure quiescent/dynamic current); the clock rate this bound assumes is TBD until a decision-time row is measured. |

**Statistical basis, stated once for the table.** sky130's `_mm` local-mismatch
corners enable real per-instance `AGAUSS()` device-mismatch terms (not a
global-process-only fallback) — the "strong" statistical story named in
`CLAUDE.md`'s "Statistical basis first" principle is available on this PDK. No
Monte Carlo run exists yet for *this* repo's own (not-yet-designed) comparator;
the offset row's basis column states the methodology this repo commits to
using once a schematic exists, and cites sky130-sar-adc's embedded-comparator
numbers only as same-PDK context for plausible magnitude, never as a
substitute measurement.

**Ratification status.** This table stays **DRAFT** in this pass — no
decision record is filed for it yet. `spec/README.md` documents when a DR is
required (whenever this table is set, changed, or scoped) and how to write
one. See issue #3 for the honest gap-to-T1 checklist this table's DRAFT
status feeds (item 5, full PVT corner sim vs. a *ratified* spec, is blocked
on this table's ratification).

## License

Apache-2.0.
