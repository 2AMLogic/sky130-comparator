# Work Plan

Live roadmap generated from GitHub label state by the Loom Guide role.

<!-- guide:plan-body:start -->
## Operator Attention: Merge-Risk-Hold Pileup

Judge-approved PRs under a hold (`loom:blocked` or `loom:operator`) — only a human merge decision is missing.

- **#288**: docs: condense target-spec Basis cells to method + links; file DR-009
- **#347**: feat: add operator-gated removal waiver manifest to sim append-only gate

## Very Important

`loom:very-important` (one counts per workspace); every stage takes these first.

_None._

## Important

`loom:important`; taken before unlabelled work.

- **#125**: Re-measure post-layout (extracted-DUT) campaigns at the 0.35 um geometry and klt 0.7.0 pin *(held)*
- **#177**: Re-pin open_pdks to f6eeac7 (ciel) — fleet retires volare c6d73a3 *(held)*
- **#179**: Re-qualify reference records and regenerate evidence under open_pdks f6eeac7 (177 part 2) *(held)*
- **#361**: Re-qualification campaign, final step: rebuild the characterization report, envelope and integrator view from the new-pin records; write the old/new decision record *(held)*

## Ready

Human-approved issues (`loom:issue`) ready for implementation — excluding held (`loom:blocked`/`loom:operator`/`loom:frozen`), `loom:building`, and issues closed by an open `loom:pr` PR (listed under Approved).

_None._

## In Progress

Issues currently being built (`loom:building`).

- **#253**: Condense README target-spec table Basis cells: ~35 KB of campaign history duplicated across DRs and records
- **#282**: No gate compares a klt sim request's models.lib against sim/pdk.json's ngspice_lib
- **#303**: Pilot notes live in protected sim/*/records/ but have no Record ID, so documentary errors in them are uncorrectable
- **#326**: Sanctioned removal of protected pilot notes cannot pass the required signoff gate (DR-010 / #303 / PR #325)
- **#348**: Waiver manifest: the cited decision record is not bound to the path it waives (DR-011 / PR #347)
- **#359**: Re-qualification campaign, step 2: schematic-DUT kickback, noise, reset and regen records under open_pdks f6eeac7
- **#360**: Re-qualification campaign, step 3: schematic-DUT offset (N=16 and N=200), offset-bisect and noise-tran records; re-point the schematic baselines

## PRs Awaiting Review

PRs waiting on Judge (`loom:review-requested`).

- **#325**: docs: move pilot notes to unprotected sim/pilots/ per DR-010 *(held)*
- **#366**: sim: requalify schematic kickback/noise/reset/regen records under open_pdks f6eeac7
- **#369**: sim: requalify schematic offset, offset-bisect and noise-tran records under f6eeac7

## Approved (Awaiting Merge)

PRs that passed review and are queued for Champion auto-merge (`loom:pr`).

- **#288**: docs: condense target-spec Basis cells to method + links; file DR-009 — closes #253
- **#347**: feat: add operator-gated removal waiver manifest to sim append-only gate — closes #326, #348

## Proposed

Issues carrying `loom:curated`.

- **#3**: Track the gap to T1 sim-validated / bronze (klayout-tools design-evidence ladder) *(curated)* *(held)*
- **#125**: Re-measure post-layout (extracted-DUT) campaigns at the 0.35 um geometry and klt 0.7.0 pin *(curated)*
- **#146**: Auditor Capability Request: worker toolchain ngspice-46 / xschem 3.4.7 to match sim/toolchain.json *(curated)* *(held)*
- **#229**: klt-pilot: the two regen bdiff dry-run artifacts name the wrong netlist *(curated)* *(held)*
- **#280**: Attestation envelopes still go stale via merge-order races: nothing requires a PR's base to be current before merge *(curated)* *(held)*
- **#282**: No gate compares a klt sim request's models.lib against sim/pdk.json's ngspice_lib *(curated)*
- **#303**: Pilot notes live in protected sim/*/records/ but have no Record ID, so documentary errors in them are uncorrectable *(curated)*
- **#326**: Sanctioned removal of protected pilot notes cannot pass the required signoff gate (DR-010 / #303 / PR #325) *(curated)*
- **#348**: Waiver manifest: the cited decision record is not bound to the path it waives (DR-011 / PR #347) *(curated)*
- **#360**: Re-qualification campaign, step 3: schematic-DUT offset (N=16 and N=200), offset-bisect and noise-tran records; re-point the schematic baselines *(curated)*

## Proposed (Architect / Hermit)

- **#134**: Measure comparator supply energy and average power at stated clock conditions *(architect)* *(held)*
- **#154**: Measure larger-sample post-layout offset with resumable serial campaigns *(architect)* *(held)*
- **#234**: characterization-envelope.py's 'no provenance block' design rests on a klt 0.6.0 gap the pinned klt 0.8.0 no longer has *(hermit)* *(held)*
- **#241**: Retire the stale ERC-spec pinning rationale: the pinned klt 0.8.0 verifies provenance.spec.content_hash and ships klt erc --check *(hermit)* *(held)*
- **#253**: Condense README target-spec table Basis cells: ~35 KB of campaign history duplicated across DRs and records *(hermit)*

## Epics

_None._

## Backlog Balance

| Bucket | Count |
|------|-------|
| Operator merge-risk holds | 2 |
| Very important | 0 |
| Important | 4 |
| Ready (`loom:issue`, net of holds/building/merge-pending) | 0 |
| In Progress (`loom:building`) | 7 |
| PRs awaiting review | 3 |
| Approved PRs awaiting merge | 2 |
| Curated | 10 |
| Architect / Hermit proposals | 5 |
| Active epics | 0 |
<!-- guide:plan-body:end -->
