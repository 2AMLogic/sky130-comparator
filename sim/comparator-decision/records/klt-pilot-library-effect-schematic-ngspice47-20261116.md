# Pilot note 2026-11-16 -- schematic kickback library A/B made single-variable (issue #283)

Not a ratified record: no `Record ID`, no graded corner set, no `limits`. It
refines the "Attribution caveat" section of
[`klt-pilot-library-effect-20261115.md`](klt-pilot-library-effect-20261115.md)
-- the schematic DUT's library A/B there was **two-variable** (its committed
`ngspice`-library leg ran ngspice-46, its `combined`-library leg ngspice-47),
so its +0.89 % bundled library+solver, and the parent note's "< 0.03 %"
bound on the solver share was inferred, never measured. This note adds the
one missing leg: the committed schematic `ngspice`-library request re-run on
ngspice-47. Naming: the `-ngspice47` suffix denotes the **solver version**,
not a model library -- `regen-request-bdiff-ngspicelib.json` already uses the
confusably similar `-ngspicelib` suffix for the *library* axis.

Follows the `*-combinedlib` naming/layout precedent of the parent note (PR
#278): the new request is its committed counterpart
[`kickback-request-loaded.json`](../klt-pilot/kickback-request-loaded.json)
with **exactly one** key changed -- `batch.capacity_wait_s: 0 -> 600` (host
rule; touches fleet queueing only, never the simulation). `models.lib` stays
`libs.tech/ngspice/sky130.lib.spice`: the library is the variable being **held
fixed** here; the solver is the axis. The committed body
[`kickback-body-loaded.spice`](../klt-pilot/kickback-body-loaded.spice) is
reused unchanged -- not copied, not re-netlisted -- so the netlist hash matches
leg A by construction.

## What ran

One leg, `tt`/27 C, same six `.meas` cards and `ngspice_init` precision
options as every sibling; one `klt sim --batch-set` submission (one member),
backend forced to `batch` -- the same provenance as both legs it is
differenced against (`environment.backend.source: "flag"` in all three). The
`ideal` leg is **not** re-run: it measures 0.0000 mV on both nodes at both
ngspice versions and under both libraries (`report-ideal.json` ng-46,
`report-kickback-ideal-combinedlib.json` ng-47), so re-running it would
confirm 0.0000 == 0.0000. Job `klt-sim-1bcd79aae93b` (us-east-1, spot
c7i.8xlarge), `elapsed_seconds: 26`, `state: "done"`, `exit_code: "0"`.

| Term | Report | library | ngspice |
| --- | --- | --- | --- |
| A | [`report-loaded.json`](../klt-pilot/report-loaded.json) | `ngspice` | 46 |
| B | [`report-kickback-loaded-combinedlib.json`](../klt-pilot/report-kickback-loaded-combinedlib.json) | `combined` | 47 |
| C | [`report-kickback-loaded-ngspice47.json`](../klt-pilot/report-kickback-loaded-ngspice47.json) (new) | `ngspice` | 47 |

## Single-variable proof (machine-checkable from the committed reports)

- `environment.netlist_sha256`: **C == A**
  (`4e584841268300653a3e80d1ab0bd247d11c9771ecb96e4ff65475c65fd9928b`) --
  same deck.
- `environment.models_lib_sha256`: **C == A**
  (`17c208a699228f5acb87bf59c09c22a4c4d3937b6766b4957737d34e8e075f64` =
  `libs.tech/ngspice/sky130.lib.spice`) -- same library.
- `environment.models_lib_sha256`: **C != B**
  (B = `48de7c677e2c6e7d09b2559279de9f818be71010a4aa933d728eb4db3b133c84` =
  `libs.tech/combined/sky130.lib.spice`) -- the library axis is really
  different between B and C.
- ngspice binary: C and B share
  `39ca1adb826660324c3626f72bd946ec40704f0f3fc8e243c623f76e24b3eee2`
  (ngspice-47); A ran ngspice-46.

So B - C differs in the library alone among the hashed axes (netlist, PDK
stamp, ngspice binary all equal), and C - A differs in the solver alone
among the hashed axes. Hashes do not pin everything: the leg pairs also
co-vary in un-hashed runner/host fields, itemized under [Provenance](#provenance)
with the reason neither pair treats them as confounds.

## Result

Peak disturbance per input node (`max(max - q, q - min)`; `q - min` is the
worst lobe on both nodes in every leg), `tt`/27 C, 1 kohm per input, 50 mV
overdrive:

| node | A (ng-46) | C (ng-47) | B (ng-47, combined) | **C - A**: ng-46 -> 47 at fixed library | **B - C**: library at fixed ng-47 |
| --- | --- | --- | --- | --- | --- |
| VINN (worst node) | 1.8736 mV | 1.8802 mV | 1.8902 mV | **+0.0066 mV (+0.354 %)** | **+0.0100 mV (+0.533 %)** |
| VINP | 0.5984 mV | 0.6014 mV | 0.6668 mV | **+0.0029 mV (+0.486 %)** | **+0.0655 mV (+10.89 %)** |

Percentages are relative to the earlier leg of each difference (C - A vs A;
B - C vs C). The two single-variable effects arithmetically compound to the
parent note's bundled A -> B deltas -- VINN (1.00354)(1.00533) = +0.889 %,
VINP (1.00486)(1.10892) = +11.43 %, equal to the measured bundles -- but
that agreement is the algebraic identity (C/A)·(B/C) = B/A, not empirical
corroboration: it holds for any values of A, B, C whatsoever, so it cannot
discriminate between "no third term" and "a third term absorbed into one of
the legs", and it bounds no cross-term. What actually excludes the extra
terms the parent note bundled is hash parity across A, B and C
(machine-checkable above): the equal `worker_environment.pdk.stamp_sha256`
(`4ca10280ae9f…`) removes the PDK-revision term, and the equal
`netlist_sha256` (`4e584841…`) removes a deck term. The bundle is therefore
the two measured single-variable effects plus whatever library×solver
interaction exists, as far as the hashes reach: the parity excludes the
PDK-revision and deck terms, while host and runner-image terms are not
hash-pinned (Provenance itemizes the co-varying fields) and are argued
immaterial there, not excluded -- and the library×solver interaction itself
is not measured here (see Caveats).

**The < 0.03 % bound is refuted.** The parent note claimed "ngspice-46 -> 47
and any PDK-revision effect are together bounded by the ~0 % pilot-vs-baseline
residual (< 0.005 mV, i.e. < 0.03 %)". Measured, the solver share alone (C -
A) is +0.0066 mV / +0.354 % on VINN and +0.0029 mV / +0.486 % on VINP --
outside that bound on both nodes, in both its mV and percent forms. The bound
was not just node-local (the curator's finding); it was **library-local**: it
came from B (ng-47, `combined`) matching the `run.py` baseline
(`20260922-070119-e084b55`, ng-46, PDK `c6d73a35`) -- both `combined`-library
decks -- so it pins the ng-46 -> 47 (+ PDK) bundle on the `combined` library
only. On the `ngspice`-library deck the same solver step moves the peak
+0.35 % to +0.49 %. A refuted bound is a measurement, not a failure: the
identity B == baseline stands (re-verified, still < 0.005 mV at recorded
precision), and what it bounds is now correctly scoped.

**The VINP 2.13x divergence is resolved -- and not the way the issue guessed.**
The curator's table showed the bundled schematic VINP delta (+11.43 %) at
2.13x the clean extracted pair's (+5.36 %), leaving open "the bundle carried a
real non-library term on VINP". Measured: it did not. The non-library (solver)
term on VINP is +0.486 %; roughly 10.9 of the 11.4 bundled VINP points are the
library. But the single-variable VINP library effect is **+10.89 % -- not
near** the extracted pair's +5.36 % either (2.03x). The divergence is real and
it is *in the library term itself*: swapping `ngspice` -> `combined` moves the
schematic DUT's small VINP peak about twice as much, relatively, as the
extracted DUT's. The extracted pair is a clean A/B of a *different DUT* and
cannot stand in for the schematic DUT's VINP sensitivity. (On VINN the two
DUTs agree in sign and order of magnitude: +0.533 % schematic vs +0.81 %
extracted, 0.66x.)

## Bearing on the two refined claims

**The parent note's headline "+0.89 % (schematic)" library figure becomes
+0.53 %.** Its worst-node library number was the bundled A -> B delta; the
library's single-variable worth on the schematic worst-node peak is B - C =
+0.0100 mV (+0.533 %), with the ng-46 -> 47 solver bump contributing the other
+0.354 %. The extracted pair's clean +0.81 % is unchanged (it was already
single-variable).

