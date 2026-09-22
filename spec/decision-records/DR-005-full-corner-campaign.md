# DR-005: Full-corner Monte Carlo and PVT campaign -- target-spec rows re-disposed against the complete corner set

- **Status**: ratified
- **Date**: 2026-09-22
- **Decided by**: issue #41 campaign (Builder pass), disposing rows ratified by DR-002 and re-anchored by DR-004

## Context

DR-002 ratified three of the five target-spec rows (Offset sigma,
Input-referred noise, Kickback) against measurements that were
deliberately narrow in corner coverage, and left Decision time vs.
overdrive DRAFT/OPEN pending exactly the fuller sweep this record now
supplies. DR-004's Open items named the remaining gaps one by one: the
other four `_mm` mismatch corners and an O(100s)-draw offset campaign;
regeneration-inclusive noise plus its PVT anchors; the `ff`/`sf`/`fs`
decision-time corners; the `sf`/`fs` kickback skews. Issue #41 was filed
to own that coverage work as one campaign, against the DR-004 topology
(`design/comparator.sch` as of PR #40, netlist-identical at this
campaign's commit), on the pinned toolchain (ngspice-46, open_pdks
`c6d73a35`) — every number below is a committed append-only evidence
record under `sim/comparator-decision/records/` (record IDs embed the
campaign commit `e23c509`).

The campaign also introduces one new measurement capability:
`run.py noise-tran`, a regeneration-inclusive input-referred noise
measurement via transient-noise Monte Carlo with equivalent-source
injection (ngspice-46 has no device-noise-enabled transient analysis —
`trnoise()` exists only on independent sources — so the AC preamp figure
and a new steering+tail gate-referred figure are re-injected as
calibrated TRNOISE sources at the comparator inputs and in series with
the steering gates, propagated through the full committed fragment's
real clocked evaluate trajectory; a pick-off Monte Carlo is the primary
statistic and a pair-symmetric decision-transition cross-check covers the
regenerative phase).

## Decision

1. **Decision time vs. overdrive moves DRAFT/OPEN → RATIFIED**, at the
   DR-002-stated bounds unchanged (target ≤ 1.5 ns at 50 mV overdrive,
   stretch ≤ 0.8 ns). The campaign completes the row's PVT sweep: with
   the DR-004 `tt`/27 °C (0.4025 ns) and `ss`/−40 °C (0.3575 ns)
   anchors, the new `ff`/125 °C (0.4975 ns), `sf`/−40 °C (0.3475 ns),
   `sf`/125 °C (0.4725 ns), `fs`/−40 °C (0.3725 ns), `fs`/125 °C
   (0.5375 ns) points close the set at seven PVT points spanning both
   process skews and both temperature extremes. The slowest point
   (`fs`/125 °C, 0.5375 ns) clears the stretch bound with 1.49× margin
   and the target with 2.8×. Every sub-mV sweep point resolves at every
   new corner (8/8); the one non-resolving point in the whole set
   remains the 0.5 mV point at `ss`/−40 °C already recorded honestly by
   DR-004 — sub-mV decisions sit below the design's own ~1.8 mV offset
   sigma, and the row's bounds are stated at 50 mV.
2. **Offset sigma stays RATIFIED, now with the multi-corner and
   large-N basis DR-002 asked for.** All five `_mm` mismatch corners
   measured at the same seed-1/27 °C methodology (`tt_mm` 1.7857 mV per
   DR-004; this campaign: `ss_mm` 1.8244, `ff_mm` 1.5954, `sf_mm`
   1.6706, `fs_mm` 1.8218 mV, each N=16 with a stdev-exactly-0
   same-seed negative control): the corner ranking is within the N=16
   relative SE (~18%), so no corner separates from the pack; the
   nominally binding corner is `ss_mm`. O(100s)-draw campaigns at both
   `tt_mm` and the nominally binding `ss_mm` (N=200, seed 1) replace the
   N=16 relative-SE caveat with a stated 95% CI: `tt_mm` σ = 2.1854 mV
   (CI [1.9707, 2.4001], `records/20260922-191034-e23c509.md`), `ss_mm`
   σ = 2.2353 mV (CI [2.0157, 2.4549], `records/20260922-202434-e026012.md`)
   — both 3σ ≈ 6.6–6.7 mV, clearing the stretch bound (≤ 8 mV) with an
   implied per-side yield > 99.96% against it (8 mV / σ ≈ 3.6σ). No bound
   changes. The N=200 estimates sit ~22% above the N=16 figures the row
   previously quoted — the small-sample estimates landed low, exactly the
   tightness gap DR-002's Open items flagged; the README row now quotes
   the N=200 numbers.
3. **Input-referred noise stays RATIFIED with its regeneration-inclusive
   evidence in place.** The `noise-tran` measurement at `tt`/27 °C,
   `ss`/−40 °C, and `ff`/125 °C (the anchor pair the kickback and
   decision-time rows already use) measures the decision-relevant
   input-referred sigma including the real evaluate trajectory and the
   latch front-end's injected noise — the measurement DR-002's Open
   items asked for. The decision-transition cross-check agrees with the
   pick-off statistic at every corner (within the cross-check's coarser
   CI), which is the evidence that the regenerative phase adds no
   material noise term beyond the injected device noise. The measured
   decision-relevant figures sit far below the AC band-integrated
   figures (1 kHz–1 GHz) the row's prior basis used — the AC figure
   remains the conservative reported basis; no bound changes.
