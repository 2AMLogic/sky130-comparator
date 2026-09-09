# sim/ — harness and evidence-record format

This directory holds the simulation harness (`sim/harness/`, driven by
`sim/run_corners.py` and `sim/monte_carlo.py`), the testbenches it runs, and
the results those runs produce.

Results are **append-only evidence**: once a record is written it is never
edited or deleted. A re-run — even one that corrects a mistake — mints a new
record with a new ID; a correction references the record it supersedes rather
than overwriting it in place.

This convention exists because `CLAUDE.md` commits this repo to two rules that
need a concrete schema to be enforceable:

- **Verification is the product.** No claim without a testbench. PVT corners
  on every recorded result (see "Corner matrix run" below).
- **`sim/` results are append-only evidence.** Re-runs get new records;
  records are never edited or deleted.

## Provenance

Per `spec/porting-plan.md`'s "Next steps" item 2, this harness is **ported
from `2AMLogic/sky130-sar-adc` rather than designed from scratch** (issue
#8) — that repo targets the identical PDK (sky130), so the port needed no
adaptation beyond docstrings/comments (no CDAC/sequencer-specific code
existed to strip; every module was already PDK/ADC-generic).

| Piece | Ported from | Commit |
| --- | --- | --- |
| `sim/harness/*.py` (all 11 modules), `sim/run_corners.py`, `sim/monte_carlo.py`, `sim/toolchain.json`, `sim/env.sh`, `sim/spiceinit`, `sim/pdk.json`, `sim/selftest.sh`, `sim/tests/test_harness.py`, `sim/harness-corner-smoke/`, `sim/mc-smoke/` | `2AMLogic/sky130-sar-adc` `sim/` | `b80c144efbf467a586f728726cabb25c1eb5a1f2` |

That repo's own harness is itself ported/adapted from two further sources,
credited there and carried forward here for the complete citation trail:

| Piece | Ultimate origin | Commit |
| --- | --- | --- |
| Record format, `<record-id>` / `<corner-id>` schemes, append-only + `Supersedes` semantics, `sim/harness/` module split, `sim/toolchain.json` pin-check convention, `sim/env.sh` | `2AMLogic/gf180-sar-adc` `sim/` | `f613571aee5b80eff1eea37bdce9dfc88c5cf396` |
| sky130 PDK plumbing: `sim/pdk.json` schema, `sim/spiceinit` (byte-identical), `sim/xschemrc` template | `2AMLogic/sky130-bandgap` `sim/` | `1f04e8524cc2d8c2c7154773749b1b2d3be2ce64` |

Every ported `sim/harness/*.py` module carries its own per-file provenance
docstring citing the exact sky130-sar-adc commit above (issue #8's own
requirement), in addition to this table.

Divergences from `sky130-sar-adc`'s harness, each deliberate:

1. **This repo's target-spec table is DRAFT, not ratified** (see the
   top-level README and `spec/README.md`). Nothing under `sim/harness/`
   hardcodes a numeric spec value either way — `corners.py` supplies only
   PDK-derived axis lists (which `.lib` process-corner sections exist, the
   canary-standard −40/27/125 °C sweep); every testbench manifest states
   its own `nominal_supply_v` and checks, unchanged from the port source.
