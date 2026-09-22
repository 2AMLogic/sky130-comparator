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
| `design-evidence-tiers.md` | **Vendored copy** of `2AMLogic/klayout-tools`'s checklist doc, pinned at klayout-tools commit `31a3e3c` (byte-for-byte: SHA-256 `c7a1e7e10627fae396007e0ff951734f37d95028b8f49f2e21e802e9f552f318`, MIT-licensed). The pinned extra copy exists because the newest released klt (0.5.0) ships a pre-item-11 checklist (10 items), while the checklist grew an eleventh item — "Power delivery (structural)" — on 2026-09-17 (klayout-tools #2025) and refined its grading rules through klayout-tools #31a3e3c (2026-09-21). `--tiers-doc` grades against this pinned copy so item 11 renders a row, as issue #31 requires. |
| `t1-signoff-report.json` | The committed **evidence record**: byte-for-byte `klt signoff --manifest` JSON output as of the pinned klt version below. This is the single row-per-item verdict (`met`/`unmet` plus per-item `reason`) the tracker (issue #3) points at. |
| `integrator-view.json` | The **rule-9 integrator view** (issue #36): what a full-chip integrator takes, as structured data at a fixed path — top cell, port list, netlist path (with its regeneration command), GDS path, measured area, maturity rung, provenance. Honest nulls (`"not yet produced"` notes) where the artifact does not exist yet (GDS, area today); the maturity rung always agrees with `t1-signoff-report.json`'s graded verdict. Consumers and their requirement rows live in [`spec/consumers.md`](../spec/consumers.md); this file is the data half of that record. |

## The current verdict, honestly

Every T1 item renders `unmet` with `reason: no_evidence` — this block has
**no `klt` JSON envelope committed yet** (no DRC/LVS/PEX run exists, and
this repo's `sim/` harness records evidence as append-only Markdown
records, not `klt sim`/`klt yield` JSON envelopes, so nothing gradeable
can be cited honestly yet). An all-`unmet` manifest is the correct result
per issue #31's own "An all-`unmet` manifest is a correct result" section:
it is the machine-readable statement of the gap, and it must not be
decorated with citations that do not actually support their rows (items
1, 2, 9 and 10 in particular are graded on "some passing envelope was
cited", never on topical relevance — see the grader contract).

Rows are `klt`-graded verdicts, not repo-content claims. Items 1
(schematic `design/comparator.sch` + `design/netlist.sh`) and 9
(`sim/comparator-decision` testbenches) have committed content, but the
grade is about a *check behind a citation*, and no `klt` envelope backs
them yet — the `unmet`/`no_evidence` row is the accurate mechanical
statement. The historical per-item prose context lives in tracker issue
#3's edit history and `## Verified corrections`.

Item 11 ("Power delivery (structural)") renders a row, `unmet`, as
issue #31 requires. Note the grading-build disclosure: as of the pinned
klt, `build_t1_item_count` (10) trails the vendored doc's item count
(11) — klt 0.5.0 predates item 11's grading rules, so when an item-11
ERC/LVS citation is eventually added, a klt upgrade must land first
(until then `klt signoff` reports what it can grade and the `#2176`
grader-notes machinery flags the rest).

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

CI (`.github/workflows/t1-signoff.yml`) installs klt **pinned to
`klayout-tools==0.5.0`** — the version that graded the committed record —
then runs the gate's hermetic selftest and the live gate. Bump the pin
deliberately, regenerate the record in the same change (see above), and
note that klt versions newer than the vendored doc's item list will
report `build_t1_item_count`/`graded_by_build` disclosures rather than
fail.

## The integrator-view gate (issue #36)

`scripts/check-integrator-view.py` is the rot gate for
`integrator-view.json`, and runs in the same CI workflow (selftest first,
then the live gate). It fails on a missing required key, on any non-null
cited path that does not exist in-tree (a stale netlist/GDS/schematic
reference — the view must never point an integrator at a vanished file),
and on a `maturity_rung` that disagrees with `t1-signoff-report.json`'s
graded `tier`. Honest nulls (`gds`, `measured_area`) are accepted only
with their "not yet produced" notes; when layout lands and the fields
flip to real values, the same existence check applies. The gate is
stdlib-only Python and needs no klt install.

## Fleet context

The fleet roll-up that consumes this manifest is
`2AMLogic/2am#956` (`klt signoff --fleet`). This repo's `block` value
(`sky130-comparator`) is that roll-up's identity for this row.
