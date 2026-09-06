# spec/

This directory holds this block's specification-related documents and their
decision history. The target-spec table itself lives in the top-level
[`README.md`](../README.md#target-specification-draft--engineering-to-ratify)
(not a `spec/target-spec.md` file — see `spec/porting-plan.md`'s citation
trail for why: this fleet's convention, confirmed by reading
[`sky130-bandgap`](https://github.com/2AMLogic/sky130-bandgap)'s repo, keeps
the table in the top-level README, ratified via a decision record).

## Decision records

A decision record is required whenever a value or approach in the
top-level README's target-spec table is **set, changed, or scoped** — not
for routine design/sim work that merely targets the existing table. To
write one: copy `decision-records/TEMPLATE.md` (create it, mirroring
[`sky130-bandgap/spec/decision-records/TEMPLATE.md`](https://github.com/2AMLogic/sky130-bandgap/tree/main/spec/decision-records),
if no template exists yet in this repo) to `decision-records/DR-NNN-<slug>.md`
(next unused `NNN`, one decision per record), fill it in, and commit it
alongside the spec change it justifies. Never edit a ratified record after
the fact — if a decision changes, supersede it with a new `DR-NNN` that says
so, per the same convention `sky130-bandgap` and `sky130-sar-adc` both use.

**This pass sets no decision record.** The target-spec table filled in by
issue #2 stays **DRAFT** — these are original engineering-judgment bounds,
each stating its own basis, not a ratified commitment. A DR is owed the
first time that table's rows are ratified, changed, or rescoped, not before.

## Review bar

One-command characterization plus README reproducibility is a standing bar
for this block, from day one — not deferred until the block reaches T1. Any
design challenge or external review of this canary should be able to
regenerate every cited result (schematic → netlist → testbench → evidence
record) from a single documented command per experiment, matching the
`sim/`-evidence conventions this repo's sibling canaries already use (see
`spec/porting-plan.md`'s citation of `sky130-sar-adc`'s
`sim/comparator-decision/run.py` invocation style). This is wired into the
gap-to-T1 tracker (#3) from the start rather than added retroactively.

## Gap-to-T1 tracker

#3 tracks this block's gap to T1 sim-validated / bronze per the
klayout-tools design-evidence ladder — a 10-item checklist, every item
honestly unchecked as of this pass (0/10; no schematic, layout, or `sim/`
tree exists yet).

## Porting plan

[`spec/porting-plan.md`](porting-plan.md) names the nearest mature sibling
(`sky130-sar-adc`) and the port/design split for this block's own
testbenches and design work.