2. **No comparator schematic exists yet.** Every experiment directory
   under `sim/` at this pass (`harness-corner-smoke/`, `mc-smoke/`) is a
   harness self-test, not a DUT — see "Harness self-test experiments"
   below. `sim/comparator-decision/`-style experiments (regen/offset/
   noise, per `spec/porting-plan.md`) are tracked separately (issue #9)
   and explicitly out of scope for this harness-bootstrap pass.
3. **`run_klt_yield()` (in `sim/harness/evidence.py`) has no caller yet.**
   It ported ahead of a caller existing so a future statistical-row
   experiment driver here does not need a second port pass; it is inert
   until one exists.

## Quick start

```sh
python3 sim/run_corners.py --check-env        # toolchain + PDK pin check
python3 sim/run_corners.py --list             # available experiments
source sim/env.sh                             # export PDK_ROOT / PDK

python3 sim/run_corners.py <experiment> --record
python3 sim/monte_carlo.py  <experiment> --seed 1 --n 100 --record

sim/selftest.sh                               # the harness acceptance test (one command)
```

`--check-env` distinguishes its failure modes on purpose: exit **3** means a
tool or the PDK is simply *missing* (skippable on an unbootstrapped machine),
exit **1** means everything is installed but a pinned version *drifted* — a
real problem, because results from a drifted toolchain are not comparable with
the records already in this directory.

**Verified in this repo's own bootstrap run (issue #8):** `sim/selftest.sh`
passes end to end (unit tests, environment check, the PVT corner run, the
Monte Carlo run and its negative control, and the `--sabotage-corners`
negative control) against `ngspice-46`, `xschem 3.4.7`, and the pinned
`open_pdks` commit below — see `sim/harness-corner-smoke/records/` and
`sim/mc-smoke/records/` for the resulting evidence records.

## Harness self-test experiments

Two of the experiment directories here are **harness proofs, not design
claims**, and neither will ever substantiate a spec row:

- **`harness-corner-smoke/`** — an ideal resistive divider (PVT-invariant
  control) plus a diode-connected `nfet_01v8` at a fixed 10 µA bias
  (process/temperature-sensitive probe). Its per-axis sensitivity checks prove
  the corner runner actually switches the `.lib` process-corner section, the
  `.temp` card, and `vdd_val` — independently, so a bug on one axis cannot
  hide behind a pass on another.
- **`mc-smoke/`** — one small diode-connected `nfet_01v8`, drawn N times at
  the `tt_mm` local-mismatch corner, with N deterministic draws at the plain
  `tt` corner as the negative control.

They exist because issue #8 stands the harness up *before* any comparator
schematic exists. Once a real testbench lands (issue #9's
`sim/comparator-decision/`-style experiment, per `spec/porting-plan.md`),
it adds an experiment directory alongside these and reuses the same two
runners unchanged; these two stay as the regression that proves the
plumbing still works.

## Directory / naming convention

```
sim/
  <experiment-slug>/                 # e.g. harness-corner-smoke, mc-smoke,
                                     # comparator-decision (future, issue #9)
    testbench/
      tb.json                        # manifest: netlist fragment, PVT axes,
                                     # measurements, checks
      <fragment>.spice               # SPICE fragment (devices/sources only)
    netlist-snapshots/
      <record-id>.spice              # frozen DUT netlist used for this record
    corners/
      <record-id>/
        <corner-id>.log              # raw ngspice output per PVT point
    mc-draws/
      <record-id>/
        draw_<i>_seed<n>.log         # raw ngspice output per Monte Carlo draw
        negctrl_<i>_seed<n>.log      # ... and per negative-control draw
    records/
      <record-id>.md                 # append-only summary record
```

- **`<experiment-slug>`** — short kebab-case name for *what is being
  verified*, one directory per distinct claim, not per run.
- **`<record-id>`** — `<YYYYMMDD>-<HHMMSS>-<short-git-sha>`, e.g.
  `20260909-054846-0b160a2`. Minted by `sim/harness/evidence.py`. The same
  `<record-id>` ties together the netlist snapshot, the raw logs, and the
  summary record for one run.
- **`<corner-id>`** — `<process>_<temp>c_<supply>v`, e.g. `ss_-40c_1.62v`,
  `tt_27c_1.80v`.
- **`testbench/`** is *not* versioned per record; it holds the current
  testbench. If it changes in a way that affects comparability across records,
  say so in the new record's note. (The per-record `netlist-snapshots/` copy
  and the netlist SHA-256 stamped into every record are what make a stale
  comparison detectable.)

### `tb.json` manifest

```jsonc
{
  "name": "<experiment-slug>",
  "description": "...",
  "claim": "top-level README's target-spec table — <row> (or: None — harness self-test)",
  "netlist_fragment": "<fragment>.spice",
  "nominal_supply_v": 1.8,          // stated per testbench, never in harness code
  "supply_tolerance": 0.10,
  "temperatures_c": [-40, 27, 125],
  "process_corners": ["tt", "ss", "ff", "sf", "fs"],
  "measure": { "<name>": "<ngspice expression>" },
  "checks": {
    "<name>": {
      "min": 0.3, "max": 1.2,
      "min_spread_pct_by_axis": { "process": 1.0, "temperature": 3.0 },
      "max_spread_pct_by_axis": { "supply": 0.001 },
      "description": "why this check exists"
    }
  }
}
```

