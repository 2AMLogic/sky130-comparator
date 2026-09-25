# DR-006: Input-referred noise — compliance basis re-opened after the post-layout corner campaign

- **Status**: ratified
- **Date**: 2026-09-25
- **Decided by**: issue #64 campaign (Builder pass), revising the disposition DR-002 §2 gave the Input-referred noise row

## Context

DR-002 §2 ratified the Input-referred noise row's bounds (≤ 1.0 mV rms
differential target, ≤ 0.6 mV rms stretch) against a **lower bound**: the
loop-broken AC sub-model excludes the regeneration phase's own noise by
construction. That record was explicit that it was ratifying on a
*quantified headroom argument*, and it stated the arithmetic:

> 0.4466 mV rms leaves a factor of ~2.24× headroom under the 1.0 mV target
> before the excluded regeneration-phase contribution would have to exceed
> the *entire* measured lower bound in quadrature to threaten compliance (a
> regeneration contribution of ~0.90 mV rms, on top of the 0.4466 mV already
> measured, would be needed to reach 1.0 mV rms combined).

That premise — *"a regeneration contribution of ~0.90 mV rms would be
needed"* — is the whole basis on which the target bound was ratified despite
the acknowledged lower-bound caveat. It was measured at `tt`/27 °C against
the **schematic** netlist.

Issue #64's post-layout PVT campaign has now measured the same loop-broken AC
sub-model against the **extracted** netlist at all seven graded corners
(records `20260925-112827-4694692.md` for `tt`/27 °C, and
`20260925-192710-bec714a.md` … `20260925-192836-bec714a.md` for the other
six):

| Corner | Post-layout AC lower bound | vs. ≤ 1.0 mV target | vs. ≤ 0.6 mV stretch |
|---|---|---|---|
| `sf`/−40 °C | 0.4886 mV rms | 2.05× | clears |
| `ss`/−40 °C | 0.5429 mV rms | 1.84× | clears |
| `fs`/−40 °C | 0.5447 mV rms | 1.84× | clears |
| `tt`/27 °C | 0.6576 mV rms | 1.52× | breached |
| `ff`/125 °C | 0.8521 mV rms | 1.17× | breached |
| `sf`/125 °C | 0.8590 mV rms | 1.16× | breached |
| `fs`/125 °C | **0.9423 mV rms** | **1.06×** | breached |

**No ratified bound is breached.** The worst corner, `fs`/125 °C, clears the
ratified target bound. But DR-002's ratification premise does not survive it:
at 0.9423 mV rms, the regeneration-phase contribution needed to reach 1.0 mV
rms in quadrature is `sqrt(1.0² − 0.9423²) = ` **0.335 mV rms**, not the
~0.90 mV DR-002 reasoned from. The headroom the row was ratified on has
shrunk by 2.7× and is no longer "a real amount of headroom to have
unmeasured" — it is a margin the excluded term could plausibly consume.

