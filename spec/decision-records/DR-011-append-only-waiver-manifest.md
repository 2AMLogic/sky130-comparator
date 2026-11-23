# DR-011: Operator-gated waiver manifest for the sim/ append-only gate

- **Status**: proposed (changes no ratified spec row; mechanism for the CI gate only; ratification pending the two key reviews and the operator)
- **Date**: 2026-11-18
- **Decided by**: operator ruling (rjwalters, `/fleet:decide` round 20261118-r16, q54, option (a)) on issue #326; condition 4 (record must name the waived path) added by operator ruling (same operator, same round, option (a)) on issue #348; implemented by builder agent

## Context

`scripts/check-sim-append-only.py` (issue #138) fails any modification,
removal or type change of `sim/<slug>/{records,corners,mc-draws,netlist-snapshots}/**`.
PR #325 (issue #303, DR-010) moves pilot notes out of `records/`, which the
gate reads as removals, so its required `signoff` check goes red. The operator
ruled for a waiver mechanism inside the gate rather than a ruleset bypass,
which would leave a red run and no in-repo record.

## Decision

1. `manifests/append-only-waivers.json` holds `{"waivers": [{"decision_record",
   "paths", "base_sha"}]}`. `paths` are exact protected paths (no globs);
   `decision_record` is a path under `spec/decision-records/`.
2. A protected path whose only change is a **removal** is waived iff an entry
   lists it, the cited record's `Status` line begins `ratified` **as read at
   the comparison base**, the record contains the waived path as a **literal
   string as read at the comparison base** (condition 4, issue #348: same
   read as the status check, so a PR cannot edit the record to name its own
   path; literal substring, no globs, no path normalisation), and the path's
   blob at the base equals its blob at the entry's `base_sha`. Modification
   and type change are never waivable.
3. Anything else fails as before, naming the path and the reason (unlisted,
   record not ratified, record missing at base, record does not name the
   path, bytes differ, not a removal).
   An absent or empty manifest behaves exactly as before; a malformed manifest
   fails explicitly. Applied waivers are printed on the gate's `ok:` line.
4. The manifest is read from head (so a PR adds its own entry); the record
   status is read at the base, so a PR cannot ratify its own waiver.
5. This record does not self-ratify. It follows the usual path: two key
   reviews, then the operator.

## Alternatives considered

- **One-time ruleset bypass** -- operator-ruled out: leaves a red `signoff`
  run on `main` and no in-repo record.
- **Duplicating the notes under `pilots/` with frozen originals** -- not chosen
  by the operator.
- **Abandoning the move ruled on #303** -- not chosen.
- **Glob or directory waivers** -- too broad for an evidence-protecting gate.
- **Reading record status from head** -- a PR could ratify its own waiver.
- **Anchoring `base_sha` to the record's ratifying commit** (ancestry
  requirement) -- not chosen by the operator (issue #348, round 20261118-r16);
  the literal-name check closes the same tautology more cheaply.
- **Leaving the binding to manifest review** (no condition 4) -- rejected:
  any PR could waive any path by citing any record already `ratified` on the
  base, making "traceable to a ratified record" vacuous (issue #348).

## Spec lines affected

None in the `README.md` target-spec table. Changes the behavior of
`scripts/check-sim-append-only.py` and adds `manifests/append-only-waivers.json`;
documented in `sim/README.md` "Append-only rule". No operator authorization
beyond this mechanism is implied.

## Consequences

- Because status is read at base, a waiver can only pass once its record is on
  the base branch as `ratified`. For #325 this means DR-010 must reach `main`
  ratified in its own PR before #325 adds its manifest entry; re-scoping #325
  accordingly is #325's work. (Not traced against the ratification lane.)
- The manifest is a standing, reviewable list of every exception ever made to
  append-only; each entry is traceable to a ratified record **that names the
  waived path verbatim** (condition 4): a waiver can only cite a record that
  ruled on that path, so "traceable" is a literal containment check at the
  base, not an intention. Records written before this condition must list
  their waived paths when a waiver cites them.
- Condition 4 costs one extra clause per waiver: the cited record must list
  each waived path verbatim, and future removal rulings must name the paths
  they remove.
- Ratification of this record is gated on the fleet ratification lane
  (2AMLogic/.loom#630). Until then the mechanism ships with an empty manifest.
