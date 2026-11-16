# Pilot note 2026-11-15 -- the model library, quantified, for the `kickback` and PEX pilots (issue #244)

Not a ratified record: no `Record ID`, no graded corner set, no `limits`. It
answers one question for #244: **how much of the two uninterpretable pilot
deltas is the model library?** Answer: **all of the schematic pilot's -0.88 %,
and none of the PEX note's -15.0 %** -- the library is worth +0.81 % to +0.89 %
on the worst-node kickback peak at `tt`/27 C, on both DUTs.

Follows the `regen` A/B precedent ([`klt-pilot-regen-20261114.md`](klt-pilot-regen-20261114.md),
PR #228): a like-for-like pair differing *only* in `models.lib`, run so the
effect is attributable rather than flagged. `sim/pdk.json` grades every
`run.py`-minted record on `libs.tech/combined/sky130.lib.spice`; the four
merged `kickback`/PEX pilot requests named `libs.tech/ngspice/sky130.lib.spice`
instead. The two libraries are not interchangeable (PR #228 measured the same
swap on `regen`: +0.12 % at `tt`/27 C, +5.12 % at `ss`/-40 C on decision time).

## What ran

The four committed pilot requests re-expressed as `*-combinedlib.json`
variants -- each its committed counterpart with one key changed
(`models.lib` -> `libs.tech/combined/sky130.lib.spice`), plus
`batch.capacity_wait_s: 600` (host rule; the two `kickback` committed
requests carry `0`, which was **not** copied forward). Same netlists, same
`tt`/27 C corner, same six `.meas` cards, same `ngspice_init` precision
options. The four original requests, their reports and both committed notes
are untouched -- `sim/` evidence is append-only, and the CI append-only gate
(`scripts/check-sim-append-only.py`) does not cover `klt-pilot/`, so leaving
them alone is a project-principle choice, not an enforced one.

The request-level diff, in full (one changed line per pair; the `kickback`
pairs also carry the capacity-wait change, which touches fleet queueing only,
never the simulation):

```diff
--- kickback-request-ideal.json        (also kickback-request-loaded.json)
+++ kickback-request-ideal-combinedlib.json
   "models": {"pdk": "sky130A", "lib": "libs.tech/ngspice/sky130.lib.spice"},
-  "models": ...
+  "models": {"pdk": "sky130A", "lib": "libs.tech/combined/sky130.lib.spice"},
-  "batch": {"runner_version_check": "warn", "capacity_wait_s": 0},
+  "batch": {"runner_version_check": "warn", "capacity_wait_s": 600},

--- pex-request-ideal.json            (also pex-request-loaded.json)
+++ pex-request-ideal-combinedlib.json
-  "models": {"pdk": "sky130A", "lib": "libs.tech/ngspice/sky130.lib.spice"},
+  "models": {"pdk": "sky130A", "lib": "libs.tech/combined/sky130.lib.spice"},
```

All four legs went to the batch fleet as **one** `klt sim --batch-set`
invocation (`--wait-for-capacity 600`, four jobs in flight; the
request -> job mapping is committed as
[`out-combinedlib/set-manifest.json`](../klt-pilot/out-combinedlib/set-manifest.json)).
No local run, no grid.

| Leg | Job id | Elapsed | Instance |
| --- | --- | --- | --- |
| `kickback` ideal, `combined` | `klt-sim-e7d6e6175873` | 11 s | m6i.4xlarge spot |
| `kickback` loaded, `combined` | `klt-sim-918a01ac5de7` | 17 s | m6i.4xlarge spot |
| PEX ideal, `combined` | `klt-sim-d58b2264a372` | 13 s | c7i.8xlarge spot |
| PEX loaded, `combined` | `klt-sim-a445a194e08a` | 12 s | c7i.8xlarge spot |

Reports: `klt-pilot/report-{kickback-ideal,kickback-loaded,pex-ideal,pex-loaded}-combinedlib.json`
(byte-copies of the per-member `report.json` under
`klt-pilot/out-combinedlib/<request-stem>/`, flattened to this directory's
`report-<leg>.json` convention); per-unit deck and `.spiceinit` under the
same `out-combinedlib/<request-stem>/` dirs. (The per-unit `ngspice.log` is
not committed -- repo-wide `*.log` gitignore; each log's substance is in the
report's `environment.engine_build.version_banner`.)

## Result

Worst-node peak disturbance (`max(max - q, q - min)` per input node, VINN is
the worst node in every leg), `tt`/27 C, 1 kohm per input, 50 mV overdrive:

| DUT | `ngspice` lib (committed leg) | `combined` lib (new leg) | Library effect |
| --- | --- | --- | --- |
| schematic (`kickback-body-loaded`) | 1.8736 mV (ngspice-46) | **1.8902 mV** (ngspice-47) | **+0.0167 mV (+0.89 %)** |
| extracted (`pex-body-loaded`) | 2.2747 mV (ngspice-47) | **2.2931 mV** (ngspice-47) | **+0.0184 mV (+0.81 %)** |

Per node: VINP 0.5984 -> 0.6668 mV (+11.43 %, schematic) and 0.8692 ->
0.9158 mV (+5.36 %, extracted) -- the small peak moves more in relative
terms, but VINN sets the worst node throughout. The `ideal` controls are
0.0000 mV on **both** libraries and both DUTs (`report-kickback-ideal-combinedlib.json`,
`report-pex-ideal-combinedlib.json`), so the A/B is clean on the leg that
carries the measurement.

Every new report's `environment.models_lib_sha256` is
`48de7c677e2c6e7d09b2559279de9f818be71010a4aa933d728eb4db3b133c84`
(= `libs.tech/combined/sky130.lib.spice`, confirmed by `sha256sum` against
the live PDK at `~/.ciel/sky130A`); every original pilot report's is
`17c208a699228f5acb87bf59c09c22a4c4d3937b6766b4957737d34e8e075f64`
(= `libs.tech/ngspice/sky130.lib.spice`). The hash pair is the proof the A/B
actually swapped libraries. All four legs: `status: "pass"`, zero failed /
errored / inconclusive, `models_lib_comparison: match`.

**Attribution caveat, one leg of it.** The extracted pair is a clean
single-variable A/B (both legs ngspice-47). The schematic pair is not --
its committed `ngspice`-lib leg ran ngspice-46 (2026-11-06 fleet) and the new
`combined` leg ran ngspice-47 -- so its +0.89 % bundles library and solver
bump. The clean extracted pair (+0.81 %, same sign, same size) plus the
regen precedent (+0.12 % on a different measurement) both support reading the
schematic delta as library-dominated, but the schematic +0.89 % is not
single-variable proven. ngspice-46 -> 47 and any PDK-revision effect are
together bounded by the ~0 % pilot-vs-baseline residual below.

## Bearing on the two committed deltas

**The schematic pilot's -0.88 % is the library, and the delta is now
interpretable.** [`klt-pilot-kickback-20261106.md`](klt-pilot-kickback-20261106.md)
compared its `ngspice`-lib pilot (1.8736 mV) against the `run.py` baseline
1.8902 mV (`20260922-070119-e084b55`) and called the -0.88 % indicative only,
confounded by PDK revision and unattributed library. Re-measured on the
grading library, the same pilot reproduces the baseline **exactly at its
recorded precision**: 1.8902 mV vs 1.8902 mV, i.e. **0.00 %**, not -0.88 %.
The library accounts for the entire delta; the remaining methodology
(`.meas max/min` over accepted timepoints vs `run.py`'s peak over sampled
`wrdata` points), ngspice-46 -> 47 and PDK `c6d73a35` -> `f6eeac7`
differences show up as at most the rounding residual (< 0.005 mV, i.e.
< 0.03 %) at this corner. Nothing in the -0.88 % was the circuit or the
`klt sim` route.

**The PEX note's -15.0 % is not the library.**
[`klt-pilot-kickback-pex-20261114.md:131-141`](klt-pilot-kickback-pex-20261114.md)
compared its 2.2747 mV against the post-layout record `20260925-094700-4694692`
(2.6767 mV, -15.0 %) under a confounder table with **six** rows (extraction,
drawn `res_high_po` width, total R/C, ngspice version, PDK revision, peak
rule) -- the model library was absent from it. Measured: the library is worth
+0.81 % there, so on the grading library the delta becomes 2.2931 vs 2.6767 mV
= **-14.33 %**. That makes the library a **seventh** confounder on that
comparison -- real, and now sized -- but it closes roughly 0.7 pp of a 15 pp
gap. The -15.0 % (now -14.33 %) remains dominated by the six named rows, and
separating those is still re-measurement campaign #125's job, exactly as the
PEX note says. That note is pointed at, not edited: `sim/` evidence is
append-only.

**Above or below noise?** The library effect (+0.81 % to +0.89 % on the
worst-node peak at `tt`/27 C) is the **same size as** the -0.88 % delta it
bears on -- far above that delta's noise, which is why it fully accounts for
it. It is roughly **1/18 of** the -15.0 % PEX delta -- far below that gap,
which is why it does not explain it. These are deck-level deterministic
differences (same deck, same models, same engine version within the extracted
pair), not repeated-run noise; no stochastic noise estimate is committed for
`.meas` kickback peaks, and this note does not fabricate one.

## Provenance

- Runner `klt` 0.9.0, client `klt` 0.9.3.dev3+gd5d57daf9a14,
  `runner_compatibility: match` on all four.
- **ngspice-47** on the fleet, `engine_build_comparison: match`.
- `worker_environment.pdk`: sky130A, `open_pdks f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7`;
  **`pdk_stamp_comparison: match`** -- the repo pin (PR #180).
- `models_lib_comparison: match` on all four (client vs runner hash; the
  request-vs-`sim/pdk.json` check still does not exist anywhere -- that gap
  is #244's own recurrence-prevention follow-up, out of scope here).
- us-east-1 spot (m6i.4xlarge / c7i.8xlarge); elapsed 11-17 s per leg; all
  four submitted in one `--batch-set` invocation on 2026-11-15.
- The committed `ngspice`-lib legs this A/B diffs against: ngspice-46
  (`kickback`, job `klt-sim-5f5e3c768c59` / `klt-sim-11100bd3d0e7`) and
  ngspice-47 (PEX, job `klt-sim-9f5b42ac764b` / ideal sibling), PDK
  `f6eeac7` throughout.

## Caveats

- Only the `kickback`/PEX operating point (`tt`/27 C) was measured. The
  `ss`/-40 C library effect is a different, larger number (+5.12 % on
  `regen`'s decision time) and was deliberately not re-measured here --
  #244's scope is the delta the two committed notes actually carry, both at
  `tt`/27 C.
- `offset`, `noise` and `reset` pilots remain unattempted (unchanged from
  the earlier pilot notes).
- The four `*-combinedlib.json` requests and their reports are committed
  evidence of what was actually run; any future correction lands as a new
  note, never an edit.
