# Pilot note 2026-11-14 -- kickback on the EXTRACTED DUT as a `klt sim` request (issue #219)

Not a ratified record: no `Record ID`, no graded corner set, one PVT point.
It is a **pilot**, and it **neither closes #125 nor changes any spec row**.

It answers one question for #127, the successor to the question issue #211's
pilot answered: **does the `klt sim` request route carry an *extracted* DUT?**
Answer: **yes.** Both legs ran on the batch fleet with the DUT instantiated
from `layout/comparator.pex.spice`, and both reports' `netlist_closure` list
that fragment at `scope: "repo"` -- the machine-checkable evidence, cited
below rather than asserted.

Secondary, and the reason the figure is interesting at all: the committed
0.35 um / klt 0.8.0 extraction previously had **no simulated figure of any
kind**. Every committed post-layout record was measured on the earlier
0.42 um-drawn layout extracted under klt 0.6.0.

## What ran

- Requests: `klt-pilot/pex-request-{loaded,ideal}.json` with bodies
  `klt-pilot/pex-body-{loaded,ideal}.spice`. They are issue #211's fleet-proven
  `kickback-*` pair with the `.include` target repointed from
  `../testbench/comparator_core.spice` to `../../../layout/comparator.pex.spice`
  and nothing else changed in the circuit: 1.8 V supply, CLK pulse 5 ns reset /
  0.1 ns edges / 40 ns evaluate, 50 mV static differential at VCM 0.9 V,
  `loaded` = 1 kohm per input, `ideal` = direct sources (zero source
  impedance). `tran 0.005n 45.1n`, `tt`, 27 C. This mirrors
  `run.py::_kickback_deck`, which emits `_dut_lines()` verbatim -- the
  `_retie_star_legs` deck surgery runs only on the `reset` and `noise-tran`
  paths, so for `kickback` the extracted DUT really is a pure `.include` swap.
- Measurements: the same six verbatim `.meas tran` cards (`find ... at=5n`,
  `max`, `min` per input node), unchanged. Peak disturbance is derived from
  them as `max(max - q, q - min)`. The extracted fragment carries the
  **schematic** net names (the 12/12 LVS correspondence), so no probe needed
  renaming.
- Two request JSON differences from the #211 template, both deliberate and
  neither cosmetic: `batch.capacity_wait_s` **600** (the host rule requires a
  capacity wait on every batch `klt sim`; the template's `0` would let a burst
  fail outright) and `options.timeout_s` **1800** (the template's 600 s was
  measured too tight -- see "On the timeout" below).
- Two single-unit jobs, one per leg (a request has one netlist), both
  `--backend batch`. No local run, no grid.
- `klt sim ... --backend batch --dry-run` was run on both requests first and
  returned `valid (1 unit(s), engine=ngspice, backend=batch)`. That check is
  live, not vacuous: the same body with its include repointed at a nonexistent
  file fails the submit with exit 1, naming the unresolvable path it looked
  for (`<repo>/layout/does-not-exist.spice`).
