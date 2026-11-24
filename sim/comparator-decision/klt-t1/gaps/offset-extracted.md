# Declared gap: extracted-DUT offset sigma (item 6 sub-case)

Status: **waiting on
[#412](https://github.com/2AMLogic/sky130-comparator/issues/412)** (open,
`loom:blocked` at declaration time).

The Offset sigma row's ratified basis is the **schematic-DUT** Monte Carlo
campaign (DR-002/DR-005: N=200 at `tt_mm` and `ss_mm`, seed 1, plus N=16 at
all five `_mm` corners). Item 6's gradeable coverage here therefore cites the
schematic-DUT `klt yield` reports (`yield/report-tt_mm.json`,
`yield/report-ss_mm.json`) over a fresh N=200 campaign run as `klt sim`
`monte_carlo` requests on the batch fleet.

What this gap records: the **extracted-DUT** N=200 counterpart — the
post-layout re-verification at the same sample size — has not run. The
committed post-layout offset evidence is N=16 per corner (records
`20261122-123618-a22c816.md` … `.../20261122-123622-a22c816.md`, 5 of 5
`_mm` corners, each with its stdev-exactly-0 same-seed negative control),
which #80's own record states cannot separate the five corners (3.0% spread
against an 18.3% relative SE at N=16); resolving them needs the O(100s)-draw
post-layout campaign, which is exactly #412's scope. Until it lands, no
`klt yield` report exists for the extracted-DUT offset draw, so the sub-case
is declared a gap rather than covered by the schematic reports.

Closing it: run the extracted-DUT N=200 campaign (#412; the `klt sim`
`monte_carlo` route this directory established works for it — swap the body's
DUT include for the extracted fragment and re-run `--yield-step`), then
either cover the row from both DUTs or split the row set by DUT provenance.
