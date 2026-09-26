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

**All six sub-commands support both provenances.** Four did from issue #57;
`reset` and `noise-tran` refused `--dut extracted` until issue #65, because
both build their decks by re-emitting *named* DUT device lines onto
substituted nodes and that is not a well-defined operation on the extracted
fragment until three questions are answered. Refusing was the right first
answer — a post-layout record that had quietly measured the schematic DUT
would be worse than no record — and issue #65 answers them rather than
guessing. The rules live next to the code that implements them (the
POST-LAYOUT DECK SURGERY note in
[`run.py`](run.py)) and are pinned by
`sim/tests/test_comparator_decision.py::TestPostLayoutTerminalMoves`:

1. **Which device, when the layout drew one schematic device as several.**
   Naming a schematic device names **every** drawn instance of it
   (`XM_PINP__a`, `XM_PINP__b`, …) and they are transformed together — one
   device that happens to be drawn in pieces. Not exercised on this layout:
   the steering pair is drawn unsplit (one W=8 device each), and the split
   devices are the W=13 input pair, which neither sub-command moves. Both
   records say so explicitly rather than leaving it implicit.
2. **Where to cut, when no terminal sits on the logical node.** Every
   extracted terminal hangs off its own star leg (`TAIL2__t2`) tied to the
   net hub through that terminal's share of the net's series R. **The star
   leg travels with the terminal**: moving a terminal re-points *that leg
   resistor's hub end* at the new net and never edits the device line. So
   nothing is stranded on a one-connection node, no extracted resistance is
   deleted, and none is re-attributed to a net it was not extracted for. The
   alternatives both lose information — dropping the leg deletes that
   terminal's resistance, keeping it in place strands it. What the rule does
   *not* claim is that this is the resistance a re-routed layout would have
   had: it is a netlist-level counterfactual, exactly as the schematic-level
   one is.
3. **Which side of the leg a series source goes on.** This one has a
   determinate answer, not a preference: a star-leg node carries exactly one
   device terminal and exactly one star resistor (the deck builder *asserts*
   this rather than assuming it), so the leg resistor and an inserted ideal
   source are two-terminal elements in series and the two placements are the
   same network. The deck inserts on the hub side, which is the same single
   mechanism rule 2 uses and makes the source line (`Vstp GST_P OUTP1`)
   textually identical in both provenances.

In practice each transformation changes **two tokens** of the committed
extracted fragment and nothing else — `reset --dut extracted`'s `gnd-tied`
control re-points `R_TAIL2__t1`/`R_TAIL2__t2` from `TAIL2` to `GND`;
`noise-tran --dut extracted` re-points `R_OUTP1__t4`/`R_OUTN1__t4` onto
`GST_P`/`GST_N`. `noise-tran`'s stage-2 AC anchor uses a third committed
fragment, `layout/comparator.pex-latch.spice` (the **latch front-end
partition**: steering pair + latch tail with their extracted parasitics,
selected by connectivity as "every device on the `TAIL2` node"), the
counterpart of the preamp partition the AC `noise` sub-command already used.

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

### Dispatch decision (issue #64)

Issue #64's multi-corner post-layout campaign had to answer a question #57
deferred: **where does a genuine multi-corner post-layout run execute?** The
answer, recorded here because it governs what the campaign could afford:
**serially, one ngspice process at a time, on the dispatch host** -- *not* on
the `klt sim` batch fleet.

