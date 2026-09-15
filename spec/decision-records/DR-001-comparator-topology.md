# DR-001: Comparator topology — single-tail dynamic latch, no static preamp

- **Status**: **proposed** — this record ratifies nothing. No ratification
  issue is filed for it yet; the top-level `README.md` target-spec table
  stays DRAFT either way (see "Spec lines affected" below). Nothing here is
  binding until an operator ratification act rules on it.
- **Date**: 2026-09-15
- **Decided by**: Builder agent, issue #21
- **Supersedes**: none — first decision record in this repo
  (`spec/decision-records/` did not exist before this PR).
- **Superseded by**: (none while this record stands)
- **Related**: #21 (this issue), #3 (gap-to-T1 tracker — this record answers
  porting-plan "Next steps" item 1), `spec/porting-plan.md` ("Next steps" §1,
  the source of this issue's scope), `README.md`'s target-specification
  table (the DRAFT bounds this record's headroom finding constrains, without
  changing any row — see below), `sim/comparator-decision/` (issue #9, PR
  #20 — the `regen`/`offset`/`noise` harness this record's schematic, once
  drawn per porting-plan next step 2, will exercise against a real device
  fragment instead of the current placeholder DUT). Cited as same-PDK prior
  art (methodology, not values — see "Clean room" below):
  [`sky130-sar-adc` DR-001](https://github.com/2AMLogic/sky130-sar-adc/blob/main/spec/decision-records/DR-001-supply-flavor-scope.md),
  [DR-003](https://github.com/2AMLogic/sky130-sar-adc/blob/main/spec/decision-records/DR-003-numeric-spec-derivation.md)
  (Item 1 — the `.op` `vth`-probe headroom-quantification technique this
  record re-runs independently),
  [DR-004](https://github.com/2AMLogic/sky130-sar-adc/blob/main/spec/decision-records/DR-004-comparator-topology-and-noise-budget.md)
  (the sibling's own comparator-topology decision and its Amendment A
  reset-integrity fix — same reasoning pattern, re-derived here, not copied).

**On `TEMPLATE.md`.** `spec/decision-records/TEMPLATE.md` does not exist yet
in this repo. Per this issue's acceptance criteria, this record is written
directly against the `sky130-sar-adc` DR-004 shape (Status / Date / Decided
by / Supersedes / Superseded by / Related / Context / Decision /
Alternatives considered / Spec lines affected / Consequences / Open items)
rather than first creating a template file — a template is left as future
work if a second decision record makes the shape worth codifying.

## Context

### Why a decision record, not just a schematic comment

Per `spec/README.md`, a DR is owed whenever a value or approach in the
target-spec table is set, changed, or scoped. A topology choice does not
itself edit a table row, but it determines the headroom/noise/speed
tradeoffs every row's basis column currently states as TBD pending a
design — `spec/porting-plan.md`'s own "Next steps" §1 already commits this
repo to writing that choice as a DR, mirroring `sky130-sar-adc`'s DR-004
shape. This record follows that precedent.

### What's different here from the nearest same-PDK prior art

`sky130-sar-adc`'s DR-004 chose a topology for a comparator whose input
common mode is fixed near `V_REF/2` by a driving differential top-plate
CDAC — that repo's comparator is embedded, not standalone. This repo has no
CDAC and no sequencer (`spec/porting-plan.md`, "What is designed fresh, not
ported"): the common-mode point a headroom argument here must use is a
stimulus assumption this record states itself, not one inherited from a
CDAC topology. This record uses **`V_CM = V_DD/2 = 0.9 V`** — the
maximal-headroom symmetric point for an ideal differential bench stimulus
with no external circuit fixing the common mode, and (coincidentally, not
by inheritance) the same numeric value DR-004 used for its own,
differently-motivated reason (`V_REF = V_DD` there).

The top-level `README.md` target-spec table's "Supply / power" row already
states the reason no complementary 3.3 V option exists on this PDK
(`sky130_fd_pr` ships no complementary enhancement pair at that node), so
the 1.8 V core flavor — and the headroom constraint `CLAUDE.md` names as
this repo's defining design pressure — is not re-litigated here.

### Clean room

The topology class evaluated below (a single-tail dynamic latch — bottom-
tail NMOS switch, NMOS input pair, cross-coupled NMOS/PMOS regenerative
latch, PMOS reset/precharge devices) is a generic, widely-published circuit
family (the StrongARM/dynamic-latch class, e.g. Razavi's *Design of Analog
CMOS Integrated Circuits*), evaluated here from first principles against
this repo's own sky130 device measurements (below) and this repo's own
headroom constraint. No specific implementation — `sky130-sar-adc`'s or any
other party's — is copied, reverse-engineered, or sized from; the reset
scheme named in the Decision section is independently re-derived from the
same generic "a live positive-feedback loop must not be conducting during
reset" correctness requirement any StrongARM-class latch design has to
satisfy, not copied from a specific netlist. `sky130-sar-adc`'s DR-004
(including its Amendment A) is cited only as same-PDK evidence that a
naive version of this reset problem is real and measurable on this PDK's
own devices — as prior art informing what to check for, per this repo's
`CLAUDE.md` clean-room convention, not as a design this record transcribes.

### Headroom quantification (fresh probe, this repo's own devices)

Mirroring the technique `sky130-sar-adc`'s DR-003 Item 1 documents — a BSIM4
`.op`-point `vth` probe (the bias-dependent operating-point threshold ngspice
reports for a BSIM4 device, not the model card's raw `vth0` fitting
parameter, which does not fold in short-channel/DIBL/`Vds` effects) — this
record runs its own probe against this repo's own installed PDK
(`spec/dr-001-support/vth_probe.spice`; run via
`source sim/env.sh && ngspice -b spec/dr-001-support/vth_probe.spice`, and
by substituting the `.lib`/`.temp` lines for the other three corner points
below). No number is copied from the cited prior art; every value here is
freshly measured. Representative planning geometry `W = 4 µm / L = 0.5 µm`
(`nfet_01v8`, source grounded, `Vgs = Vds = 0.9 V`, `Vbs = 0 V`) — not a
locked design point; final sizing is porting-plan next step 2, out of scope
here.

| Corner | Temp | `Vth,n` (measured) | `Vdsat,n` (measured) |
|---|---|---|---|
| `tt` | 27 °C | 629.5 mV | 221.3 mV |
| `ss` | 27 °C | 646.9 mV | 211.5 mV |
| `tt` | −40 °C | 691.1 mV | 168.5 mV |
| `ss` | −40 °C | 708.5 mV | 159.3 mV |

Taking the same conservative, deliberately-modest planning convention
DR-003 Item 1 used for the two headroom terms a real bias/sizing pass would
otherwise have to fix first (`V_ov,in = V_dsat,tail = 125 mV` each — a
generic low-power-analog planning heuristic, not itself a sky130-specific or
`sky130-sar-adc`-specific number):

```
V_cm,min = Vth,n + V_ov,in + V_dsat,tail
Margin   = V_cm − V_cm,min   (V_cm = V_DD/2 = 900 mV, this record's own
                               standalone-bench assumption — see above)
```

| Corner | Temp | `V_cm,min` | Margin |
|---|---|---|---|
| `tt` | 27 °C | 879.5 mV | **+20.5 mV** |
| `ss` | 27 °C | 896.9 mV | **+3.1 mV** |
| `tt` | −40 °C | 941.1 mV | **−41.1 mV** |
| `ss` | −40 °C | 958.5 mV | **−58.5 mV** |

**This is a harder result than the same headroom argument produced on the
sibling PDK/repo.** DR-003 Item 1 found a thin (23.1 mV) but positive margin
at `tt`/27 °C and explicitly could not quantify the slow/cold corner (their
`ss`/−40 °C `vth_probe.spice` sweep did not converge while that record was
drafted, so it was carried as an unresolved open item). This record's own
`tt`/27 °C margin (+20.5 mV) is consistent with that same thin-but-positive
finding — independent evidence of the same underlying effect, not a copy —
but the `ss`/−40 °C probe **did** converge here (a few seconds, no
convergence difficulty on this device/bias), and it comes back **negative**:
at the planning `V_ov,in = V_dsat,tail = 125 mV` convention, a plain
bottom-tail NMOS-input dynamic latch at `V_CM = 900 mV` does **not**
have enough headroom at the slow-process/cold-temperature corner. Reading
the two single-axis points against the two-axis corners shows temperature
dominates the degradation (`tt`/−40 °C alone: −41.1 mV, already negative)
far more than process skew alone (`ss`/27 °C: still +3.1 mV, barely
positive) — both together (`ss`/−40 °C) compound to −58.5 mV.

**What this measurement is not.** It is a representative-geometry planning
check, not a sizing result — the eventual `design/comparator.sch` sizing
(next step 2) is free to choose a different `W/L` and a different, lower
operating overdrive than the 125 mV/125 mV planning convention used here
(overdrive is a sizing lever: a wider device reaches a given current at a
lower `Vov`). This record's job is to name the constraint the sizing pass
inherits, quantified against real device data, not to resolve it.

## Decision

**1. No static preamp.** `design/comparator.sch` (next step 2, not drawn by
this record) is committed to a single dynamic-latch stage with no preceding
static (continuously-biased) preamplifier. Rationale:

- The headroom finding above is the load-bearing argument, and it is
  **stronger** here than in the cited same-PDK prior art: even the bare
  single-tail latch's own input pair and tail device do not clear the
  planning-overdrive budget at the slow/cold corner (−58.5 mV at
  `ss`/−40 °C). A static preamp needs its own input pair, its own
  tail/bias device, and its own load — stacking a second headroom-consuming
  device group in front of a budget that is already negative at one corner
  with only the latch's own devices to fit. There is no quantified headroom
  to spend on a preamp stage at this supply; adding one would make an
  already-negative margin worse, not close it.
- This is a design-judgement call, made explicitly on the headroom argument
  above (now backed by a four-corner measurement, not an unresolved
  prediction) — consistent with, and independently re-derived alongside,
  the same conclusion the cited prior art reached from a thinner evidence
  base. Future work could revisit this if a full sizing/corner campaign
  against the actual `design/comparator.sch` geometry (next step 2, then a
  future corner campaign) finds the no-preamp latch's performance
  unacceptable at a corner this record's representative-geometry probe does
  not resolve on its own (see Open items).

**2. Single-tail, bottom-tail NMOS-input dynamic latch (StrongARM/dynamic-
latch class), 11 devices: 1 tail switch + 2 input pair + 2 cross-coupled
latch NMOS + 2 cross-coupled latch PMOS + 2 output-node PMOS reset/precharge
+ 2 internal-node PMOS reset/precharge.** Not a double-tail (two-stage
dynamic) latch — see Alternatives.

- The topology class follows from the same headroom mechanism above: an
  NMOS input pair over a bottom tail switch is the textbook low-device-count
  way to satisfy `V_cm,min = Vth,n + V_ov,in + V_dsat,tail` measured up from
  `GND`, and this record's own measurement (above) is against exactly that
  stack. No alternative device count for the tail/input/latch core is
  evaluated — the class itself, not a device-count variant, is what the
  headroom argument bears on.

**3. Reset scheme: CLK-gated PMOS precharge of *both* the differential
output nodes and the cross-coupled latch NMOS pair's internal source nodes
to `VDD` — not a reset that ties the latch NMOS pair's sources directly to
`GND`.**

- **The generic correctness requirement this follows from.** A StrongARM-
  class cross-coupled NMOS/PMOS latch pair is a positive-feedback loop.
  During reset, before the deliberate evaluate edge, that loop must not be
  live — if the latch NMOS pair's sources sit at `GND` while the outputs are
  held near `VDD` by the reset PMOS pair, every latch NMOS device conducts
  (`Vgs > 0`) throughout the reset phase, in direct DC opposition to the
  reset pull-ups. That is not just a static-current waste; it puts the
  cross-coupled loop's gain above unity while the inputs still float, which
  makes the reset state an **unstable** equilibrium that any asymmetry
  (corner skew, temperature, subthreshold input-pair leakage) can amplify
  toward either rail before the real decision edge — a functional defect,
  not only a power or timing one. This is a first-principles consequence of
  what a cross-coupled pair *is*, independent of any specific
  implementation.
- **Fix, independently re-derived.** Precharging the latch NMOS pair's
  source nodes to `VDD` alongside the output nodes forces every latch NMOS
  device to `Vgs = 0` during reset (gate at `VDD` from the opposite
  precharged output, source at `VDD` from its own precharged internal
  node) — loop gain is exactly zero, the reset state is a stable
  all-devices-off equilibrium, and no DC path from `VDD` to `GND` exists
  through the latch at all during reset.
- **Why this is stated now, in the topology DR, rather than left for the
  schematic PR to discover.** `sky130-sar-adc`'s DR-004 is cited here as
  same-PDK evidence, not a copied design: that record's Amendment A
  documents finding this exact defect **empirically**, after the naive
  (sources-tied-to-`GND`) version was already drawn and simulated — a
  reset-integrity negative control failed at 3 of 9 PVT corners, with
  outputs observed separating toward opposite rails during the CLK = 0
  reset window with no input applied. Stating the correct reset scheme as
  part of this topology decision, before a schematic exists, is this
  record's attempt to avoid re-discovering the same defect the hard way on
  this repo's own netlist.

## Alternatives considered

- **A static preamp ahead of the dynamic latch.** Rejected — see Decision
  §1. The headroom evidence against it is stronger here (a measured
  negative margin at the slow/cold corner even without a preamp) than in
  the cited prior art (a thin but positive `tt`/27 °C margin only). Not
  ruled out permanently: if the sizing pass (next step 2) or a future
  corner/Monte-Carlo campaign finds the no-preamp latch's performance
  unacceptable at a corner this record's representative-geometry probe does
  not resolve, a preamp becomes the natural next escalation — but it would
  need to close this record's own negative-margin finding first, not just
  the thinner one the prior art flagged.
- **A double-tail (two-stage dynamic) latch instead of the single-tail
  topology chosen.** Not adopted, but named here as a **more strongly
  motivated** escalation path than in the cited prior art, precisely
  because of this record's negative-margin finding at the slow/cold corner:
  a double-tail arrangement lets a first-stage tail (sized/timed
  independently) do a coarse pre-amplification with its own discharge path
  before a second regeneration stage takes over, which can relax the single
  stacked tail/input/latch headroom budget this record measured as
  insufficient at `ss`/−40 °C. This record does not adopt it because the
  chosen single-tail class still clears the simpler, lower-device-count
  bar this record set out to check (a headroom argument, not a full sizing
  study), and per Decision §1's own "no headroom to spend on extra devices"
  logic, adding a second dynamic stage carries its own device-count and
  headroom cost that this record has not evaluated. If the sizing pass
  cannot close the `ss`/−40 °C deficit within the single-tail class (Open
  items), double-tail is the documented next escalation, not preamp.
- **Deferring the topology decision until a full PVT/Monte-Carlo campaign
  exists.** Rejected as a process matter, mirroring the cited prior art's
  own reasoning: this issue is independently designable and simulatable
  without the rest of this repo's future work, and a representative-
  geometry, four-corner headroom check (this record) is a reasonable
  "first-pass, not sigma-adequate" characterization to commit a topology
  class against, not a full campaign. Waiting for a full campaign before
  any topology commits would block porting-plan next steps 2–4 on work that
  itself needs a topology to exercise.

## Spec lines affected

**None.** This record changes no row of the top-level `README.md`
target-spec table. Every row there remains **DRAFT**, exactly as
`spec/README.md` describes: this record supplies a topology-class and
reset-scheme commitment, plus a quantified headroom constraint the future
sizing pass inherits, for a future ratification act to weigh — it does not
ratify anything on its own, and no table row is edited by this record or by
issue #21's PR. In particular, the "Decision time vs. overdrive" row's
basis column already names the slow/cold corner as the expected binding
case; this record's headroom finding is consistent with, and sharpens
without changing, that expectation.

## Consequences

1. **Porting-plan next step 2 (`design/comparator.sch`) now has a committed
   topology class, device count, and reset scheme to design against**,
   instead of starting from zero — closing this issue's acceptance
   criteria on the topology/reset-scheme decision with a concrete,
   evidence-backed answer.
2. **A real, quantified headroom deficit at the slow/cold corner
   (`ss`/−40 °C: −58.5 mV against the planning `V_ov,in = V_dsat,tail =
   125 mV` convention) is now a named design constraint the sizing pass
   must resolve** — either by sizing the input pair/tail for a lower
   operating overdrive than this record's planning convention, or by
   accepting and documenting corner-limited performance at that extreme.
   This is a real, load-bearing finding, not a footnote: the no-preamp
   decision above does not remove it, and no sizing choice is made in this
   record to paper over it.
3. **The `ss`/−40 °C convergence gap the cited prior art left open is
   closed on this repo's own devices** — this record's probe converges in
   seconds at that corner, so any future comparator-headroom check on this
   PDK/repo has a working, committed reference deck
   (`spec/dr-001-support/vth_probe.spice`) rather than a known-troublesome
   sweep to re-attempt from scratch.
4. **Double-tail is now a more concretely motivated fallback than a
   generically-named alternative** (Alternatives, above) — a future sizing
   pass that cannot close the `ss`/−40 °C deficit within the single-tail
   class has a documented escalation path and the reason it exists.
5. **This record sets no numeric target-spec row and ratifies nothing** —
   the top-level README table stays DRAFT (Spec lines affected, above).

## Open items

- **Closing the `ss`/−40 °C headroom deficit at real sizing.** This
  record's probe uses a representative planning geometry and a fixed
  125 mV/125 mV overdrive convention, not the eventual design's sizing. The
  schematic/sizing pass (porting-plan next step 2) owns resolving this —
  either by demonstrating a real `W/L` choice that reaches the needed
  headroom at a lower operating overdrive, or by explicitly accepting and
  documenting reduced performance/yield at that corner extreme.
- **A full PVT sweep at the actual sized geometry**, once
  `design/comparator.sch` exists — this record's four points (`tt`/`ss` ×
  27 °C/−40 °C) are a headroom-argument check at a representative geometry,
  not a sigma-adequate or corner-complete characterization of the real
  design. A future corner campaign (mirroring the cited prior art's own
  #28-equivalent scope) is the next owner, once a real netlist exists to
  run it against.
- **Double-tail topology re-evaluation** if the single-tail sizing pass
  cannot close the slow/cold deficit within the single-tail class at
  acceptable performance cost (Alternatives, above).
- **The 125 mV/125 mV planning-overdrive convention itself** is a generic,
  deliberately conservative heuristic (mirroring the cited prior art's own
  choice of it), not a sky130- or design-specific derivation — a future
  sizing pass may find a real design point needs a different (likely lower)
  operating overdrive than this record assumed for the headroom check, in
  which case the margins above should be re-derived at that operating
  point rather than trusted as a final verdict.
- **No offset, noise, or kickback measurement is performed by this
  record** — this is a topology-class and reset-scheme decision only, per
  this issue's explicit scope; those testbench measurements are porting-plan
  next steps 3–4, once a schematic and harness exist.
- **This record does not draw or reference `design/comparator.sch`** — per
  this issue's explicit scope, the schematic itself is porting-plan next
  step 2, filed as its own follow-up issue once this record merges.
- **Ratification** — nothing in this record is binding until an operator
  ratification act rules on it; no such issue is filed yet for this record.
