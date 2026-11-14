# Work Plan

Live roadmap generated from GitHub label state by the Loom Guide role.

<!-- guide:plan-body:start -->
## Operator Attention: Merge-Risk-Hold Pileup

Judge-approved PRs under a hold (`loom:blocked` or `loom:operator`) — only a human merge decision is missing.

_None._

## Very Important

`loom:very-important` (one counts per workspace); every stage takes these first.

- **#127**: Establish a verified execution route for comparator campaign #125

## Important

`loom:important`; taken before unlabelled work.

- **#125**: Re-measure post-layout (extracted-DUT) campaigns at the 0.35 um geometry and klt 0.7.0 pin
- **#177**: Re-pin open_pdks to f6eeac7 (ciel) — fleet retires volare c6d73a3
- **#179**: Re-qualify reference records and regenerate evidence under open_pdks f6eeac7 (177 part 2)

## Ready

Human-approved issues ready for implementation (`loom:issue`).

- **#235**: Consolidate the duplicated axis-spread metric: ladder.py's copy already ignores max_spread_pct_by_axis and hardcodes the baseline
- **#236**: Delete gen_comparator.py's retired length_param/width_param LVS rationale — the repo's own negative control refutes it
- **#240**: sim/harness: write_evidence boilerplate is copied in runner.py and mc_runner.py, and the fail-closed preflight in both CLIs
- **#243**: Drop check-artifact-manifests.py's 'verify' subcommand: an untested, never-run stdlib twin of the pinned klt 0.8.0's 'klt artifact verify'
- **#245**: Consolidate the klt/klayout toolchain pin: one fact, five Python constants and four CI copies
- **#246**: Retire the stale 'target-spec table is DRAFT' claim from five live modules — four rows are ratified and the same files grade against them

## In Progress

Issues currently being built (`loom:building`).

- **#222**: manifests/README.md contradicts the graded report: items 1 and 9 are met, and the item-7 gap is closed upstream
- **#242**: Retire sim/selftest.sh's stale 'no comparator schematic yet' header: the sim/README.md section it cites already refutes it

## PRs Awaiting Review

PRs waiting on Judge (`loom:review-requested`).

- **#247**: docs: rescope selftest.sh header to stages 3-4, dropping the stale 'no comparator schematic yet' claim
- **#250**: docs(manifests): align README per-item prose with the graded T1 report

## Approved (Awaiting Merge)

PRs that passed review and are queued for Champion auto-merge (`loom:pr`).

_None._

## Proposed

Issues carrying `loom:curated`.

- **#3**: Track the gap to T1 sim-validated / bronze (klayout-tools design-evidence ladder) *(curated)*
- **#125**: Re-measure post-layout (extracted-DUT) campaigns at the 0.35 um geometry and klt 0.7.0 pin *(curated)*
- **#127**: Establish a verified execution route for comparator campaign #125 *(curated)*
- **#146**: Auditor Capability Request: worker toolchain ngspice-46 / xschem 3.4.7 to match sim/toolchain.json *(curated)*
- **#221**: Pilot: input-referred noise (.noise analysis) as a klt sim request *(curated)*
- **#222**: manifests/README.md contradicts the graded report: items 1 and 9 are met, and the item-7 gap is closed upstream *(curated)*
- **#226**: Split layout/gen_comparator.py (2225 lines): the evidence emitters are half the file and a one-way seam *(curated)*
- **#232**: Stale CI comment at t1-signoff.yml:111 names the retired 'member'/'digest' mechanism *(curated)*
- **#237**: Collapse the duplicated deck preambles and record headers in sim/comparator-decision/ *(curated)*
- **#239**: scripts/layout-envelope.py is the one _gate_common importer without the sys.path.insert preamble *(curated)*
- **#249**: manifests/README.md calls integrator-view's GDS and area 'not yet produced'; both now carry real values *(curated)*

## Proposed (Architect / Hermit)

- **#125**: Re-measure post-layout (extracted-DUT) campaigns at the 0.35 um geometry and klt 0.7.0 pin *(architect)*
- **#134**: Measure comparator supply energy and average power at stated clock conditions *(architect)*
- **#154**: Measure larger-sample post-layout offset with resumable serial campaigns *(architect)*
- **#226**: Split layout/gen_comparator.py (2225 lines): the evidence emitters are half the file and a one-way seam *(hermit)*
- **#234**: characterization-envelope.py's 'no provenance block' design rests on a klt 0.6.0 gap the pinned klt 0.8.0 no longer has *(hermit)*
- **#241**: Retire the stale ERC-spec pinning rationale: the pinned klt 0.8.0 verifies provenance.spec.content_hash and ships klt erc --check *(hermit)*

## Epics

_None._

## Backlog Balance

| Bucket | Count |
|------|-------|
| Operator merge-risk holds | 0 |
| Very important | 1 |
| Important | 3 |
| Ready (`loom:issue`) | 6 |
| In Progress (`loom:building`) | 2 |
| PRs awaiting review | 2 |
| Approved PRs awaiting merge | 0 |
| Curated | 11 |
| Architect / Hermit proposals | 6 |
| Active epics | 0 |
<!-- guide:plan-body:end -->