**"Entirely the library" softens to "dominated by the library".** The parent
note read the pilot-vs-baseline identity (B == 1.8902 mV baseline) as "the
library accounts for the entire delta". That identity holds, but the bundled
+0.89 % it absorbs decomposes 60/40: library +0.533 %, solver +0.354 % on
VINN. The library remains the largest single term and the -0.88 % pilot delta
remains nothing circuit-like; it is just no longer *entirely* the library.
`sim/comparator-decision/README.md`'s #278 paragraph is updated to say so;
the PEX note's -15.0 % -> -14.33 % rescaling stands unchanged on its clean
extracted pair.

## Provenance

- Client `klt` 0.9.3.dev39+g205f77baff57, runner `klt` 0.9.0,
  `runner_compatibility: match`; `models_lib_comparison: match`.
- ngspice-47 on the fleet, binary sha256
  `39ca1adb826660324c3626f72bd946ec40704f0f3fc8e243c623f76e24b3eee2` --
  byte-identical to the local host's `ngspice` and to leg B's recorded
  `engine_build.binary_sha256`, so local-vs-fleet is not a solver variable
  (and batch was forced anyway, matching A's and B's
  `environment.backend.source: "flag"`).
- `worker_environment.pdk`: sky130A, `open_pdks f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7`
  (the repo pin) -- same stamp as legs B and the extracted pair; leg A also
  ran `f6eeac7` (2026-11-06 fleet), so the PDK axis is fixed across A, B, C.
