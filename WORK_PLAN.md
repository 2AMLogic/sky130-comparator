# Work Plan

Live roadmap generated from GitHub label state by the Loom Guide role.

<!-- guide:plan-body:start -->
## Operator Attention: Merge-Risk-Hold Pileup

Judge-approved PRs under a hold (`loom:blocked` or `loom:operator`) — only a human merge decision is missing.

- **#288**: docs: condense target-spec Basis cells to method + links; file DR-009
- **#377**: fix: match waived paths as whole tokens and ratified statuses exactly
- **#386**: docs: submit DR-010 pilot-note removals for two-key ratification

## Very Important

`loom:very-important` (one counts per workspace); every stage takes these first.

_None._

## Important

`loom:important`; taken before unlabelled work.

- **#177**: Re-pin open_pdks to f6eeac7 (ciel) — fleet retires volare c6d73a3

## Ready

Human-approved issues ready for implementation (`loom:issue`).

- **#177**: Re-pin open_pdks to f6eeac7 (ciel) — fleet retires volare c6d73a3

## In Progress

Issues currently being built (`loom:building`).

- **#253**: Condense README target-spec table Basis cells: ~35 KB of campaign history duplicated across DRs and records
- **#282**: No gate compares a klt sim request's models.lib against sim/pdk.json's ngspice_lib
- **#303**: Pilot notes live in protected sim/*/records/ but have no Record ID, so documentary errors in them are uncorrectable
- **#373**: Tighten the append-only waiver matches and ratify DR-011

## PRs Awaiting Review

PRs waiting on Judge (`loom:review-requested`).

_None._

## Approved (Awaiting Merge)

PRs that passed review and are queued for Champion auto-merge (`loom:pr`).

- **#288**: docs: condense target-spec Basis cells to method + links; file DR-009
- **#377**: fix: match waived paths as whole tokens and ratified statuses exactly
- **#386**: docs: submit DR-010 pilot-note removals for two-key ratification

## Proposed

Issues carrying `loom:curated`.

- **#3**: Track the gap to T1 sim-validated / bronze (klayout-tools design-evidence ladder) *(curated)*
- **#146**: Auditor Capability Request: worker toolchain ngspice-46 / xschem 3.4.7 to match sim/toolchain.json *(curated)*
- **#154**: Measure larger-sample post-layout offset with resumable serial campaigns *(curated)*
- **#177**: Re-pin open_pdks to f6eeac7 (ciel) — fleet retires volare c6d73a3 *(curated)*
- **#229**: klt-pilot: the two regen bdiff dry-run artifacts name the wrong netlist *(curated)*
- **#280**: Attestation envelopes still go stale via merge-order races: nothing requires a PR's base to be current before merge *(curated)*
- **#282**: No gate compares a klt sim request's models.lib against sim/pdk.json's ngspice_lib *(curated)*
- **#303**: Pilot notes live in protected sim/*/records/ but have no Record ID, so documentary errors in them are uncorrectable *(curated)*
- **#373**: Tighten the append-only waiver matches and ratify DR-011 *(curated)*
- **#412**: Run N=200 extracted-DUT offset campaigns on the #127 route (tt_mm/27C + second anchor) *(curated)*

## Proposed (Architect / Hermit)

- **#253**: Condense README target-spec table Basis cells: ~35 KB of campaign history duplicated across DRs and records *(hermit)*
- **#375**: Remove run.py compatibility re-exports in comparator-decision (test-only shim from #224) *(hermit)*
- **#432**: Remove or correct the generic Monte Carlo runner (only mc-smoke uses it; docstring contradicts spec) *(hermit)*

## Epics

_None._

## Backlog Balance

| Bucket | Count |
|------|-------|
| Operator merge-risk holds | 3 |
| Very important | 0 |
| Important | 1 |
| Ready (`loom:issue`) | 1 |
| In Progress (`loom:building`) | 4 |
| PRs awaiting review | 0 |
| Approved PRs awaiting merge | 3 |
| Curated | 10 |
| Architect / Hermit proposals | 3 |
| Active epics | 0 |
<!-- guide:plan-body:end -->
