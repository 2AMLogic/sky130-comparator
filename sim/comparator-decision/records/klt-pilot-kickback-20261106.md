# Pilot note 2026-11-06 -- kickback as a `klt sim` request on the batch fleet (issue #211)

Not a ratified record: no `Record ID`, no graded corner set. It answers one
question for #127: **does a `klt sim` route exist for this bench?** Answer:
**yes, for `kickback`** (the other four measurements were not attempted).

## What ran

- Requests: `klt-pilot/kickback-request-{loaded,ideal}.json` with bodies
  `klt-pilot/kickback-body-{loaded,ideal}.spice`. They mirror
  `run.py::_kickback_deck`: 1.8 V supply, CLK pulse 5 ns reset / 0.1 ns edges /
  40 ns evaluate, 50 mV static differential at VCM 0.9 V, `loaded` = 1 kohm
  per input, `ideal` = direct sources. `tran 0.005n 45.1n`, `tt`, 27 C.
- Measurements are verbatim `.meas tran` cards (`find ... at=5n`, `max`,
  `min` per input node). The peak disturbance is derived from them:
  `max(max - q, q - min)`. No `expr` entries were needed.
- Two single-unit jobs, one per leg (a request has one netlist), both
  `KLT_SIM_BACKEND=batch --backend batch`. No local run, no grid.
- Reports: `klt-pilot/report-{loaded,ideal}.json`; per-unit deck and ngspice
  log under `klt-pilot/out-*/`.

## Result

| Leg | Job id | Peak VINP (mV) | Peak VINN (mV) | Peak, worst node (mV) |
| --- | --- | --- | --- | --- |
| `loaded` | `klt-sim-5f5e3c768c59` | 0.5984 | 1.8736 | **1.8736** |
| `ideal` | `klt-sim-11100bd3d0e7` | 0.0000 | 0.0000 | **0.0000** |

- Runner: `klt` 0.9.0 (client 0.9.2.dev103+g9f4cec35997a), `runner_compatibility: match`,
  ngspice-46, c7i.8xlarge spot, us-east-1, 42 s / 45 s elapsed.
- Runner PDK (`worker_environment.pdk`): sky130A, `open_pdks f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7`.
  `pdk_stamp_comparison` was `not_comparable` (`client_stamp_unavailable`), so the
  match to the repo pin `f6eeac7` rests on the runner's own stamp text.

## Delta against the `run.py` baseline

Baseline record `20260922-070119-e084b55`: `loaded` 1.8902 mV, `ideal` 0.0000 mV.

- `loaded`: 1.8736 - 1.8902 = **-0.0166 mV (-0.88 %)**. `ideal`: 0 vs 0.
- The pilot's PDK is `f6eeac7`; the baseline was minted on `c6d73a35`. The
  revisions **do not match**, so the delta is **indicative only**; it cannot
  separate a PDK-revision effect from a solver/executor effect.
- Not checked: `run.py` saves with `tstep` 0.005n as well, but takes the peak
  over sampled `wrdata` points, while `.meas max/min` evaluate on the same
  accepted timepoints; any difference from that is folded into the delta.

## Caveats

- The `ideal` control is a second job, so two units ran rather than one; the
  issue's acceptance criteria require the control.
- Only the `kickback` point at `tt`/27 C was tested. `regen`, `offset`,
  `noise` and `reset` were not attempted, and no record or corner file changed.
