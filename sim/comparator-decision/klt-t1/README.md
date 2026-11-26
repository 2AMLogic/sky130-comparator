# klt-t1/ — T1 items 5 and 6 evidence (issue #188)

The `klt sim` envelopes and `klt yield` reports that make T1 item 5 ("full
corner verification vs a ratified spec") and item 6 ("statistical claims
carry Monte Carlo evidence") **gradeable** for this block. Everything here
was produced by real tool runs on the batch fleet (`klt sim`, backend
`batch`, `--wait-for-capacity 600`) and by `klt yield`/`klt yield-samples`
over those runs' committed reports — nothing is hand-assembled. The requests,
bodies and yield inputs are owned by
[`scripts/t1-items56-envelope.py`](../../../scripts/t1-items56-envelope.py):
`--write` regenerates them byte-for-byte from `run.py`'s own deck builders,
`--check` fails on any drift (including a moved DUT fragment, via the sha256
each body header records), and `--selftest` is the hermetic negative-control
suite for that gate.

This directory follows `sim/`'s append-only evidence convention: the
committed reports are never edited; a re-run writes a new report and the
manifest citation moves with it.

## Row map (the manifest's declared `spec_rows`)

| Row id | Spec row (top-level README) | Item | Disposition |
| --- | --- | --- | --- |
| `t_dec` | Decision time vs. overdrive (DR-005) | 5 | covered by `report-regen.json` |
| `kickback` | Kickback (DR-002) | 5 | covered by `report-kickback.json` |
| `noise_ir_ac` | Input-referred noise, AC corner-spread basis (DR-002) | 5 | covered by `report-noise.json` |
| `power` | Supply / power | 5 | **declared gap**: DRAFT/OPEN, no ratified bound exists to verify against (DR-002; re-anchoring deliberately open per DR-004) |
| `offset_sigma` | Offset sigma, schematic-DUT MC (DR-002/DR-005) | 6 | covered by `yield/report-tt_mm.json` + `yield/report-ss_mm.json` |
| `offset_sigma_extracted` | Offset sigma, extracted-DUT N=200 sub-case | 6 | **justified gap**: waiting on [#412](https://github.com/2AMLogic/sky130-comparator/issues/412) — see [`gaps/offset-extracted.md`](gaps/offset-extracted.md) |
| `noise_ir_tran` | Input-referred noise, regeneration-inclusive basis (DR-006 Amdt 1) | 6 | **justified gap**: waiting on [klayout-tools#7762](https://github.com/2AMLogic/klayout-tools/issues/7762) — see [`gaps/noise-tran.md`](gaps/noise-tran.md) |

The Input-referred noise row is deliberately split across the two items the
way the issue's row map directs: its corner-spread (AC) half is a
deterministic per-corner figure (item 5), its regeneration-inclusive half is
a sample statistic (item 6). No other ratified row carries a sigma or yield
bound beyond Offset sigma.

## Item 5 — three `klt sim` envelopes over the seven graded corners

All three requests run exactly the seven graded PVT points (tt/27, ss/−40,
ff/125, sf/±, fs/± at 1.8 V) via the top-level `exclude` mechanism, with the
ratified **target** bound as a graded `limits` entry and the row id in
`spec_row`, so `klt signoff` derives each row's coverage from the envelope
itself (`row_sources: "derived"`), not from the manifest's say-so. Stretch
figures are not compliance requirements and are compared in prose only.

- **`report-regen.json`** (request `regen-request.json`, body
  `bodies/regen-body.spice` = `run.py::_regen_deck` at +50 mV, machinery
  stripped). The measurement is a single `.meas` TRIG/TARG card: decision
  time from the clock's 50 % point (`v(CLK)` crossing 0.9 V) to the output
  difference crossing ±0.9 V. **Convention difference vs the committed
  records, stated not hidden:** the records measure from the evaluate-edge
  *start* (ramp end, 5.1 ns); this envelope measures from the clock's 50 %
  point (5.05 ns), so its figures are one half rise-time (50 ps) larger by
  construction. A second, ungraded `t_dec_abs` measurement carries the
  absolute crossing time, which bridges to the records' convention directly.
  Worst corner `fs`/125 °C: **0.5829 ns** against ≤ 1.5 ns (2.57× margin).
- **`report-kickback.json`** (loaded variant, 1 kΩ source impedance). The
  peak disturbance is measured **in-deck** as
  `MAX par('abs(v(VINx) − Vquiet)*1000')` per input node — the quiet
  reference is the ideal source value, which pre-edge is exact (no static
  current flows through the source resistor). Worst node/corner:
  `VINN` at `sf`/−40 °C **2.0208 mV** against ≤ 5 mV (2.48×) — the same
  figure the committed schematic record quotes at that corner. The `ideal`
  zero-impedance control variant is not re-run here: every committed kickback
  record carries it collapsing to exactly 0.0000 mV (append-only records
  `20261122-123556-a22c816.md` … `.../20261122-123604-a22c816.md`).
- **`report-noise.json`** (body = `run.py::_noise_deck`'s loop-broken DR-004
  preamp sub-model). Graded measurement is the `expr`
  `inoise_total*sqrt(2)*1000` — ngspice's own band-integrated input-referred
  total over the swept 1 kHz–1 GHz band, ×√2 for the differential estimate,
  the same arithmetic the committed AC records use. A second, ungraded
  `measurements[].noise` band entry cross-checks it through klt's own
  integrator; on the `dec 20` grid the two agree only to ~2 % (klt's band
  value is a trapezoid approximation on a log-spaced grid; the graded value
  is ngspice's own integral, which is also what the records quote). Worst
  corner `fs`/125 °C: **0.8057 mV** against ≤ 1.0 mV (1.24×). This is the
  row's conservative lower-bound basis; the regeneration-inclusive basis and
  its DR-006 history are the item-6 gap above.

## Item 6 — offset sigma as `klt yield` reports over a fresh N=200 campaign

The committed offset campaigns persist **summary statistics only** (records
+ 19-line ngspice log stubs under `mc-draws/`), so no sample-set document
could be derived from them without inventing numbers — the issue's "from the
committed Monte Carlo samples" premise does not hold on the ground. What this
directory does instead is re-run the campaign **as `klt sim` `monte_carlo`
requests** (the route the `klt-pilot` notes established for the deterministic
benches, extended here to the pick-off statistic), which makes the per-draw
values themselves committed, klt-native evidence:

1. **Calibration** (`offset-calib-request.json` → `report-offset-calib.json`):
   the 4-point ideal-device vindiff sweep at plain `tt`/27 °C through
   `corners.params`, pick-off read by an interpolated `FIND ... AT=5.75n`
   card. Zero-intercept least-squares gain **64.052698 V/V**
   (`offset-gain.json`; the committed records' 64.4571 V/V used the
   nearest-sample pick-off, which reads ~0.6 % high — the same rule
   difference the regen pilot decomposed).
2. **Nominal legs** (`offset-mc-{tt_mm,ss_mm}-request.json`): N=200, seed 1,
   sequential per-draw seeds, 27 °C — the committed N=200 campaigns' own
   convention — with the gain baked into the measurement card so the samples
   are input-referred mV directly. Resulting sigmas: `tt_mm` **2.2274 mV**,
   `ss_mm` **1.9193 mV** (the committed campaigns measured 2.3197 / 2.3782;
   different draw streams and the interpolated pick-off rule — each number
   is an estimate of the same σ with ~5 % relative SE, and both clear the
   row identically).
3. **Known-bad legs** (`offset-ctl-*.json`): same shape with
   `monte_carlo.mismatch_scale: 4` (sky130's `mc_mm_switch`), independently
   seeded (424242) — the `klt yield` negative-control convention. Observed
   control sigmas 9.11 / 7.48 mV ≈ 4× nominal, and both yield reports grade
   the control **`detected`** (Clopper-Pearson intervals disjoint from the
   nominal's at 95 % confidence).
4. **Determinism control** (`offset-det-tt_mm-request.json`): the repo's own
   negative-control convention — same seed sequence as the nominal `tt_mm`
   leg, per-instance mismatch off (`mismatch_scale: 0`). Across all 200
   draws: **stdev exactly 0.0**, mean −4.5e-12 mV.
5. **Yield** (`yield/`): `klt yield-samples` derives the sample set from the
   nominal + known-bad reports (paths repo-relative; the derivation block
   records both source hashes), the generator stamps the run provenance
   (seed 1, N 200, RNG identity, corner matrix `["tt_mm","ss_mm"]`), and
   `klt yield` grades against `yield/spec-limits.json`: the ratified
   "≤ 15 mV, 3σ" read as `target_sigma: 3` over the ±15 mV window, **no
   `target_yield`** (the row ratifies no yield fraction). Both reports:
   measurement `pass` (`sigma_to_spec` lower bound 5.91 / 6.89 ≥ 3),
   `sample_size.verdict: "sufficient"` (N=200 ≥ the 183 a ±0.01 interval
   needs at zero failures), negative control `detected`.

The `klt` producer pin for the yield steps is recorded in the generator
(`klayout-tools[yield]==0.9.2` via uvx); the grading side is the repo's
signoff pin and reads schema-1 yield reports whatever wrote them.

## Provenance

All fleet runs: runner/client klt 0.9.x (`runner_version_check: "warn"`,
versions recorded per report), ngspice-47 on the fleet `sim` image, sky130A
@ `f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7` (the repo pin; each report's
`worker_environment.pdk` records the stamp comparison). Batch receipts under
`out-*/batch-receipt.json`: all nine `out-*/` directories (item-5, calibration
and Monte Carlo legs alike) commit `batch-receipt.json` only — no per-unit
decks are kept. Decks regenerate deterministically from the committed
request + body of each leg.

## Regeneration

```sh
python3 scripts/t1-items56-envelope.py --write        # bodies + requests + yield inputs
python3 scripts/t1-items56-envelope.py --check        # drift gate (CI runs this too)
python3 scripts/t1-items56-envelope.py --selftest
```

Fleet runs (from this directory, one at a time):

```sh
klt sim regen-request.json          -o out-regen          --format json > report-regen.json
klt sim kickback-request.json       -o out-kickback       --format json > report-kickback.json
klt sim noise-request.json          -o out-noise          --format json > report-noise.json
klt sim offset-calib-request.json   -o out-calib          --format json > report-offset-calib.json
# then: --write --calib-report report-offset-calib.json (bakes the fitted gain)
klt sim offset-mc-tt_mm-request.json    -o out-offset-mc-tt_mm    --format json > report-offset-mc-tt_mm.json
# ... likewise mc-ss_mm, ctl-tt_mm, ctl-ss_mm, det-tt_mm
python3 ../../../scripts/t1-items56-envelope.py --yield-step tt_mm
python3 ../../../scripts/t1-items56-envelope.py --yield-step ss_mm
# then, from the repo root:
uvx --from "klayout-tools[yield]==0.9.2" klt yield \
    sim/comparator-decision/klt-t1/yield/samples-tt_mm.json \
    --limits sim/comparator-decision/klt-t1/yield/spec-limits.json \
    --format json > sim/comparator-decision/klt-t1/yield/report-tt_mm.json
# ... likewise ss_mm
```

After any re-run, move the manifest citations (`--pins` prints the new
content hashes) and regenerate `manifests/t1-signoff-report.json` per
`manifests/README.md`.