- Un-hashed axes co-vary across both leg pairs, so the "single-variable"
  claims above hold among the hashed fields only, not across the whole
  runner stack. C - A also moves the runner AMI
  (`ami-095c25ae241a4d360` on A's 2026-11-06 fleet -> `ami-09c14f55df4958cbd`
  here) and the client `klt` build (0.9.2.dev103+g9f4cec35997a ->
  0.9.3.dev39+g205f77baff57) -- the runner's whole software image, glibc and
  libm included, is not pinned across the solver leg. B - C also moves
  instance type (`m6i.4xlarge` -> `c7i.8xlarge`), CPU (Xeon Platinum 8375C
  -> 8488C), physical cores (8 -> 16), concurrency (1 -> 2), availability
  zone (`us-east-1f` -> `us-east-1a`) and the client `klt` build
  (0.9.3.dev3+gd5d57daf9a14 -> 0.9.3.dev39+g205f77baff57). Neither pair is
  treated as a confound on measured grounds, not by assumption: the hashed
  fields pin the solver binary, deck and PDK where the effects are claimed,
  and across the runner-image move (C - A) the two legs reproduce to well
  under 1e-9 V on the barely-moving max lobes -- `vinn_max` 0.87506960391
  (A) vs 0.87506960412 (C), a ~2e-10 V difference on different ngspice
  builds -- roughly four orders of magnitude below the smallest effect
  claimed here (C - A +0.0066 mV = 6.6e-6 V), so the image/host moves are
  argued immaterial, not excluded.
- us-east-1 spot c7i.8xlarge; submitted 2026-11-16, elapsed 26 s.
- Reports: `klt-pilot/report-kickback-loaded-ngspice47.json` (byte-copy of
  `out-ngspice47/kickback-request-loaded-ngspice47/report.json`, flattened to
  the `report-<leg>.json` convention); per-unit deck and `.spiceinit` under
  the same `out-ngspice47/<request-stem>/` dir; request-to-job mapping in
  [`out-ngspice47/set-manifest.json`](../klt-pilot/out-ngspice47/set-manifest.json).

## Caveats

- One PVT point (`tt`/27 C), same scope as the parent note; no claim about
  other corners.
- Only the `loaded` leg ran. The `ideal` control is kickback-free by
  construction (0.0000 mV at both solver versions -- see the parent note's
  verified corrections), and the extracted (`pex`) pair is already clean
  single-variable; neither was re-run.
- The library×solver interaction is **not measured** and is unbounded by
  anything in this note: the interaction term is (B - C) - (D - A) where
  D = f(ng-46, `combined`), and D was not run. The A -> B bundle absorbs the
  interaction identically -- B - A = (C - A) + (B - C) holds whatever the
  interaction is -- so the compounding check cannot bound it. The same
  fourth leg D would also measure the library effect *at ng-46*.
- `records/klt-pilot-library-effect-20261115.md` is intentionally untouched:
  `sim/` evidence is append-only (`scripts/check-sim-append-only.py`
  byte-freezes committed records); this note is the correction, and cites the
  caveat it refines.
