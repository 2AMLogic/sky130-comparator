# Pilot note 2026-11-14 -- `regen` as a `klt sim` request on the batch fleet (issue #220)

Not a ratified record: no `Record ID`, no graded corner set, no `limits`. It
answers one question for #127: **can `regen`'s decision time be expressed as a
`klt sim` request, and does the fleet reproduce `run.py`'s number?** Answer:
**yes to both** -- and the better of the two expressions needs no change to
the circuit body at all.

Follows the `kickback` pilot ([`klt-pilot-kickback-20261106.md`](klt-pilot-kickback-20261106.md),
issue #211 / PR #212). `offset`, `noise` and `reset` remain unattempted.

## Result

Decision time at 50 mV differential input, evaluate-relative
(`t_crossing - 5.1 ns`, where 5.1 ns = `RESET_NS + RESET_TR_NS`):

| Corner | Decision time | `run.py` baseline (record) | Delta |
| --- | --- | --- | --- |
| `tt` / 27 C | **0.401379 ns** | 0.4025 ns (`20260922-070800-e084b55`) | **-1.121 ps (-0.278 %)** |
| `ss` / -40 C | **0.352366 ns** | 0.3575 ns (`20260922-071313-e084b55`) | **-5.134 ps (-1.436 %)** |

Both corners are `resolved` in `run.py`'s three-way sense: the
expected-polarity crossing count is 1 and the opposite-polarity count is 0 at
both. No corner errored; report `status: "pass"`, `coverage.nothing_checked:
false`, zero diagnostics.

**The delta is fully decomposed below** -- it is *not* the
"indicative only, PDK revisions differ" caveat the kickback note had to
carry. See "Why the delta is what it is".

## What ran

Canonical leg -- `klt-pilot/regen-request.json` + `klt-pilot/regen-body.spice`:

- The body is `run.py::_regen_deck` at `vindiff = +50 mV`, **unmodified**:
  1.8 V supply, `PULSE(0 1.8 5n 0.1n 0.1n 40n 55.1n)` clock, `Vinp = 0.925`,
  `Vinn = 0.875` (VCM 0.9 +/- 25 mV), `.include ../testbench/comparator_core.spice`.
  It differs from the deck `run.py` generates only in what `klt sim` supplies
  itself (`.lib`, `.temp`, the `.control` block) and in `5n`/`40n` vs
  `5.0n`/`40.0n`. `tran 0.005n 45.1n` is `_regen_deck`'s own.
- Two corners from one request: `corners` is the full cross product
  (`["tt","ss"] x [27,-40]` = 4), narrowed to 2 by the **top-level**
  `exclude`. One job, 2 units.
- The measurement is two `measurements[].crossings` entries on the vector
  expression `v(OUTP) - v(OUTN)`, at `level: 0.9` / `edge: "rise"` and
  `level: -0.9` / `edge: "fall"`, windowed `from: "5.1n"` `to: "45.1n"`.
  `0.9 V` is `DECIDE_THRESHOLD_V` (= `0.5 * VDD`).
- Backend `batch`, `--wait-for-capacity 600`.
- Report `klt-pilot/report-regen.json`; batch receipt and the per-unit
  `corner.cir` / `.spiceinit` under `klt-pilot/out-regen/`. (The per-unit
  `ngspice.log` is *not* committed -- this repo's `.gitignore` excludes
  `*.log` repo-wide. Each log's substance is already in the report's
  `environment.engine_build.version_banner` and per-corner diagnostics.)

Two secondary legs are committed as evidence for the findings below, not as
the result: `*-bdiff*` is the same measurement written as `.meas ... WHEN`
cards against an added behavioral difference node, and `*-bdiff-ngspicelib*`
is that leg again with the other model library.

| Leg | Job id | Elapsed | Model library |
| --- | --- | --- | --- |
| canonical (`crossings`) | `klt-sim-c4def0fed8b8` | 12 s | `libs.tech/combined` |
| `bdiff` (`.meas WHEN`) | `klt-sim-dd7483f18fc1` | 13 s | `libs.tech/combined` |
| `bdiff-ngspicelib` | `klt-sim-c991b3a2facc` | 22 s | `libs.tech/ngspice` |

## Provenance

- Runner `klt` 0.9.0, client `klt` 0.9.2.dev1022+g2a9c52b27ce7,
  `runner_compatibility: match`.
- **ngspice-47** on the fleet, `engine_build_comparison: match`. Note this is
  a change since the kickback pilot, which ran ngspice-46.
- `worker_environment.pdk`: sky130A, `open_pdks f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7`;
  **`pdk_stamp_comparison: match`** -- also an improvement on the kickback
  pilot, where it was `not_comparable (client_stamp_unavailable)`. This matches
  the repo pin `f6eeac7` (PR #180).
- `models_lib_comparison: match`; `models_lib_sha256`
  `48de7c677e2c6e7d09b2559279de9f818be71010a4aa933d728eb4db3b133c84`.
- c7i.4xlarge / m7i.4xlarge spot, us-east-1.
- The two committed baselines were minted on `c6d73a35` and ngspice-46.

## How the decision instant is derived, and how it differs from `run.py`

Two different rules, and the difference is named rather than folded in:

- **`klt sim` (`crossings`, and `.meas ... WHEN` alike) interpolates**: a
  crossing is `t0 + (level - y0)(t1 - t0)/(y1 - y0)` between the two samples
  that bracket the level.
- **`run.py::_classify_decision` takes the first sample at or after the
  crossing** -- it walks the `wrdata` rows and breaks on the first one whose
  `expected_sign * (outp - outn)` exceeds `DECIDE_THRESHOLD_V`. No
  interpolation.

So `run.py`'s answer is **quantized to the 5 ps output grid** (`tstep` =
0.005 ns) and is biased late by up to one full step; the request's answer is
not. The two rules cannot agree exactly except by coincidence.

The two forms of the request agree with each other to 10 significant digits,
so this is a property of the rule, not of the measurement form:

| Corner | `crossings` | `.meas ... WHEN` |
| --- | --- | --- |
| `tt` / 27 C | 5.501379216430e-09 s | 5.501379217e-09 s |
| `ss` / -40 C | 5.452365794600e-09 s | 5.452365794e-09 s |

## Why the delta is what it is

The baselines were minted in a different environment, so a bare fleet-vs-record
delta would confound the rule change with PDK/solver drift. To separate them,
`_regen_deck` was run **locally, one corner at a time** on the *current*
environment (ngspice-47, `f6eeac7`) and `run.py`'s own
`_classify_decision` applied to the resulting `wrdata` -- i.e. the `run.py`
rule, measured now. That gives a bridge value per corner:

| Corner | `run.py` rule, current env | `run.py` rule, baseline record | PDK/solver drift | Rule (interp. vs grid) | Total |
| --- | --- | --- | --- | --- | --- |
| `tt` / 27 C | 0.402500 ns | 0.4025 ns | **0.000 ps** | -1.121 ps | -1.121 ps |
| `ss` / -40 C | 0.352500 ns | 0.3575 ns | **-5.000 ps** | -0.134 ps | -5.134 ps |

- At **`tt` / 27 C the baseline reproduces exactly** -- 0.402500 ns against a
  recorded 0.4025 ns. There is no measurable PDK or solver drift at this
  corner, and the whole -1.121 ps delta is the interpolation rule.
- At **`ss` / -40 C the drift is exactly -5.000 ps, one output sample.** That
  is the grid rule quantizing a small real shift: the true crossing moved far
  enough to fall into the next 5 ps bin down. How far it actually moved cannot
  be recovered from the committed record, because the baseline stored only its
  grid value -- the underlying shift is bounded by (0, 10 ps) and no tighter.

**Consequence worth carrying to #127**: a sub-picosecond change in the circuit
or the models can appear in a `run.py` record as a 5 ps / 1.4 % step, and two
records differing by one grid step may not differ physically at all. The
interpolating rule does not have this failure mode. This is a reason to prefer
the request route for future `regen` records -- but changing `run.py` is out of
scope here and would rewrite the baseline this pilot exists to difference
against.

## Findings on expressing the measurement

1. **No circuit-body change is needed.** `measurements[].crossings` takes a
   one-line vector expression as its `signal`, so `v(OUTP) - v(OUTN)` is
   expressible directly. The canonical leg's body is therefore an unmodified
   `_regen_deck`, and nothing is added to the netlist under test in order to
   measure it.
2. **The `.meas ... WHEN` form cannot do this**, because ngspice requires a
   single vector on a `WHEN` left-hand side. Expressing it that way needs a
   behavioral difference node (`Bdiff DIFF 0 V = v(OUTP)-v(OUTN)` plus a
   `1T` shunt) added to the body -- the `*-bdiff*` leg. It gives the same
   numbers, and `Bdiff` draws no current from `OUTP`/`OUTN` so it does not
   perturb the circuit, but it does mean editing the DUT deck to measure it.
   Prefer `crossings`.
3. **`crossings` grades more cleanly for a three-way outcome.** Zero crossings
   is `value: 0`, `times: []`, `status: "pass"` -- not an error -- so the
   opposite-polarity card needs no `on_unreached` escape hatch, and the report
   carries **zero** diagnostics. The `.meas` form needs
   `on_unreached: "null"` on both cards and still logs two
   `measurement_not_reached` `info` diagnostics. A crossings-only request is
   also a *checked* request: `coverage.nothing_checked` is `false` and the
   status is `pass`, not `not_checked`, despite the pilot declaring no
   `limits`.
4. **The model library is load-bearing and is not interchangeable.** sky130A
   ships two libraries whose `tt`/`ss` sections resolve to different model
   sets: `libs.tech/combined/sky130.lib.spice` (open_pdks' `continuous/`
   models) and `libs.tech/ngspice/sky130.lib.spice` (the legacy per-corner
   `corners/` + `r+c/` set). `run.py` uses **`combined`**
   (`pdk.PdkInfo.ngspice_lib`). Switching only the library moves this
   measurement by:

   | Corner | `combined` (= `run.py`) | `ngspice` | Difference |
   | --- | --- | --- | --- |
   | `tt` / 27 C | 0.401379 ns | 0.401850 ns | +0.471 ps (+0.12 %) |
   | `ss` / -40 C | 0.352366 ns | 0.370397 ns | **+18.03 ps (+5.12 %)** |

   That is an order of magnitude larger than the rule difference this note is
   otherwise about. **The `kickback` pilot's request used
   `libs.tech/ngspice`**, so its committed -0.88 % delta against its own
   baseline folds in an unquantified library effect as well as the PDK-revision
   caveat it names. That note is append-only evidence and is not edited here;
   this is flagged so the number is read correctly, and so any later pilot
   copies `combined`.

## Friction filed

[`2AMLogic/klayout-tools#5651`](https://github.com/2AMLogic/klayout-tools/issues/5651)
-- a `.meas ... WHEN` card with an expression left-hand side passes
`--dry-run` as `valid`, then errors every corner (a paid round trip on the
batch backend), and the resulting diagnostic quotes ngspice's "no such vector"
without naming the `crossings` form that expresses exactly this. Described
generically; it extends #2826's right-hand-side lint to the left-hand side.

Two things looked at and deliberately **not** filed:

- `exclude` nested under `corners` does run the full 4-corner matrix, but
  `klt` emits a named, actionable warning (`"'exclude' belongs at the top
  level of the request"`) that appears in `--dry-run` text and in the
  machine-readable `warnings[]`. Verified; the `--dry-run` gate catches it.
  Reasonable behaviour, not a gap.
- A `crossings` entry writes one `.raw` of its `signal` per entry, so the two
  entries here produced two 469 KB files whose data rows are byte-identical
  (headers differ only in the internal vector name). Mildly wasteful, not
  wrong.

## Caveats and what was not done

- **Only the 50 mV point, only two corners, only the schematic netlist.** The
  full overdrive sweep, the five remaining graded `regen` corners and the
  extracted DUT were all out of scope.
- **No `limits` are declared**, deliberately: the output is a measured number,
  not a graded spec row. Nothing here grades a spec.
- **`run.py` is unchanged** and no ratified record is minted. The baselines
  keep their meaning.
- The four `crossings_*.raw` artifacts the canonical job produced are **not
  committed** (1.9 MB, and duplicated per finding 4's companion note above).
  The extracted `crossings.times` are in `report-regen.json`, which is the
  evidence; the raws are regenerable by re-running the request.
- The local single-corner runs used for the bridge column are a **cross-check,
  not committed evidence** -- they ran outside the repo tree and minted no
  record. Reproduce with `run.py::_regen_deck(info, corner, temp, 50.0, ...)`,
  `ngspice -b`, then `run.py::_classify_decision(..., evaluate_start_ns=5.1,
  expected_sign=1.0)`.