- Reports: `klt-pilot/report-pex-{loaded,ideal}.json`; batch receipt and
  per-unit deck under `klt-pilot/out-pex-*/` (`ngspice.log` is produced but
  `*.log` is gitignored repo-wide, so it is not committed -- same as #211's).

## The extracted DUT was carried -- the closure entry

Both reports' `environment.netlist_closure` contain exactly two entries:

| Leg | Closure entries (`scope`) |
| --- | --- |
| `loaded` | `sim/comparator-decision/klt-pilot/pex-body-loaded.spice` (`repo`), `layout/comparator.pex.spice` (`repo`) |
| `ideal` | `sim/comparator-decision/klt-pilot/pex-body-ideal.spice` (`repo`), `layout/comparator.pex.spice` (`repo`) |

The off-host backend stages the netlist's whole resolved `.include` closure
with a per-file sha256, so that second row is the report's own record that the
extracted fragment was uploaded and executed. **Acceptance criterion 6 (commit
the failing request and file a klayout-tools issue) therefore does not fire:**
nothing about the request route needed working around.

## Result

| Leg | Job id | Peak VINP (mV) | Peak VINN (mV) | Peak, worst node (mV) |
| --- | --- | --- | --- | --- |
| `loaded` | `klt-sim-9f5b42ac764b` | 0.8692 | 2.2747 | **2.2747** |
| `ideal` | `klt-sim-4e7647e29a20` | 0.0000 | 0.0000 | **0.0000** |

Both legs `status: pass`, `corner_count: 1`, `passed: 1`, `failed: 0`,
`errored: 0`.

- The sensitivity criteria `run.py` applies are met: `loaded` worst node
  2.2747 mV is well above the 1 mV floor (`KICKBACK_SENSITIVITY_MIN_V` 1e-3 V),
  and `ideal` collapses to 0.0000 mV, inside `KICKBACK_IDEAL_TOL_V`
  (1e-9 V = 1e-6 mV).
- **The `ideal` control collapsing is the load-bearing part of that**: it says
  the parasitic star legs between the driven hub and the device terminals do
  not themselves manufacture a disturbance. Driving the hub from a
  zero-impedance source still pins `v(vinp)`/`v(vinn)`, so the `loaded` figure
  is a genuine source-impedance-dependent effect on the extracted netlist and
  not an artifact of the extraction.
- Raw cards, `loaded`: `vinp_q` 0.925, `vinp_max` 0.9250613367128,
  `vinp_min` 0.9241308207609; `vinn_q` 0.875, `vinn_max` 0.875110699062,
  `vinn_min` 0.8727252771416. `ideal`: all six at exactly the quiescent
  values (0.925 / 0.875).

## Environment, as the reports state it

- Runner `klt` **0.9.0** (client `0.9.2.dev1022+g2a9c52b27ce7`),
  `runner_compatibility: match`.
- **ngspice-47** on the runner. Note this differs from #211's pilot, which ran
  on **ngspice-46**; it is a confounder in the delta below, not a detail.
- Runner PDK (`worker_environment.pdk`): sky130A, `stamp_scheme`
  `sources-sha256`, `stamp_text` **`open_pdks f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7`**,
  `stamp_scope: executed`.
- **`pdk_stamp_comparison: {"status": "match"}`** on both legs -- a real
  comparison, matching the repo pin `f6eeac7`. #211's pilot could only record
  `not_comparable` (`client_stamp_unavailable`); pinning `$PDK_ROOT` on the
  client (the only client-side pin backend `batch` accepts) is what makes the
  client stamp available and turns it into an actual match. That is a usable
  finding for #127: the batch route *can* produce a stamp comparison, if the
  submit pins `$PDK_ROOT`.
- c7i.4xlarge spot, us-east-1. Elapsed 23 s (`loaded`) / 34 s (`ideal`);
  in-corner runtime 13.2 s / 12.2 s.

## Delta against the schematic pilot

#211's pilot, same `klt-pilot/` template and same PDK revision `f6eeac7`,
schematic netlist: `loaded` 1.8736 mV, `ideal` 0.0000 mV.

- `loaded` worst node: 2.2747 - 1.8736 = **+0.4011 mV (+21.4 %)**.
  `ideal`: 0 vs 0. Per-node, VINN stays the worst node and VINP rises
  0.5984 -> 0.8692 mV.
- **Indicative only, and it is not a clean DUT delta.** Two things changed
  between the two pilots, not one: the DUT fragment (schematic -> extracted)
  *and* the runner's ngspice (46 -> 47). The PDK revision is **not** a
  confounder here -- both ran on `f6eeac7` -- but the solver version is, so
  the +21.4 % cannot be attributed to the parasitics alone.
- A same-ngspice reading of the DUT effect would need #211's schematic leg
  re-run on ngspice-47. That is one more fleet job and is **not** done here;
  it is the obvious cheap follow-up if #127 wants the parasitic effect
  separated from the solver bump.

## For orientation only: the old-geometry post-layout record

Canonical post-layout `kickback` at `tt`/27 C, `20260925-094700-4694692`:
`loaded` **2.6767 mV** (VINP 1.4696), `ideal` 0.0000 mV. This pilot sits
**15.0 % below** it (2.2747 - 2.6767 = -0.4020 mV).

**That difference is not interpretable as a geometry effect**, and this note
does not claim it is. At least four things differ at once:

| | `20260925-094700-4694692` | this pilot |
| --- | --- | --- |
| Extraction | klt 0.6.0 / klayout 0.30.10 | klt 0.8.0 / klayout 0.30.12 |
| Drawn `res_high_po` | w=0.42 um | w=0.35 um |
| Total series R / ground C | 17.52 kohm / 117.65 fF | 17.814 kohm / 123.016 fF |
| ngspice | 46 | 47 |
| PDK | `c6d73a35` | `f6eeac7` |
| Peak rule | `run.py` peak over sampled `wrdata` points | `.meas max/min` |

Note in particular that the *narrower* resistors came out with slightly
**more** total series R and ground capacitance, not less -- so even the sign of
a naive "narrower resistor -> less kickback" expectation is not established by
these numbers. Separating any of this is re-measurement campaign #125's job,
under whatever route #127 picks.

**Against the ratified bound, stated for completeness and legislating
nothing**: DR-002 ratifies Kickback at <= 5 mV (target) / <= 2 mV (stretch)
into 1 kohm. 2.2747 mV clears the target with 2.20x margin and breaches the
stretch, which is the same disposition every committed post-layout corner
already records. No row is re-opened, no decision record is filed, and a
single-point pilot is not the evidence that would do either.

## On the timeout

`options.timeout_s` was raised 600 -> 1800 because the `ideal` leg had been
measured at **410 s** in a local single-corner probe (vs 41.8 s for `loaded`,
~10x on the same template) -- close enough to a 600 s ceiling to risk an
**errored corner** rather than a slow pass. On the fleet the asymmetry did not
reproduce at anything like that scale: 34 s vs 23 s elapsed, 12.2 s vs 13.2 s
in-corner. So the local 10x looks like a property of the shared 8-vCPU
dispatch host rather than of the deck, and 1800 was headroom that turned out
not to be needed. Left at 1800 regardless: it costs nothing when the run is
fast, and the local measurement that motivated it was real.

## Caveats

- One PVT point (`tt`/27 C) and one measurement (`kickback`). `regen`,
  `offset`, `noise` and `reset` were not attempted on the extracted DUT via
  this route; `run.py` was not touched; no corner file, record or
  `sim/characterization-report.md` row changed.
- The `ideal` control is a second job, so two units ran rather than one.
- The delta to #211 carries an ngspice 46 -> 47 confounder; the comparison to
  the old-geometry record carries four or more. Neither is a graded result.
- Unrelated to this pilot's result but observed while running it:
  `layout/comparator.pex.spice`'s generated header still claims the fragment
  "deliberately carries through" a `res_high_po` w=0.42 um-drawn vs
  w=0.35 um-schematic delta, while `layout/extract_pex.py`'s docstring says
  that delta is gone since #123 and the committed device lines read `w=0.35`.
  The stale sentence comes from the generator's header template. Deliberately
  **not** fixed here -- regenerating the fragment would change the DUT
  mid-pilot.
