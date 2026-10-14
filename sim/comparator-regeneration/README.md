# comparator-regeneration

Forward overdrive ladder (issue #171): decision time at 50 / 1 / 0.1 mV, tau,
polarity proof, static current and switching energy, over PVT. Twin of
gf180-comparator's `sim/comparator-regeneration` with identical measure and
check names; the file layout differs by design (DR-008:
`spec/decision-records/DR-008-forward-ladder-bench.md`).

    python3 sim/comparator-regeneration/ladder.py build /tmp/ladder
    klt sim /tmp/ladder/request-process.json --format json -o /tmp/ladder/out-process > /tmp/ladder/resp-process.json
    ... (temperature, supply, graded-cold, graded-hot)
    python3 sim/comparator-regeneration/ladder.py grade /tmp/ladder/resp-*.json
    # negative control: build --sabotage-polarity, grade --expect-fail

`testbench/ladder.json` holds measure expressions, `.meas` cards and checks;
`ladder.py` generates the circuit body and the requests; `klt sim` runs them
(batch fleet on a dispatch worker). `klt sim` cannot express per-axis spread
floors, so `ladder.py grade` evaluates them. Why the grid is five small
requests and not one 45-point request: the first record's "Fleet submit"
section. `records/` is append-only.

Supplemental reverse ladder (issue #170, DR-008 addendum): mirrored
instances (HIGH->LOW decision, same rungs/strobes/window) appended after the
forward netlist and declared under `ladder.json`'s separate `reverse_ladder`
key; names `td_od*_rev_ns`, `tau_rev_ps`, `dout_*_rev_first/_end`,
`dtd_*_rev_ps`, `dtau_rev_ps`. REPORTED, NEVER SCORED: no klt-sim limits, no
ratified row, and `grade` exits on forward checks only (it prints reverse
results as REVERSE lines). Forward netlist and fields are unchanged (pinned by
a test); `build --no-reverse` regenerates the forward-only deck. Negative
control: `build --suppress-reverse-flip`, then `grade --reverse --expect-fail`.
Extracted-DUT trip-point centring (gf180 `dut_vos`) is not implemented.
