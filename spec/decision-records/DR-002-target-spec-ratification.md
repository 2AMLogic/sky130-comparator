# DR-002: Target-spec table ratification pass 1 — three rows ratified, two left explicitly open

- **Status**: **proposed** — a recommendation for two-key ratification via
  this PR (Judge review + Champion/operator merge), per the 2026-08-19
  ratification-via-PR ruling cited on issue #3 (operator comment,
  2026-09-15: "The item-5 spec-ratification gate is also agent work under
  the 2026-08-19 ratification-via-PR ruling... a Builder drafts the
  decision record as a PR recommending one option, and the two-key
  mechanism evaluates it"). Nothing here is binding until this PR merges.
  Upon merge, the per-row dispositions in "Decision" below take effect
  exactly as stated — this is a **partial** ratification by design: three
  rows (Offset sigma, Input-referred noise, Kickback) move from DRAFT to
  RATIFIED, two rows (Decision time vs. overdrive, Supply/power) stay
  DRAFT/OPEN, explicitly, not silently.
- **Date**: 2026-09-16
- **Decided by**: Builder agent, issue #28
- **Supersedes**: none — second decision record in this repo. Does not
  supersede DR-001; DR-001 addressed topology/reset-scheme and explicitly
  ratified no target-spec row (its own "Spec lines affected" section states
  this). This record is the first to touch the table's ratification status
  itself.
