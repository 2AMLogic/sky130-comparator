# DR-009: Target-spec table Basis column condensed to method + links — evidence consolidation

- **Status**: **proposed** — drafted under @rjwalters' operator ruling of
  2026-11-15 (attended `/fleet:decide` round 20261111-r14, q94, recorded on
  issue #253), which approved this record's drafting and the Basis-column
  condensation as filed. Per the 2026-08-19 ratification-via-PR ruling, this
  record is an ordinary PR: Judge review plus Champion/operator merge, and the
  ratification is **not** the agent's to give. A PR carrying this record arms
  the ratification hold and parks for operator release.
- **Date**: 2026-11-16
- **Decided by**: builder agent, issue #253 (scope per the operator ruling and
  the Champion's review of 2026-11-15)
- **Supersedes**: none — changes no prior record; it disposes the *format* of
  the ratified table's Basis column, which no earlier record addressed (DR-002
  ratified row bounds and dispositions; DR-002 itself added Basis-column text,
  and later records added more — this record ends that growth mode).
- **Superseded by**: (none while this record stands)
- **Related**: #253 (this issue, including the Champion escalation comment and
  the operator ruling it carries), #148 and #130 (the two hand repairs of
  already-stale Basis cells — the failure mode this record removes),
  [DR-002](DR-002-target-spec-ratification.md),
  [DR-004](DR-004-comparator-preamp-supersession.md),
  [DR-005](DR-005-full-corner-campaign.md),
  [DR-006](DR-006-post-layout-noise-headroom-reopened.md),
  [DR-007](DR-007-systematic-decision-offset-row.md) (the owning records the
  condensed cells now link), `sim/characterization-report.md` (the evidence
  hub the condensed cells point at, and the new home of the three prior-art
  figures that existed only in `README.md`), `spec/README.md` ("A DR is owed
  the first time that table's rows are ratified, changed, or rescoped" — the
  ratified table's own column text is the artifact being changed here, so the
  record is owed even though no value moves).

## Context

The four graded rows' **Basis** cells in the top-level `README.md`'s
target-spec table had grown into a per-campaign narrative log: lines 126–129
measured 9269, 11867, 6977 and 7256 characters — ~35 KB, ~75% of the 46692-byte
file. Every campaign appended its findings to these cells, and the cells twice
went stale and needed hand repair (#148, #130). As single-line ~10 KB table
cells they are unreviewable in diffs and unreadable when rendered, and the
content is a *copy*: every figure already lives in a decision record, an
evidence record under `sim/comparator-decision/records/`, or
`sim/characterization-report.md` (spot-checked with `grep -rlF`; the full
confirm-then-delete pass is recorded under "Decision" below). Whether the
ratified table's Basis column is a front door that may link to its evidence or
a self-contained compliance record that must carry it inline is a preference,
not something a measurement settles — the Champion escalated it (#253), and the
operator ruled for the linking form.

## Decision

The **Basis** cell of each of the four graded rows (Offset sigma,
Input-referred noise, Decision time vs. overdrive, Kickback) is condensed to:

1. the row's **measurement method** (one to two sentences — instrument,
   statistic, grid, controls), and
2. **links** to the owning decision records and the row's section of
   `sim/characterization-report.md`, which carries all figures, corner tables,
   ratios, confidence intervals, caveats and the verdict.

The Parameter, Status, Target and Stretch cells of all five rows are carried
verbatim — **no bound, status, or `spec/` figure changes**. The Supply/power
row (DRAFT/OPEN) is out of scope and untouched. What is given up, deliberately:
the Basis cells are no longer self-contained — an integrator reading only
`README.md` must follow the links for measurement history.

The condensation was executed under a confirm-then-delete pass: every figure
removed from a Basis cell was confirmed present in a decision record, an
evidence record, or `sim/characterization-report.md` (`grep -rlF`, then
re-checked with word-boundary matching). The only figures that existed
**only** in `README.md` are three sky130-sar-adc prior-art numbers — offset
mean 35.24 mV / stdev 97.08 mV (N=16, `tt_mm`, first-pass `W = 4 µm` sizing),
noise 0.7064 mV rms differential (`tt`/27 °C), and decision time
0.5325–1.3975 ns across a 0.5–50 mV sweep (`tt`/27 °C). Per the ruling these
were **moved, not dropped**: `sim/characterization-report.md` now carries a
"Prior art — sky130-sar-adc" section holding all three verbatim, framed as
same-PDK context rather than as measurements of this block. Derived figures
stated only as arithmetic in the prose (margin ratios, percentage breaches,
ratio spans over stored raws) were not carried cell-by-cell: each is
re-derivable from raw figures the records and the report already commit.

From this record on, Basis cells stay at method + links: new campaign results
land in `sim/characterization-report.md` (and, when a disposition changes, in
a decision record) and are **not** appended to the table's cells.

## Alternatives considered

- **Keep the Basis cells self-contained** (carrying the history inline) — the
  status quo that produced the 35 KB cells, the two stale-repair passes, and
  the unreviewable diffs. Declined by the operator ruling (option (a) chosen
  over this).
- **Move the whole target-spec table into `spec/`** and leave a pointer in
  `README.md` — would relocate the ratified artifact this repo's convention
  deliberately keeps in the top-level README (`spec/README.md` records why).
  Not offered in the ruling's option set; declined.
- **Condense without a decision record** — rejected outright: `CLAUDE.md`
  routes every change to the ratified table through `spec/` plus a decision
  record, and `DR-002` already disposes Basis-column text, so editing that
  text needs a record disposing the change.

## Spec lines affected

No target, stretch, or status value changes on any row. What this record
changes is the **Basis column text of rows 1–4** of the target-spec table in
`README.md` (Offset sigma, Input-referred noise, Decision time vs. overdrive,
Kickback), plus the standing convention for how that column grows. The
Supply/power row (row 5) is untouched. `spec/README.md`'s claim that the
table "is ratified via a decision record" is unaffected — this record is that
decision record for this change.

## Consequences

- **Diff-reviewable table**: the four rows shrink from ~35 KB of single-line
  prose to four ≤ 1.6 KB cells (`README.md` 46692 → ~16 KB), so the next
  disposition change is reviewable at the diff level.
- **The stale-repair failure mode (#148/#130 class) loses its substrate**: a
  figure can no longer drift in two places, because the cells no longer carry
  figures. The cost of a stale cell is now a stale link, which is mechanical
  to check.
- **Integrators must follow links**: the measurement history behind a
  ratified bound is one link away, not inline. This is the trade the ruling
  explicitly accepted.
- **`sim/characterization-report.md` gains a section it did not have**
  (prior-art context), making it the single home for the sky130-sar-adc
  comparison figures.
- **No gate changes and no gate breaks**: nothing in `scripts/`,
  `sim/selftest.sh`, or `.github/workflows/` parses the Basis prose
  (re-verified on this tree); `sim/selftest.sh --quick` and
  `scripts/check-integrator-view.py gate` pass on the condensation commit.
- **Ratification path**: merging this record's PR ratifies the condensation
  per the standing two-key mechanism; the record is filed **proposed** so the
  hold applies by construction.
