# Work Plan

Live roadmap generated from GitHub label state by the Loom Guide role.

<!-- guide:plan-body:start -->
## Operator Attention: Merge-Risk-Hold Pileup

Judge-approved PRs under a hold (`loom:blocked` or `loom:operator`) — only a human merge decision is missing.

_None._

## Very Important

`loom:very-important` (one counts per workspace); every stage takes these first.

- **#219**: Pilot: kickback on the extracted netlist as a klt sim request (tt/27 C)

## Important

`loom:important`; taken before unlabelled work.

- **#125**: Re-measure post-layout (extracted-DUT) campaigns at the 0.35 um geometry and klt 0.7.0 pin
- **#127**: Establish a verified execution route for comparator campaign #125
- **#220**: Pilot: regen (decision time at 50 mV overdrive) as a klt sim request

## Ready

Human-approved issues ready for implementation (`loom:issue`).

_None._

## In Progress

Issues currently being built (`loom:building`).

_None._

## PRs Awaiting Review

PRs waiting on Judge (`loom:review-requested`).

- **#218**: docs: roadmap as of 2026-11-13

## Approved (Awaiting Merge)

PRs that passed review and are queued for Champion auto-merge (`loom:pr`).

_None._

## Proposed

Issues carrying `loom:curated`.

- **#3**: Track the gap to T1 sim-validated / bronze (klayout-tools design-evidence ladder) *(curated)*
- **#125**: Re-measure post-layout (extracted-DUT) campaigns at the 0.35 um geometry and klt 0.7.0 pin *(curated)*
- **#127**: Establish a verified execution route for comparator campaign #125 *(curated)*
- **#146**: Auditor Capability Request: worker toolchain ngspice-46 / xschem 3.4.7 to match sim/toolchain.json *(curated)*

## Proposed (Architect / Hermit)

- **#125**: Re-measure post-layout (extracted-DUT) campaigns at the 0.35 um geometry and klt 0.7.0 pin *(architect)*
- **#134**: Measure comparator supply energy and average power at stated clock conditions *(architect)*
- **#154**: Measure larger-sample post-layout offset with resumable serial campaigns *(architect)*

## Epics

_None._

## Backlog Balance

| Bucket | Count |
|------|-------|
| Operator merge-risk holds | 0 |
| Very important | 1 |
| Important | 3 |
| Ready (`loom:issue`) | 0 |
| In Progress (`loom:building`) | 0 |
| PRs awaiting review | 1 |
| Approved PRs awaiting merge | 0 |
| Curated | 4 |
| Architect / Hermit proposals | 3 |
| Active epics | 0 |
<!-- guide:plan-body:end -->
