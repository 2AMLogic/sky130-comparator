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
write one: copy [`decision-records/TEMPLATE.md`](decision-records/TEMPLATE.md)
to `decision-records/DR-NNN-<slug>.md`
(next unused `NNN`, one decision per record), fill it in, and commit it
alongside the spec change it justifies. Never edit a ratified record after
the fact — if a decision changes, supersede it with a new `DR-NNN` that says
so, per the same convention `sky130-bandgap` and `sky130-sar-adc` both use.

**This pass sets no decision record.** The target-spec table filled in by
issue #2 stays **DRAFT** — these are original engineering-judgment bounds,
each stating its own basis, not a ratified commitment. A DR is owed the
first time that table's rows are ratified, changed, or rescoped, not before.

**Update (issue #28,
[DR-002](decision-records/DR-002-target-spec-ratification.md),
2026-09-16).** That first time has arrived for three of the table's five
rows (Offset sigma, Input-referred noise, Kickback), each now ratified
against a real measurement of this repo's own design; the other two
(Decision time vs. overdrive, Supply/power) stay DRAFT, explicitly scoped
as open pending further evidence rather than left silently unaddressed.
`spec/decision-records/TEMPLATE.md` did not exist when DR-002 was
written — like DR-001 before it, DR-002 is written directly against
DR-001's shape.

**Update (issue #33, 2026-09-22).** DR-003 was the third record written
that way, which is the trigger `spec/README.md` had named twice for
codifying the shape. It now exists:
[`decision-records/TEMPLATE.md`](decision-records/TEMPLATE.md), mirrored
from `sky130-bandgap`'s template. The three existing records conform to
it — each also carries permissible extensions the template does not
mandate (`Supersedes`/`Superseded by`/`Related` bullets, `## Open items`;
DR-001 an `### Amendment`), which stay as-is.

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

The **verdict of record** for this block's gap to T1 is the graded
manifest, not a hand-read checklist: `manifests/sky130-comparator.json`,
graded by `klt signoff --manifest` into the committed evidence record
`manifests/t1-signoff-report.json` (issue #31), with CI re-grading on
every push. As of this writing every T1 item renders `unmet`/`no_evidence`
— an honest machine-readable statement of the gap (and of the T2+ ladder
this repo has no mechanism to check). Tracker issue #3 points at that
manifest rather than maintaining its own duplicate checkbox list; its
edit history and `## Verified corrections` preserve the per-item
engineering context behind the rows.

## Consumers

[`spec/consumers.md`](consumers.md) is this block's rule-9 record (2am
cross-cutting rule 9, `2am#899`; issue #36): every repo recorded in
`2am/repos.yml` as consuming this block, the requirement rows each imposes
(port list, rails, input range, speed, offset, noise, area budget), a
met / not-met / unknown status for each row against this repo's spec, the
same-class/different-instance shape note, and the findings-routing rule
(findings about a consumer's block are filed on the consumer's tracker —
the `sky130-sar-adc#346` pattern). The structured-data half of that record
— what an integrator takes — is `manifests/integrator-view.json`, gated
against rot in CI by `scripts/check-integrator-view.py`.

## Porting plan

[`spec/porting-plan.md`](porting-plan.md) names the nearest mature sibling
(`sky130-sar-adc`) and the port/design split for this block's own
testbenches and design work.
