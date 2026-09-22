# DR-004: Comparator topology supersession — static preamplifier ahead of the StrongARM latch, closing the kickback gap

- **Status**: **proposed** — a recommendation for two-key ratification via
  PR merge, exactly as DR-001 and DR-003 before it. Nothing here is binding
  until this PR merges; the README target-spec rows it touches keep their
  DR-002 dispositions until then.
- **Date**: 2026-09-22
- **Decided by**: Builder agent, issue #34
- **Supersedes**: **two clauses of
  [DR-001](DR-001-comparator-topology.md)**, and only those clauses:
  - Decision 1's "No static preamp" ruling (this record's §2.1);
  - Decision 2's "Not a double-tail (two-stage dynamic) latch" exclusion
    (this record's §2.2 — evaluated first, measured, and left standing as
    an exclusion for a different, measured reason than DR-001 gave).
    Everything else in DR-001 stands unchanged: the 1.8 V core-flavour
    scoping, the L = 0.5 µm / Pelgrom-area discipline, the input-pair
    offset-budget lever, and — carried onto the new latch stage — Decision
    3's reset-integrity property. DR-003's soft-clock shaper is retained
    on the clock port unchanged.
- **Superseded by**: (none while this record stands)
- **Related**: #34 (this issue), #30 / PR #35 (DR-003, whose measured
  option table is this record's evidence base and whose Open items name
  this exact follow-on), #26 / PR #27 (the kickback testbench), #24 (the
  DR-001 design + reset check this record's latch stage inherits),
  [DR-002](DR-002-target-spec-ratification.md) (the ratified Kickback /
  Offset / Noise rows this record is graded against),
  [DR-001](DR-001-comparator-topology.md) and its Amendment 1 (the
  superseded clauses and the four-corner headroom discipline this record
  re-runs),
  `spec/dr-004-support/` (this record's committed probe decks),
  `sim/comparator-decision/records/20260922-*` (this record's evidence).

## Context

### The gap this record closes

DR-002 ratified the Kickback row (≤ 5 mV disturbance into a 1 kΩ source
impedance, stretch ≤ 2 mV, single decision edge) against a measured
144.60 mV. DR-003's soft-clock shaper improved that to **85.71 mV** at
the like-for-like tt/27 °C point — a 40.7 % cut that still left the bound
~17× away — and DR-003's measured candidate table showed the remaining
gap was **not closable inside DR-001's topology class**: input-pair
resizing tracks kickback roughly ∝ W and destroys the ratified offset
budget; CLK-correlated cancellation caps cannot cancel the post-ramp
tail; input isolation switches meet the pin bound but regress the
ratified noise row's own methodology (0.4466 → 17.53 mV) and decision
time (0.68 → 3.80 ns @ 50 mV), breaching 5 mV at ff/125 °C in the 3-deep
variant; rate-based slowdown trades ~1:1 into decision time. Issue #34
was filed to own exactly that residue, and this record is the
topology-class change it tracks.

### Why a decision record, and which clauses

Per `spec/README.md`, a DR is owed whenever a target-spec row's approach
is changed. Changing the comparator's topology class changes the basis of
every row at once — the kickback mechanism, the offset/noise budgets, the
decision-time anchor, and the Supply row's very framing — so the change
goes through the spec's own supersession convention (never edit a
standing record's decided text in place). This record supersedes the two
DR-001 clauses named above and nothing else; it does not touch any
ratified numeric bound (see "Spec lines affected").

### Clean room

The static-preamplifier-plus-StrongARM-latch class evaluated here is the
same generic, widely-published circuit family DR-001's clean-room note
covered (e.g. Razavi, *Design of Analog CMOS Integrated Circuits*,
comparator front-ends), evaluated from first principles against this
repo's own installed sky130 models and measured by this repo's own
committed testbenches. No external implementation is copied or transcribed;
`sky130-sar-adc`'s comparator work is cited only as same-PDK
methodology prior art, per this repo's standing clean-room convention.

## Decision

### 1. Adopt a static resistive-load NMOS preamplifier ahead of a StrongARM-class latch

`design/comparator.sch` now implements, per this record:

- a **continuously-biased preamplifier**: gate-at-VDD NMOS current source
  `M_PTAIL` (W = 0.8 µm), input pair `M_PINN`/`M_PINP` (W = 13 µm — the
  offset lever, widened one step from DR-001 Amd 1's 10 µm as the noise
  lever), poly loads `R_LP`/`R_LN` (res_high_po_0p35, L = 22 µm ≈ 30 kΩ
  solved), and OUT1 absorber MOS caps `M_C1P`/`M_C1N` (W = 40 µm) at the
  preamp outputs;
- a **clocked StrongARM-class latch**: tail switch `M_TAIL2` (W = 8 µm),
  steering pair `M_STN_P`/`M_STN_N` (W = 8 µm) gated by the preamp
  outputs `OUTP1`/`OUTN1`, cross-coupled PMOS `M_LATP_P`/`M_LATP_N`
  (W = 16 µm), output reset PMOS `M_RST_P`/`M_RST_N` (W = 8 µm);
- the **DR-003 soft-clock shaper retained unchanged** on the clock port
  (`R_CLKS` L = 1.75 µm + `M_CLKCAP` W = 20 µm → `CLKT`, driving the
  latch tail and both reset PMOS).

16 devices (13 MOSFETs + 3 poly resistors), all
`sky130_fd_pr__{n,p}fet_01v8`, ports unchanged (`VDD GND CLK VINP VINN
OUTP OUTN` — the preamp is internally biased; no new port), polarity
convention unchanged.

**Why this class wins, in one paragraph:** the kickback the pins see is
set by what moves at the input devices' gates during the decision edge.
With a dynamic input stage (single-tail or double-tail), the input pair's
channels do not exist during reset and must be formed at the edge — a
transient gated by the same source-node ramp that gates the stage's
transconductance, so kickback and decision speed trade ~1:1 (measured
again below for the double-tail). A continuously-biased preamp removes
the mechanism at its root: the channels are always formed, `Vgs` is
constant, and whatever the latch kicks back arrives at the preamp
**output** nodes, where explicit capacitance absorbs it before the pins.
The measured result: **1.89 mV worst-node peak at tt/27 °C, 1.86 mV at
ss/−40 °C, 1.77 mV at ff/125 °C — all three PVT anchors clear both the
ratified 5 mV target and the 2 mV stretch bound** (records
`20260922-070119/070212/070307-e084b55`, ideal controls 0.0000 mV
everywhere).

### 2. The option ladder, measured

Per issue #34's guidance, route A (double-tail) was evaluated **first**,
with a committed probe deck
(`spec/dr-004-support/double_tail_probe.spice` — this repo's own device
set, same stimulus and shaper as the graded benches, scratch-deck series
convention as DR-003's option table used):

| Route | Measurement | Verdict |
|---|---|---|
| **A: double-tail** (single-CLK, first-stage regenerative PMOS added after the minimal variant's steering drive was measured to decay with the mid-node discharge — sep max 0.655 V @ 40 ns, diagnostic in the probe header) | worst-node kickback **7.5 mV @ 0.77 ns** (shaper τ ≈ 220 ps); softening the shaper to τ ≈ 500 ps gives **7.1 mV @ 1.14 ns** | **Rejected**: the channel-formation kick stays above the 5 mV bound while the decision time stretches 1.5× — the same ~1:1 elasticity DR-003 measured on the single tail, now measured on the two-stage form. The class cannot buy kickback with speed it doesn't have. |
| **B: static preamp** (this record) | worst-node kickback **1.89 mV @ 0.40 ns** (tt/27 °C, τ ≈ 220 ps) | **Adopted**: mechanism removed at the root; the pins are isolated behind a stage whose outputs are capacitively clamped, at *better* speed than the DR-003 design (0.4025 vs 1.18 ns @ 50 mV). |

DR-001 Decision 2's double-tail exclusion therefore **stands, with new
measured grounds**: not the un-quantified headroom anxiety DR-001 recorded,
but the measured elasticity of a dynamic input stage's channel-formation
kick. A future double-tail variant with mid-node clamping or a
first-stage tail current could re-open it; nothing here forbids that, it
just prices it.

### 3. Headroom — the supersession clause, answered with DR-001's own discipline

DR-001 Decision 1's load-bearing argument against a preamp was headroom
("no quantified headroom to spend on a second device group"). A
supersession carries the four-corner probe discipline DR-001 established;
`spec/dr-004-support/preamp_op_probe.spice` re-runs it on the real
static stage (no stand-ins — the preamp holds its own continuous
operating point):

| Corner | V(TAILP) | V(OUT1) CM | I/side | Vov,in | **Vds,in − Vdsat,in** |
|---|---|---|---|---|---|
| tt / 27 °C | 0.177 V | 1.145 V | 21.8 µA | 60 mV | **+0.876 V** |
| tt / −40 °C | 0.141 V | 1.097 V | 23.3 µA | 43 mV | **+0.881 V** |
| ss / 27 °C | 0.170 V | 1.248 V | 18.3 µA | 53 mV | **+0.989 V** |
| ss / −40 °C | 0.135 V | 1.213 V | 19.5 µA | 36 mV | **+1.008 V** |

The input pair saturates with ~0.9–1.0 V of margin at every corner —
because the load is a resistor hanging from the rail, the preamp stack is
*shorter* than the DR-001 single-tail latch stack it displaces. `M_PTAIL`
sits in deep triode at every corner (Vds = 0.13–0.18 V against Vdsat =
0.54–0.65 V), so DR-001 Amd 1's finding that a switch-like tail's Vdsat
budget is recoverable transfers to this always-on tail verbatim. The
headroom clause is answered: the 1.8 V constraint bounds the latch stack
(as before) and leaves the preamp stack *more* room than the design it
replaces.

### 4. Reset integrity — DR-001 Decision 3's property, carried forward

The latch stage keeps the reset mechanism: with `CLKT` low, `M_RST_P/N`
precharge `OUTP`/`OUTN` to VDD, which are also the cross-coupled PMOS
pair's gates — so every latch PMOS sits at exactly `Vgs = 0` and the loop
gain is zero. The steering pair's gates sit at the preamp's static CM with
`M_TAIL2` off, so no supply path exists; `TAIL2` floats to ~the steering
pair's Vth and conduction self-limits. The re-derived check
(`run.py reset`, counterfactual moved onto the steering pair's sources):
**5/5 as-drawn corners hold reset; 5/5 gnd-tied controls break it**
(record `20260922-070024-e084b55`, as-drawn |I(VDD)| ≤ 68 µA against
controls at 0.9–1.1 mA — the current bound re-derived around the
preamp's own static floor, stated in the record).

## Alternatives considered

- **Stay inside DR-001's class and keep softening the clock.** Rejected on
  DR-003's own measured ladder: rate-based reduction trades ~1:1 into
  decision time; τ drift with PVT floats the trade. No τ reaches 5 mV at
  a usable decision time.
- **Adopt the double-tail (route A).** Evaluated first per the issue's
  guidance, measured, rejected — §2's table.
- **Input isolation switches.** Already measured and rejected by DR-003
  (ratified-noise methodology regression to 17.53 mV; 3.80 ns decision;
  ff/125 °C breach in the 3-deep variant). Not re-run here; DR-003's
  numbers stand.
- **Widen the preamp to chase margin instead of compliance.** The adopted
  sizing lands every ratified row inside its bounds with margin (§
  Consequences); further widening spends Supply-row budget (already the
  binding open cost) for no binding gain. Stopped where the bounds are met.

## Spec lines affected

- **`README.md` Kickback row**: Basis/Status annotation updated — the
  design is **compliant at all three graded PVT anchors** (first design to
  meet the row; DR-002's ratification of the bound is vindicated
  unchanged). Bound values untouched.
- **`README.md` Decision-time row** (DRAFT): re-anchored at the new
  design's measured numbers (0.4025 ns @ 50 mV tt; 0.3575 ns ss/−40 °C)
  with the sub-mV ss/−40 °C finding recorded. No bound change.
- **`README.md` Supply/power row** (DRAFT/OPEN): basis annotated with this
  record's measured currents; **no bound change** — the row's framing
  ("one decision per clock edge at TBD clock rate") is documented as
  superseded-in-substance by the class change and its re-anchoring is
  explicitly left as an open ratification item, not silently rewritten.
- **`README.md` Offset sigma / Input-referred noise rows** (RATIFIED):
  Basis annotations cite the new records (1.7857 mV σ; 0.5704 mV rms).
  Bounds untouched; both still clear target and stretch.
- **`design/comparator.sch`, `design/netlist.sh`,
  `sim/comparator-decision/testbench/comparator_core.spice`** — the
  design itself (schematic is the source of truth; the fragment is its
  generated build product).
- **`sim/comparator-decision/run.py`** — the `noise` sub-model re-derived
  onto the real static preamp stage; the `reset` check's counterfactual
  and current bound re-derived; the `offset` pick-off re-anchored
  1.0 → 0.65 ns. All methodology constants print into their records.

## Consequences

1. **Kickback compliance, stated plainly**: 1.8902 mV (tt/27 °C),
   1.8605 mV (ss/−40 °C), 1.7677 mV (ff/125 °C) against the ratified
   ≤ 5 mV target and ≤ 2 mV stretch — the target met with 2.65–2.83×
   margin, the stretch with 1.06–1.13×. The stretch margin is thin and
   PVT-dependent; the committed anchors bracket it, and a layout-stage
   re-verification (as DR-002 already requires for every row) remains the
   gate before any compliance is claimed of silicon.
2. **Offset**: 1.7857 mV σ (N = 16, `tt_mm`, seed 1; 3σ = 5.36 mV) —
   clears target (≤ 15 mV) and stretch (≤ 8 mV). The pick-off
   re-anchoring (0.65 ns, 6 % calibration compression) is itself a
   recorded consequence: the preamp design is fast enough that the
   DR-003-era pick-off sat in saturation.
3. **Noise**: 0.5704 mV rms differential (tt/27 °C) on the re-derived
   REAL-static sub-model — clears target (≤ 1.0 mV) and stretch
   (≤ 0.6 mV). Getting under the stretch bound cost the widened input
   pair (10 → 13 µm) and the raised bias (≈ 22 µA/side): at the first-cut
   sizing the measured value was 0.72 mV, under the target but over the
   stretch. The noise/speed/kickback levers are now coupled through the
   preamp bias — future re-tuning must re-measure all three together.
4. **Decision time**: 0.4025 ns @ 50 mV (tt), 0.3575 ns (ss/−40 °C) —
   ~2.9× faster than the DR-003 design at the same point, with the
   small-overdrive ladder shifted accordingly (1.1375 ns @ 0.5 mV, tt).
   **At ss/−40 °C the 0.5 mV point no longer resolves** — a dedicated
   400 ns probe shows it creeping to only 11.7 mV separation, where the
   DR-001 design resolved it in 2.5575 ns (record `20260916-001345`).
   With input-referred offset σ ≈ 1.8 mV, sub-mV differential decisions
   are below the design's own offset floor in practice, and the row's
   bounds are stated at 50 mV overdrive — but the regression is real,
   recorded here rather than hidden, and priced into the Open items.
5. **Supply/power, measured for the first time**: the class costs static
   current — ~51–55 µA in reset (preamp + self-limited off-path) and
   ~344–564 µA during evaluate (preamp + the winning latch branch, whose
   steering gate stays DC-biased — the StrongARM evaluate-phase current,
   present for as long as CLK is high; measured by
   `spec/dr-004-support/evaluate_idd_probe.spice` at tt/27 °C,
   ss/−40 °C, ff/125 °C). At 1.8 V the static term alone is ~95 µW, above
   the DRAFT row's 50 µW figure; the row's "one decision per clock edge"
   framing predates any preamp and is superseded in substance. **No bound
   is changed by this record** — re-anchoring the Supply row is an open
   ratification decision (Open items).
6. **The `u`-suffix netlist gotcha, recorded for the fleet**: a
   `res_high_po_0p35` instance's `L=` parameter silently falls back to the
   model default `l=1` when given a suffixed value (`4u`) or a
   `.param`-expanded value under this spiceinit's hsa/scale mode — plain
   literals bind correctly (verified empirically; the committed DUT and
   probe decks use plain literals). Bit this record's own option-probe
   ladder once; the probe header documents it.
7. **DR-003's shaper is no longer the kickback mechanism** — it is
   retained as onset conditioning (and its ~250 ps contention window
   consequence is subsumed by the now-measured evaluate current). A
   future pass could re-evaluate whether the shaper still earns its two
   devices; nothing here depends on it.

## Open items

- **Supply/power re-anchoring** — the row needs its own ratification pass
  with a stated clock rate and duty cycle, against this record's measured
  reset/evaluate currents. Blocked on an operator framing decision (the
  row is DRAFT; agents do not relax spec rows).
- **Sub-mV overdrive at ss/−40 °C** — characterize or fix (candidate
  levers: preamp gain at cold, steering width, or an explicit
  metastability-report requirement in the Decision-time row's
  methodology). The 40 ns window and the 0.5 mV sweep point stay as they
  are; the record honestly reports UNRESOLVED.
- **Full PVT campaign** — unchanged from DR-002's open items: this record
  grades three kickback anchors, one noise/offset corner pair, and five
  reset corners; the sf/fs skews and a supply sweep remain unmeasured for
  every row.
- **Offset MC breadth** — still N = 16 / seed 1 / `tt_mm` only (relative
  SE on σ ≈ 18 %); the O(100s)-draw, multi-corner campaign DR-002 asked
  for is still open, now against the new topology.
- **Layout-stage re-verification** — DR-002's standing item, now applying
  to the preamp's resistors (poly matching is not an `_mm` model term on
  this PDK — the MC record measures whatever it contributes, but layout
  proximity effects on `res_high_po` are unmodelled here).
- **Cross-pollination** — the topology-class finding (dynamic-input
  channel-formation kick vs. static-preamp isolation, with the measured
  double-tail ladder) is to be filed/extended on
  `2AMLogic/sky130-sar-adc` per CLAUDE.md's protocol (that repo's #346
  already carries the DR-003 finding).
