# DR-010: Store pilot notes in `sim/<experiment>/pilots/`

- **Status**: ratified on merge after the EE and market key reviews and operator approval. Until that merge, this record is proposed.
- **Date**: 2026-11-17 (operator ruling on the directory convention)
- **Decided by**: rjwalters chose option (a) on issue #303 and required separate ratification for the protected-path removals. Issue #326 specifies how the gate applies that decision.

## Context

The comparator pilot notes describe route investigations. They carry no
`Record ID`, yet their location under `records/` makes them immutable. When
issue #286 identified a mistaken comparison in the noise note, the authors
had to publish a separate erratum. The usual `Supersedes` field requires a
record ID and cannot identify a pilot note.

## Decision

Reserve `sim/<experiment>/records/` for graded evidence. Write new pilot
notes under `sim/<experiment>/pilots/`, where authors can correct commentary
in place.

This decision authorizes removal of the following seven original paths at
the blob versions in `c5b25de973cec5b421647e243e88735f68bd7381`.
Move these six notes with `git mv` to `sim/comparator-decision/pilots/`,
retain their filenames, and update references to their old locations.

- `sim/comparator-decision/records/klt-pilot-kickback-20261106.md`
- `sim/comparator-decision/records/klt-pilot-kickback-pex-20261114.md`
- `sim/comparator-decision/records/klt-pilot-library-effect-20261115.md`
- `sim/comparator-decision/records/klt-pilot-library-effect-schematic-ngspice47-20261116.md`
- `sim/comparator-decision/records/klt-pilot-noise-20261115.md`
- `sim/comparator-decision/records/klt-pilot-regen-20261114.md`

Fold the corrected comparison clause from the seventh file into the moved
noise note, then remove the redundant erratum.

- `sim/comparator-decision/records/klt-pilot-noise-20261115-erratum.md`

## Alternatives considered

- **Give pilot notes supersession IDs (option b).** Every documentary
  correction would require a new note in the graded-evidence directory.
- **Add sibling corrections citing filenames (option c).** Readers would
  need to find and reconcile errata to determine which wording applies.

## Spec lines affected

The “Directory / naming convention” and “Append-only rule” sections of
`sim/README.md` describe the new location and the scope of `records/`.
The change concerns document storage and the wording of the comparison in
issue #286. The measured values and target-spec rows retain their existing
dispositions.

## Consequences

PR #325 can use this decision once the ratified record is in its comparison
base. Its entry in `manifests/append-only-waivers.json` must cite DR-010,
list each original path above, and pin the original blobs with the full
commit SHA above. The gate then verifies and reports each removal under
the waiver mechanism described in DR-011.