The fragment is a plain SPICE deck fragment (devices and sources only) that
refers to `{vdd_val}` for its supply. The harness prepends the `.lib` corner
include, `.temp`, `.param vdd_val`, and (for Monte Carlo) `.option rndseed`,
and appends the `.control`/`let`/`print` block built from `measure`.

`min_spread_pct_by_axis` is this harness's sharpest tool and deserves a note:
it asserts a measurement *must* move by at least some amount along a given PVT
axis. That is what catches the failure mode a corner runner is most prone to —
silently simulating typical everywhere while printing a plausible-looking
table. `sim/selftest.sh` stage 4 exercises exactly this (see below).

### Corner-grid shape (one-at-a-time, not full factorial)

`sim/run_corners.py` runs a baseline point plus, for each axis in turn, every
other value on that axis with the remaining two axes held at baseline. This is
precisely the set the per-axis sensitivity computation consumes, and a single
ngspice invocation against sky130's combined model library costs ~15–20 s on
the reference toolchain (library load dominates, not the simulation). A record
therefore states 9 points where a full grid would state 45, at no loss of
per-axis signal (verified empirically in this repo's own bootstrap run —
`sim/harness-corner-smoke/records/`). A record whose claim genuinely needs
corner *interactions* (e.g. worst-case ss/−40 °C/low-supply simultaneously)
must say so and run those points explicitly — the OAT default is a cost
choice, not a statement that interactions do not exist.

## Summary record format

Each run writes one `records/<record-id>.md`. All records carry the base
fields.

### Base fields

- **Record ID** — matches the filename and the `netlist-snapshots/` /
  `corners/` / `mc-draws/` subdirectory names.
- **Claim** — which spec parameter/line this record substantiates (a row in
  the top-level README's target-spec table), or an explicit "None — harness
  self-test". This repo's target-spec table is currently **DRAFT** (see
  `spec/README.md`) — a claim naming a draft row must say so; a DRAFT value
  is never quoted as if settled.
- **Netlist provenance** — `schematic` (`design/...`) or `extracted`
  (post-layout, `layout/...`).
- **Corner matrix run** — the explicit (process, temperature, supply) points
  actually executed, with a count.
- **Statistical convention** — for Monte Carlo records; see below.
- **Result** — per-corner pass/fail plus an overall verdict.
- **Environment** — PDK variant + resolved open_pdks commit, ngspice version,
  harness version, git commit + branch + **dirty flag**, and the DUT netlist's
  **SHA-256**. Written by `sim/harness/evidence.py`; a record produced from a
  dirty tree says so rather than pretending otherwise.
- **Supersedes** — the prior `<record-id>` this record replaces, or `(none)`.

#### Subset-corner justification

A record may legitimately run fewer than the full matrix (a mismatch
distribution at nominal PVT only, a bounded sweep to keep runtime tractable).
That is allowed, but the record must **state which corners ran and why the
rest were omitted**. An unexplained subset is not a valid record.

#### Correction-supersession vs distinct-claim

`Supersedes` is only for a record that **replaces** a prior result for the
*same claim* (a correction, or a schematic → extracted re-run). A record
testing a *different* claim about the same DUT leaves `Supersedes` empty, even
when the two are closely related.

## Monte Carlo records

`sim/monte_carlo.py` writes a record that additionally states:

- **Statistical convention** — the mismatch corner used (`<corner>_mm`), the
  **sample count N**, the **base seed** (draws use `seed, seed+1, …,
  seed+N−1`, so the exact draw set is reconstructible), and the fixed PVT
  point the draws were taken at.
- **Distributions** — per measurement: N, mean, stdev, min, max. A
  distribution, not a corner point; this repo's offset-sigma row (top-level
  README, DRAFT) will be a statistical row once a comparator schematic
  exists, per `spec/porting-plan.md`.
- **Negative control** — N draws at the *plain* (non-`_mm`) corner with the
  same seed sequence, which must reproduce every measurement **exactly**
  (stdev == 0).

The negative control is the load-bearing part. sky130's per-instance mismatch
is gated by `MC_MM_SWITCH`, entered through the `_mm` `.lib` sections; at a
plain corner the `AGAUSS()` terms inside the device subcircuits are disabled,
so `rndseed` has no effect at all. A nonzero negative-control stdev therefore
means either mismatch leaked into the disabled corner or the measurement is
seed-sensitive for some unrelated reason — either way the accompanying
distribution is not trustworthy and the record is marked FAIL. Conversely a
zero-stdev control alongside a nonzero-stdev `_mm` distribution is direct
evidence that the spread reported is device mismatch and not harness noise
(exactly what `sim/mc-smoke/records/` shows).

