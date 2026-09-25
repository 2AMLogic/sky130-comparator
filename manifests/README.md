# Block manifests — the graded T1 verdict of record

Issue #31 replaced this repo's hand-maintained gap-to-T1 checkbox list
(tracker issue #3) with a `klt signoff` block manifest: the block's T1
state is **graded** by the `klt` grader on demand, not hand-read from
prose that goes stale the moment the checklist, the evidence, or both
move.

## Files

| File | What it is |
| --- | --- |
| `sky130-comparator.json` | The block manifest — `block` (the fleet roll-up's identity for this repo), `kind`, and per-T1-item evidence citations. Grader contract: `klayout-tools` `docs/cli/signoff.md` → "Tier-verdict report". |
| `design-evidence-tiers.md` | **Vendored copy** of `2AMLogic/klayout-tools`'s checklist doc, pinned at klayout-tools commit `31a3e3c` (byte-for-byte: SHA-256 `c7a1e7e10627fae396007e0ff951734f37d95028b8f49f2e21e802e9f552f318`, MIT-licensed). It was introduced because klt 0.5.0 shipped a pre-item-11 checklist (10 items) while the doc had already grown an eleventh item — "Power delivery (structural)" — on 2026-09-17 (klayout-tools #2025), refined through #31a3e3c (2026-09-21). **The pinned klt now ships all 11 itself** (0.6.0 reports `build_t1_item_count: 11`), so the vendored copy's job is no longer "restore a missing row" but "pin the checklist revision": `--tiers-doc` keeps the record graded against one fixed, hash-recorded doc (`source_doc_content_hash`) rather than whatever revision the installed klt happens to carry. |
| `t1-signoff-report.json` | The committed **evidence record**: byte-for-byte `klt signoff --manifest` JSON output as of the pinned klt version below. This is the single row-per-item verdict (`met`/`unmet` plus per-item `reason`) the tracker (issue #3) points at. |
| `integrator-view.json` | The **rule-9 integrator view** (issue #36): what a full-chip integrator takes, as structured data at a fixed path — top cell, port list, netlist path (with its regeneration command), GDS path, measured area, maturity rung, provenance. Honest nulls (`"not yet produced"` notes) where the artifact does not exist yet (GDS, area today); the maturity rung always agrees with `t1-signoff-report.json`'s graded verdict. Consumers and their requirement rows live in [`spec/consumers.md`](../spec/consumers.md); this file is the data half of that record. |

## The current verdict, honestly

**1 of 11 T1 items is `met`: item 3, "DRC clean"** (issue #46), cited from
`layout/drc-report.json` — a committed `klt drc` envelope over
`layout/comparator.gds`, `status: "clean"`, 0 violations, deck identified by
content hash, with the cited input hash pinned in the manifest so a
regenerated GDS renders the row `unmet` (stale) rather than grading a
superseded run. Item 3's coverage disclosure is **claimant-enforced, not
graded** (`design-evidence-tiers.md` item 3): the
`layers_in_stream_without_rules` / `rules_skipped` / `deck_scope` fields that
qualify that "clean" are quoted in full in
[`layout/README.md`](../layout/README.md) → "DRC signoff, and the coverage
gaps behind 'clean'". A `met` row here is **not** evidence that they were
disclosed — read them against the claim.

**Item 4 ("LVS clean") is the one `unmet` row that has a passing envelope
behind it, deliberately uncited** (issue #49). `klt lvs` is run over
`layout/comparator.gds` against the item-1 netlist
(`sim/comparator-decision/testbench/comparator_core.spice`, what
`design/netlist.sh` writes out of `design/comparator.sch`, hand-edited
nowhere), the envelope is committed at
[`layout/lvs-report.json`](../layout/lvs-report.json), and it reports
`engine: "klayout"` (0.30.10), `status: "match"`, 0 errors, 16/16 devices and
12/12 nets paired, `power_connectivity.status: "unchecked"`.

It is not cited, because this block has a known layout-versus-schematic
device difference — the three poly resistors are drawn 20 % wider than the
`res_high_po_0p35` device `design/comparator.sch` specifies (`res_array`'s
0.42 µm width floor, klayout-tools#2407) — and that `match` holds only at
klt's **default parameter scope**, which compares no resistor geometry at
all. The committed
[`layout/lvs-coverage-probe.json`](../layout/lvs-coverage-probe.json)
measures both halves: three rows prove the compare can fail (connectivity and
MOSFET geometry really are verified, so the `match` is not vacuous), and a
forced-scope row reports the delta as a `device.property` error — `w_um`,
layout 0.42 vs reference 0.35, on all three resistors — with an attribution
control that flips back to `match` once the reference carries the drawn
width. Citing `met` from the configuration that happens not to look would
tell a fleet integrator this layout matches its schematic, which is not true.

That is a stricter reading than item 3's precedent, deliberately: there, a
*disclosed coverage hole* sits behind a `clean` verdict with nothing known to
be wrong inside it; here a **known defect** sits inside the hole. The full
reasoning, the warnings-only mismatches, and what
`power_connectivity: "unchecked"` does and does not mean are in
[`layout/README.md`](../layout/README.md) → "LVS: run, committed — and why T1
item 4 is still not claimed". The row becomes honestly citable once
klayout-tools#2436 reaches a released `klt` pin and the resistors are
re-drawn at 0.35 µm, removing the delta instead of disclosing it.

The other ten items render `unmet` with `reason: no_evidence`: apart from
item 4's uncited envelope above, no LVS/PEX citation exists, and this repo's
`sim/` harness records evidence as append-only Markdown records, not
`klt sim`/`klt yield` JSON envelopes, so nothing gradeable can be cited
honestly for them yet. Those `unmet` rows are the correct result per issue
#31's own "An all-`unmet` manifest is a correct result" section: they are the
machine-readable statement of the gap, and they must not be decorated with
citations that do not actually support them (items 1, 2, 9 and 10 in
particular are graded on "some passing envelope was cited", never on topical
relevance — see the grader contract).

Rows are `klt`-graded verdicts, not repo-content claims. Items 1
(schematic `design/comparator.sch` + `design/netlist.sh`), 2 (the
committed `layout/comparator.gds`) and 9 (`sim/comparator-decision`
testbenches) have committed content, but the grade is about a *check
behind a citation*, and no `klt` envelope backs them yet — the
`unmet`/`no_evidence` row is the accurate mechanical statement, and for
those three the grader could not tell a relevant citation from an
irrelevant one anyway. The historical per-item prose context lives in
tracker issue #3's edit history and `## Verified corrections`.

Item 11 ("Power delivery (structural)") renders a row, `unmet`, as
issue #31 requires. The grading-build disclosure now agrees with the doc:
as of the pinned klt, `build_t1_item_count` (11) **equals** the vendored
doc's item count (11) — klt 0.6.0 carries item 11's grading rules, so an
item-11 ERC/LVS citation is gradeable when one is eventually produced, and
no further klt upgrade is a prerequisite for it. (Under the previous 0.5.0
pin the build knew only 10 of the 11, and `scripts/check-t1-signoff.py`
carried a warning for that case; the check remains, it simply no longer
fires.) The report also records the grading build itself — `build.version`,
`git_commit`, `git_tag`, `is_release`, and a `grading_ruleset_id` hash —
so "which grader produced this verdict" is in the record, not inferred
from the CI pin.

## Regenerating the evidence record

```sh
klt signoff --manifest manifests/sky130-comparator.json \
    --tiers-doc manifests/design-evidence-tiers.md \
    --format json > manifests/t1-signoff-report.json
```

Exit code 3 (`tier: null`, some item `unmet`) is a **successful
grader run** — it is not an error; only exit 1 (manifest/doc/flag
parse failure) is. Gate on the payload, never the exit code
(`klayout-tools` `docs/cli/signoff.md` → "Exit codes and errors").

Regenerate whenever:

- a citation is added, removed, or its pinned artifact changes (the
  committed record and the manifest must tell the same story),
- the klt pin is bumped, or
- the vendored checklist doc is re-pinned to a newer upstream revision.

## The gate

`scripts/check-t1-signoff.py` re-runs the signoff and compares the fresh
report against the committed record:

- **fails** on any cited item that is not `met` fresh (a pinned artifact
  that changed, vanished, or was replaced — CI goes red instead of
  grading yesterday's evidence); on any regression vs the committed
  record; on a met citation whose re-hashed input disagreed
  (`input_verified: false`);
- **warns** (loudly, never passes silently) on a null `input_verified`
  with a recorded hash, a checklist-count move, or a new pass not yet
  reflected in the committed record;
- **passes** on the honest pre-T1 state — `unmet` uncited rows are the
  gap, visibly, which is the point.

**The gate runs warning-free today** (issue #47). Under the previous klt
0.5.0 pin it did not: 0.5.0 predates klayout-tools #2196, so item 3's
citation carried a `content_hash` the grading build never re-hashed
(`input_verified: null`) and the gate said so, loudly, on every run. klt
0.6.0 re-hashes `layout/comparator.gds` on disk against the envelope's own
`provenance.input.content_hash` and records `input_verified: true`, so
rule 3 now gets an affirmative verification instead of a standing warning.
The `input_verified: null` branch stays in the gate and stays covered by
the selftest — it is the correct behavior for any future citation graded by
a build that cannot re-hash.

Item 3's citation also now carries a `coverage` block (klayout-tools
#2002) echoing the cited envelope's `layers_in_stream_without_rules` /
`rules_skipped` / `deck_scope` verbatim, so the claimant-enforced
disclosure is readable next to the verdict. Reported is still not graded —
see "The current verdict, honestly" above, and read them against
[`layout/README.md`](../layout/README.md)'s claim.

CI (`.github/workflows/t1-signoff.yml`) installs klt **pinned to
`klayout-tools==0.6.0`** on the **`klayout==0.30.10`** engine — the build
that graded the committed record — then runs the gate's hermetic selftest
and the live gate. Bump the pin deliberately, regenerate the record in the
same change (see above), and note that a klt whose own checklist differs
from the vendored doc reports `build_t1_item_count`/`graded_by_build`
disclosures rather than failing. **A klt bump can move the evidence as well
as the report**: 0.6.0's curated sky130 deck added 10 rules over 0.5.0's,
so `layout/drc-report.json` had to be re-run in the same change — diff the
verdicts and the coverage, don't rubber-stamp the version string.

## The integrator-view gate (issue #36)

`scripts/check-integrator-view.py` is the rot gate for
`integrator-view.json`, and runs in the same CI workflow (selftest first,
then the live gate). It fails on a missing required key, on any non-null
cited path that does not exist in-tree (a stale netlist/GDS/schematic
reference — the view must never point an integrator at a vanished file),
and on a `maturity_rung` that disagrees with `t1-signoff-report.json`'s
graded `tier`. It also holds `maturity_rung_basis` to that same report
(issue #50): the field is required, must name the report's path (checked
for existence like any other cited path), and if it states an
`N/M T1 items met` figure, that figure must agree with the report's
`t1_met_count`/`t1_item_count` or the gate fails — a hand-maintained
sentence about a machine-graded verdict can no longer drift from the
record unnoticed. Honest nulls (`gds`, `measured_area`) are accepted only
with their "not yet produced" notes; when layout lands and the fields
flip to real values, the same existence check applies. The gate is
stdlib-only Python and needs no klt install.

## Fleet context

The fleet roll-up that consumes this manifest is
`2AMLogic/2am#956` (`klt signoff --fleet`). This repo's `block` value
(`sky130-comparator`) is that roll-up's identity for this row.
