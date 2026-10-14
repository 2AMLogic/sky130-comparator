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
section. `records/` is append-only. The reverse-polarity ladder is #170.
Extracted-DUT trip-point centring (gf180 `dut_vos`) is not implemented.