For scale on "plausibly": DR-005 measured the regeneration-*inclusive*
figure via `noise-tran` at 0.1362 / 0.1213 / 0.1754 mV rms
(decision-referred, `tt`/27 °C, `ss`/−40 °C, `ff`/125 °C). Those are neither
directly comparable to the AC band-integrated figure (different referral,
~3–4× below it) nor available post-layout — `noise-tran` refuses
`--dut extracted` because it has no post-layout deck form (issue #65). So the
repo cannot presently say whether 0.335 mV rms is enough margin. That is the
point of this record.

## Decision

1. **The Input-referred noise row's *bounds* are unchanged.** Target ≤ 1.0 mV
   rms differential, stretch ≤ 0.6 mV rms differential, exactly as DR-002
   ratified them. Per `CLAUDE.md`, agents do not relax the ratified spec to
   make results pass — and nothing here failed, so there is nothing to relax.

2. **The row's *compliance basis* moves RATIFIED-and-clear → RATIFIED, basis
   OPEN.** The bound stays ratified; what is re-opened is the claim that the
   measured evidence establishes compliance with it. DR-002 §2's headroom
   argument is recorded here as **superseded by measurement** and must not be
   cited as current justification.

3. **The evidence that would close it again** is a regeneration-inclusive
   input-referred noise measurement against the extracted netlist at
   `fs`/125 °C — i.e. post-layout `noise-tran`, which requires the
   post-layout deck form issue #65 owns. Until that exists, the row's target
   compliance rests on a lower bound with 1.06× margin at its worst corner,
   and every statement of it must say so.

4. **The stretch figure is recorded as breached at four of seven corners**
   (`tt`/27 °C, `ff`/125 °C, `sf`/125 °C, `fs`/125 °C) post-layout, and
   cleared at the three cold-skew corners. Unchanged in value; not a
   compliance requirement.

## Alternatives considered

- **Do nothing — no bound is breached, so no record.** Rejected. The
  acceptance test for a decision record here is not "did a number cross a
  line" but "is the ratified disposition still supported by its stated
  reasoning". DR-002 committed its reasoning to writing precisely so it could
  be checked later; checking it is what this campaign did, and the answer is
  no. Leaving that unrecorded would let a reader cite a ratification whose
  premise the repo's own evidence has retired.
- **De-ratify the row outright (→ DRAFT/OPEN).** Rejected as
  over-correction. The bound itself is still a reasonable number to commit
  to, and every measured figure at every corner clears it. What is uncertain
  is the *margin*, not the *bound*.
- **Relax the target bound to restore comfortable headroom.** Rejected
  outright — `CLAUDE.md` forbids relaxing the ratified spec to make results
  pass, and there is no failing result to accommodate anyway.
- **Tighten the stretch figure to match the post-layout spread.** Rejected as
  out of scope: this record disposes an existing claim against existing
  evidence; re-deriving stretch targets is a separate decision needing its
  own basis.

## Spec lines affected

- `README.md` target-spec table, **Input-referred noise** row: the Status
  cell gains the "basis OPEN post-layout" qualifier, and the Evidence cell
  records the seven-corner post-layout AC spread and the 1.06× worst-corner
  margin. The two bound cells (target, stretch) are **unchanged**.
- `spec/decision-records/DR-002-target-spec-ratification.md` §2: its headroom
  argument is superseded by this record. DR-002 itself is **not** edited —
  per the template's own rule, a ratified record is superseded, never
  rewritten.

## Consequences

- **A post-layout `noise-tran` capability is now on the critical path for
  this row**, not merely a completeness nicety. Issue #65 (post-layout deck
  form for `reset` and `noise-tran`) inherits that weight.
- **Any silicon or sign-off claim citing the noise row must carry the 1.06×
  worst-corner qualifier** until the measurement in Decision §3 exists. A
  bare "clears the noise target" statement is no longer supportable.
- **The hot corners are the binding ones for this row**, which the
  schematic-level `tt`/27 °C-only basis could not have revealed: the
  post-layout AC figure spans 0.4886–0.9423 mV rms and is ~1.9× worse at
  125 °C than at −40 °C. Any future noise work should anchor at `fs`/125 °C,
  not at `tt`/27 °C.
- **The supply-net parasitic model is a plausible source of pessimism here.**
  The extraction uses a single lumped star R per net, and `GND` + `VDD`
  carry 52.0 % of the block's 17.52 kΩ total series R (see
  `sim/comparator-decision/README.md`, "Parasitic model, and where it is
  coarse"). Re-extracting the supply nets with `klt extract --distributed-rc`
  could recover margin — but that is an argument for *measuring* it, not for
  assuming the margin is there. This record deliberately does not
  pre-discount the figure.
- **Nothing about the Offset sigma, Kickback or Decision time rows changes.**
  Issue #64's campaign cleared the ratified target bound at all seven corners
  for `kickback` (worst `sf`/−40 °C, 3.1989 mV against ≤ 5 mV, 1.56×) and for
  `regen` (worst `fs`/125 °C, 0.7725 ns against ≤ 1.5 ns, 1.94×; the ≤ 0.8 ns
  stretch also still holds everywhere, at 1.04× worst case). Those rows'
  dispositions stand as DR-005 left them.