4. **Kickback stays RATIFIED (target-compliant at all seven graded
   corners); the stretch annotation tightens.** The `sf`/`fs` skew
   corners at both temperature extremes complete the row's PVT set:
   `sf`/−40 °C **2.0208 mV**, `sf`/125 °C 1.7837 mV, `fs`/−40 °C
   1.8408 mV, `fs`/125 °C 1.6091 mV (every `ideal` control still
   collapses to 0.0000 mV). All seven corners clear the ratified ≤ 5 mV
   target (2.5–3.1× margin). The ≤ 2 mV stretch bound, which the three
   DR-004 anchors cleared with 1.06–1.13× margin, is **breached at
   `sf`/−40 °C by 1%** (2.0208 vs 2.0 mV). The stretch bound is not a
   compliance requirement and is not changed; the README row now
   records the breach explicitly instead of implying uniform stretch
   clearance.
5. **Supply/power stays DRAFT/OPEN, untouched by this campaign** — no
   current or power measurement was added; DR-004's re-anchoring open
   item stands unchanged.

## Alternatives considered

- **A `## Campaign` addendum to DR-004 instead of a new record** —
  rejected: this record ratifies the Decision-time row (a status change
  to the target-spec table), which is a spec change requiring its own
  decision record per `spec/README.md`; DR-004's own Open-items list is
  the trigger, not the container.
- **Relaxing the Kickback stretch bound to absorb the `sf`/−40 °C
  breach** — rejected per CLAUDE.md ("agents do not relax the ratified
  spec to make results pass"); the breach is 1% on a non-binding
  stretch figure and is recorded, not legislated away. If the operator
  wants the stretch row re-scoped, that is a future DR's call.
- **Big-N campaign at the binding corner only** — rejected: the N=16
  corner ranking is inside its own relative SE, so "binding" is not a
  statistically significant designation; both the `tt_mm` anchor corner
  and the nominally binding `ss_mm` were measured at N=200 so the
  yield-fraction claim does not rest on an N=16 ranking.
- **Ratifying Decision-time at bounds tightened to the measured
  0.54 ns figure** — rejected: nothing in the campaign asks for tighter
  bounds, and tightening a ratified row's bound on the strength of one
  topology generation invites churn; the DR-002 bounds stand.

## Spec lines affected

- `README.md` target-spec table, **Decision time vs. overdrive** row:
  status DRAFT/OPEN → **RATIFIED (DR-005)**; basis column extended with
  the five new PVT points and the worst-corner margin.
- `README.md` target-spec table, **Offset sigma** row: basis column
  extended with the four `_mm` corners and the N=200 CI-bearing
  campaigns; status and bounds unchanged.
- `README.md` target-spec table, **Input-referred noise** row: basis
  column extended with the regeneration-inclusive `noise-tran` results
  and their anchors; status and bounds unchanged.
- `README.md` target-spec table, **Kickback** row: basis column extended
  with the four skew corners; stretch-clearance wording corrected to
  name the `sf`/−40 °C breach; status, target, and stretch bounds
  unchanged.

## Consequences

- The ratified row count moves from three to four; only Supply/power
  remains open, still blocked on the operator framing decision DR-004
  recorded (clock rate / duty cycle).
- The Decision-time row is now graded against seven PVT points; any
  future topology change re-runs the full set, not just `tt`/`ss`.
- The kickback stretch figure's 1% breach at `sf`/−40 °C is a recorded
  fact with no action item; a future mitigation pass (if any) would
  have to clear 2 mV at that corner to restore uniform stretch
  compliance.
- `run.py` gains `noise-tran` and `--jobs`; the unit-test suite gains
  the deck-shape and estimator coverage for both (construction-level,
  no PDK needed).
- The `noise-tran` methodology finding (equivalent-source injection on
  ngspice-46, the TRNOISE calibration factor, and the
  noise-update-grid/timestep-collapse interaction) is cross-filed on
  `2AMLogic/sky130-sar-adc` as that repo's issue #350 per CLAUDE.md's
  protocol, since that repo's own DR-004 carries the same
  regeneration-inclusive open item.

## Open items

- **Supply/power ratification** — unchanged from DR-004: needs the
  operator's clock-rate/duty-cycle framing; no new current data.
- **Sub-mV overdrive at `ss`/−40 °C** — unchanged from DR-004; the
  campaign adds no new non-resolving point (all new corners 8/8).
- **Layout-stage re-verification** — unchanged from DR-002/DR-004; the
  campaign is all schematic-level.
- **Kickback stretch at `sf`/−40 °C** — recorded breach (2.0208 mV);
  whether to mitigate or accept is an operator scoping decision, not
  opened as work by this record.
