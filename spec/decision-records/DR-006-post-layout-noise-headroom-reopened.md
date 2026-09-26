# DR-006: Input-referred noise — compliance basis re-opened after the post-layout corner campaign

- **Status**: ratified
- **Date**: 2026-09-25
- **Decided by**: issue #64 campaign (Builder pass), revising the disposition DR-002 §2 gave the Input-referred noise row
- **Amended by**: **Amendment 1** (issue #83, 2026-09-26; at the end of this
  record) — Decision §3's closure condition ran and the
  ≤ 1.0 mV **target** bound's compliance basis **closes**. Decision §1 (the
  bounds) and §4 (the stretch figure) are unchanged. **Read the amendment
  before citing Decision §2 or §3.**

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

---

## Amendment 1 (issue #83, 2026-09-26): the closure condition ran, and the target bound's compliance basis CLOSES

This amendment is **append-only**, per this repo's evidence convention: no
decision, measurement or argument above it is revised, deleted, or softened —
the only edit above this line is the navigational **Amended by** pointer added
to the header, so a reader who never scrolls this far is not left citing a
disposition this section moves. The seven-corner AC table, the 0.335 mV rms
quadrature arithmetic, and the text of Decision §§1–4 all stand exactly as
recorded. What this section reports is what happened when the measurement
Decision §3 named as the closing evidence actually ran.

**Status of this amendment**: same as the record it amends — **ratified**.
No bound is set, changed, relaxed or re-derived here. What moves is a
*compliance basis*, in the direction the measurement points.

### What ran

`noise-tran --dut extracted --corner fs --temp 125` — Decision §3's condition
verbatim: regeneration-inclusive, against the extracted netlist, at
`fs`/125 °C. Record
[`sim/comparator-decision/records/20260926-055806-3034c41.md`](../../sim/comparator-decision/records/20260926-055806-3034c41.md),
**N = 32 pick-off seeds, 4 seeds/sign/decision point** (both stated on that
record's own face, with the measured host-cost reason: this dispatch host
budgets each agent a **one-core cgroup CPU quota**, so `--jobs 2` buys no
parallel throughput, and the extracted decks at this corner cost ~350–500 s of
CPU each — roughly 3× the `tt`/27 °C cost issue #65's budget was extrapolated
from). **Because the sample is smaller than the `tt`/27 °C post-layout
record's, every disposition below is read against the conservative end of the
95 % CI, not the point estimate.**

| Quantity at `fs`/125 °C, post-layout | Value |
|---|---|
| Regeneration-inclusive input-referred σ (pick-off MC, N = 32) | **0.2540 mV rms differential** |
| 95 % CI | [0.1961, 0.3009] mV |
| AC loop-broken **lower bound** at the same corner (unchanged, from this record's table) | 0.9423 mV rms |
| Decision-transition cross-check | degenerate (see below) |

### The reading, both ways

1. **Directly**, which is the correct comparison: 0.2540 mV rms differential
   against the ratified ≤ 1.0 mV target is **3.94× margin — 3.32× at the CI's
   upper bound**. This is not a lower bound and carries no
   excluded-regeneration caveat: it is the regeneration-inclusive figure
   itself, at the binding corner, against the extracted netlist.
2. **Under a deliberately indefensible double-count**, stated so the closure
   does not rest on one arithmetic: treat the *entire* measured
   regeneration-inclusive figure as an independent term and add it in
   quadrature on top of the 0.9423 mV AC lower bound — which double-counts,
   because both figures are dominated by the **same** preamp input-referred
   source (0.6663 mV rms/side at this corner) and are two estimates of one
   quantity, not two separable terms. Even then,
   `sqrt(0.9423² + 0.2540²) = ` **0.9759 mV rms**, still inside the ≤ 1.0 mV
   target at 1.025× (0.9892 mV / 1.011× using the CI's upper bound).

This record's own 0.335 mV rms allowance is also not exceeded: the measured
regeneration-inclusive figure is 0.2540 mV, **0.76× of it**.

### Decision (amending Decision §2 and §3, not §1 or §4)

**A. The Input-referred noise row's compliance basis for the ≤ 1.0 mV target
moves RATIFIED-basis-OPEN → RATIFIED-and-clear.** Decision §2 re-opened the
claim that the measured evidence establishes compliance with the target bound;
the evidence Decision §3 named now exists and clears it under both readings
above. The row's target compliance therefore **no longer rests on a lower
bound plus a headroom argument** — it rests on a direct, regeneration-inclusive
post-layout measurement at the corner that binds the row.

**B. Decision §3's closure condition is DISCHARGED.** The measurement it named
exists. Nothing further is required of this record.

**C. The Consequences bullet requiring the 1.06× qualifier is retired, and
replaced narrowly.** A bare "clears the noise target" statement *is* now
supportable, provided it cites the regeneration-inclusive basis. What must
still carry the 1.06× qualifier is any statement that cites the **AC
lower-bound figure** as the row's basis — that figure is unchanged at
0.9423 mV rms with 1.06× target margin, and what this amendment changes is
that the AC figure is no longer the row's *only* basis at this corner.

**D. Decision §1 (the bounds) and Decision §4 (the stretch figure) are
UNCHANGED.** Explicitly: the ≤ 0.6 mV stretch figure stays recorded as
**breached at four of seven corners on the AC basis**. The transient basis
clears it (2.36×; 1.99× at the CI's upper bound) but has only **2 of 7**
corners, and the two bases disagree. Per `CLAUDE.md` the breach record stands
rather than being erased by a different method's number, and the stretch
figure is not a compliance requirement either way. **No stretch claim is
changed by this amendment.**

### What this does NOT close

- **Five of seven graded corners remain unmeasured post-layout** for
  `noise-tran` (`ss`/−40 °C, `ff`/125 °C, `sf`/−40 °C, `sf`/125 °C,
  `fs`/−40 °C). The basis closes at the **binding** corner, which is what
  Decision §3 asked for and what this record's own Consequences identified as
  the one to anchor at — not at all seven.
- **This corner has no committed schematic-level `noise-tran` counterpart**
  (only `tt`/27 °C, `ss`/−40 °C and `ff`/125 °C do), so the record reports no
  schematic-to-layout ratio and says so, rather than inventing one.
- **The `--distributed-rc` supply-net question is untouched.** This amendment
  does not pre-discount the AC figure for lumped-star pessimism, exactly as
  the Consequences above refuse to.

### Two findings worth carrying forward

- **Method consistency, as corroboration.** The AC-to-transient gap at this
  corner is 3.71× (0.9423 / 0.2540), squarely inside the ~3–4× gap this
  record's Context already observed at `tt`/27 °C, `ss`/−40 °C and
  `ff`/125 °C (`tt`/27 °C post-layout is 4.54×). So the closing figure is not
  an outlier of the method at the corner where it happens to matter most.
- **"The hot corners bind this row" is now confirmed on the
  regeneration-inclusive basis, not inferred from the lower bound** — and it
  is *resolved*, unlike the `tt`/27 °C record's schematic-to-layout ratio.
  0.2540 mV at `fs`/125 °C against 0.1448 mV at `tt`/27 °C is **1.754×**, and
  the two 95 % CIs ([0.1961, 0.3009] against [0.1224, 0.1641]) **do not
  overlap**. The transient figure degrades *faster* with corner than the AC
  sub-model's own 1.433× (0.9423 / 0.6576), so anchoring future noise work at
  `fs`/125 °C rather than `tt`/27 °C — this record's standing advice — is
  reinforced, not weakened, by the closure.