**Why not the batch fleet.** The fleet is reached by submitting a `klt sim`
**request JSON** with a `corners` or `monte_carlo` block; the backend then
fans that request out. `run.py` is not such a request and cannot become one
cheaply -- it drives `ngspice` directly because none of this bench's five
measurements is expressible as the verbatim `.meas` cards a `klt sim` request
grades against limits. That is the *same* structural gap, for the *same*
reason, that makes `klt pex` unusable for T1 item 7 (see "Why not `klt pex`?"
above), and it is already filed as
[`2AMLogic/klayout-tools#2478`](https://github.com/2AMLogic/klayout-tools/issues/2478).
Routing this campaign to the fleet therefore means first re-expressing the
bench as a `klt sim` request -- which is not a dispatch detail, it is the
tool gap itself, and it is out of scope for a measurement issue. No new
friction issue was filed: #2478 already describes this gap exactly, and #64
encountered it in the same form rather than a new one.

**Why serial was affordable anyway.** The estimate #64 was scoped against
(~20 min per `regen` sweep, ~25 min per `offset` N=16 run, "well over a
host-day" for a 4x7 grid) held for `regen` and `offset` but was an order of
magnitude pessimistic for `kickback`, which is the campaign's cheapest and
most informative sub-command (2 decks per corner). Measured wall clock for
this campaign, serially, on the shared dispatch host:

| Sub-command | Decks/corner | Measured wall clock per corner |
|---|---|---|
| `kickback` | 2 | **~30-40 s** (first corner 7.6 min, queued behind a sibling sweep's ngspice) |
| `regen` | 8 | **~20 min** |
| `offset` | ~37 | **19-64 min** (issue #80's four corners, serially; #57 estimated ~25) |

So the six remaining `kickback` corners cost ~14 min in total and the five
remaining `regen` corners ~100 min -- both inside one session, with no
parallel grid and no fleet submission. `offset` and `noise` were the
deliberately-skipped part of *this* campaign; see "Deliberately skipped, and
why" below. Issue #80 later ran `offset`'s four remaining corners under the
same rule, at ~2.6 h total. Its per-corner spread is worth noting for future
budgeting: the same 37-deck run took **19 min** on a quiet host and **64
min** at a 15-min load average of 14.5 on these 8 vCPUs. Per-corner wall
clock on this host is set by sibling-sweep contention at least as much as by
the corner, so a serial-campaign estimate should carry a range, not a point.

**The host rule this respects.** This is a shared 8-vCPU dispatch worker, not
a simulation box, and other sweeps run concurrently on it (one sibling sweep's
ngspice is visible in the `kickback` first-corner time above). The campaign
therefore ran `--jobs 1` *and* one corner at a time -- never a hand-launched
parallel `ngspice` grid. A re-run should do the same:

```sh
# One corner, one process. Not a loop with `&`, `xargs -P` or `parallel`.
SIM_NGSPICE_TIMEOUT_S=900 python3 sim/comparator-decision/run.py \
    kickback --corner sf --temp -40 --dut extracted --jobs 1 --record
```

**Assert the provenance you asked for.** A `--dut extracted` run that
silently measured the *schematic* netlist would produce a record that looks
post-layout and is not. `run.py` writes the provenance into every record, so
a campaign script can and should check it before trusting a result:

```sh
grep -q "POST-LAYOUT / EXTRACTED" "$newest_record" || exit 9
```

This is not hypothetical -- during #64 a first campaign launch omitted
`--dut extracted` entirely and produced six records whose figures reproduced
the schematic baselines exactly. They were caught by that grep, discarded
before any commit, and the corners re-run.

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

**The aggregated view across all five target-spec rows is
[`sim/characterization-report.md`](../characterization-report.md)** (issue #86,
T1 item 8): every row's ratification status and bounds, its measured figure at
every condition that has one -- schematic and post-layout, across the seven
graded PVT corners with the schematic->post-layout ratio per row -- and the
record below each figure rests on, in one place. It adds no measurement; every
number in it is copied from a record in this directory. It is the evidence
`manifests/sky130-comparator.json` cites for T1 item 8, through a `"kind":
"generic"` envelope whose freshness is re-checked live by
`scripts/characterization-envelope.py` -- so editing a record the report
cites, without re-pinning, makes that item grade `unmet`. What that `met` row
does and does not establish (in particular: it asserts aggregation and
currency, **not** that any bound is met) is stated in
[`manifests/README.md`](../../manifests/README.md) -> "Item 8 -- the
characterization report".

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
corners, four sub-commands. `reset` and `noise-tran` had no post-layout deck
form when this pass landed, so the regeneration-inclusive noise figure
(0.1362 mV decision-referred at `tt`/27C) had **no** post-layout counterpart;
**issue #65 has since closed that** -- see "Post-layout records (issue #65)"
below. The five remaining graded PVT corners were unmeasured post-layout when
this pass landed; **issue #64 has since closed that gap for `kickback` and
`regen`** -- see the next section for the completed corner set and for which
sub-commands were deliberately left at one corner.

### Post-layout records (issue #65 -- the last two sub-commands)

`reset` and `noise-tran` had no post-layout deck form until issue #65 decided
the three star-leg / split-device rules stated under
[Post-layout (extracted) DUT](#post-layout-extracted-dut----dut-extracted)
above. They use the same deck template, the same corners and the same
`## Post-layout delta` format as the five records above.

**`reset` -- `records/20260925-165718-8ea399d.md`.** The DR-001 Decision 3
reset-integrity screen, run against layout parasitics for the first time.
Both controls survive: **5/5 corners hold reset as-drawn** (`tt`/27C,
`ss`/-40C, `ss`/125C, `ff`/-40C, `ff`/125C -- the same five the
schematic-level counterpart `records/20260922-070024-e084b55.md` used) and
**5/5 positive-control corners still BREAK it** on all four criteria. The
second half is the load-bearing one: a negative control whose paired positive
control cannot be shown to fail is not evidence, so the port had to preserve
the control's *sensitivity*, not just the screen's verdict. The one genuinely
continuous column keeps its separation -- worst \|I(VDD)\| over the settle
window is 4.789e-05…6.642e-05 A as-drawn (schematic-level
4.228e-05…6.756e-05 A) against 7.856e-04…8.306e-04 A for the GND-tied control
(schematic-level 8.376e-04…1.056e-03 A). There is no scalar delta table
because `reset` is a four-criterion pass/fail screen, not a measurement.

**`noise-tran` -- `records/20260925-214740-81f594b.md`** (`tt`/27C).

| Sub-command | Corner | Schematic | Post-layout | Ratio | Record |
|---|---|---|---|---|---|
| `noise-tran` (decision-referred) | `tt`/27C | 0.1362 mV | **0.1448 mV** | 1.063x | `records/20260925-214740-81f594b.md` |

Two things about this row must be read together, and the record says both on
its own face:

- **The sample size is smaller than its counterpart's, deliberately**: N=64
  pick-off seeds and 16 seeds/sign/decision point, against
  `records/20260922-192722-e23c509.md`'s N=128 and 64. The extracted decks are
  several times slower than the schematic ones, and the counterpart's
  (128 + 256) = 384 noise-seeded transients do not fit a shared dispatch host
  held to two concurrent `ngspice` processes.
- **The ratio is INSIDE the confidence interval.** The post-layout 95% CI is
  [0.1224, 0.1641] mV and the schematic figure (0.1362 mV) sits within it. So
  this record establishes the post-layout figure *and its uncertainty*; it does
  **not** establish that this quantity moved between schematic and layout.
  That is a weaker statement than the other post-layout rows make, and it is
  stated rather than rounded away.

**What this does and does not do for DR-006.** DR-006 re-opened this row's
*compliance basis* and named the evidence that would close it: a
regeneration-inclusive post-layout measurement **at `fs`/125 °C**, the corner
that binds the row. This record supplies the *capability* DR-006 said issue
#65 owned, and a first figure at `tt`/27 °C -- not the closing measurement.
DR-006 stays open, and the run that would close it is now unblocked rather
than impossible. **Issue #83 has since made that run** -- see
"[Post-layout `noise-tran` at `fs`/125C -- DR-006's closure condition (issue
#83)](#post-layout-noise-tran-at-fs125c----dr-006s-closure-condition-issue-83)"
below. The paragraph above is left as written because it was true of *this*
record; what changed is the corner that was missing, not anything about the
`tt`/27 °C figure.

**The decision-transition cross-check is degenerate here, for a different
reason than at schematic-level `ss`/-40C, and the difference matters.** All 64
decision runs *resolved* (0 unresolved) and all 64 decided the **same way** at
**both** signs of the overdrive, so `p+ = p-` exactly. That is not the
resolvable-overdrive floor the `ss`/-40C record hit; it says a
**deterministic** term larger than the +/-0.109 and +/-0.217 mV sigma-scaled
overdrives is setting the outcome. The obvious candidate is already measured:
the post-layout `offset` record's mismatch-disabled negative control has a
**0.6547 mV** input-referred systematic mean (zero by construction on the
symmetric schematic fragment), 3-6x these overdrives. This is therefore
independent evidence for the sub-20 mV polarity asymmetry issue #66 tracks, at
a far smaller overdrive than the `regen` sweep probes. `run.py` derives that
explanation from the counts (`degenerate_cross_check_reason()`) instead of
asserting a canned one, so a record can no longer name the wrong cause.

### Post-layout `noise-tran` at `fs`/125C -- DR-006's closure condition (issue #83)

`records/20260926-055806-3034c41.md`. This is the one run DR-006 named as the
evidence that would re-close the Input-referred noise row's compliance basis:
regeneration-inclusive, extracted netlist, **at `fs`/125C** -- the corner where
the AC lower bound left only 1.06x target margin.

| Quantity | Value |
|---|---|
| Regeneration-inclusive input-referred sigma (pick-off MC, N=32) | **0.2540 mV rms differential** |
| 95% CI | [0.1961, 0.3009] mV |
| vs. ratified `<= 1.0 mV` **target** | **3.94x** margin (3.32x at the CI's upper bound) |
| vs. `<= 0.6 mV` stretch figure | 2.36x (1.99x at the CI's upper bound) -- but see below |
| AC loop-broken **lower bound**, same corner (unchanged) | 0.9423 mV rms |
| Decision-transition cross-check | degenerate, all-one-way (16/16 resolved) |

**It closes DR-006's target-bound basis, and the amendment says so**
([DR-006 Amendment 1](../../spec/decision-records/DR-006-post-layout-noise-headroom-reopened.md)).
The closure is stated two ways on purpose, so it does not rest on one
arithmetic:

- **Directly** (the correct comparison): 0.2540 mV rms differential against
  `<= 1.0 mV` is 3.94x, 3.32x at the CI's upper bound. This figure carries no
  excluded-regeneration caveat -- it *is* the regeneration-inclusive number.
- **Under a deliberately indefensible double-count**: add the *entire*
  measured figure in quadrature on top of the same corner's 0.9423 mV AC lower
  bound -- which double-counts, because both are dominated by the same preamp
  input-referred source (0.6663 mV rms/side here) and are two estimates of one
  quantity, not two separable terms. Even then
  `sqrt(0.9423^2 + 0.2540^2) = 0.9759 mV rms`, still inside the target at
  1.025x (0.9892 mV / 1.011x at the CI's upper bound).

DR-006's own 0.335 mV rms quadrature allowance (`sqrt(1.0^2 - 0.9423^2)`) is
not exceeded either: 0.2540 mV is 0.76x of it.

**What it does NOT do, stated so the closure is not over-read:**

- **The `<= 0.6 mV` stretch figure stays recorded as breached at four of seven
  corners on the AC basis.** The transient basis clears it but had only 2 of 7
  corners when this record was written (4 of 7 since issue #89, which does not
  change the disposition) and the two bases disagree; per `CLAUDE.md` the breach
  record stands rather than being erased by a different method's number. DR-006
  Decision 4 is unchanged.
- **Statements that cite the AC lower-bound figure still carry the 1.06x
  qualifier.** That figure is unchanged. What changed is that it is no longer
  the row's *only* basis at this corner.
- **Five graded corners remain unmeasured post-layout** for this sub-command as
  of this record. Issue #89 has since run two of them (`ss`/-40C, `ff`/125C),
  leaving three.

**Sample size, and how it is handled.** N=32 pick-off seeds and 4
seeds/sign/decision point -- smaller than the `tt`/27C post-layout record's 64
and 16 -- both stated on the record's own face, with the measured reason. Two
host costs, neither previously recorded here, set it:

- **This dispatch host budgets each agent a one-core cgroup CPU quota**
  (`cpu.max 100000 100000` on the agent's systemd scope). So `--jobs 2` buys
  **no** parallel throughput for a campaign like this one -- a single deck
  already saturates ~93% of the quota -- and the run is quota-bound, one deck
  at a time. This is worth knowing before scoping any future campaign here: the
  serial dispatch convention issue #64 adopted for politeness turns out to also
  be the *only* throughput available.
- **`fs`/125C decks cost ~350-500 s of CPU each**, roughly **3x** the
  `tt`/27C cost the issue-#65 budget was extrapolated from. `fs` skew at 125C
  is the stiffest graded corner for this fragment. At that cost the `tt`/27C
  record's (64 + 64) decks is a ~10 h quota-bound run at this corner and full N
  (128 + 256) is over a host-day.

The smaller sample is handled by reading **every** disposition above against
the conservative end of the 95% CI, never the point estimate -- and the
closure holds there too (3.32x direct, 1.011x under the double-count). The
record reports **no schematic-to-layout ratio**, because no committed
schematic-level `noise-tran` record exists at this corner; it says that
instead of inventing one, the same convention the post-layout `noise` records
use at their six counterpart-less corners.

**A resolved corner-dependence finding.** 0.2540 mV at `fs`/125C against
0.1448 mV at `tt`/27C is **1.754x**, and the two 95% CIs ([0.1961, 0.3009]
against [0.1224, 0.1641]) **do not overlap** -- so unlike that record's
schematic-to-layout ratio, this corner-to-corner difference *is* resolved at
these sample sizes. It degrades faster with corner than the AC sub-model's own
1.433x (0.9423 / 0.6576). The AC-to-transient gap here is 3.71x, squarely
inside the ~3-4x gap DR-006 recorded at `tt`/27C, `ss`/-40C and `ff`/125C
(`tt`/27C post-layout is 4.54x), so the closing figure is not an outlier of
the method at the corner where it matters most.

**The cross-check is degenerate for the same reason as at `tt`/27C.** All 16
decision runs resolved (0 unresolved) and all decided the **same way** at
**both** signs of the +/-0.191 and +/-0.381 mV sigma-scaled overdrives, so
`p+ = p-` exactly -- the all-one-way branch, not the resolvable-overdrive
floor. As at `tt`/27C that is a *deterministic* term, not noise, and the
post-layout `offset` record's 0.6547 mV input-referred systematic mean is the
standing candidate (issue #66). It is why the 4 seeds/sign/point reduction
costs little: the classification `degenerate_cross_check_reason()` derives from
the counts is the same one 16 seeds/sign produced at the only other
post-layout corner.

### Post-layout `noise-tran` at `ss`/-40C and `ff`/125C -- the two corners with a schematic counterpart (issue #89)

`records/20260926-110218-b64004b.md` (`ss`/-40C) and
`records/20260926-102605-b64004b.md` (`ff`/125C), both N=32/4. These are the
first two post-layout `noise-tran` records to **difference against a committed
schematic-level counterpart at a corner other than `tt`/27C** -- and they can
only do that because this same change closed a code gap that would otherwise
have made them lie.

**The code gap, and why it had to be fixed in the same change.** `run.py`'s
`SCHEMATIC_BASELINES` carried a `noise-tran` anchor at `tt`/27C **alone**, even
though the issue #41 schematic-level campaign committed records at `ss`/-40C
(`20260922-205857-ebea4e2`, 0.1213 mV, N=128) and `ff`/125C
(`20260923-010427-ebea4e2`, 0.1754 mV, N=128). A post-layout run at either
corner therefore fell through to `post_layout_delta_lines()`'s "No committed
schematic-level `noise-tran` record exists at ..." line -- honest in form and
**false in fact**, with the counterpart sitting in `records/` the whole time.
Run the corner without the anchor and the record ships a false negative. Both
anchors are now present and three tests in
`sim/tests/test_comparator_decision.py` pin the anchor set to exactly the set
of corners a schematic-level record was committed at, so the same drift cannot
recur silently.

The four graded points with **no** schematic-level counterpart (`sf`/-40C,
`sf`/125C, `fs`/-40C, `fs`/125C) deliberately keep falling through to that
line. That is the correct behaviour, the convention the post-layout `noise`
records use at six of their seven corners, and what #83's `fs`/125C record
already does.

| Corner | Schematic (N=128) | Post-layout (N=32) | Ratio | Post-layout 95% CI | Cross-check |
|---|---|---|---|---|---|
| `ss`/-40C | 0.1213 mV | **0.1382 mV** | 1.139x | [0.1046, 0.1666] | degenerate -- resolvable-overdrive floor, as on the schematic side |
| `ff`/125C | 0.1754 mV | **0.1956 mV** | 1.115x | [0.1606, 0.2212] | **0.2175 mV -- MEASURABLE** |

**No single one of these ratios is resolved, and all three that exist point the
same way.** The schematic figure sits *inside* the post-layout 95% CI at
`ss`/-40C, at `ff`/125C and at `tt`/27C alike, so no corner on its own
establishes that the layout moved this quantity. What the three corners
together add is a **sign**: 1.063x (`tt`/27C), 1.139x (`ss`/-40C), 1.115x
(`ff`/125C) -- three independent corners, all above 1, in a band of 1.06-1.14x.
Three-of-three in one direction is a one-sided sign-test p of 0.125: suggestive
corroboration that the post-layout penalty on this row is small and positive,
**not** a resolved measurement of it. Resolving it needs N, not more corners,
and that is the open item below.

**`ff`/125C's cross-check is the first post-layout one that is measurable**, and
that matters for how the other two are read. At `tt`/27C and `fs`/125C every
decision pair was degenerate *all-one-way*, which those records attribute to a
deterministic term (the `offset` sub-command's 0.6547 mV post-layout systematic
mean, issue #66) swamping the sigma-scaled overdrives -- an explanation that
would be much weaker if the cross-check never worked post-layout at all. Here
it does: at +/-0.1467 mV the pair splits 2/4 against 0/4 and yields **0.2175
mV**, against the same record's 0.1956 mV pick-off figure. Two independent
statistics on the same extracted fragment agreeing to 11% is the corroboration
the degenerate corners could not supply. `ss`/-40C is degenerate for the third,
distinct reason its own schematic-level counterpart already recorded -- the
overdrives sit below that corner's resolvable-overdrive floor -- so degeneracy
there is the corner's behaviour, not a post-layout finding.

**Corner scaling on the regeneration-inclusive basis**, now four corners deep
and monotone in temperature: 0.1382 mV (`ss`/-40C), 0.1448 mV (`tt`/27C),
0.1956 mV (`ff`/125C), 0.2540 mV (`fs`/125C). The hot corners bind this row on
the transient basis exactly as they do on the AC one. **Nothing here touches
DR-006**: its compliance basis was closed at its own named binding corner,
`fs`/125C, by `20260926-055806-3034c41` and Amendment 1. Every figure above
clears the ratified `<= 1.0 mV` target by more than 5x even at its CI's upper
bound, so no decision record is filed.

#### A second host cost, measured by #89: a hard ~60-minute wall-clock ceiling

#83 recorded the one-core cgroup quota (`cpu.max 100000 100000`) that makes
`--jobs 2` worthless here. #89 hit a second limit that constrains campaign
scoping at least as hard, and it is **wall clock, not CPU time**: an agent
session's background-task supervisor **kills any single command at ~60
minutes**. An N=32/4 run at `ss`/-40C was killed by it at 59.5 min with the
pick-off phase complete (N=32 -> 0.1280 mV) and the decision phase in flight,
and **no record was written** -- the entire hour produced nothing committable.

Two consequences for anyone scoping the remaining corners:

- **Budget a corner as `4 gaincal + N + 4 x seeds-per-point` decks against a
  hard 60-minute ceiling**, not against a CPU-time estimate. Measured per-deck
  wall clock on this fragment ranged **~35 s to ~285 s** purely with co-tenant
  load on these shared 8 vCPUs -- an 8x spread, which is why the same N=32/4
  configuration took 59.5+ min (killed) and then 35 min at the same corner
  hours apart.
- **A full-N (128 + 256) corner cannot be run as one command on this host at
  all.** It is not a budgeting question; it exceeds the ceiling by an order of
  magnitude. Closing item 3 of #89 needs either a resumable/chunked runner or a
  different execution host, and that is a scoping fact, not a preference.

The `ss`/-40C corner carries **two** records for this reason, and both are
committed. `20260926-100015-b64004b` is an N=16/2 run made while the host was
loaded, so that the corner would have *some* post-layout figure; it read
0.0955 mV (95% CI [0.0646, 0.1149]), a 0.788x ratio. When the host quietened
the corner was re-run at N=32/4 as `20260926-110218-b64004b`, which
`--supersedes` it and reads 0.1382 mV / 1.139x. The pair is kept rather than
quietly dropped because it *is* the item-3 measurement in miniature: at one
corner, on one fragment, with nothing changed but N, the point estimate moved
45% and the sign of the ratio flipped. Cite the superseding record; read the
superseded one as evidence that N=16 is below this statistic's useful floor.

### Post-layout corner campaign (issue #64, `--dut extracted`)

Issue #57 measured two PVT points. DR-005 grades the ratified rows across
**seven**. This campaign closes that gap for the two sub-commands whose rows
the layout was expected to move -- `kickback` (the row DR-002/DR-005 named as
the standing layout-stage gate) and `regen` -- leaving `offset` and `noise` at
#57's single anchor for the stated reason below. Dispatch: serial, one
ngspice at a time, per "Dispatch decision (issue #64)" above.

**Issue #80 has since closed the `offset` half of that skip**, running all
four remaining `_mm` mismatch corners post-layout under the same serial
dispatch rule; its results are the `offset` subsection below, and the
"Deliberately skipped, and why" entry is struck through accordingly. `noise`
was never a coverage gap in the same sense -- all seven graded corners were
run, six simply have no schematic-level AC counterpart to difference against.

#### `kickback` -- all seven graded corners now measured post-layout

| Corner | Schematic | Post-layout | Ratio | Record |
|---|---|---|---|---|
| `tt`/27C | 1.8902 mV | 2.6767 mV | 1.416x | `records/20260925-094700-4694692.md` (#57) |
| `ss`/-40C | 1.8605 mV | **2.7564 mV** | 1.482x | `records/20260925-165936-45f0767.md` |
| `ff`/125C | 1.7677 mV | **2.2985 mV** | 1.300x | `records/20260925-170317-45f0767.md` |
| `sf`/-40C | 2.0208 mV | **3.1989 mV** | **1.583x** | `records/20260925-165719-45f0767.md` |
| `sf`/125C | 1.7837 mV | **2.3443 mV** | 1.314x | `records/20260925-165748-45f0767.md` |
| `fs`/-40C | 1.8408 mV | **2.6795 mV** | 1.456x | `records/20260925-165825-45f0767.md` |
| `fs`/125C | 1.6091 mV | **1.9558 mV** | 1.215x | `records/20260925-165858-45f0767.md` |

Every `ideal` zero-impedance control still collapses to exactly 0.0000 mV at
every corner, so the deck is still isolating a genuine source-impedance
-dependent effect and not an artifact of the extracted fragment.

**Against the ratified bounds.** The worst corner is `sf`/-40C at **3.1989
mV**. The **`<= 5 mV` target bound is cleared at all seven corners**, worst-case
margin **1.56x** -- so the Kickback row is **not** re-opened and no decision
record is filed. The `<= 2 mV` **stretch** figure is breached at six of seven
corners (by 60% at `sf`/-40C); `fs`/125C at 1.9558 mV is the only corner that
still meets it. Per `CLAUDE.md` that is recorded, not legislated away: the
stretch figure is unchanged and is not a compliance requirement.

**The finding this campaign actually produced** is about the *ratio*, and it
is the reason the extrapolation #64 was scoped against was not good enough.
Issue #64 reasoned that #57's measured 1.35x `tt`/27C ratio, applied to the
schematic-level worst corner, extrapolated to ~2.7 mV at `sf`/-40C. The
measured figure is **3.1989 mV** -- 18% above that extrapolation -- because
**the post-layout penalty is not a corner-independent constant**. It ranges
1.215x-1.583x, and it is systematically *larger at the cold corners*
(`sf`/-40C 1.583x, `ss`/-40C 1.482x, `fs`/-40C 1.456x) than at the hot ones
(`fs`/125C 1.215x, `ff`/125C 1.300x, `sf`/125C 1.314x). So the layout penalty
and the schematic-level worst case **reinforce rather than cancel**: the
corner that was already worst pre-layout is also the corner the layout
degrades most. A single-corner post-layout ratio is therefore not a safe
basis for extrapolating this row, which is precisely why the row needed
measuring at every corner rather than scaling from one.

#### `regen` -- all seven graded corners now measured post-layout

50 mV overdrive is the point both bounds are stated at.

| Corner | Schematic | Post-layout | Ratio | Sweep points resolved | Record |
|---|---|---|---|---|---|
| `tt`/27C | 0.4025 ns | 0.5325 ns | 1.323x | 6/8 | `records/20260925-085247-4694692.md` (#57) |
| `ss`/-40C | 0.3575 ns | 0.4725 ns | 1.322x | 3/8 | `records/20260925-093624-4694692.md` (#57) |
| `ff`/125C | 0.4975 ns | **0.6475 ns** | 1.302x | 8/8 | `records/20260925-175622-bec714a.md` |
| `sf`/-40C | 0.3475 ns | **0.4425 ns** | 1.273x | 5/8 | `records/20260925-192610-bec714a.md` |
| `sf`/125C | 0.4725 ns | **0.6375 ns** | 1.349x | 7/8 | `records/20260925-182949-bec714a.md` |
| `fs`/-40C | 0.3725 ns | **0.4875 ns** | 1.309x | 5/8 | `records/20260925-185950-bec714a.md` |
| `fs`/125C | 0.5375 ns | **0.7725 ns** | **1.437x** | 7/8 | `records/20260925-173228-bec714a.md` |

**Against the ratified bounds.** The slowest corner is `fs`/125C at **0.7725
ns**. The `<= 1.5 ns` **target** bound is cleared at all seven corners (worst
case 1.94x), and the `<= 0.8 ns` **stretch** bound is *also* still cleared at
all seven -- but at `fs`/125C **with only 1.04x margin (3.4%)**. The row is
**not** re-opened: both ratified bounds hold everywhere. The thin stretch
margin is flagged here rather than smoothed over, because it is the figure
that would move first if the supply-net parasitic model were refined (see
"Parasitic model, and where it is coarse" above -- the lumped star R on
`GND`/`VDD` is expected to be *pessimistic*, so `fs`/125C's true margin is
plausibly better than 1.04x, not worse; that is an argument for re-measuring
it with `--distributed-rc`, not for assuming it).

**The ratio is corner-dependent here too, and in the opposite direction to
`kickback`.** `regen`'s post-layout penalty spans 1.273x-1.437x and is
largest at the **hot** corner `fs`/125C, where `kickback`'s was largest at
the **cold** corners. So the two rows do not share a worst corner, and
neither row's PVT shape can be inferred from the other's -- another reason
one anchor corner is not a basis for extrapolation.

**Sub-20 mV resolution degrades further at the skew corners.** #57 recorded
`tt`/27C falling to 6/8 resolved points and `ss`/-40C to 3/8 post-layout. The
new corners continue that: 8/8 at `ff`/125C, 7/8 at both 125C skews (the
+0.5 mV point does not resolve), and **5/8 at both -40C skews** (+0.5, +1 and
+2 mV do not resolve, while -10 mV does in ~1.21 ns). As #57 recorded, the
sweep *brackets* this asymmetry rather than measuring it -- `regen`'s
criterion is sign-corrected, so a wrong-polarity decision and a genuine
non-decision both read `UNRESOLVED`. The new data localises the cold-corner
bracket to **between 2 and 5 mV** at both `sf`/-40C and `fs`/-40C. This does
not touch either bound (both are stated at 50 mV overdrive, which resolves at
every corner), and quantifying the mechanism remains issue #66.

#### `noise` -- all seven graded corners, stated without a delta at six

`noise` is the loop-broken AC sub-model. It is cheap (one deck, ~20 s per
corner), so every graded corner was run. **Six of the seven carry no
post-layout *delta*, by construction**: DR-005's corner campaign measured
`noise-tran` (the regeneration-inclusive Monte Carlo figure) at the non-`tt`
corners, not this AC sub-model, so there is no committed schematic-level AC
counterpart to difference against. Each record says exactly that instead of
inventing a ratio, and the figure is still graded against the ratified bound.

#### `offset` -- all five `_mm` corners now measured post-layout (issue #80)

Issue #64 deliberately skipped `offset` at the four non-`tt_mm` mismatch
corners and recorded why (see "Deliberately skipped, and why" below, now
closed). Issue #80 ran them: `--dut extracted` at `ss_mm`, `ff_mm`, `sf_mm`
and `fs_mm`, each at **27 C, N=16, seed 1** -- the one methodology anchor
every committed offset record in this repo uses, schematic-level and
post-layout alike, so the five figures differ only in process. Dispatch was
the same as #64's: `--jobs 1`, one corner at a time, serial.

Note that `offset`'s graded axis is **not** `GRADED_CORNERS`. It grades the
`_mm` mismatch variant of each process corner at a single temperature, so the
coverage question for this row is "all five `_mm` corners at 27 C", not "all
seven (corner, temperature) points". `run.py` names that axis explicitly as
`OFFSET_GRADED_CORNERS`, and a test asserts a schematic-level anchor exists
for each, so the claim below is checkable against a list rather than prose.

| Corner | Schematic | Post-layout | Ratio | Negative-control mean (systematic) | Record |
|---|---|---|---|---|---|
| `tt_mm`/27C | 1.7857 mV | 2.4446 mV | 1.369x | 0.6547 mV | `records/20260925-112809-4694692.md` (#57) |
| `ss_mm`/27C | 1.8244 mV | **2.4133 mV** | 1.323x | **0.6780 mV** | `records/20260926-022304-5b02508.md` |
| `ff_mm`/27C | 1.5954 mV | **2.4796 mV** | **1.554x** | **0.6355 mV** | `records/20260926-032735-85c288e.md` |
| `sf_mm`/27C | 1.6706 mV | **2.4794 mV** | 1.484x | **0.6350 mV** | `records/20260926-034704-dfaee77.md` |
| `fs_mm`/27C | 1.8218 mV | **2.4078 mV** | 1.322x | **0.6874 mV** | `records/20260926-041419-38f6227.md` |

Every corner's same-seed mismatch-disabled negative control reproduced stdev
**exactly 0**, and every mismatch-enabled positive control showed genuine
spread, so all five records are `Overall: PASS` and the deck is still
isolating mismatch rather than an artifact of the extracted fragment.

**Against the ratified bounds.** The worst corner is `ff_mm` at stdev 2.4796
mV, **3 sigma = 7.4388 mV**. The `<= 15 mV` 3-sigma **target** bound is
cleared at all five corners with worst-case **2.02x** margin, and the `<= 8
mV` 3-sigma **stretch** figure is *also* still cleared everywhere, worst case
**1.08x**. The Offset sigma row is therefore **not** re-opened and **no
decision record is filed** -- per `CLAUDE.md`, a ratified bound is only
re-opened by evidence, and this evidence does not breach one.

**The corner spread collapses, and that is the finding.** Schematic-level the
five corners span 1.5954-1.8244 mV (**14.4%**, `ss_mm` nominally binding).
Post-layout they span 2.4078-2.4796 mV -- **3.0%**. Two consequences, and the
second matters more than the first:

1. **The schematic-level ranking does not survive layout.** `ss_mm`, the
   nominally binding schematic corner and the reason this issue was filed, is
   now the *second-lowest* post-layout figure; `ff_mm`, the *lowest*
   schematic corner, is the highest. So the worry that motivated the work --
   that `ss_mm` might bind harder post-layout -- is answered, and answered
   negatively.
2. **But no post-layout binding corner is resolvable at N=16 either.** The
   3.0% post-layout span sits far inside this sample size's own **18.3%**
   relative standard error on the stdev. The five post-layout corners are
   statistically indistinguishable from one another; the honest reading is
   not "`ff_mm` binds" but "**at N=16 this row has no identifiable worst
   corner post-layout**". Separating them needs the O(100s)-draw post-layout
   campaign, which is explicitly *not* part of this work and remains open.

**The ratio is corner-dependent, and anti-correlated with the schematic-level
value.** The post-layout penalty spans **1.322x-1.554x**, and it is largest
exactly where the schematic-level figure was *smallest* (`ff_mm` 1.5954 mV ->
1.554x) and smallest where it was largest (`fs_mm` 1.8218 -> 1.322x, `ss_mm`
1.8244 -> 1.323x). Unlike the stdevs themselves, these ratios are *paired*
comparisons -- same seed sequence, same draws, same deck template, only the
DUT fragment differs -- so the ordering is better determined than an
independent-sample reading of the 18.3% SE would suggest.

This confirms #64's central finding from a third direction, and extends it.
`kickback`'s post-layout penalty was largest at the corner that was already
worst pre-layout (**reinforcing**: 1.583x at `sf`/-40C); `regen`'s was largest
hot (1.437x at `fs`/125C); `offset`'s is largest where the schematic figure
was *best* (**compressing**). Three rows, three different corner shapes -- so
no row's PVT shape can be inferred from another's, and a single-corner
post-layout ratio remains an unsafe basis for extrapolating any of them.

**The ratio ordering is not a gain-loss ordering.** #57 attributed the
`tt_mm` offset rise to the 2.12x pick-off-gain loss, and that remains the
mechanism for the overall *level*. It does not explain the corner-to-corner
*ordering*, because the two run opposite ways: `ff_mm` and `sf_mm` retain the
**most** gain post-layout (35.7356 and 35.9542 V/V, losses of only 1.81x and
1.84x) yet carry the **largest** offset ratios, while `fs_mm` and `ss_mm`
lose the most gain (2.37x and 2.07x, down to 25.7414 and 26.0386 V/V) and
carry the **smallest**. Layout also *widens* the gain spread (schematic
53.9582-66.0461 V/V, 1.22x; post-layout 25.7414-35.9542 V/V, 1.40x) while
*narrowing* the input-referred offset spread. So the flat post-layout offset
figure is a net of two spreads that partially cancel, not a gain artifact.

**The systematic term is essentially corner-independent.** The
mismatch-disabled negative control's *mean* -- exactly 0 by construction on
the symmetric schematic fragment, and the first measurement of a systematic,
layout-induced offset on this block (#57) -- is non-zero at every corner and
spans only **0.6350-0.6874 mV (8.3%)** across all five. It is the second
output this campaign was scoped for. Because it barely moves with process, it
is a robust term to carry into [issue
#66](https://github.com/2AMLogic/sky130-comparator/issues/66)'s analysis of
the sub-20 mV polarity asymmetry rather than a corner-specific artifact: the
0.6547 mV figure that analysis already leans on is representative of the
whole `_mm` set, not just of `tt_mm`. Note this row's bounds are stated on
sigma only, so they do not cover this term at any corner.

**Measured wall clock.** 19-64 min per corner serially on the shared
dispatch host, against #57's ~25 min estimate -- the spread is contention
from sibling sweeps, not from the corner (the slowest ran at a 15-min load
average of 14.5 on 8 vCPUs). ~2.6 h total for the four corners.

#### Deliberately skipped, and why

Stated here so the gap is a decision on the record, not a silent absence:

- ~~**`offset` is measured post-layout at `tt_mm`/27C only** (issue #57)~~ --
  **CLOSED by issue #80**, which ran the other four `_mm` corners; see
  "`offset` -- all five `_mm` corners now measured post-layout" above. The
  original reason is kept on the record: `offset` is the campaign's most
  expensive sub-command by an order of magnitude (~37 decks per corner,
  ~25 min each serially), and under the serial dispatch decision above the
  four remaining corners cost ~100 min of additional host time on a shared
  dispatch worker, so the two rows whose ratified compliance the layout was
  *expected* to move -- `kickback` (DR-002/DR-005's named layout-stage gate)
  and `regen` -- were prioritised for that budget instead. That reasoning was
  sound on cost and wrong on outcome in one respect worth recording: the
  skipped corners turned out to carry the campaign's *largest* post-layout
  ratio (1.554x at `ff_mm`, against `tt_mm`'s 1.369x anchor), so the skip did
  cost information, not merely coverage. What it did not cost is compliance
  -- every corner clears both bounds. An O(100s)-draw post-layout campaign
  remains genuinely open and is not part of #80.
- **`reset` and `noise-tran` had no post-layout deck form at all** when this
  campaign ran, and refused `--dut extracted`. Not a coverage choice at the
  time -- there was nothing to run. **Issue #65 has since built that deck
  form** and run both: `reset` at all five of its corners and `noise-tran` at
  `tt`/27C (see "Post-layout records (issue #65)" above). **Issue #83 has
  since added `fs`/125 °C**, the corner DR-006 named as the one that would
  close the re-opened noise row, and it does close it (DR-006 Amendment 1).
  **Issue #89 has since added `ss`/-40C and `ff`/125C** -- the two remaining
  corners that have a committed *schematic-level* `noise-tran` counterpart to
  difference against -- and filled the `SCHEMATIC_BASELINES` entry gap that
  would otherwise have made both records print "no committed counterpart" when
  one existed (see "Post-layout `noise-tran` at `ss`/-40C and `ff`/125C"
  above). `noise-tran`'s remaining **three** graded corners (`sf`/-40C,
  `sf`/125C, `fs`/-40C) are still unmeasured post-layout; none of the three has
  a schematic-level counterpart, so each will correctly report no ratio.
- **The supply nets' `--distributed-rc` re-extraction** was not done. The
  single lumped star R on `GND`/`VDD` is 52.0% of the block's total series R
  and is expected to be pessimistic, so every post-layout degradation above
  is an upper bound on the supply-network contribution.

| Sub-command | Post-layout corner coverage | Gap |
|---|---|---|
| `kickback` | **7 of 7** graded corners | none |
| `regen` | **7 of 7** graded corners | none |
| `noise` (AC) | **7 of 7** graded corners | delta only at `tt`/27C (no AC counterpart elsewhere) |
| `offset` | **5 of 5** `_mm` corners (all at 27C, #80) | none at N=16; no O(100s)-draw post-layout campaign |
| `noise-tran` | **4 of 7** graded corners (`tt`/27C, #65; `fs`/125 °C, #83; **`ss`/-40C and `ff`/125C, #89**) | 3 corners (`sf`/-40C, `sf`/125C, `fs`/-40C) -- but **not** the corner DR-006 closes on: `fs`/125 °C is measured and DR-006 Amendment 1 closes the target-bound basis on it. All three remaining corners lack a schematic-level counterpart, so none can yield a ratio; the two that could, #89 ran. Separately open: every post-layout figure is N=32-64 against the schematic side's N=128, so no individual ratio is resolved |
| `reset` | **5 of 5** of its own corner set (#65) | none |

Earlier records (`20260916-*`, `20260921-*`) characterize the DR-001/
DR-003 single-tail design, and `20260909-*` the **ported placeholder
DUT**; they remain, unedited, as append-only evidence. See [The DUT](#the-dut)
for why they remain, unedited.