- **Superseded by**: (none while this record stands)
- **Related**: #28 (this issue), #3 (gap-to-T1 tracker — this record
  answers `spec/porting-plan.md` "Next steps" item 5; #3 itself is **not**
  edited by this PR, per that issue's own convention — the Curator updates
  it separately after this merges), `spec/porting-plan.md` ("Next steps"
  §5, the source of this issue's scope), `spec/README.md` (states a DR is
  owed "the first time that table's rows are ratified, changed, or
  rescoped" — this record does exactly that, row by row), `README.md`'s
  target-specification table (the table this record disposes),
  [DR-001](DR-001-comparator-topology.md) (the topology/reset-scheme
  decision and its Amendment 1 sizing pass — cited below for the headroom
  and sizing context each row's disposition draws on),
  `design/README.md` ("What is not here" — flags the offset-driven input
  pair widening as an unmeasured kickback cost, cited in the Kickback
  disposition below). Evidence records cited by path in each subsection
  below.

## Context

`spec/porting-plan.md`'s "Next steps" lists five items in dependency order.
Items 1–4 are done as of `origin/main` @ `b6b5f77` (2026-09-16): the
topology decision record (#21/DR-001), the schematic (#23/#24), the
`sim/comparator-decision/` harness with `regen`/`offset`/`noise`/`reset`
(#7/#8/#9), and the kickback experiment (#26/PR #27). Item 5 — "once real
measurements exist, revisit the README target-spec table's DRAFT bounds and
file a ratification decision record if/when the table is set, changed, or
scoped" — is this record.

Real measurements now exist against this repo's own `design/comparator.sch`
for every DRAFT row:

| Row | Evidence record | Measured |
|---|---|---|
| Offset sigma | `sim/comparator-decision/records/20260916-003531-52eb9b2.md` | N=16, `tt_mm`/27°C, stdev 2.019 mV (3σ = 6.06 mV) |
| Input-referred noise | `sim/comparator-decision/records/20260916-001416-52eb9b2.md` | `tt`/27°C, reduced-sub-model lower bound, 0.4466 mV rms differential (estimated) |
| Decision time vs. overdrive | `sim/comparator-decision/records/20260916-000727-52eb9b2.md` (tt/27°C) and `.../20260916-001345-52eb9b2.md` (ss/−40°C) | 0.6775 ns and 0.6875 ns at 50 mV overdrive, respectively |
| Kickback | `sim/comparator-decision/records/20260916-060139-f1eb978.md` | `tt`/27°C, 1 kΩ source impedance, 50 mV overdrive: 144.60 mV peak |
| Supply/power | (none) | not measured — no clock-rate assumption exists to measure against |

Every one of these records states, in its own `Claim` field, that it
substantiates no row of the DRAFT table (per `spec/README.md`'s convention:
a DR is owed before any row is ratified, changed, or rescoped, and none had
been filed until now). This record's job is to read those five records
against the table row by row and state, for each, whether the existing
DRAFT bound is ratified as-is, revised, or left explicitly open pending
more evidence — not to invent any new number. No value asserted below is
unsupported by one of the five records above or by DR-001/its Amendment 1.

**What this record explicitly is not.** It is not a full PVT/Monte-Carlo
campaign, and it does not claim one exists. `README.md`'s own statistical
basis note is unchanged by this record: sky130's `_mm` local-mismatch
corners remain the committed methodology, and nothing here relaxes that
commitment.

## Decision

### 1. Offset sigma — RATIFY the existing bound as-is

**Bound**: ≤ 15 mV, 3σ (target) / ≤ 8 mV, 3σ (stretch), input-referred,
post-calibration-free. **Unchanged.**

**Evidence**: `sim/comparator-decision/records/20260916-003531-52eb9b2.md`
— N=16 draws at `tt_mm`/27°C/1.8 V, input-referred offset stdev
2.019 mV, i.e. 3σ = 6.057 mV. That clears not only the 15 mV target but
also the 8 mV stretch bound, with the same-seed mismatch-disabled negative
control reproducing exactly stdev = 0 (confirming the measurement pipeline
isolates a genuine mismatch effect, not noise in the pick-off statistic
itself).

**Why ratify rather than leave open, given N=16.** The record's own stated
relative standard error on the stdev estimate is 18.3% at N=16 — sized, by
its own account, "for distribution shape, not for a yield-fraction claim."
That is a real limitation, but it bears on *how tight* a compliance claim
can be made, not on whether the *bound itself* is a reasonable number to
commit the table to. Even reading the stdev at the top of its 18.3%
confidence band (2.019 mV × 1.183 ≈ 2.39 mV, 3σ ≈ 7.17 mV) still clears the
15 mV target with more than 2× margin, and clears the 8 mV stretch bound
too. Ratifying the *bound* is a defensible first pass; it is the
*compliance claim* at a tight sigma level that stays open (see Open items).

**What is explicitly not decided here**: this measurement is a single
mismatch corner (`tt_mm`). The other four (`ss_mm`, `ff_mm`, `sf_mm`,
`fs_mm`) are unmeasured, and a larger-N (O(100s)) campaign is still needed
before a yield-fraction claim against the now-ratified bound can be made.
Ratifying the bound commits this repo to that numeric target; it does not
assert the design is already proven to meet it at production-relevant
confidence.

### 2. Input-referred noise — RATIFY the existing bound as-is

**Bound**: ≤ 1.0 mV rms (target) / ≤ 0.6 mV rms (stretch), differential.
**Unchanged.**

**Evidence**: `sim/comparator-decision/records/20260916-001416-52eb9b2.md`
— reduced-sub-model `.noise` analysis at `tt`/27°C, differential
input-referred estimate 0.4466 mV rms. This record's own methodology note
states the figure is a **lower bound**: the cross-coupled latch pair is
diode-connected to break the positive-feedback loop for a well-posed
small-signal analysis, so the regeneration phase's own noise contribution
is excluded by construction.

**Why ratify despite the lower-bound caveat.** 0.4466 mV rms leaves a
factor of ~2.24× headroom under the 1.0 mV target before the excluded
regeneration-phase contribution would have to exceed the *entire* measured
lower bound in quadrature to threaten compliance (a regeneration
contribution of ~0.90 mV rms, on top of the 0.4466 mV already measured,
would be needed to reach 1.0 mV rms combined: `sqrt(0.4466² + 0.90²) ≈
1.005`). That is a real amount of headroom to have unmeasured, but it is
headroom, not a deficit — the bound is a reasonable number to commit to,
not a number this measurement is already known to violate. Ratifying the
target bound; the tighter 0.6 mV stretch bound has much less headroom over
this lower bound (0.4466 vs. 0.6, only 1.34×) and compliance against it is
correspondingly less certain — this record ratifies the stretch bound's
*value* as unchanged, but flags it explicitly as the one more likely to be
revisited once regeneration-inclusive noise is measured (Open items).

**What is explicitly not decided here**: a full regeneration-inclusive
noise measurement (not a loop-broken sub-model), and noise across the full
PVT corner set (this is `tt`/27°C only).

### 3. Decision time vs. overdrive — leave OPEN, explicitly (not ratified)

**Bound**: ≤ 1.5 ns (target) / ≤ 0.8 ns (stretch) at 50 mV overdrive,
1.8 V. **Unchanged, and status stays DRAFT.**

**Evidence**: `sim/comparator-decision/records/20260916-000727-52eb9b2.md`
(`tt`/27°C: 0.6775 ns at 50 mV) and
`.../20260916-001345-52eb9b2.md` (`ss`/−40°C, the corner DR-001's headroom
probe and this table's own Basis column both flagged as the expected
binding case: 0.6875 ns at 50 mV). Both points clear not only the 1.5 ns
target but also the 0.8 ns stretch bound, and the flagged slow/cold corner
shows almost no penalty at 50 mV overdrive relative to nominal (0.6875 vs.
0.6775 ns) — consistent with DR-001 Amendment 1's finding that the sizing
pass closed the headroom deficit that record's original planning-convention
probe found.

**Why this row stays open despite both measured points clearing both
bounds.** Two points (`tt`/27°C, `ss`/−40°C), both at the single 50 mV
overdrive figure the bound itself is stated at, is not a PVT sweep — `ff`,
`sf`, and `fs` are entirely unmeasured, and the sub-50-mV overdrive shape
(both records show regeneration time growing sharply as `Vindiff` shrinks
toward 0.5 mV, to 1.68–2.56 ns) is not itself bound by this row's stated
50 mV reference point, so a corner that shifts the effective overdrive
budget could interact with that shape in ways these two points do not
probe. This is exactly the row this issue's own Implementation Guidance
names as the example to leave open ("decision time, which has no full PVT
sweep"), and this record follows that guidance rather than over-claiming
from two favorable points. The two measured points are recorded here as
**strong preliminary evidence the bound is achievable**, not as
confirmation.

**What is explicitly not decided here**: the full PVT sweep (`ff`/`sf`/`fs`
corners), and the sub-50-mV overdrive shape's behavior away from the
`tt`/`ss` axis this record's two points sit on.

### 4. Kickback — RATIFY the existing bound as-is; the design does not meet it; mitigation is follow-on work

**Bound**: ≤ 5 mV disturbance into a 1 kΩ source impedance (target) / ≤ 2 mV
(stretch), single decision edge. **Unchanged.**

**Evidence**: `sim/comparator-decision/records/20260916-060139-f1eb978.md`
— `tt`/27°C, 1 kΩ source impedance, 50 mV overdrive: 144.60 mV peak
disturbance on `VINP` (131.07 mV on `VINN`), against a zero-impedance
`ideal` control that collapses to exactly 0.0000 mV (confirming the
testbench isolates a genuine source-impedance-dependent effect, not a
measurement artifact). **144.60 mV is ~29× the 5 mV target bound and ~72×
the 2 mV stretch bound.**

**This record does not revise the bound to match the measurement.**
`CLAUDE.md` states plainly: "agents do not relax the ratified spec to make
results pass." Revising ≤5 mV up to, say, ≤150 mV to match the current
sizing's measured behavior would be exactly that — laundering a design gap
into a spec change instead of fixing or explicitly deferring the design.
The 5 mV / 2 mV bounds were first-principles engineering judgment
(README's own Basis column, unchanged by this record) about what a
comparator feeding a real driving stage should limit its own kickback to;
nothing in the new measurement is evidence that judgment was *wrong*, only
that *this sizing* does not meet it yet.

**So the bound is ratified, and the gap is named, not hidden.** The
disposition: the ≤5 mV / ≤2 mV bounds become RATIFIED target-spec values;
`design/comparator.sch` at its current (issue #24) sizing is documented as
**non-compliant** against them, by a wide margin; and closing that gap is
recommended as explicit follow-on design work, not a spec change. Candidate
mitigation directions (none designed or evaluated here — this record scopes
the problem, it does not solve it):

- **Reduce the input pair's `Cgd`** — `design/README.md`'s own "What is not
  here" section already flags that the offset-budget sizing pass widened
  the input pair relative to the placeholder, which increases `Cgd` and
  therefore kickback, as "an explicit, unmeasured cost of the offset budget
  above." That tradeoff is now measured (this record) and is the most
  directly implicated mechanism, per the kickback record's own "Reading
  this record" section (Miller coupling through the input pair's own
  gate-drain parasitic capacitance from the `DIP`/`DIN` swing). A resizing
  pass would need to weigh reduced `Cgd` against the offset sigma this same
  input pair sizing was chosen to hit (Decision §1).
- **Dummy/compensation switches** at the input nodes or internal
  (`DIP`/`DIN`) nodes, sized to inject a canceling charge — a standard
  kickback-mitigation technique in dynamic comparator design generally, not
  evaluated against this specific circuit here.
- **Bootstrapped or slew-limited clocking** at the reset→evaluate
  transition, to reduce the rate of the `DIP`/`DIN` swing that couples
  through `Cgd` — also not evaluated here; this would trade decision speed
  (Decision §3) against kickback, a tradeoff this record does not
  quantify.

Filing the mitigation work as a follow-on issue (recommended, not filed by
this PR — see Consequences) keeps this record's own scope to what it can
support with existing evidence: the bound is right, the current sizing does
not meet it, and closing that gap is a design problem, not a spec problem.

**What is explicitly not decided here**: which mitigation (if any) to
implement, whether the offset-sigma/kickback tradeoff the `Cgd` mechanism
implies is acceptable to resolve in either direction, and a full-corner
kickback sweep (this is a single nominal-corner measurement, per the
kickback record's own subset-corner justification).

### 5. Supply / power — leave OPEN, explicitly (not ratified)

**Bound**: 1.8 V ±10% core supply; ≤ 50 µW average (target) / ≤ 20 µW
(stretch), one decision per clock edge at a stated clock rate (TBD).
**Unchanged, and status stays DRAFT.**

**Evidence**: none. No current/power measurement exists for this design at
any corner. The supply-voltage half of this row (1.8 V core, `nfet_01v8`/
`pfet_01v8`) is not itself in question — it follows directly from sky130
shipping no complementary 3.3 V enhancement pair, per this row's own Basis
column and DR-001's clean citation of the same fact — but the power figures
remain first-principles engineering judgment with no measurement behind
them.

**Why this stays open.** The row's own bound is explicitly conditioned on
"a stated clock rate (TBD)" — and that TBD is not filled in by any evidence
this record has, because a clock rate assumption is downstream of the
Decision-time row (§3, above), which this record leaves open for exactly
the same full-PVT-sweep reason. Measuring power against an unratified clock
rate would not be evidence of anything; ratifying a power bound before the
clock-rate row it depends on is settled would put the dependency in the
wrong order.

**What is explicitly not decided here**: the clock rate, any current/power
measurement (quiescent or dynamic), and therefore this row's compliance
status at any corner.

## Alternatives considered

- **Ratify all five rows now, closing the table fully.** Rejected. The
  Decision-time and Supply/power rows have either an incomplete PVT
  basis (two points, one overdrive value) or no measurement at all (power).
  Ratifying a numeric bound with no evidentiary basis behind it would be
  exactly the kind of unsupported spec assertion `CLAUDE.md`'s
  "verification is the product" principle and this issue's own acceptance
  criteria ("no new spec value is asserted without citing the specific
  evidence record that supports it") rule out.
- **Revise the Kickback bound upward to match the 144.60 mV measurement (or
  some multiple of it) instead of ratifying the original figure
  unmet.** Rejected — see Decision §4. This would relax the spec to make a
  result pass, which `CLAUDE.md` names explicitly as the thing agents do
  not do. The measured figure is new information about the *design*, not
  evidence the original bound was miscalibrated.
- **Leave all five rows DRAFT, filing no ratification record at all, until
  a full PVT/Monte-Carlo campaign exists for every row.** Rejected as a
  process matter, mirroring DR-001's own "Deferring the topology decision"
  alternative's reasoning: `spec/porting-plan.md`'s "Next steps" item 5 asks
  for a ratification pass once real measurements exist, not once a
  campaign-complete measurement set exists for every row simultaneously —
  three of five rows have evidence that supports a first-pass ratification
  today, and `spec/README.md` itself frames ratification as due "the first
  time that table's rows are ratified, changed, **or rescoped**" (not
  necessarily all at once). Blocking all five rows on the two that are
  genuinely not ready would leave three well-supported rows sitting DRAFT
  for no evidentiary reason.
- **Treat the Kickback row's ~29×/~72× deviation as disqualifying this
  record from ratifying *any* row, on the theory that a badly-missed row
  undermines confidence in the whole table.** Rejected — the five rows are
  independent measurements against independent mechanisms (mismatch,
  thermal/flicker noise, regeneration dynamics, capacitive feedthrough,
  quiescent/dynamic current); a large miss on one does not cast doubt on
  the methodology or result of another. Treating them as a bundle would
  also cut against `spec/README.md`'s own row-by-row rescoping language.

## Spec lines affected

`README.md`'s target-specification table:

- **Offset sigma** row: status changes DRAFT → **RATIFIED**. Target/stretch
  values unchanged (≤15 mV / ≤8 mV, 3σ). Basis column gains the
  `tt_mm`/N=16 measurement citation.
- **Input-referred noise** row: status changes DRAFT → **RATIFIED**.
  Target/stretch values unchanged (≤1.0 mV / ≤0.6 mV rms). Basis column
  gains the lower-bound measurement citation.
- **Decision time vs. overdrive** row: status stays **DRAFT**, now with an
  explicit "OPEN pending full PVT sweep, see DR-002" note rather than a
  bare DRAFT with no ratification-pass comment. Values unchanged.
- **Kickback** row: status changes DRAFT → **RATIFIED (bound)**, with an
  explicit **non-compliant, mitigation open** annotation — this is not a
  plain "ratified, passing" status; it is a ratified target the current
  design fails, with recommended follow-on work named. Values unchanged
  (≤5 mV / ≤2 mV).
- **Supply/power** row: status stays **DRAFT**, now with an explicit "OPEN,
  no measurement exists, blocked on Decision-time row, see DR-002" note.
  Values unchanged.

`spec/porting-plan.md`'s "Next steps" §5 is marked addressed by this
record (append-only — the original numbered list is not deleted or
reworded, a completion note is added).

`spec/decision-records/TEMPLATE.md` still does not exist as of this
record, for the same reason DR-001 gave: this record is written directly
against DR-001's own shape rather than first creating a template — a
template remains future work if a third decision record makes the shape
worth codifying.

## Consequences

1. **Three of five target-spec rows are no longer bare DRAFT placeholders**
   — Offset sigma, Input-referred noise, and Kickback now carry a ratified
   numeric bound backed by a cited measurement, closing part of gap-to-T1
   tracker #3's item 5 (full PVT corner sim vs. a *ratified* spec) — though
   only partially, since two rows remain open and even the ratified rows'
   underlying measurements are single-corner or limited-N (Open items).
2. **The Kickback finding is now a named, tracked design problem instead of
   an unratified DRAFT figure with a comment.** A ~29×/~72× deviation
   against a bound this record declines to relax is exactly the kind of
   finding that should not sit quietly in a DRAFT table's Basis column —
   ratifying the bound while documenting non-compliance makes the gap
   visible to anyone reading the table, not just anyone who reads the
   kickback evidence record.
3. **A follow-on kickback-mitigation design issue is recommended** (Decision
   §4) — not filed by this record itself; whoever merges/curates this
   record's outcome (Champion, operator, or a subsequent Curator pass) owns
   deciding whether and how to file it, consistent with this repo's
   Curator/Builder division of labor.
4. **Decision time and Supply/power stay explicitly open**, each with a
   stated reason (incomplete PVT coverage; no measurement and a dependency
   on the still-open Decision-time row, respectively) rather than a silent
   DRAFT with no ratification-pass comment — satisfying this issue's
   acceptance criteria that no row goes unaddressed even where the outcome
   is "not yet."
5. **Gap-to-T1 tracker #3 is not edited by this PR**, per the same
   convention PR #27 and PR #25 both followed — the Curator updates #3
   separately once this record merges.

## Open items

- **Offset**: the other four `_mm` corners (`ss_mm`, `ff_mm`, `sf_mm`,
  `fs_mm`) are unmeasured; a larger-N (O(100s) draws) campaign is needed
  before a yield-fraction claim against the now-ratified bound can be made
  at production-relevant confidence. The bound is ratified; the compliance
  claim at tight sigma is not.
- **Noise**: a full regeneration-inclusive noise measurement (not the
  loop-broken reduced sub-model this record's evidence uses) is still
  needed, along with a PVT sweep — this record's measurement is `tt`/27°C
  only. The 0.6 mV stretch bound in particular has less headroom over the
  measured lower bound than the 1.0 mV target does, and is the more likely
  candidate to be revisited once regeneration-inclusive noise is measured.
- **Decision time**: the full PVT sweep (`ff`/`sf`/`fs` corners, not just
  `tt`/`ss`), and the sub-50-mV overdrive shape's behavior off the
  `tt`/`ss` axis, remain open — this row itself stays DRAFT/OPEN pending
  that work, per Decision §3.
- **Kickback mitigation.** No mitigation is designed, sized, or evaluated
  by this record — Decision §4 names candidate directions only. A future
  design pass owns resolving the input-pair-sizing/kickback/offset-sigma
  interaction `design/README.md` already flagged as unmeasured before this
  record's evidence existed.
- **Kickback PVT coverage.** The 144.60 mV figure is a single nominal
  corner (`tt`/27°C); a full-corner kickback sweep is unmeasured and could
  move the figure (up or down) at process/temperature extremes.
- **Supply/power.** No measurement exists at all. This row cannot progress
  until the Decision-time row's clock-rate dependency is resolved (which
  itself needs the full PVT sweep named above), then a dedicated
  current/power measurement against that rate.
- **Layout-stage re-verification.** Every measurement cited by this record
  is schematic-level (`design/comparator.sch` via `./design/netlist.sh`,
  per each evidence record's own "Netlist provenance" field) — no parasitic
  extraction or layout-stage re-simulation exists yet. All ratified bounds
  in this record are ratified against schematic-level evidence only; a
  future layout pass may find any of them needs revisiting.
- **`spec/decision-records/TEMPLATE.md`** still does not exist (see "Spec
  lines affected," above) — left as future work, same as DR-001 left it.
- **Gap-to-T1 tracker #3** is not updated by this record — the Curator's
  job, per this issue's own acceptance criteria and the PR #25/#27
  convention.
