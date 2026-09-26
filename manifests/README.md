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

**2 of 11 T1 items are `met`: item 3, "DRC clean" and item 8,
"Characterization report."**

**Item 3, "DRC clean"** (issue #46), cited from
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

**Item 8, "Characterization report"** (issue #86), is cited from
[`sim/characterization-report.md`](../sim/characterization-report.md) through a
`"kind": "generic"` evidence envelope. **What that `met` row does and does not
establish has its own section below** — read it before citing the row; this is
the one T1 item whose verdict is a claimant assertion rather than a tool's.

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

**Item 7 ("Post-layout verification") is the second row with real evidence
that cannot be cited — and here the blocker is the grader's own input
contract, not a defect in the evidence** (issue #57). Post-layout
re-simulation has run: `layout/extract-parasitics.json` and
`layout/comparator.extract.spice` are a committed `klt extract --parasitics`
envelope and netlist over `layout/comparator.gds`, and five append-only
records under `sim/comparator-decision/records/` re-measure four spec rows
against it with the schematic-vs-extracted delta stated per row
(`sim/comparator-decision/README.md` → "Post-layout records").

Item 7 is *kind-restricted*: for an `analog` partition `klt signoff` accepts
**only** a `klt pex` envelope, and a `klt extract` citation renders `unmet`
with `reason: "wrong_kind"` no matter how much post-layout work stands behind
it. `klt pex` in turn can only be driven by `klt sim` **request JSON**
testbenches, whose `measurements[]` entries are verbatim `.meas` cards — and
none of this bench's five measurements is expressible as a `.meas` card (see
`sim/comparator-decision/README.md` → "Why not `klt pex`?"). So the envelope
item 7 wants cannot be produced here at all. Filed generically per
`CLAUDE.md`'s friction protocol as
[2AMLogic/klayout-tools#2478](https://github.com/2AMLogic/klayout-tools/issues/2478);
the row stays `unmet`/`no_evidence` rather than being decorated with a
citation of the wrong kind.

**Item 11 ("Power delivery (structural)") is the third row with real evidence
that is deliberately not cited — and its blocker is item 4's defect, reached
through the grader's own compound rule** (issue #68). The ERC half is done and
clean: `layout/erc-spec.json` declares `VDD`/`GND` as `"kind": "supply"` over
the four conductor roles they route on plus a `ties[]` entry for each of the
p-substrate and n-well taps, and `layout/erc-report.json` is a committed
`klt erc` envelope over `layout/comparator.gds` reporting `erc_status:
"clean"`, 0 findings, and — the field that matters as much as the verdict —
`erc_coverage.skipped: []`, i.e. both ties were actually *checked* rather than
rejected as unfalsifiable. `layout/erc-coverage-probe.json` is the
negative-control matrix behind it: nine runs against perturbed scratch copies
of the spec (and one of the stream), each asserting the exact findings and the
exact `erc_coverage.skipped` reasons its perturbation must produce, including
the two rows that show klt's own degeneracy rejections firing against this very
spec once its narrowing is removed.

For an `analog` block with no P&R run, `klt signoff` grades item 11 on that ERC
run **plus `layout/lvs-report.json`, which must itself pass** — the envelope
item 4 withholds. The grader does not require item 4 to be cited, so the
citation *would* grade `met` and move this count 1 → 2; that is measured, not
assumed (`layout/erc-coverage-probe.json` → `signoff_if_cited`). It is left
uncited because the item's LVS half turns out to carry **no information beyond
"item 4's envelope reports `match`"**: `net_correspondence` lists only matched
nets, so the supply-pairing predicate is satisfied by every `match` and failed
by every `mismatch` — including one whose perturbation is a single MOSFET width
and touches no rail. Each probe row now records that measurement
(`layout/lvs-coverage-probe.json` → `supply_pairing`). So a `met` item 11 would
rest on exactly the verdict this file already says must not be cited. The full
reasoning, the measurement table, and what the ERC evidence *does* establish are
in [`layout/README.md`](../layout/README.md) → "ERC: supply-spec run, committed
— and why T1 item 11 is still not claimed". The grader-side weakness is filed
generically as
[2AMLogic/klayout-tools#2495](https://github.com/2AMLogic/klayout-tools/issues/2495);
the row itself becomes a one-line manifest change the moment item 4 is honestly
citable, which is the same klayout-tools#2436 + re-draw step item 4 is waiting
on.

The other nine items render `unmet` with `reason: no_evidence`: apart from
item 4's uncited envelope, item 7's ungradeable one and item 11's uncited
ERC evidence above, no LVS/PEX citation exists, and this repo's
`sim/` harness records evidence as append-only Markdown records, not
`klt sim`/`klt yield` JSON envelopes, so nothing gradeable can be cited
honestly for them yet. Item 8 is the one exception to that last clause, and
only because the checklist makes it one: it is the sole T1 item whose grading
table accepts a hand-assembled record through the opt-in `generic` envelope
(see its section below). Those `unmet` rows are the correct result per issue
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

Item 11's row is present and graded, as issue #31 requires, and the
grading-build disclosure agrees with the doc: as of the pinned klt,
`build_t1_item_count` (11) **equals** the vendored
doc's item count (11) — klt 0.6.0 carries item 11's grading rules, so the
compound ERC/LVS citation described above is gradeable today (verified: it
renders `met` against a scratch manifest), and no klt upgrade is a
prerequisite for it. What holds the row at `unmet` is the citation decision
above, not the grader. (Under the previous 0.5.0
pin the build knew only 10 of the 11, and `scripts/check-t1-signoff.py`
carried a warning for that case; the check remains, it simply no longer
fires.) The report also records the grading build itself — `build.version`,
`git_commit`, `git_tag`, `is_release`, and a `grading_ruleset_id` hash —
so "which grader produced this verdict" is in the record, not inferred
from the CI pin.

## Item 8 — the characterization report, and what its `met` row does not establish

Item 8 is the second `met` row (issue #86), and it is unlike item 3 in a way
that matters more than the verdict: **`klt` does not check it.** The other ten
T1 items are graded on a `klt` verb's own output — a run the tool performed and
whose result it classified. Item 8 names no verb (`design-evidence-tiers.md`
says so explicitly: "there is no dedicated aggregation command, and its
evidence may be a hand-assembled record"), and the only kind it accepts is the
opt-in `"kind": "generic"` envelope, whose pass predicate is literally
`status == "pass"`. Nothing in `klt` reads
[`sim/characterization-report.md`](../sim/characterization-report.md), checks
that it covers five rows, or checks that anything in it is true.

So the `met` row is a **claimant assertion**, and this file states its exact
scope. It asserts two things:

1. **Aggregation** — one artifact exists that covers all five target-spec rows
   (Offset sigma, Input-referred noise, Decision time vs. overdrive, Kickback,
   Supply/power), each with its ratification status, its bounds, the measured
   figure at every condition that has one — schematic and post-layout, across
   the seven graded PVT corners with the schematic→post-layout ratio per row —
   and the `sim/comparator-decision/records/*.md` record each figure rests on.
2. **Currency** — that report and every artifact its "Evidence index" names are
   byte-for-byte the ones the citation was generated against. This half is
   mechanically enforced; see "How freshness is enforced" below.

It asserts **nothing whatsoever about whether any bound is met**, and the rows
below are live counter-examples that a reader must not smooth over:

- **Input-referred noise.** The bound is RATIFIED, every measured figure clears
  it, and for a while the row was still **not** compliant-as-read:
  [DR-006](../spec/decision-records/DR-006-post-layout-noise-headroom-reopened.md)
  moved its *compliance basis* from RATIFIED-and-clear to **RATIFIED, basis
  OPEN**, because the post-layout worst corner (`fs`/125 °C, 0.9423 mV rms
  against a ≤ 1.0 mV target, on a figure the methodology states is a **lower**
  bound) leaves only 0.335 mV rms of quadrature headroom for the excluded
  regeneration-phase term, where DR-002 ratified the row on an argument that
  ~0.90 mV would be needed. **DR-006's closure condition has since run**
  ([#83](https://github.com/2AMLogic/sky130-comparator/issues/83)): post-layout
  `noise-tran` at `fs`/125 °C measures 0.2540 mV rms differential
  regeneration-inclusive (3.94× under the target; 3.32× at its 95% CI's upper
  bound), and **DR-006 Amendment 1 closes the target-bound basis**. What
  remains recorded rather than closed: the ≤ 0.6 mV **stretch** figure is still
  breached at four of seven corners on the AC basis, and five graded corners are
  still unmeasured post-layout for `noise-tran`. The point for *this* document
  is unchanged either way — a `met` item 8 never closed that basis, weakened
  it, or implied it away; the measurement did.
- **Supply / power.** Still **DRAFT / OPEN**: no ratified bound exists at all,
  no average-power figure exists at all (the clock rate the DRAFT figure
  assumes is TBD), and the measurement that does exist — ~95 µW static at
  1.8 V, from DR-004's preamplifier bias — is already above the DRAFT 50 µW
  figure. A `met` item 8 says a report covers this row honestly, not that the
  row passes anything.

This is the same register as the item-4, item-7 and item-11 paragraphs above,
reached from the other direction. There, real passing evidence is **not** cited
because citing it would tell a fleet integrator something untrue. Here the
citation *is* made, because the thing it asserts — "an aggregated, current
characterization artifact exists" — is exactly what item 8 asks for and is
exactly true. What must not happen is the two being conflated: a `met` item 8
next to an `unmet` item 7 does not mean the characterization is signed off, it
means the aggregation exists.

### How freshness is enforced

Item 8's manifest entry is **command-backed**, not file-backed:

```json
"8": { "command": ["python3", "scripts/characterization-envelope.py"] }
```

`klt signoff` runs that script and grades the item against *that run's own*
stdout. The script re-hashes the report and every artifact its Evidence index
names against the pins committed in
[`sim/characterization-envelope.json`](../sim/characterization-envelope.json),
and emits `status: "pass"` only when everything matches — so an edited report,
a regenerated evidence record, a vanished record, or an index that has drifted
out of step with the pins each render item 8 `unmet`/`check_failed` rather than
grading a stale document. Regenerate with
`python3 scripts/characterization-envelope.py --update`, then regenerate the
signoff record below. `python3 scripts/characterization-envelope.py --selftest`
is the hermetic negative-control suite proving each of those cases bites, and
runs in CI alongside the other gates' selftests.

Two properties of that design are load-bearing and easy to get wrong:

- **The drift signal is the envelope's `status`, not the exit code.**
  `_grade_evidence` parses a command-backed entry's stdout *before* it inspects
  `exit_status`, and grades whatever parses regardless of it. A guard that
  exited 1 while still printing `status: "pass"` would grade `met` anyway. The
  script derives its exit code *from* the status, and the selftest asserts that
  no failing path ever prints `status: "pass"`.
- **The emitted envelope deliberately carries no `provenance` block.** `klt`
  0.6.0 lists no input-artifact field for the `generic` kind
  (`_INPUT_ARTIFACT_FIELDS`), so a generic citation's `input_verified` is
  always `null` and the grader never re-hashes anything. Had the envelope
  carried a `provenance.input.content_hash`, the citation would pair a non-null
  `content_hash` with `input_verified: null` — the exact shape rule 3 of the
  gate below warns on, permanently. With no provenance block the citation's
  `content_hash` is `null`, rule 3 stays silent, and the freshness claim is
  anchored by the live re-hash instead of by a pin nothing checks. That gap is
  filed generically, per `CLAUDE.md`'s friction protocol, as
  [2AMLogic/klayout-tools#2403](https://github.com/2AMLogic/klayout-tools/issues/2403)
  — closed upstream against an unreleased build, so the pinned 0.6.0 still has
  it; when a release carrying the fix is pinned here, this entry could become
  file-backed with a provenance-anchored hash and the live re-hash could
  retire.

The report is cross-linked from
[`sim/comparator-decision/README.md`](../sim/comparator-decision/README.md),
whose per-record prose it aggregates. It adds no measurement: every figure in
it is copied from a committed record, and the report says so on its face.

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

**Item 8's citation keeps it warning-free by construction, not by luck.** Its
`input_verified` *is* `null` (no `klt` build can re-hash a `generic`
envelope), but rule 3 warns only on a null `input_verified` paired with a
**non-empty** `content_hash` — and item 8's envelope carries no `provenance`
block, so its `content_hash` is `null` too and the rule does not fire. That is
a deliberate choice, not an omission: the freshness the pin would have claimed
is instead re-checked live by the command the entry runs. See "Item 8 — the
characterization report" above.

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
