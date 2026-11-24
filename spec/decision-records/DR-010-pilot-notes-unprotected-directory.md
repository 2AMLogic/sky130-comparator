# DR-010: Pilot notes live in an unprotected `pilots/` directory, not under `records/`

- **Status**: proposed (this record itself follows the usual ratification
  path — two reviews, then the operator; the PR that lands the move does not
  self-ratify it)
- **Date**: 2026-11-17
- **Decided by**: operator ruling (rjwalters, 2026-11-17, attended
  `/fleet:decide` round 20261116-r15, q100), scoped for implementation in
  issue #303

## Context

`sim/comparator-decision/records/` held prose "pilot note" documents (the
`klt-pilot-*.md` route investigations of issues #211/#219/#220/#221/#244/#283)
alongside harness-written graded records. Each note declares itself **not** a
record — no `Record ID`, no graded corner set — but sitting under `records/`
put it inside the append-only gate's protected scope
(`scripts/check-sim-append-only.py`: `records|corners|mc-draws|netlist-snapshots`),
so the notes inherited full record immutability while carrying none of a
record's structure.

The consequence (issue #303): every correction remedy the ratified convention
prescribes is unexecutable on a pilot note. In-place correction is blocked by
the gate (demonstrated by PR #302's failed `signoff`); appending an erratum
alongside is a modification like any other, also blocked; minting a
superseding record needs a `Supersedes` citation of the prior `<record-id>`
(`sim/README.md`), which a pilot note does not have by declaration. A
documentary error in a pilot note was permanently uncorrectable — #286 (a
false cross-reference in the noise pilot note) was the live instance.

## Decision

1. `records/` holds graded evidence only. Prose pilot notes are commentary,
   not records, and live in a separate, unprotected
   `sim/<experiment>/pilots/` directory.
2. The seven notes then under `sim/comparator-decision/records/` move to
   `sim/comparator-decision/pilots/` with `git mv` (history follows the
   files), and every reference to their old paths is updated.
3. New pilot notes are written under `pilots/` from now on; documentary
   corrections to them are ordinary in-place edits.
4. `scripts/check-sim-append-only.py` and its protected-scope regex are
   **unchanged**: `pilots/` never matched the protected pattern, so no gate
   change is needed or made. The removals at the old `records/` paths are
   sanctioned by this record through its ratification, not by relaxing the
   gate.

## Alternatives considered

- **Give pilot notes their own supersession ID (option b)** — makes "mint a
  new note" a clean operation but keeps prose commentary inside the
  evidence-protected namespace, permanently freezing every typo. Declined by
  the operator.
- **Correct-by-addition, cite by filename (option c)** — cheapest (a README
  paragraph only), and what PR #302's review recommended as the immediate
  route, but it ratifies unbounded note sprawl as the correction mechanism.
  Declined by the operator.

## Spec lines affected

- `sim/README.md` — "Directory / naming convention" (adds `pilots/`) and
  "Append-only rule" (states `records/` holds graded evidence only; `pilots/`
  is outside protected scope). Documentation of the convention, not a change
  to any gate mechanism.
- No target-spec table row is affected: no measured value, graded corner set,
  or provenance statement changes. The documentary corrections folded into
  the moved notes (issue #286's comparison clause) alter prose only.

## Consequences

- Documentary errors in pilot notes become correctable in place, as ordinary
  prose (unblocks corrections of the #286 class; #286 itself is already
  closed).
- The gate reports the seven expected `D` removals under
  `sim/comparator-decision/records/` while this record is `proposed`; the PR
  carrying the move passes CI only through this record's ratification path —
  reviewers and the operator should read those `D` entries as sanctioned by
  this decision, not as evidence tampering.
- Pilot notes lose the accidental discoverability of living next to the
  records they discuss; `pilots/` beside `records/` in the same experiment
  directory preserves most of that, and the README cross-references carry
  the rest.
- Any future tooling that enumerates `records/` as evidence input stops
  seeing commentary in its list — the intended effect, but a behaviour change
  for anything that was (incorrectly) treating pilot notes as evidence.
