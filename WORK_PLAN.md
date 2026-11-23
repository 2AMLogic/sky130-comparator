# Work Plan

Live roadmap generated from GitHub label state by the Loom Guide role.

<!-- guide:plan-body:start -->
## Operator Attention: Merge-Risk-Hold Pileup

Judge-approved PRs awaiting an operator decision (`loom:blocked` or `loom:operator`).

- **#288**: docs: condense target-spec Basis cells to method + links; file DR-009
- **#377**: fix: match waived paths as whole tokens and ratified statuses exactly

## Very Important

`loom:very-important` (one counts per workspace); every stage takes these first.

_None._

## Important

`loom:important`; taken before unlabelled work.

- **#177**: Re-pin open_pdks to f6eeac7 (ciel) — fleet retires volare c6d73a3 *(held)*
- **#179**: Re-qualify reference records and regenerate evidence under open_pdks f6eeac7 (177 part 2)

## Ready

Human-approved issues (`loom:issue`) ready for implementation — excluding held (`loom:blocked`/`loom:operator`/`loom:frozen`), `loom:building`, and issues closed by an open `loom:pr` PR (listed under Approved).

- **#134**: Measure comparator supply energy and average power at stated clock conditions
- **#179**: Re-qualify reference records and regenerate evidence under open_pdks f6eeac7 (177 part 2)

## In Progress

Issues currently being built (`loom:building`).

- **#154**: Measure larger-sample post-layout offset with resumable serial campaigns
- **#241**: Retire the stale ERC-spec pinning rationale: the pinned klt 0.8.0 verifies provenance.spec.content_hash and ships klt erc --check
- **#253**: Condense README target-spec table Basis cells: ~35 KB of campaign history duplicated across DRs and records
- **#282**: No gate compares a klt sim request's models.lib against sim/pdk.json's ngspice_lib
- **#303**: Pilot notes live in protected sim/*/records/ but have no Record ID, so documentary errors in them are uncorrectable
- **#373**: Tighten the append-only waiver matches and ratify DR-011
- **#398**: characterization-report: "the two hot skew corners fell" contradicts the sf/125 °C rise named in the same sentence
- **#402**: prose: "skew corner" names three different corner sets across the noise write-ups
- **#404**: ladder.py grade: an unreadable or undecodable response file raises an uncaught traceback instead of the exit-2 input error

## PRs Awaiting Review

PRs waiting on Judge (`loom:review-requested`).

- **#386**: docs: submit DR-010 pilot-note removals for two-key ratification
- **#403**: fix: relabel two noise-tran figures that fell past their old CIs
- **#408**: fix: grade exits 2 naming the file on unreadable or malformed response
- **#409**: feat: add klt pex measure-command adapter for decision-time and kickback rows

## Approved (Awaiting Merge)

PRs that passed review and are queued for Champion auto-merge (`loom:pr`).

- **#288**: docs: condense target-spec Basis cells to method + links; file DR-009 — closes #253
- **#377**: fix: match waived paths as whole tokens and ratified statuses exactly — closes #373
- **#405**: fix: stop calling ff/125C a skew corner; record the skew-naming convention — closes #402

## Proposed

Issues carrying `loom:curated`.

- **#3**: Track the gap to T1 sim-validated / bronze (klayout-tools design-evidence ladder) *(curated)* *(held)*
- **#146**: Auditor Capability Request: worker toolchain ngspice-46 / xschem 3.4.7 to match sim/toolchain.json *(curated)* *(held)*
- **#187**: Re-cite T1 item 7 with klt pex --measure-command after the post-layout re-measure *(curated)* *(held)*
- **#229**: klt-pilot: the two regen bdiff dry-run artifacts name the wrong netlist *(curated)* *(held)*
- **#241**: Retire the stale ERC-spec pinning rationale: the pinned klt 0.8.0 verifies provenance.spec.content_hash and ships klt erc --check *(curated)*
- **#280**: Attestation envelopes still go stale via merge-order races: nothing requires a PR's base to be current before merge *(curated)* *(held)*
- **#282**: No gate compares a klt sim request's models.lib against sim/pdk.json's ngspice_lib *(curated)*
- **#303**: Pilot notes live in protected sim/*/records/ but have no Record ID, so documentary errors in them are uncorrectable *(curated)*
- **#373**: Tighten the append-only waiver matches and ratify DR-011 *(curated)*
- **#390**: Restore test coverage for schematic_comparison()'s differing-environment branch *(curated)*
- **#398**: characterization-report: "the two hot skew corners fell" contradicts the sf/125 °C rise named in the same sentence *(curated)*
- **#402**: prose: "skew corner" names three different corner sets across the noise write-ups *(curated)*
- **#404**: ladder.py grade: an unreadable or undecodable response file raises an uncaught traceback instead of the exit-2 input error *(curated)*

## Proposed (Architect / Hermit)

- **#253**: Condense README target-spec table Basis cells: ~35 KB of campaign history duplicated across DRs and records *(hermit)*
- **#375**: Remove run.py compatibility re-exports in comparator-decision (test-only shim from #224) *(hermit)* *(held)*

## Epics

_None._

## Backlog Balance

| Bucket | Count |
|------|-------|
| Operator merge-risk holds | 2 |
| Very important | 0 |
| Important | 2 |
| Ready (`loom:issue`, net of holds/building/merge-pending) | 2 |
| In Progress (`loom:building`) | 9 |
| PRs awaiting review | 4 |
| Approved PRs awaiting merge | 3 |
| Curated | 13 |
| Architect / Hermit proposals | 2 |
| Active epics | 0 |
<!-- guide:plan-body:end -->