## Extracted vs schematic semantics

**Netlist provenance** states `schematic` or `extracted`. A post-layout
extracted re-run of an existing claim lives in the *same* experiment directory
with its own `<record-id>`, `Netlist provenance: extracted`, and a
`Supersedes` field, carrying the schematic-vs-extracted delta in its Result
section. The extracted record **appends alongside** the schematic one; it
never replaces or edits it.

## Append-only rule

`records/*.md` are never edited or deleted after creation, and neither are the
raw logs under `corners/` / `mc-draws/` or the snapshots under
`netlist-snapshots/`. This applies even to typo fixes: the append-only
guarantee is what makes `sim/` usable as an evidence trail, and "just fixing"
a record in place defeats it. Note that `.gitignore` carves `*.log` exceptions
for `sim/*/corners/**` and `sim/*/mc-draws/**` precisely so this raw evidence
is committed rather than swept up by the generic log-ignore rule.

## The harness acceptance test (`sim/selftest.sh`)

`sim/selftest.sh` is the harness's own gate — the one-command runner this
issue's acceptance criteria ask for:

| Stage | What it proves | Needs PDK? |
| --- | --- | --- |
| 1/4 | `sim/harness/*` unit tests (`sim/tests/`) | no |
| 2/4 | toolchain + PDK pin match `sim/toolchain.json` | — |
| 3/4 | `harness-corner-smoke` PVT run and `mc-smoke` Monte Carlo run (incl. its negative control) both pass end to end | yes |
| 4/4 | **negative control**: re-running `harness-corner-smoke` with `--sabotage-corners` (the process-corner `.lib` section forced to `tt`, everything else untouched) must **FAIL** its process-axis sensitivity floor | yes |

Stage 4 is the one that matters most. Stages 1–3 can all pass while the corner
runner silently simulates typical everywhere — every number would look
plausible and every downstream record would be worthless. Stage 4 is the check
that a pass means something.

On a machine without ngspice or the pinned PDK, stages 3–4 **skip** (exit 0
with a loud SKIP) so headless CI stays useful; `--require-pdk` turns that skip
into a failure, and `--quick` stops after stage 2. A *drifted* toolchain never
skips — it fails.

Stage 2 distinguishes drift from a warning by asking which tool the evidence
depends on. ngspice below the pinned floor, or a different open_pdks commit,
is **fatal**: every number under `sim/` comes out of ngspice reading the PDK
model library, so those make records incomparable. A differing **xschem**
version is a **warning**: xschem only turns a schematic into a netlist, and
each record already pins the exact netlist it ran by SHA-256, so the drift is
reported and recorded without blocking a PVT run.

Runtime: the default run is 17 ngspice invocations, ~5 minutes measured on
this repo's own bootstrap toolchain (`ngspice-46`) and dominated by sky130
model-library load (~15–20 s per invocation, largely independent of the
circuit). `--full` runs the complete corner grid and a larger Monte Carlo N
and is meant as a deliberate periodic deeper pass. On a runner without
ngspice or the PDK it costs seconds.

## PDK / toolchain pins

`sim/pdk.json` pins the sky130 PDK family/variant and the exact `open_pdks`
commit every record is expected to run against; `sim/toolchain.json` pins
the ngspice/xschem/python floors `sim/harness/toolchain.py`'s `check_env()`
checks before any simulation runs. Both are kept identical to
`2AMLogic/sky130-sar-adc`'s and `2AMLogic/sky130-bandgap`'s pins across this
workspace's sky130 canaries, for PVT/model provenance consistency — see each
file's own `notes` / `_comment` field for the full rationale and citation
chain.

## Environment setup

See [`docs/environment-setup.md`](../docs/environment-setup.md) for the
step-by-step volare/xschem/ngspice bootstrap against the pins above (a dated
toolchain-versions table, the `sim/pdk.json` `install_command`, `sim/env.sh`
usage, and a final `sim/run_corners.py --check-env` verification step).
`sim/pdk.json`'s `install_command` and `sim/toolchain.json`'s pinned versions
remain the authoritative install target; `sim/run_corners.py --check-env`
tells you whether the current machine matches them.
