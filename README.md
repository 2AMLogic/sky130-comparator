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

Offset sigma (basis stated), input-referred noise, decision time vs
overdrive at 1.8 V, kickback into stated source impedance, supply/power.

## License

Apache-2.0.
