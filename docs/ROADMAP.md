# Roadmap

A dynamic latched comparator (static preamplifier ahead of a StrongARM latch)
on SkyWater sky130, 1.8 V core devices, characterized standalone with open tools.

Status as of 2026-11-13, `main` @ `592c621`.

[`WORK_PLAN.md`](../WORK_PLAN.md) is the generated label-state view of the
tracker; the verdict of record is
[`manifests/t1-signoff-report.json`](../manifests/t1-signoff-report.json);
figures live in [`sim/characterization-report.md`](../sim/characterization-report.md).

## Where it stands

**Spec.** Four of five target-spec rows are ratified (Offset sigma,
Input-referred noise, Kickback: DR-002; Decision time: DR-005). Supply / power
is DRAFT / OPEN with no measurement behind it ([#134](https://github.com/2AMLogic/sky130-comparator/issues/134)). DR-007
(systematic decision offset row) and DR-008 (forward ladder bench) are
`proposed`.

**Evidence ladder (T1 sim-validated).** `klt signoff` under klayout-tools
0.8.0 grades 8 of 11 T1 items `met`; the tracker is [#3](https://github.com/2AMLogic/sky130-comparator/issues/3).

| Item | Verdict | Citation or gap |
|---|---|---|
| 1 Design sources | met | `evidence/item1.json` (attested, PR #210) |
| 2 Layout | met | `evidence/item2.json` (PR #190) |
| 3 DRC clean | met | `layout/drc-report.json` |
| 4 LVS clean | met | `layout/lvs-report.json` |
| 5 Full corner verification | unmet, `no_evidence` | campaigns ran (DR-005) but are Markdown records, not `klt sim` envelopes: [#188](https://github.com/2AMLogic/sky130-comparator/issues/188) |
| 6 Monte Carlo evidence | unmet, `no_evidence` | same, needs `klt yield` reports: [#188](https://github.com/2AMLogic/sky130-comparator/issues/188) |
| 7 Post-layout verification | unmet, `no_evidence` | needs a `klt pex` envelope: [#187](https://github.com/2AMLogic/sky130-comparator/issues/187), after [#125](https://github.com/2AMLogic/sky130-comparator/issues/125) |
| 8 Characterization report | met | `scripts/characterization-envelope.py` |
| 9 Testbenches shipped | met | `evidence/item9.json` (attested, PR #210) |
| 10 Repo hygiene | met | `evidence/item10.json` (attested, PR #201) |
| 11 Power delivery (structural) | met | `layout/erc-report.json` + `layout/lvs-report.json` |

**Two things are stale under the met rows, and both are tracked.**

- Every committed post-layout record was measured on the earlier 0.42 um
  resistor layout extracted under klt 0.6.0. The current layout draws 0.35 um
  and is extracted under 0.8.0 (PRs #205, #208). No simulation metric has been
  re-measured on it: [#125](https://github.com/2AMLogic/sky130-comparator/issues/125).
- The PDK pin moved to open_pdks `f6eeac7` (PR #180), but the reference
  records and `sim/characterization-report.md` still stand on `c6d73a3`:
  [#179](https://github.com/2AMLogic/sky130-comparator/issues/179).

**The one thing holding all of it.** #125, #179 and everything behind them wait
on an execution route for multi-corner campaigns, [#127](https://github.com/2AMLogic/sky130-comparator/issues/127). The harness
`sim/comparator-decision/run.py` drives ngspice directly and its campaigns do
not fit a shared dispatch host. The pilot in PR #212 changed the picture:
`kickback` was expressed as a `klt sim` request and ran on the batch fleet,
landing within 0.88 % of the `run.py` baseline
(`sim/comparator-decision/records/klt-pilot-kickback-20261106.md`). The other
measurements (`regen`, `offset`, `noise`, `reset`) have not been attempted.

## Now

None of these has an issue yet; each is one pull request and needs no decision.
Items 1 to 3 extend the PR #212 pilot so #127 can be answered with measurements.

1. **Pilot `kickback` on the extracted netlist as a `klt sim` request.**
   Done when `sim/comparator-decision/klt-pilot/` holds a request, report and
   dated pilot note for the `tt`/27 C point against
   `layout/comparator.pex.spice`, with the delta to the schematic pilot stated.
   This is the first simulated figure on the current 0.35 um layout.
2. **Pilot `regen` (decision time at 50 mV overdrive) as a `klt sim` request.**
   Done when a request, report and pilot note exist for `tt`/27 C and
   `ss`/-40 C on the schematic netlist, with the delta to the current
   `run.py` records for those corners stated, or the
   request that failed and its error output are committed with a linked
   klayout-tools issue.
3. **Pilot `noise` (the `.noise` analysis on the loop-broken sub-model) as a
   `klt sim` request.** Same done-criterion as item 2, at `tt`/27 C.
4. **Bring `manifests/README.md` back in line with the graded report.** It
   still says items 1 and 9 wait on a matching host, that "the other seven
   items" are unmet, and that an item-7 envelope "cannot be produced here at
   all" (klayout-tools#2478 is closed). Done when every per-item statement
   agrees with `manifests/t1-signoff-report.json` and
   `python3 scripts/check-t1-signoff.py gate` still passes.

## Next

- **Close the worker toolchain request** [#146](https://github.com/2AMLogic/sky130-comparator/issues/146): only the recorded
  decision remains (the 2026-11-06 `./sim/selftest.sh --quick` re-run exited 0).
- **Replace the raw xschem call with `klt netlist`** [#184](https://github.com/2AMLogic/sky130-comparator/issues/184), blocked
  by #146. Done when `design/netlist.sh --check` passes through `klt netlist`
  and the item-1 attestation still checks.
- **Choose the campaign route** [#127](https://github.com/2AMLogic/sky130-comparator/issues/127), once Now items 1 to 3 show
  which measurements `klt sim` can carry. Done when the route, a clean
  environment check on it and its budget are in `sim/comparator-decision/README.md`.
- **Re-measure post-layout at the current geometry** [#125](https://github.com/2AMLogic/sky130-comparator/issues/125), after
  #127. Done when new append-only extracted-DUT records cover every mode and
  corner already recorded and the characterization report and envelope cite them.
- **Re-qualify the reference records under `f6eeac7`** [#179](https://github.com/2AMLogic/sky130-comparator/issues/179), after
  #127. Done when superseding records exist and its parent [#177](https://github.com/2AMLogic/sky130-comparator/issues/177) closes.
- **Cite item 7** with `klt pex --measure-command` [#187](https://github.com/2AMLogic/sky130-comparator/issues/187), after #125.
- **Make items 5 and 6 gradeable** with `klt sim` and `klt yield` envelopes
  [#188](https://github.com/2AMLogic/sky130-comparator/issues/188), after #179.
- **Measure supply energy and average power** [#134](https://github.com/2AMLogic/sky130-comparator/issues/134), after #127 and
  #125, or sooner if the issue is revised to declare a runner-and-hermetic-test
  subset that needs no campaign, as its Champion review suggested.

## Later

- **Ratify the Supply / power row.** First: at what clock rate and duty cycle
  is the bound stated? The draft leaves the rate TBD.
- **Larger-sample post-layout offset** [#154](https://github.com/2AMLogic/sky130-comparator/issues/154). First: which second
  corner, chosen from the refreshed #125 evidence, is worth N=200?
- **Dispose DR-007 and DR-008** (both `proposed`). First: does the systematic
  layout offset survive re-measurement on the 0.35 um layout?
- **Retire the direct-ngspice campaign path** if the pilots carry every mode.
  First: can `offset` (mismatch draws plus a negative control) and resumable
  `noise-tran` be requests without losing the append-only record contract?

## Blocked and waiting

Nothing on the tracker is dispatchable today: every open issue carries
`loom:blocked` or `loom:operator`. The chain is
`#127 (route decision) -> #125, #179 -> #187, #188, #134, #154 -> #3`,
with #146 -> #184 as a separate, shorter one. Each chain starts at a decision
recorded as a ranked question on its issue (#127, #146). The four Now items
are the work that can start without either.

## Not planned

- Relaxing a ratified bound to make a result pass (`CLAUDE.md`); a breach is
  recorded and, where it matters, re-opened by decision record, as DR-006 did.
- A 3.3 V variant: sky130 ships no complementary 3.3 V enhancement pair (see
  the Supply / power row basis in the README).
- Hand-launched campaigns on a shared dispatch host
  (`sim/comparator-decision/README.md`, "Dispatch decision").
