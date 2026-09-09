# sim/comparator-decision/ -- regen/offset/noise experiment

Standalone characterization experiment for a dynamic latched comparator's
decision behavior: regeneration time vs. differential input (`regen`),
mismatch-driven offset (`offset`), and input-referred noise (`noise`). Every
stimulus here is an ideal differential DC/pulse source -- there is no CDAC
array or SAR sequencer dependency, because this repo (`sky130-comparator`)
has no SAR ADC. This directory implements `spec/porting-plan.md`'s "Next
steps" item 3.

```sh
python3 sim/comparator-decision/run.py --check-env
python3 sim/comparator-decision/run.py regen  --record
python3 sim/comparator-decision/run.py offset --record --n 16 --seed 1
python3 sim/comparator-decision/run.py noise  --record
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
- **`noise`**: break the cross-coupled latch's positive-feedback loop
  (diode-connect the tail + input pair's own drain-node loads instead of
  cross-coupling the latch pair) to get a well-posed small-signal `.noise`
  analysis, holding CLK at VDD (steady evaluate bias, tail on). This is a
  standard "break the loop for small-signal analysis" circuit-analysis
  technique, not specific to any one topology, and is a deliberate **lower
  bound** on the true regeneration-inclusive noise (the latch pair's own
  regenerative-phase noise contribution is excluded by construction) -- see
  the port source's own `spec/decision-records/
  DR-004-comparator-topology-and-noise-budget.md` for the full derivation.
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
  response to a specific bug in *its own* pre-fix device set (see
  "Placeholder DUT" below) -- not reproduced here because the placeholder
  DUT below already uses the fixed device set and this repo's own
  regen record shows a clean, monotonic reset-hold.

## Placeholder DUT

`testbench/comparator_core.spice` is **not this repo's own topology
decision**. `spec/porting-plan.md`'s "Next steps" item 1 (`design/
comparator.sch`, sized from first principles against sky130 device models,
with its own decision record) is explicitly out of scope for issue #9 (see
that issue's "Out of Scope" section). The fragment committed here is ported
**verbatim** (devices, sizing, node names -- nothing adapted) from the port
source's `comparator_core.spice` as it stood after that repo's own issue
#175 / DR-004 Amendment A reset-integrity fix -- the pre-fix device set is
known, by that repo's own evidence records, to leave the latch at an
unstable mid-rail equilibrium during the CLK=0 reset phase. Citing the fixed
device set rather than the original one avoids porting a known-bad starting
point into this repo, even though the topology itself remains just a
borrowed placeholder pending this repo's own `design/comparator.sch` (issue
#9's parent tracking issue, #7, next step 1).

It exists for exactly the reason `sim/harness-corner-smoke/` and
`sim/mc-smoke/` exist for the PVT/MC harness (`sim/README.md` "Harness
self-test experiments"): so `run.py`'s regen/offset/noise driver has
something real to exercise end to end, proving the plumbing works, before a
real design/comparator.sch exists. **None of the records under `records/`
substantiate any row of the top-level README's target-spec table** -- every
record's own `Claim` field says so explicitly, and each will need to be
re-run against the real schematic once it exists (a distinct claim, not a
correction, so the placeholder records are never edited or superseded --
they simply stop being the freshest evidence once real records land
alongside them).

## Committed records (nominal corner: tt/27C/1.8V)

One record per experiment, proving the ported plumbing runs end to end
against the placeholder DUT on this repo's pinned toolchain
(`sim/toolchain.json`) and PDK (`sim/pdk.json`):

- `regen` -- `records/20260909-153206-c6e2e1d.md`: 8/8 Vindiff points
  resolved within the evaluate window; regeneration time grows monotonically
  as Vindiff shrinks (1.11 ns at 50 mV -> 2.36 ns at 0.5 mV), the expected
  `ln(1/Vindiff)` positive-feedback-latch shape.
- `offset` -- `records/20260909-154218-c6e2e1d.md`: N=16 draws at `tt_mm`,
  offset mean 0.26 mV / stdev 3.90 mV; same-seed negative control at plain
  `tt` reproduces stdev == 0 exactly, confirming the mismatch-corner
  statistical convention works end to end on this PDK/toolchain.
- `noise` -- `records/20260909-154235-c6e2e1d.md`: single-ended
  input-referred noise 0.4814 mV rms, differential estimate 0.6808 mV rms
  (informational -- no noise-budget spec row exists in this repo yet to
  grade against).
