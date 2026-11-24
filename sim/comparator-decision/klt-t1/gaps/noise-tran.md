# Declared gap: regeneration-inclusive input-referred noise (item 6 sub-case)

Status: **waiting on
[2AMLogic/klayout-tools#7762](https://github.com/2AMLogic/klayout-tools/issues/7762)**
(filed 2026-11-24 per this repo's friction protocol).

The Input-referred noise row has two measured bases:

- the **AC corner-spread basis** — ngspice `.noise` on the loop-broken preamp
  sub-model, one deterministic figure per PVT corner. This half IS gradeable
  and is covered for item 5 by `report-noise.json` (seven graded corners, the
  ≤ 1.0 mV target as a graded limit, `spec_row: noise_ir_ac`).
- the **regeneration-inclusive basis** — transient-noise Monte Carlo with
  equivalent-source injection (`run.py noise-tran`), whose per-corner figure
  is a **sample statistic** (input-referred sigma over N pick-off seeds with a
  95% CI, plus a decision-transition cross-check). This is the half
  DR-006 Amendment 1 closed the row's compliance basis on.

This gap declares the second half for item 6, for two stacked reasons:

1. **No campaign expression.** The transient-noise MC cannot be run as a
   `klt sim` request: `monte_carlo.vary` re-seeds mismatch/process draws,
   with no contract for re-drawing transient-noise source streams per sample
   (klayout-tools#7762; cf. #5772's seed-pinning gap). The committed
   campaigns were driven by the bespoke harness.
2. **No committed per-draw values.** The harness persists summary statistics
   only — the records carry the sigma and its CI, and the committed
   `mc-draws/` logs are ngspice log stubs, not sample values — so no
   `klt yield` sample-set document can be derived from what is committed
   without inventing numbers.

Closing it needs the tool-side work (#7762: either a transient-noise-aware
`monte_carlo`, or a first-class ingest for caller-campaign per-draw values
that records campaign provenance the way a sim-report-backed sample set
does), then a `noise-tran` campaign that emits per-draw values and a
`klt yield` report per corner. Until then the row's statistical half reads
as this declared gap, and the row's graded coverage rests on the AC basis
cited for item 5 plus the committed schematic/post-layout `noise-tran`
records, which remain the row's basis of record.
