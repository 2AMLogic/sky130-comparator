# Erratum 2026-11-17 -- comparison clause of the noise pilot note (issue #286)

Not a ratified record: no `Record ID`. This is a documentary erratum to the
pilot note [`klt-pilot-noise-20261115.md`](klt-pilot-noise-20261115.md)
(issue #221). It is a separate file because `sim/` evidence is append-only
(`sim/README.md`; enforced by `scripts/check-sim-append-only.py` against the
Git base): a committed record must stay byte- and mode-identical, so a
correction is added alongside the record it corrects and cites it by
filename -- the way these notes already reference each other.

## What it corrects

The "Result" section of
[`klt-pilot-noise-20261115.md`](klt-pilot-noise-20261115.md) (lines 31-34)
reads:

> Unlike the `kickback` and `regen` pilots, whose deltas had to be flagged
> "indicative only" against unquantified environment drift, this measurement
> shows **no visible PDK/ngspice-revision confounder at this corner**: nothing
> moved beyond what the record's storage precision can express.

That comparison clause is wrong in both directions:

- It groups the `regen` pilot with the "indicative only" pilots. The `regen`
  pilot's delta is **fully decomposed, not indicative** -- `run.py`'s rule
  re-measured on the current environment reproduces the `tt` baseline
  exactly, so the delta is attributed entirely to the crossing-detection
  methodology ([`klt-pilot-regen-20261114.md`](klt-pilot-regen-20261114.md)
  lines 27-28 and its "Why the delta is what it is" section;
  `sim/comparator-decision/README.md` states the same in its #220 paragraph:
  "the delta is **decomposed, not indicative**").
- It omits the `kickback-pex` pilot, whose deltas are also flagged
  "indicative only" -- and worse than PDK drift, since the DUT fragment
  (schematic -> extracted) *and* the runner's ngspice (46 -> 47) both
  changed, so the delta cannot be attributed to the parasitics alone
  ([`klt-pilot-kickback-pex-20261114.md`](klt-pilot-kickback-pex-20261114.md)
  lines 119-123).

## Corrected clause

For reading
[`klt-pilot-noise-20261115.md`](klt-pilot-noise-20261115.md), replace lines
31-34 with:

> Unlike the `kickback` and `kickback-pex` pilots, whose deltas had to be
> flagged "indicative only" against unquantified environment drift (the
> `regen` pilot's delta, by contrast, was fully decomposed, not indicative),
> this measurement shows **no visible PDK/ngspice-revision confounder at
> this corner**: nothing moved beyond what the record's storage precision can
> express.

## Scope

- Documentary only. No measured value, table row, deck line, or provenance
  statement of [`klt-pilot-noise-20261115.md`](klt-pilot-noise-20261115.md)
  is corrected: the DR-002 noise comparison itself (0.5704 mV rms
  differential against the <= 1 mV rms target) is unchanged and correct, as
  is the note's answer to #127's question (the `.noise` route works; the
  body-`.control`-block construction and its cost stand).
- Pilot notes carry no `Record ID`, so the `Supersedes` convention for
  corrections cannot cite this record; the structural gap is filed as #303.
  This erratum cites its predecessor by filename instead.
- `run.py` was not touched; no ratified record, spec row, characterization
  report or `regen-*` artifact changed.
