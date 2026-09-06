# Porting / design plan

**Status**: DRAFT. This plan names what transfers from the nearest mature
sibling and what this repo designs fresh. It ratifies nothing and is not
itself a decision record — see [`spec/README.md`](README.md) for when a DR
is required.

## Primary port source: `2AMLogic/sky130-sar-adc`

[`sky130-sar-adc`](https://github.com/2AMLogic/sky130-sar-adc) is the
nearest mature sibling for this block: same PDK (sky130), same 1.8 V core
supply flavor (ratified there in
[DR-001](https://github.com/2AMLogic/sky130-sar-adc/blob/main/spec/decision-records/DR-001-supply-flavor-scope.md)),
and its comparator is not a peripheral testbench — it is a core subblock of
that ADC's own design, exercised in a dedicated standalone experiment at
[`sim/comparator-decision/`](https://github.com/2AMLogic/sky130-sar-adc/tree/main/sim/comparator-decision).
That directory is the primary transfer target for this repo's own
testbenches.

### What is inventoried there (confirmed present, contents read directly)

- `sim/comparator-decision/testbench/comparator_core.spice` — the
  xschem-netlisted device fragment exercised by the driver below.
- `sim/comparator-decision/run.py` — a bespoke driver (not that repo's
  generic `sim/run_corners.py` / `sim/monte_carlo.py`) with four
  subcommands: `regen` (transient regeneration time vs. differential
  input), `offset` (mismatch-driven offset via `tt_mm`-class mismatch
  corners, Monte Carlo draws varying `rndseed`), `noise` (reduced-sub-model
  `.noise` analysis of the input pair + tail with the cross-coupled latch
  pair diode-connected to break the positive-feedback loop), and
  `noise-corners` (the noise measurement swept across the ratified PVT
  corner set).
- `sim/comparator-decision/corners/`, `sim/comparator-decision/mc-draws/`,
  `sim/comparator-decision/records/` — evidence directories following that
  repo's `sim/README.md` append-only convention (testbench/,
  netlist-snapshots/, corners/, mc-draws/, records/).
- `spec/decision-records/DR-004-comparator-topology-and-noise-budget.md` —
  the design-rationale record for that repo's comparator topology choice
  (single-tail dynamic latch, no static preamp) and its noise-budget
  measurement methodology.

### What transfers nearly whole (methodology and harness, not numbers)

- **The bespoke-driver pattern itself.** `sky130-sar-adc`'s
  `sim/comparator-decision/run.py` docstring explains *why* a dynamic
  latched comparator needs its own driver rather than the generic
  `.op`-based corner/Monte-Carlo runners: a clocked bistable circuit has no
  static DC operating point during regeneration, so offset and
  regeneration-time are inherently transient-analysis quantities, and
  noise needs a `.noise` analysis on a linearized (loop-broken) sub-model.
  That reasoning is generic to any dynamic latched comparator, sky130 or
  otherwise — this repo's own driver should follow the same shape (a
  standalone `run.py` under a `sim/<experiment-name>/` directory, reusing a
  shared `sim/harness/{pdk,toolchain,evidence,corners}.py`-style layer for
  PDK resolution, ngspice invocation, and evidence-record scaffolding, once
  this repo has its own harness — see "Fresh work" below).
- **The `regen` / `offset` / `noise` measurement methodology**, each with
  a documented, generic (not sky130-sar-adc-specific) technique:
  - `regen`: single reset→evaluate transient edge per differential-input
    point, sweeping `Vindiff` and reading the decision time.
  - `offset`: Monte Carlo draws at a `_mm`-suffixed mismatch corner
    (varying `rndseed`), with a same-seed, mismatch-disabled negative
    control expected to reproduce identical results across draws (the
    standard negative-control convention this repo's own `sim/` evidence
    should also use, per `CLAUDE.md`'s append-only-evidence and
    verification-is-the-product principles).
  - `noise`: break the cross-coupled latch's positive-feedback loop
    (diode-connect the latch pair instead of cross-coupling it) to get a
    well-posed small-signal `.noise` analysis, holding `CLK` at `VDD`
    (steady evaluate bias). This is a standard "break the loop for
    small-signal analysis" circuit-analysis technique, not specific to any
    one topology, and DR-004 documents it as producing a **lower bound**
    on the true regeneration-inclusive noise (the latch pair's own
    regeneration-phase noise contribution is excluded by construction).
  - The mismatch/negative-control statistical methodology is generic to
    sky130's `_mm` local-mismatch corners (`AGAUSS()` per-instance terms,
    confirmed present in the installed `sky130.lib.spice` combined
    library) — this is the PDK-level statistical basis `CLAUDE.md`'s
    "Statistical basis first" principle asks this repo to establish, and
    it is already established (by sky130-sar-adc, independently) on this
    exact PDK.
- **PVT-corner conventions**: `sim/pdk.json`'s `process_corners` /
  `mismatch_corners` schema (`tt`/`ss`/`ff`/`sf`/`fs`, each with a `_mm`
  local-mismatch variant), pinned to a specific `open_pdks` commit hash for
  reproducibility, and the one-at-a-time (OAT / "star") PVT grid convention
  in `sim/harness/corners.py` (baseline point plus, per axis, every other
  value with the remaining axes held at baseline — chosen there because a
  full factorial grid costs materially more wall-clock time for no
  additional per-axis sensitivity signal). Both are PDK/tooling
  conventions, not spec numbers, and transfer directly.

### What is designed fresh, not ported

- **All numeric target-spec bounds.** No sibling (sky130-sar-adc included)
  has a ratified standalone-comparator spec table to port — sky130-sar-adc's
  comparator numbers (README target-spec table, this repo) are cited there
  only as same-PDK prior art on plausible magnitude, explicitly not as
  inherited targets. sky130-sar-adc's own comparator is *embedded*: its
  input common mode is fixed near `V_REF/2` by a driving differential
  top-plate CDAC (per that repo's DR-004), and its sizing (`W = 4 µm` input
  pair, per DR-004's own account) was a first-pass choice with no offset
  budget target at all — not a validated, reusable sizing this repo should
  copy.
- **The schematic and its sizing.** This repo needs its own
  `design/comparator.sch` (or equivalent), sized from first principles
  against sky130 device models for this repo's own headroom/noise/speed
  tradeoffs — not a copy of sky130-sar-adc's embedded topology, even though
  the topology *class* (dynamic latch, no static preamp, per the headroom
  argument in that repo's DR-001/DR-003/DR-004) is a reasonable starting
  hypothesis to re-derive independently, per `CLAUDE.md`'s clean-room
  convention (DR-004 itself states no external implementation was
  consulted for its own topology decision).
- **A standalone stimulus.** A SAR ADC's embedded comparator bench assumes
  a driving CDAC (fixed common mode, discrete-time comparison decisions
  tied to the SAR sequencer's clock). A standalone comparator bench for
  this repo needs its own ideal differential DC/pulse/noise stimulus with
  no CDAC or sequencer dependency — closer to what sky130-sar-adc's own
  `sim/comparator-decision/` driver already does (it is itself a
  standalone, ideal-stimulus experiment, not routed through the ADC's
  sampling front end or sequencer), which is exactly why it is the nearest
  transferable starting point rather than a different sky130-sar-adc
  testbench (e.g. `sim/sampling-cdac-handoff/` or
  `sim/sar-sequencer-behavioral/`, both of which assume the surrounding
  ADC).
- **A kickback experiment.** sky130-sar-adc's `sim/comparator-decision/`
  does not currently include a kickback measurement — this repo's target
  spec has a kickback row (see the top-level README) with no same-PDK
  standalone-comparator prior art to port; the testbench for it is
  original work.
- **Layout.** sky130-sar-adc's comparator subblock's layout maturity (if
  any) is out of scope for this survey — this repo's `layout/` work is
  independent per-PDK physical design regardless.

## Other siblings consulted (not primary port sources)

- [`sg13g2-comparator`](https://github.com/2AMLogic/sg13g2-comparator) and
  [`gf180-comparator`](https://github.com/2AMLogic/gf180-comparator) are
  this block's own twins (identical bench structure, per this repo's
  `CLAUDE.md`) but both are simultaneous wave-5 standups at the identical
  bootstrap stage as this repo — neither has a ratified spec or design to
  port from yet. They remain the comparative targets this repo's numbers
  will eventually be read against (the 1.8 V vs. 3.3 V vs. SG13G2-node
  headroom/speed/offset tradeoff `CLAUDE.md` and the top-level README call
  out), not sources for this pass.
- [`sky130-bandgap`](https://github.com/2AMLogic/sky130-bandgap) is cited
  for repo-convention precedent only (its `spec/README.md` DR-process
  wording, its README target-spec table format, and its
  `spec/decision-records/DR-001-supply-flavor-scope.md` mechanism
  precedent, which sky130-sar-adc's own DR-001 explicitly credits) — it is
  a different block (bandgap reference, not comparator) and has no
  comparator-relevant numbers to port.

## Next steps (not part of this issue's scope)

1. Design `design/comparator.sch` from first principles against sky130
   device models, documenting the topology decision as a decision record
   (mirroring sky130-sar-adc's DR-004 shape: context, decision, sizing
   rationale, alternatives considered, spec lines affected, consequences,
   open items).
2. Stand up `sim/harness/{pdk,toolchain,evidence,corners}.py`-equivalent
   plumbing (or adopt a shared harness if one exists at fleet level) plus a
   `sim/pdk.json` pin, following sky130-sar-adc's schema.
3. Port the `regen`/`offset`/`noise` *methodology* (not numbers) into a
   standalone `sim/comparator-decision/`-equivalent experiment directory
   here, with its own ideal-stimulus testbench.
4. Design an original kickback experiment (no same-PDK standalone prior
   art exists to port).
5. Once real measurements exist, revisit the README target-spec table's
   DRAFT bounds and file a ratification decision record if/when the table
   is set, changed, or scoped (see `spec/README.md`).
