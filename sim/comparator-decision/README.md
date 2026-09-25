# sim/comparator-decision/ -- regen/offset/noise/reset/kickback experiment

Standalone characterization experiment for a dynamic latched comparator's
decision behavior: regeneration time vs. differential input (`regen`),
mismatch-driven offset (`offset`), input-referred noise (`noise`), reset
integrity (`reset`), and input-node kickback disturbance (`kickback`). Every
stimulus here is an ideal differential DC/pulse source -- there is no CDAC
array or SAR sequencer dependency, because this repo (`sky130-comparator`)
has no SAR ADC. `regen`/`offset`/`noise` implement `spec/porting-plan.md`'s
"Next steps" item 3; `reset` and `kickback` are this repo's own additions
(issues #24 and #26).

```sh
python3 sim/comparator-decision/run.py --check-env
python3 sim/comparator-decision/run.py regen    --record
python3 sim/comparator-decision/run.py offset   --record --n 16 --seed 1
python3 sim/comparator-decision/run.py noise    --record
python3 sim/comparator-decision/run.py reset    --record
python3 sim/comparator-decision/run.py kickback --record
```

See `sim/README.md` for the general `sim/` evidence-record and directory
conventions (`testbench/`, `netlist-snapshots/`, `corners/`, `mc-draws/`,
`records/`) this experiment follows; this file covers only what is specific
to `comparator-decision/`.

## Provenance

The `regen` / `offset` / `noise` **measurement methodology** implemented by
`run.py` is ported from
[`2AMLogic/sky130-sar-adc`](https://github.com/2AMLogic/sky130-sar-adc)'s
`sim/comparator-decision/run.py`, verified against that repo's `main` branch
at commit `a94fde09244c5e86bafb2adb0a97533d2d59dd65` (2026-09-09) via the
GitHub API. That repo's comparator is not a peripheral testbench -- it is a
core subblock of its own ADC design, exercised in this same directory shape
-- per `spec/porting-plan.md`'s "Primary port source" section, which this
issue's own scope statement (issue #9) cites in full.

### What ported directly (methodology, not numbers)

- **The bespoke-driver pattern itself** -- a dynamic latched comparator has
  no static DC operating point during regeneration (it is a clocked,
  bistable circuit), so offset and regeneration time are inherently
  transient-analysis quantities and noise needs an AC `.noise` analysis on a
  linearized, loop-broken sub-model. This is why `run.py` is a standalone
  driver rather than reusing `sim/run_corners.py` / `sim/monte_carlo.py` (see
  `run.py`'s own module docstring for the full argument) -- generic to any
  dynamic latched comparator, not sky130-sar-adc-specific.
- **`regen`**: single reset->evaluate transient edge per differential-input
  point, sweeping Vindiff and reading the decision (regeneration) time off a
  `|v(outp)-v(outn)| > 0.5*VDD` threshold crossing.
- **`offset`**: a linearized pick-off statistic (differential output at a
  fixed early time after the evaluate edge, well before the latch saturates)
  calibrated to an input-referred gain via a small ideal-device Vindiff
  sweep (zero-intercept least-squares fit), then applied to N Monte Carlo
  draws at a `_mm`-suffixed local-mismatch corner (varying `rndseed`), with
  a same-seed, mismatch-disabled negative control at the plain corner
  expected to reproduce identical results across every draw (stdev == 0) --
  the standard negative-control convention `sim/README.md` already uses for
  every other Monte Carlo record in this repo.
- **`noise`**: break the latch's positive-feedback loop to get a
  well-posed small-signal `.noise` analysis -- the standard "break the loop
  for small-signal analysis" circuit-analysis technique, not specific to
  any topology, and a deliberate **lower bound** on the true
  regeneration-inclusive noise (the latch pair's own regenerative-phase
  noise contribution is excluded by construction -- see the port source's
  own `spec/decision-records/
  DR-004-comparator-topology-and-noise-budget.md` for the full
  derivation). Pre-DR-004 this meant diode-connecting stand-in loads on a
  dynamic input stage's drain nodes with CLK held at VDD (an
  integration-phase proxy); since DR-004 (issue #34) the DUT itself
  carries a continuously-biased preamplifier, and the sub-model is simply
  that REAL static stage re-emitted verbatim (tail + input pair + poly
  loads + OUT1 absorber caps), everything past the preamp outputs omitted
  as the loop break -- no stand-ins, no steady-bias trick, no clocked
  device in the sub-model at all.
- **The negative-control / mismatch-corner statistical convention** itself,
  generic to sky130's `_mm` local-mismatch corners (`AGAUSS()` per-instance
  terms, confirmed present in the installed `sky130.lib.spice` combined
  library and already exercised by this repo's own `sim/mc-smoke/` harness
  self-test, per issue #8).
- **Directory/evidence-record shape** -- `testbench/`, `netlist-snapshots/`,
  `corners/`, `mc-draws/`, `records/`, matching `sim/README.md`.

### What was deliberately NOT ported

- **Any sky130-sar-adc-specific number.** No sigma, offset mean, noise
  budget, or regeneration-time figure from that repo transfers -- this
  repo's own comparator has no schematic yet (see "Placeholder DUT" below),
  so there is nothing yet to compare against, and `spec/porting-plan.md`
  explicitly scopes numeric target-spec bounds as "designed fresh, not
  ported."
- **Any CDAC/SAR-sequencer dependency.** There is none to strip -- the port
  source's own `sim/comparator-decision/` experiment is itself standalone
  (an ideal differential DC/pulse stimulus, no driving CDAC or sequencer
  clock), which is exactly why it was the nearest transferable starting
  point (`spec/porting-plan.md`, "A standalone stimulus").
- **`regen-corners` / `noise-corners`.** The port source's `run.py` also
  ships two full-ratified-PVT-corner-sweep subcommands, added there later in
  response to that repo's own topology-specific reset-integrity bug and its
  own ratified noise-budget spec row. Issue #9's acceptance criteria ask for
  one committed record per experiment at the nominal corner, not a corner
  campaign against a spec that does not exist here yet -- a future issue can
  add a corners sweep once this repo has a real, ratified design to
  characterize across PVT.
- **The reset-integrity `classify()` / `RESET-NOT-HELD` / `WRONG-POLARITY`
  instrumentation** the port source's `regen`/`regen-corners` accumulated in
  response to a specific bug in *its own* pre-fix device set -- not ported
  as such. This repo instead grew its own, differently-shaped
  reset-integrity check under issue #24 (the `reset` sub-command below),
  derived from DR-001 Decision 3's first-principles argument rather than
  transcribed from the port source's instrumentation.

## The DUT

`testbench/comparator_core.spice` is **this repo's own design**, and has
been since issue #24: it is a generated artifact of
[`design/comparator.sch`](../../design/comparator.sch), produced by
`./design/netlist.sh` and carrying a "do not hand-edit" header. See
[`design/README.md`](../../design/README.md) for the topology, the sizing
derivation, and the regeneration command.

Before issue #24 it was a **placeholder** -- ported verbatim from
`2AMLogic/sky130-sar-adc`, so that `run.py`'s driver had something real to
exercise end to end while this repo had no schematic, exactly the role
`sim/harness-corner-smoke/` and `sim/mc-smoke/` play for the PVT/MC harness.
That placeholder is gone from the working tree (it remains in git history),
and with it the last gap issue #3's T1 checklist item 9 named: "every
testbench here exercises a placeholder DUT."

**The records written against the placeholder are still here and are still
correct.** `sim/README.md`'s evidence convention is append-only: a record is
never edited or deleted, and these were not *wrong*, they simply
characterized a different circuit. They are not superseded either --
superseding means replacing a record that made the same claim, and these
made a different one (each says so in its own `Claim` field). They just stop
being the freshest evidence. The `Netlist provenance` field is what tells
the two generations apart:

- `schematic, placeholder (...)` -- the ported placeholder (issue #9).
- `schematic-derived (design/comparator.sch -> ./design/netlist.sh -> ...)`
  -- this repo's own design (issue #24 onward).

**Neither generation substantiates any row of the top-level README's
target-spec table**, because that table is DRAFT and unratified. Records
written since issue #24 do quote the DRAFT rows, but only as the design
intent the sizing pass aimed at -- never as a pass/fail grade.

### Post-layout (extracted) DUT -- `--dut extracted`

Since issue #57 (T1 item 7) there is a **second DUT provenance**: the
parasitics-annotated netlist extracted from the committed
[`layout/comparator.gds`](../../layout/comparator.gds).

```sh
python3 layout/extract_pex.py                  # (re-)extract + rewrite
python3 layout/extract_pex.py --check          # verify the committed copy

SIM_NGSPICE_TIMEOUT_S=900 \
  python3 sim/comparator-decision/run.py regen --dut extracted --record
```

**The extraction is pinned to `klayout-tools==0.6.0` on `klayout==0.30.10`**
-- the same pin `docs/environment-setup.md` records and both
`.github/workflows/t1-signoff.yml` jobs install -- and `extract_pex.py`
*asserts* it rather than merely recording it. That is not provenance hygiene:
measured on this repo's own GDS, the pin and an unreleased `0.6.0+g1828313`
/ klayout `0.30.12` dev build give bit-identical capacitances but total
series resistance 17.52 kΩ vs 14.70 kΩ -- 1.19× overall, up to 2.30× on an
individual net (`CLKT`), 1.55-1.86× on `OUTP1`/`OUTN1`/`VINP`/`VINN`, i.e. on
exactly the nets the post-layout deltas below are attributed to. If your host
`klt` is off-pin, run the script under a throwaway env (the script's error
message prints the exact `uv venv` + `uv pip install` invocation); do not
change host tooling. `extract_pex.py --check` is a CI gate in the
`layout-device-count` job, which installs that pin.

**Parasitic model, and where it is coarse.** The extractor's default is a
single lumped star R per net (its own header in each fragment says so
verbatim: "not a per-segment, distributed RC ladder"). On the *signal* nets
that is a reasonable first-order model. On the **supply nets it is the coarse
default and is expected to be pessimistic**: `GND` carries 6.76 kΩ and `VDD`
2.36 kΩ of lumped star R -- together 52.0% of the block's 17.52 kΩ total
series R -- i.e. 94.7-463.0 Ω per device leg in series with every source/body
tie, where the real drawn supply is a wide low-impedance shape whose
distributed resistance a single star node cannot represent. So the
post-layout degradations below should be read as an **upper bound on the
supply-network contribution**, not a best estimate of it. `klt extract`
offers `--distributed-rc` with `--critical-net` for a per-segment ladder;
re-running the supply nets that way is follow-on work (issue #64), not done
here.

`--dut schematic` is the default and its deck text is **byte-identical** to
what it was before the switch existed, so a post-layout figure and the
schematic-level record it is differenced against come from decks that differ
only in the DUT. That property is what makes the delta attributable to the
layout, and it is pinned by a test
(`sim/tests/test_comparator_decision.py::TestDutProvenance`).

**`regen`, `offset`, `noise` and `kickback` support both provenances.
`reset` and `noise-tran` refuse `--dut extracted`** and say so, rather than
silently falling back to the schematic DUT. Both build their decks by
re-emitting *named* DUT device lines onto substituted nodes, which is not a
well-defined operation on the extracted fragment: a schematic device can
correspond to more than one drawn device (each W=13 input-pair device is two
W=6.5 fingers) and every terminal sits on a per-terminal parasitic star leg
rather than on the node itself, so "re-emit this device somewhere else" also
needs its parasitics re-partitioned. A post-layout record that had quietly
measured the schematic DUT would be worse than no record, so the refusal is
loud. Giving those two a real post-layout deck form is follow-on work
(issue #65).

**Why not `klt pex`?** It is the canonical tool and it is not usable here,
for a reason that is *not* the missing `.include` line that
`testbench/comparator_core.spice` lacks. `klt pex` re-runs **`klt sim`
request JSON** testbenches, whose `measurements[]` entries are verbatim
`.meas` cards graded against limits. None of this bench's five measurements
is expressible that way -- `regen` locates a threshold crossing by a
caller-side rule (sign-corrected per point, with "unresolved" a first-class
outcome), `offset` divides a Monte Carlo pick-off statistic by a gain fitted
from a companion calibration sweep, `noise` analyses a loop-broken sub-model
that does not exist as a file until the harness assembles it, and so on.
Adding an `.include` line would let `klt pex` *rewrite* a file it still could
not *drive*. So this takes the other path issue #57 sanctions: `klt extract
--parasitics` (the same extraction engine `klt pex` calls) plus a documented,
committed swap -- the same choice `2AMLogic/gf180-sar-adc`'s
comparator-regeneration bench made. The full derivation, and what the rewrite
does and does not touch, is in
[`layout/extract_pex.py`](../../layout/extract_pex.py)'s module docstring.
The grading consequence is real and is filed as friction rather than hidden:
`klt signoff` accepts **only** a `klt pex` envelope for T1 item 7, so this
evidence cannot be cited there
([`2AMLogic/klayout-tools#2478`](https://github.com/2AMLogic/klayout-tools/issues/2478)).

The extracted decks need a longer per-deck ngspice budget than the 120 s
default -- hence `SIM_NGSPICE_TIMEOUT_S=900` above. That is a wall-clock
budget, not a numerical setting: no deck text, solver option or tolerance
differs from the schematic-side runs.

## Sub-commands

`regen`, `offset` and `noise` are the ported methodology (above). `reset`
was added by issue #24 and is this repo's own:

```sh
python3 sim/comparator-decision/run.py reset --record
```

It is a reset-integrity **negative control** with a matching **positive
control**. DR-001 Decision 3 derives from first principles that a
StrongARM-class latch whose NMOS sources sit at `GND` during reset leaves
the feedback loop live, making the reset state an unstable equilibrium that
any asymmetry can amplify before the real decision edge -- and cites
same-PDK prior art where precisely that defect was found empirically, after
the fact, failing at 3 of 9 PVT corners. DR-001 states the correct reset
scheme up front specifically so this repo checks for it before, rather than
after, being bitten. `reset` is that check:

- It starts the transient from a deliberately **wrong** state -- outputs
  pinned at opposite rails, latch internal nodes at GND (the preamp's
  static nodes start near their own DC bias) -- with reset asserted and
  no input applied, and requires the design to reject that asymmetry rather
  than amplify it.
- Its primary criterion is DR-001 Decision 3's own mechanism measured
  directly, carried by the DR-004 latch stage onto its (PMOS) cross-coupled
  pair: every latch PMOS's `|Vgs|` must be ~0 during reset (the precharged
  outputs ARE the pair's gates).
- It runs the same check against a **`GND`-tied counterfactual** (the
  latch steering pair's sources moved from the floated `TAIL2` node to
  GND, nothing else changed -- the same counterfactual shape DR-001
  Decision 3 established for its own latch's source-precharge scheme) and
  requires that variant to FAIL. A negative control that cannot be shown
  to fail on the defect it screens for is not evidence that the defect is
  absent.

One caveat is written into the record itself and worth repeating: the
supply-current criterion is not "zero current". Since DR-004 the design
carries a continuously-biased preamplifier whose static current
(~42-68 uA across the five reset-matrix corners) flows during reset too,
on top of a small self-limiting off-state path. That floor is a property
of the topology class, not a defect; the positive control (~0.9-1.1 mA)
is what gives the criterion its scale.

`kickback` was added by issue #26 and is this repo's own -- an ORIGINAL
experiment, since no same-PDK standalone kickback prior art exists to port
(`spec/porting-plan.md`'s "Next steps" item 4):

```sh
python3 sim/comparator-decision/run.py kickback --record
```

It measures the voltage disturbance the comparator's own regeneration
injects back onto its input nodes at the reset->evaluate transition, through
the input-pair devices' gate-drain parasitic capacitance and the
common-mode step at `TAIL`. That disturbance is only visible to a real
driving stage -- an ideal (zero-impedance) voltage source absorbs any
injected charge with no voltage deviation -- which is exactly why the
top-level README's target-spec Kickback row states its bound "into a 1 kOhm
source impedance": the source impedance is what turns injected charge into
a voltage disturbance at all.

- `VINP`/`VINN` are biased at the existing `VCM` through an explicit 1 kOhm
  series resistor each (the `loaded` variant), driven by a static 50 mV
  differential step sized to guarantee a clean decision (matching `regen`'s
  largest tested overdrive and the target-spec table's own "Decision time
  vs. overdrive" 50 mV reference point), then the same single
  reset->evaluate edge `regen`/`reset` already use.
- The peak absolute deviation of `v(VINP)`/`v(VINN)` from each node's own
  settled pre-edge value, over the whole window, is the disturbance
  reported.
- A **control** variant (`ideal`) drives `VINP`/`VINN` directly from the
  ideal source (zero source impedance) -- it must collapse to
  (numerically) zero by construction, the same "must be able to fail" bar
  `reset`'s own positive control states: a `loaded` reading that cannot be
  told apart from a broken measurement pipeline is not evidence of
  anything.

This is a single nominal-corner (`tt`/27C) record, per issue #9's original
scope note (one nominal-corner record per experiment, not a corner
campaign) -- a full-corner sweep remains open work.

`noise-tran` was added by issue #41 and is this repo's own -- the
**regeneration-inclusive** input-referred noise measurement the `noise`
sub-command's loop-broken AC sub-model deliberately is not:

```sh
python3 sim/comparator-decision/run.py noise-tran --record --n 128
```

ngspice-46 has no device-noise-enabled transient analysis (`trnoise()`
exists only on independent sources), so the measurement injects
equivalent noise sources into the FULL committed fragment and measures
the decision-relevant dispersion they produce: per-side TRNOISE sources
at the comparator inputs (carrying the AC `noise` sub-command's preamp
input-referred rms) and in series with the steering gates (carrying a
new steering+tail AC sub-model's gate-referred rms, biased at the
preamp's own static output common mode), all propagated through the real
clocked evaluate trajectory. Two statistics come out: a pick-off Monte
Carlo at `Vindiff=0` (the primary figure, with a bootstrap 95% CI) and a
pair-symmetric decision-transition cross-check at +/-{0.75, 1.5} sigma
(whose agreement with the pick-off figure is the evidence that the
regenerative phase adds no material noise term beyond the injected
device noise). Injection rms is calibrated empirically against this
ngspice build's TRNOISE semantics (std ~= 0.86 x na measured; the record
states achieved-vs-target directly), and the update interval is 0.37 ns
-- NOT the 0.5 ns Nyquist interval, whose update grid coincides exactly
with the reset->evaluate edge and collapses the transient solver's
timestep (observed on ngspice-46; a per-deck retry at a perturbed
interval covers other pathological coincidences). Modeling boundaries
are stated in each record: the cross-coupled PMOS pair's noise during
exponential separation (divided by the growing regenerative gain) and
the reset PMOS (off in evaluate) are the residual omissions.

## Committed records

Records against **this repo's own design** (`design/comparator.sch`), on the
pinned toolchain (`sim/toolchain.json`) and PDK (`sim/pdk.json`). DRAFT
target-spec rows are quoted for orientation only -- the table is unratified,
so nothing below is a pass/fail grade.

- `reset` -- `records/20260916-004042-52eb9b2.md`: reset-integrity negative
  control + positive control, 5 PVT points each (tt/27C, ss/-40C, ss/125C,
  ff/-40C, ff/125C). **As-drawn holds reset at all 5**: the deliberate
  opposite-rails initial condition collapses to exactly 0 mV of output
  difference, both outputs precharge to 1.8000 V, and the latch NMOS pair's
  Vgs stays at most 0.23 mV -- DR-001 Decision 3's "Vgs = 0, loop gain
  exactly zero" mechanism, measured. **The GND-tied positive control breaks
  reset at all 5**, on all four criteria at once: outputs separate to
  ~1.65-1.74 V (i.e. toward opposite rails, with no input applied -- the
  same failure signature the prior art DR-001 cites observed), latch Vgs sits
  at the full 1800 mV, and supply current rises to 300-390 uA against the
  as-drawn leakage floor of 0.13-0.25 uA. That ~1500x separation is what
  makes the as-drawn result meaningful rather than merely unfalsified.
- `regen` (tt/27C) -- `records/20260916-000727-52eb9b2.md`: 8/8 Vindiff
  points resolved; 0.6775 ns at 50 mV rising monotonically to 1.6825 ns at
  0.5 mV, the expected `ln(1/Vindiff)` positive-feedback-latch shape. The
  -10 mV point reproduces the +10 mV time to the sample (1.0225 ns), i.e.
  the decision is polarity-symmetric.
- `regen` (ss/-40C) -- `records/20260916-001345-52eb9b2.md`: the slow/cold
  corner DR-001's headroom probe flagged, and the corner the DRAFT
  "Decision time vs. overdrive" row already expected to bind. 8/8 points
  still resolve. At 50 mV the penalty is almost nil (0.6875 ns vs
  0.6775 ns); it grows as the input shrinks and regeneration -- rather than
  the input pair -- dominates the decision (2.5575 ns vs 1.6825 ns at
  0.5 mV). Read together with DR-001 Amendment 1's operating-point evidence,
  this is the transient half of the case that the flagged headroom deficit
  is closed, not merely accounted for.
- `offset` -- `records/20260916-003531-52eb9b2.md`: N=16 draws at `tt_mm`,
  input-referred offset mean -0.57 mV / stdev **2.02 mV** (3 sigma =
  6.06 mV). Same-seed negative control at plain `tt` reproduces stdev == 0
  exactly. Note the sample size: SE(s)/s ~= 18% at N=16, so the stdev is
  known to roughly +/-0.4 mV -- adequate for distribution shape, not for a
  yield-fraction claim.
- `noise` -- `records/20260916-001416-52eb9b2.md`: single-ended
  input-referred noise 0.3158 mV rms, differential estimate 0.4466 mV rms.
  Still the loop-broken lower bound by construction (it excludes the
  regenerative phase) -- see the methodology note above.
- `kickback` (tt/27C) -- `records/20260916-060139-f1eb978.md`: first-ever
  measurement, both variants PASS. `loaded` (1 kOhm source impedance, 50 mV
  overdrive) peaks at **144.60 mV** on `VINP` / 131.07 mV on `VINN`; the
  `ideal` (zero-impedance) control collapses to exactly 0.0000 mV on both,
  confirming the deck is isolating a genuine source-impedance-dependent
  effect rather than a measurement artifact. The mechanism is Miller
  coupling from the internal precharged nodes (`DIP`/`DIN`) through the
  input pair's own gate-drain capacitance at the reset->evaluate edge.

For orientation against the **DRAFT, unratified** target-spec table (not a
grade -- that table sets no binding bound until ratified):

| DRAFT row | Target | Stretch | Measured here |
|---|---|---|---|
| Offset sigma (3 sigma, input-referred) | <= 15 mV | <= 8 mV | 6.06 mV @ `tt_mm`/27C, N=16 |
| Input-referred noise (differential) | <= 1.0 mV rms | <= 0.6 mV rms | 0.4466 mV rms @ tt/27C |
| Decision time @ 50 mV overdrive | <= 1.5 ns | <= 0.8 ns | 0.6775 ns @ tt/27C; 0.6875 ns @ ss/-40C |
| Kickback | <= 5 mV | <= 2 mV | 144.60 mV @ tt/27C, 1 kOhm source, 50 mV overdrive (well above both bounds) |
| Supply / power | <= 50 uW | <= 20 uW | **not measured** -- no clock-rate assumption ratified |

Only one row now has no measurement at all, and every row that does is a
single-corner (or five-corner, for `reset`) result against a table that has
not been ratified. Nothing here closes the gap issue #3's T1 item 5 names:
a full PVT corner campaign against a *ratified* spec -- and the kickback
figure above is new information that the DRAFT bound itself may need
revisiting once ratification is considered, not a design defect this
issue's scope asks to fix.

### DR-004 records (issue #34 -- static preamplifier + StrongARM latch)

The topology-class change superseding DR-001's no-preamp scoping (see
`spec/decision-records/DR-004-comparator-preamp-supersession.md`) produced
a fresh record set at the new sizing, all against the DUT fragment as of
`e084b55` + the DR-004 device set:

- `offset` -- `records/20260922-065300-e084b55.md`: N=16 @ `tt_mm`/27C,
  seed 1, input-referred offset stdev **1.7857 mV** (3-sigma = 5.36 mV);
  same-seed mismatch-disabled negative control stdev == 0 exactly. Pick-off
  re-anchored 1.0 -> 0.65 ns for the preamp design's faster separation
  (calibration line 1 mV -> 68.1 mV ... 10 mV -> 639.3 mV, 6% compression).
- `noise` -- `records/20260922-065534-e084b55.md`: input-referred noise
  **0.5704 mV rms differential** at `tt`/27C, on the re-derived REAL-static
  preamp sub-model.
- `reset` -- `records/20260922-070024-e084b55.md`: **5/5 as-drawn corners
  hold reset, 5/5 gnd-tied controls break it** (the counterfactual moved
  onto the steering pair; the current bound re-derived around the preamp's
  static-current floor).
- `kickback` -- `records/20260922-070119-e084b55.md` (`tt`/27C: **1.8902
  mV**), `records/20260922-070212-e084b55.md` (`ss`/-40C: **1.8605 mV**),
  `records/20260922-070307-e084b55.md` (`ff`/125C: **1.7677 mV**) -- all
  three PVT anchors clear BOTH the ratified 5 mV target and the 2 mV
  stretch bound, with ideal controls collapsing to 0.0000 mV everywhere.
- `regen` -- `records/20260922-070800-e084b55.md` (`tt`/27C: 8/8 resolved,
  **0.4025 ns @ 50 mV**, 1.1375 ns @ 0.5 mV) and
  `records/20260922-071313-e084b55.md` (`ss`/-40C: 7/8 -- the 0.5 mV point
  is UNRESOLVED; a dedicated 400 ns probe confirms it never regenerates at
  that corner, recorded as a DR-004 consequence and open item, while the
  50 mV point resolves in 0.3575 ns).

### DR-005 campaign records (issue #41 -- full-corner Monte Carlo + PVT)

All at the same DR-004 topology (netlist-identical, campaign commit
`e23c509`), same seed-1 methodology, same pinning:

- `offset` four-corner mismatch sweep -- `records/20260922-173622-e23c509.md`
  (`ss_mm`: **1.8244 mV**), `.../20260922-174326-e23c509.md` (`ff_mm`:
  **1.5954 mV**), `.../20260922-174831-e23c509.md` (`sf_mm`: **1.6706
  mV**), `.../20260922-175152-e23c509.md` (`fs_mm`: **1.8218 mV**) --
  N=16/seed-1/27C each, every same-seed negative control stdev == 0
  exactly. Corner ranking is inside the N=16 relative SE; `ss_mm` is
  nominally binding.
- `offset` N=200 campaigns -- `tt_mm` and the nominally binding `ss_mm`,
  stated 95% CI on the stdev, records named in DR-005.
- `regen` PVT completion -- `records/20260922-175252-e23c509.md`
  (`ff`/125C: **0.4975 ns** @ 50 mV, 8/8), `.../20260922-175425-e23c509.md`
  (`sf`/-40C: **0.3475 ns**, 8/8), `.../20260922-175554-e23c509.md`
  (`sf`/125C: **0.4725 ns**, 8/8), `.../20260922-175734-e23c509.md`
  (`fs`/-40C: **0.3725 ns**, 8/8), `.../20260922-175918-e23c509.md`
  (`fs`/125C: **0.5375 ns**, 8/8) -- the worst point of the whole
  seven-corner set clears the stretch bound with 1.49x margin, which is
  what ratifies the Decision-time row (DR-005).
- `kickback` skew corners -- `records/20260922-180026-e23c509.md`
  (`sf`/-40C: **2.0208 mV**), `.../20260922-180157-e23c509.md`
  (`sf`/125C: **1.7837 mV**), `.../20260922-180319-e23c509.md`
  (`fs`/-40C: **1.8408 mV**), `.../20260922-180425-e23c509.md`
  (`fs`/125C: **1.6091 mV**) -- every `ideal` control collapses to
  0.0000 mV. Note `sf`/-40C breaches the 2 mV stretch figure by 1%
  (target still cleared 2.5x); recorded, not legislated (DR-005).
- `noise-tran` regeneration-inclusive noise --
  `records/20260922-192722-e23c509.md` (`tt`/27C: **0.1362 mV**, 95% CI
  [0.1216, 0.1493], decision cross-check 0.1342 mV -- agrees),
  `records/20260922-205857-ebea4e2.md` (`ss`/-40C: **0.1213 mV**, CI
  [0.1084, 0.1335]; cross-check honestly not measurable at this corner --
  the sigma-scaled overdrives sit below the resolvable-overdrive floor
  DR-004 recorded, so noise does not bound decisions there),
  `records/20260923-010427-ebea4e2.md` (`ff`/125C: **0.1754 mV**, CI
  [0.1594, 0.1905], cross-check 0.1515 mV -- agrees).

### Post-layout records (issue #57 -- T1 item 7, `--dut extracted`)

The first records against a DUT that is **not** `design/comparator.sch`'s
netlist: the parasitics-annotated extraction of `layout/comparator.gds` (see
[Post-layout (extracted) DUT](#post-layout-extracted-dut----dut-extracted)).
Each names its schematic-level counterpart record and the numeric delta in
its own `## Post-layout delta` section; the pairs below are the same anchors
DR-004/DR-005 used, so nothing but the DUT differs.

| Sub-command | Corner | Schematic | Post-layout | Ratio | Record |
|---|---|---|---|---|---|
| `regen` @ 50 mV | `tt`/27C | 0.4025 ns | **0.5325 ns** | 1.323x | `records/20260925-085247-4694692.md` |
| `regen` @ 50 mV | `ss`/-40C | 0.3575 ns | **0.4725 ns** | 1.322x | `records/20260925-093624-4694692.md` |
| `kickback` | `tt`/27C | 1.8902 mV | **2.6767 mV** | 1.416x | `records/20260925-094700-4694692.md` |
| `offset` stdev | `tt_mm`/27C | 1.7857 mV | **2.4446 mV** | 1.369x | `records/20260925-112809-4694692.md` |
| `noise` (AC) | `tt`/27C | 0.5704 mV rms | **0.6576 mV rms** | 1.153x | `records/20260925-112827-4694692.md` |

**These five supersede an earlier post-layout set** (`20260925-065137-87f0013`
… `20260925-072817-2e2ef84`, each named in the corresponding new record's
`Supersedes` field). The superseded set measured the same DUT topology but
was extracted on an **off-pin** klt/klayout build (`0.6.0+g1828313bdf02` on
klayout `0.30.12`) whose per-net series resistances differ from the pinned
build's by up to 2.30x -- see "Post-layout (extracted) DUT" above. The older
records stay in place, unedited, per `sim/README.md`'s append-only rule; they
are **not** the figures any row cites.

Every ratified row still clears its **target** bound. Two now sit over their
**stretch** figures, recorded rather than legislated away (`CLAUDE.md`:
agents do not relax the ratified spec to make results pass):

- **Kickback 2.6767 mV** against the <= 2 mV stretch bound (<= 5 mV target
  cleared 1.87x). This is precisely the row DR-002/DR-005 named as the
  standing layout-stage risk: its governing mechanism is input-node parasitic
  capacitance, the schematic-level stretch margin was already only 1.06-1.13x,
  and a 1 % breach was already recorded at `sf`/-40C. The layout moves it the
  predicted way. The `ideal` control still collapses to exactly 0.0000 mV.
- **Input-referred noise 0.6576 mV rms** against the <= 0.6 mV stretch bound
  (<= 1.0 mV target cleared 1.52x), still the loop-broken lower bound.

Offset 3-sigma is 7.3338 mV against the 8 mV stretch bound -- cleared, with
1.09x left. Decision time clears both bounds at both anchors.

Three post-layout facts beyond the deltas, each read off a committed record:

- **The pick-off gain falls 64.4571 -> 30.4600 V/V (2.12x)**, which is the
  common cause behind offset sigma, noise and decision time all degrading
  together: parasitic loading on the long `OUTP1`/`OUTN1` nets the floorplan
  deliberately traded for short input routes, plus the disclosed
  drawn-vs-schematic load-resistor width delta (PR #55; ~19 % less load R).
  See [`layout/README.md`](../../layout/README.md)'s "Floorplan against the
  input-node parasitic-capacitance risk", which predicted this axis would pay.
- **A systematic, layout-induced input offset now exists.** The
  mismatch-disabled negative control's mean is 0.0000 mV on the schematic
  fragment (symmetric by construction) and **0.6547 mV** post-layout, its
  stdev still exactly 0. First measurement of this term on this block -- the
  schematic bench had nothing to measure, so it is new information, not a
  regression against a prior figure.
- **The sub-20 mV decision polarity is asymmetric.** `tt`/27C resolves 6/8
  sweep points (+1 mV and +0.5 mV no longer do; the schematic anchor was 8/8)
  and `ss`/-40C resolves 3/8 (+2 through +10 mV do not, while -10 mV resolves
  in 2.3725 ns). The sweeps *bracket* the asymmetry rather than measuring it:
  `regen`'s criterion is sign-corrected, so a wrong-polarity decision and a
  non-decision both read `UNRESOLVED` and this evidence cannot tell them
  apart. Nor does the 0.6547 mV pick-off-referred systematic term above
  explain the `ss`/-40C magnitude on its own. Open question, tracked as
  issue #66;
  the spec rows are stated at 50 mV overdrive, which resolves at both anchors.

Scope of this pass, stated so the gaps are not mistaken for coverage: two
corners, four sub-commands. `reset` and `noise-tran` have no post-layout deck
form yet (above), so the regeneration-inclusive noise figure (0.1362 mV
decision-referred at `tt`/27C) has **no** post-layout counterpart. The five
remaining graded PVT corners are unmeasured post-layout (issue #64). Both are
follow-on work, not claims made here.

Earlier records (`20260916-*`, `20260921-*`) characterize the DR-001/
DR-003 single-tail design, and `20260909-*` the **ported placeholder
DUT**; they remain, unedited, as append-only evidence. See [The DUT](#the-dut)
for why they remain, unedited.
