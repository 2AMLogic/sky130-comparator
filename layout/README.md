# layout/

Physical layout for the comparator block, klayout-tools (`klt`) driven.

## What is committed

| File | What it is |
| --- | --- |
| `comparator.gds` | The composed layout — one top cell `gen_compose_0`, all 16 devices of `sim/comparator-decision/testbench/comparator_core.spice`, all 12 nets (7 ports + 5 internal), body ties drawn. |
| `gen_comparator.py` | The reviewable source of the GDS: `klt gen` per device group, explicit floorplan, a deterministic met1/met2 channel router, `klt draw` + `klt gen-compose` (placer only), and the verification flow (per-block DRC, composed DRC, `klt extract` device count, the repo-root signoff DRC that writes `drc-report.json`, and the repo-root signoff LVS — plus the coverage-probe matrix — that writes `lvs-report.json` and `lvs-coverage-probe.json`). |
| `compose-report.json` | The `klt gen-compose` response for the committed GDS (evidence). |
| `route-summary.json` | Per-net wiring metrics and the differential wire-area symmetry numbers below. |
| `drc-report.json` | The committed `klt drc` envelope over the committed GDS — T1 item 3's cited evidence (`manifests/sky130-comparator.json`). `status: "clean"`, 0 violations, deck identified by content hash, and the `coverage` block whose three disclosure fields are quoted in "DRC signoff" below. |
| `lvs-report.json` | The committed `klt lvs` envelope over the committed GDS against the schematic netlist. `status: "match"`, 0 errors, 16/16 devices and 12/12 nets paired, engine `klayout`. **Committed as evidence but deliberately *not* cited for T1 item 4** — read "LVS: run, committed — and why T1 item 4 is still not claimed" below before quoting the verdict. |
| `lvs-request.json` | The `klt lvs` request document behind that envelope, committed because the response echoes the input paths and `options` but *not* `reference.form` / `reference.device_map` (klayout-tools#2459) — without it the envelope would not record the device-class mapping the compare was reached through. |
| `lvs-coverage-probe.json` | The negative-control matrix behind that envelope: eight extra `klt lvs` compares against perturbed scratch copies of the reference netlist, each asserting the verdict it must produce. Three prove the compare can fail (so the `match` is not vacuous); five measure the drawn resistor geometry it does and does not compare — including the two forced-parameter rows that report the drawn-vs-schematic width delta as `device.property` `w_um` 0.42 vs 0.35. |
| `extract-device-count.json` | The independent device-count check: `klt extract` over the committed GDS re-derives the 16 devices counted by model from the extracted netlist (9 `nfet_01v8`, 4 `pfet_01v8`, 3 `res_high_po`), not from the generator's own parameters. Raw pre-merge counts (11 nfets — the input pair's cross-quad legs) are recorded beside the merged ones. Re-asserted on every push by `scripts/check-layout-device-count.py` (CI job `layout-device-count` in `.github/workflows/t1-signoff.yml`, hermetic selftest included). |

Generation (regenerates the GDS and every evidence file, ~1 min):

```sh
python3 layout/gen_comparator.py           # regenerate + verify + emit
python3 layout/gen_comparator.py --check   # byte-compare against the committed GDS
```

`--check` passes: the flow is deterministic (no randomness, no dict-ordering
dependence), so a re-run at the pinned toolchain reproduces
`comparator.gds` byte-for-byte. It also survived the klt 0.5.0 → 0.6.0 bump
(#47) unchanged — the committed GDS is byte-identical across both generator
builds, so nothing in that toolchain move is a geometry change.
`compose-report.json` did move: klt 0.6.0 records a `source_path` +
`source_digest` per placed block (additive; no field removed), so the
compose evidence now pins each `klt gen` block's own GDS by hash.

**Toolchain pin.** `klt` (klayout-tools) **0.6.0** on the **klayout
0.30.10** engine, the same pin as `docs/environment-setup.md` and
`.github/workflows/t1-signoff.yml`; PDK `sky130A` at open_pdks
`c6d73a35f5…` (`~/.volare`, per `sim/pdk.json`). Override the install root
with `--pdk-root`, and the binary with `--klt` (e.g. a venv that holds the
pin). The engine is pinned because klt declares only `klayout>=0.30` and
stamps `provenance.klayout_version_mismatch` against the version it
build-tests on; see `docs/environment-setup.md` for the measurement behind
that pin.

## Method

Devices are 100 % `klt gen` geometry — `diff_pair` (input pair, steering
pair, latch pairs, reset pair, absorber-cap pair), `mos_array` 1×1 (the two
single tail devices, the clock cap), `res_array` (the load pair, folded
`rows=2`; the shaper resistor). Placement and every wire come from the
repo-controlled router in `gen_comparator.py`, emitted through `klt draw`
and merged by `klt gen-compose` used **as a placer only** — its own routing
is not a signoff path (routed legs land li1/met1 spacing violations and a
block with more than one same-block self-net — which a `splits`-interleaved
pair inherently is — can only get one routed; klayout-tools#1386). The split
is safe because every `klt gen` block draws only nwell/diff/poly/licon1/li1:
met1 and met2 belong entirely to the routing cell, so a route cannot short
into a block; only a deliberately placed `mcon` connects them. Both the
method and the router architecture follow the same-PDK precedent
(`2AMLogic/sky130-sar-adc` `layout/comparator/`), adapted to this design's
16-device DR-004 topology; the generator file name follows the gf180 twin's
convention (`gen_comparator.py`).

Matching priorities, in the order the ratified spec rows track them:

1. **Input pair `M_PINN`/`M_PINP`** (W=13, the offset-critical pair):
   `diff_pair --splits 2` — a common-centroid cross-quad interleave of two
   W=6.5 µm legs per device. A linear process gradient across the pair
   cancels to first order.
2. **`R_LP`/`R_LN`**: the two folded rows of one `res_array` (adjacent
   identical bodies, shared environment). Poly-resistor matching is not an
   `_mm` model term on this PDK — layout proximity is the only place this
   matching is addressed.
3. **Steering/latch/reset pairs**: plain `splits=1` A/B placement at full
   width — symmetric under the OUTP↔OUTN swap, proportionate effort.

Routing symmetry is measured, not asserted (`route-summary.json`): wire-area
imbalance **OUTP/OUTN 3.50 %**, **OUTP1/OUTN1 7.82 %**, **VINP/VINN 13.52 %**
(wire area is a proxy for capacitance; the VINP/VINN residual is structural —
the cross-quad's two input nets must cross, one above the pads and one
below, and cannot share a track).

## Floorplan against the input-node parasitic-capacitance risk

DR-004/DR-005 record the asymmetry this floorplan trades against: layout
capacitance at `VINP`/`VINN` **raises** kickback, and the Kickback row's
margin is thin (1.06–1.13× at the DR-004 anchors; a 1 % stretch-bound
breach at `sf`/−40 °C already recorded), while capacitance at
`OUTP1`/`OUTN1` lowers noise but slows the preamp (Decision-time ratified
≤ 1.5 ns vs 0.5375 ns worst graded corner — margin is large).

The trade taken, and what the post-layout re-verification issue (T1 item 7)
should re-examine:

- **The clock shaper (`R_CLKS`, `M_CLKCAP` W=20) and the two W=40 absorber
  caps sit on the far side of the steering pair from the input pair** — the
  `CLKT` trunk set lives at x ≥ 17.3 µm while `inpair` geometry ends at
  x ≈ 8.6 µm and the VINP/VINN trunks at x ≈ 5.1 µm, so the clock net and
  the three largest devices never cross the input region.
- **Input routes are short and symmetric** — VINP/VINN trunks exist only
  beside `inpair` (4.3 µm² / 3.7 µm² of wire).
- **What pays for it**: the `OUTP1`/`OUTN1` nets run long (from the input
  pair's drains past the loads to the absorber-cap gates ~22 µm away),
  adding preamp-output node capacitance — the axis with margin. The
  measured imbalance between the two halves stays single-digit (7.82 %).

### What the post-layout re-verification measured (issue #57, T1 item 7)

The extraction and re-simulation this section anticipated has since run — see
[`sim/comparator-decision/README.md`](../sim/comparator-decision/README.md)'s
"Post-layout records" for the full table and
[`extract_pex.py`](extract_pex.py) for how the extracted DUT is derived.
The trade above is **confirmed, and it cost more on the kickback axis than the
floorplan assumed**:

- **Kickback rose 1.8902 → 2.6767 mV** at `tt`/27 °C (1.42×), clearing the
  ≤ 5 mV target with 1.87× margin but **breaching the ≤ 2 mV stretch figure by
  34 %**. Keeping the clock shaper and the two W=40 caps off the input region
  did not make the input nodes parasitic-free: `klt extract --parasitics`
  reports 117.65 fF of ground capacitance and 17.52 kΩ of series resistance
  across the 12 nets, and the input pair's own routing and star-leg resistance
  are enough to widen the disturbance. This was the predicted direction; the
  magnitude is the new information. (The series-R figure is the extractor's
  coarse single-lumped-star default, dominated by the supply nets and expected
  to be pessimistic there — see the sim README.)
- **The axis "with margin" paid as expected, and then some.** The long
  `OUTP1`/`OUTN1` nets cost 2.12× of pick-off gain (64.4571 → 30.4600 V/V) —
  together with the drawn-vs-schematic load-resistor width delta below — which
  is what pushes decision time 0.4025 → 0.5325 ns (both bounds still cleared),
  offset σ 1.7857 → 2.4446 mV, and input-referred noise 0.5704 → 0.6576 mV rms
  (over the 0.6 mV stretch figure). So the trade landed on the axis it was
  aimed at; that axis simply had less margin against the *stretch* figures than
  against the targets.
- **The 7.82 % `OUTP1`/`OUTN1` wire-area imbalance is not free.** The extracted
  DUT has a **systematic** input-referred offset of 0.6547 mV where the
  symmetric schematic netlist has exactly 0, and the sub-20 mV decision is
  polarity-asymmetric (see the sim README). Wire-area imbalance was committed
  here as a proxy for capacitance imbalance; this is the first measurement of
  what that proxy costs electrically. Quantifying it is tracked as issue #66.

## Body ties

Drawn here even though ERC is graded later (T1 item 11), because a layout
without them is not what item 4's LVS compares: a p-substrate tap
outside every n-well contacted up to GND, and an n-well tap inside the
merged pfet well contacted up to VDD. `klt extract` over the committed GDS
shows every NMOS body on GND and every PMOS body on VDD as real nets — not
a deck-synthesized proxy, which is why `lvs-report.json` records
`body_verification.status: "verified"` rather than `unverified`. (The first compose attempt had the well tap
straddling the n-well edge — its outside half acted as a substrate tap and
extract reported a single merged `GND|VDD` net; the fix, fully inside the
well, is in the committed geometry.)

## Known drawn-versus-schematic device delta (filed as friction)

`res_array` rejects `width_um < 0.42`, so the netlist's 0.35 µm-wide
`res_high_po_0p35` variant is not expressible: the three resistors are drawn
at the generator floor, **0.42 µm**, at the schematic's lengths (22 µm
loads, 1.75 µm shaper). The extraction deck consequently classifies them
`res_high_po` (`w=0.42`), and the drawn sheet-count differs from the 0.35 µm
device's — **~20 % lower resistance for the same length** (R ∝ L/W), which
lands on the preamp's gain and output common mode. Filed generically per
CLAUDE.md's friction protocol as
[2AMLogic/klayout-tools#2407](https://github.com/2AMLogic/klayout-tools/issues/2407);
if a narrower width becomes drawable, the loads should be re-drawn at 0.35 µm
and this README updated.

**Upstream status (checked 2026-09-25).** #2407 is **closed** — merged
upstream as klayout-tools#2436 (2026-09-24), a per-flavour `res_array` width
floor that accepts `width_um >= 0.35` for sky130's `high`/`xhigh` flavours.
It is **not in a released `klt`**: the latest tag is still `v0.6.0`
(2026-09-22), two days before that merge, so the pinned toolchain this repo
grades against still enforces the 0.42 µm floor and the delta above is still
live. Re-drawing the resistors at 0.35 µm is gated on a klt release carrying
#2436 plus a pin bump here; it is not in scope for a signoff-citation change.

**This delta is not closed by the LVS `match` below, which does not detect
it at its default parameter scope — and does detect it when asked to.** Both
halves are measured (`lvs-coverage-probe.json`), and together they are why
T1 item 4 is left uncited; see "Why item 4 is left uncited" below.

## DRC signoff, and the coverage gaps behind "clean" (T1 item 3)

`drc-report.json` is the committed `klt drc` envelope
`manifests/sky130-comparator.json` cites for T1 item 3: `status: "clean"`,
`violation_count: 0`, exit status 0, deck `sky130` identified by content
hash `sha256:a1d90e06…`, over `layout/comparator.gds` at
`sha256:cad5ad55…` — the input hash the manifest **pins**, so a regenerated
GDS renders item 3 `unmet` (stale evidence) instead of silently grading
yesterday's run. The envelope also records `provenance.pdk` (`sky130A`,
open_pdks `c6d73a35f5…`, resolved from the `--pdk-root` flag) and
`provenance.klayout_version_mismatch: false` — the engine that produced it
is the one klt 0.6.0 build-tests against.

`gen_comparator.py` refreshes it with every other deliverable
(`emit_drc_evidence`, which unlike the scratch "[6/7] composed DRC" step
runs from the **repo root** against the emitted GDS — so the envelope
records the path CI resolves and the hash the manifest pins — and refuses
to write anything but a clean verdict). Standalone, the same run is:

```sh
klt drc layout/comparator.gds --deck sky130 --pdk sky130A --pdk-root ~/.volare \
    --format json > layout/drc-report.json
```

**A clean verdict is only as wide as the deck that produced it.** Per
`manifests/design-evidence-tiers.md` item 3, that disclosure is
*claimant-enforced* — `klt signoff` grades item 3 on `status: "clean"`
alone, so a deck with rule-free drawn layers grades `met` exactly like a
fully-covering one. The three fields it requires, quoted verbatim from the
committed envelope's own `coverage` block:

- **`layers_in_stream_without_rules`** (5): `65/44` (`tap.drawing`), `66/13`
  (`poly.res`), `68/5` (`met1.pin`), `86/20` (`rpm`), `94/20` (`psdm`).
  This layout draws all five and the curated sky130 deck carries no rule
  that reads any of them — so nothing about the body-tie **tap** geometry,
  the poly-resistor ID marker, the precision-resistor implant, the P+
  implant, or the met1 pin shapes was checked. Implant
  enclosure/spacing and tap rules are **not** covered by this clean verdict;
  the body ties documented above are geometry this deck cannot grade.
- **`rules_skipped`** (34): `capm.{enclosing.via3.1,separation.via3.1,space.1,width.1}`,
  `capm2.{enclosing.via4.1,separation.via4.1,space.1,width.1}`,
  `met2.enclosing.via2.1`,
  `met3.{area.1,enclosing.capm.1,enclosing.via2.1,enclosing.via3.1,holes_area.1,space.1,width.1}`,
  `met4.{area.1,enclosing.capm2.1,enclosing.via3.1,enclosing.via4.1,holes_area.1,space.1,width.1}`,
  `met5.{area.1,enclosing.via4.1,holes_area.1,space.1,width.1}`,
  `via2.{space.1,width.1}`, `via3.{space.1,width.1}`, `via4.{space.1,width.1}`.
  Each was skipped because a layer it reads is absent from this stream —
  top metal here is met2 and no MIM capacitor is drawn — i.e. "no geometry
  to check", not "checked and waived". The envelope now says so per rule:
  `coverage.inapplicable` carries all 34 with `reason:
  no_applicable_geometry`. The unabridged list is in `drc-report.json`.
- **`deck_scope`** (17): `cap2m, capm, ct, difftap, li, licon, m1, m2, m3,
  m4, m5, nwell, poly, via, via2, via3, via4`. sky130's source decks
  (`sky130.lydrc` / `sky130A_mr.drc`) have no numbered DRM sections to cite,
  so `deck_scope` is the rule-id prefix family each rule claims
  (`klayout-tools` `docs/cli/drc.md` → `coverage.deck_scope`). What it does
  not name matters as much as what it does: **no** implant (`nsdm`/`psdm`),
  density/`areaid`, antenna, or latchup/tap-distance family appears — the
  deck does not attempt those DRM chapters at all, for any layout.

Three positive statements belong beside the gaps. `coverage.layers_checked`
is 9 of the deck's 17 layers — `64/20, 65/20, 66/20, 66/44, 67/20, 67/44,
68/20, 68/44, 69/20` (nwell, diff, poly, licon1, li1, mcon, met1, via,
met2): the entire stack this layout actually draws for connectivity, width,
space and enclosure. `coverage.rules_checked` (23, new in the 0.6.0
envelope) names them rule-by-rule, so "which of the deck's rules actually
ran" is now readable off the evidence instead of inferred from the skipped
list. And `coverage.voltage_domain_warnings` is empty — no `hvi` (75/20)
medium-voltage marker is drawn, so no checked geometry was graded against
the wrong threshold column.

**What the klt 0.6.0 pin changed about this verdict (#47).** The bump off
0.5.0 moved the deck, not the layout: the curated sky130 deck grew from 47
to 57 rules (10 added, none removed) — `met1`–`met5` `area.1` and
`holes_area.1`, transcribed from `sky130A_mr.drc`'s `m1.6`/`m2.6`/`m3.6`/
`m4.4a`/`m5.4` and their `m*.7` holes companions (klayout-tools #1955,
#1976). Before that the deck carried **no area check at all**, so a
sub-minimum-area metal sliver graded clean unlooked-at. Four of the ten
(`met1.area.1`, `met1.holes_area.1`, `met2.area.1`, `met2.holes_area.1`)
actually ran against this layout and found nothing; the other six are the
met3/met4/met5 entries in the skipped list above. **The `met` verdict is
unchanged and the geometry is byte-identical — but the "clean" behind it is
strictly wider than the one 0.5.0 produced.** The deck's content hash moved
with it (`sha256:a903acb1…` → `sha256:a1d90e06…`), which is exactly what
that hash is for.

Two grader-side disclosures arrived in the same bump.
`manifests/t1-signoff-report.json` now records item 3's citation with
`input_verified: true` (klayout-tools #2196 — signoff re-hashes
`layout/comparator.gds` on disk and compares it against the envelope's own
`provenance.input.content_hash`), so `scripts/check-t1-signoff.py` rule 3
gets an affirmative verification instead of the `input_verified: null`
warning it used to emit on every run; and the `coverage` block above is
echoed into the citation itself (#2002), so the three claimant-enforced
disclosure fields sit next to the verdict without re-opening this envelope.

## LVS: run, committed — and why T1 item 4 is still **not** claimed

`klt lvs` runs over the committed GDS, the envelope is committed, and it
reports `status: "match"`. **`manifests/sky130-comparator.json` still carries
no item-4 citation.** This block has a known layout-versus-schematic device
difference — the 0.42 µm-drawn resistors above against the schematic's
`res_high_po_0p35` — and that `match` holds only at klt's default parameter
scope, which compares no resistor geometry at all. Asked to compare it, the
same tool reports the delta as an error. The full reasoning is in "Why item 4
is left uncited" below; the evidence behind it is committed as
`lvs-coverage-probe.json`.

The verdict:

- `engine: "klayout"` — KLayout's native `NetlistComparer` /
  `NetlistSpiceReader`, engine version **0.30.10**, driven by klt **0.6.0**
  (`provenance.klt_version`, `provenance.klayout_version_mismatch: false`).
- `status: "match"`, `error_count: 0`. `counts`: **16/16 devices**, **12/12
  nets**, **7/7 pins** paired.
- Layout side: `layout/comparator.gds` at `sha256:cad5ad55…` — the hash a
  manifest citation would pin (and the one `klt lvs --check` re-hashes), so a
  regenerated GDS is detectable as drift rather than silently graded.
  Extraction deck `sky130` at `sha256:a1d90e06…`.
- Reference side: `sim/comparator-decision/testbench/comparator_core.spice`
  at `sha256:e83be11d…` — **the item-1 netlist**, i.e. what
  `./design/netlist.sh` writes out of `design/comparator.sch`. It was not
  hand-edited for this compare (`./design/netlist.sh --check` asserts that,
  and is the command to re-assert it).
- `body_verification.status: "verified"` — no MOS body terminal was compared
  against a deck-synthesized net. This is the drawn body ties above paying
  off; without them this field would read `unverified`.
- `options.combine_devices: true` — what reconciles the layout's folded input
  pair (two W=6.5 µm legs per device, the common-centroid cross-quad) against
  the schematic's single W=13 µm device. It is the same fold
  `extract-device-count.json`'s `merged_counts` already records, not a
  loosening of the compare.

### `power_connectivity.status: "unchecked"` means the question was never asked

Not "verified". Per `manifests/design-evidence-tiers.md` item 4, `unchecked`
is what every `reference.form` other than `gate-level-verilog` gets, and both
that item and `klt signoff` read it as **"does not apply here"**. The
envelope's own `reason` says why: a SPICE reference carries its own
power/ground pins and nets, so they take part in the ordinary compare rather
than needing the separate per-instance pin-to-net check that exists to cover
the signal-only gate-level form. So: VDD and GND connectivity was compared as
ordinary connectivity, and **nothing here is a statement about the power
grid** — not rail continuity, not IR drop, not EM. Those stay `klt
ring-check` / `klt power` / the DRC deck's business, and T1 item 11 remains
`unmet`.

### Warnings-only mismatches (item 4 requires these listed with the claim)

`mismatch_count: 2`, `error_count: 0`. Both, verbatim from the envelope:

1. `device.placeholder_value` — *"reference device class 'RES_HIGH_PO' was
   converted from a subcircuit call (`request.reference.form:
   "subckt-call"`), so its 'R' value is the literal 0 placeholder on all 3
   reference instance(s) — klt lvs has no PDK sheet-resistance/
   capacitance-per-area data to compute a real one. 'R' was therefore
   excluded from this compare on both sides (layout: 3 instance(s), R
   1733.151997..17394.465547) and the two sides were paired on topology alone
   — that dimension of the compare is not independently verified."*
2. `topology` — *"device class has no counterpart on the other side, but no
   devices of this class were extracted either — not a real topology
   mismatch."* The deck structurally recognises classes this layout does not
   draw (`pnp`, the two `cap_mim` models); zero instances on either side.

### The resistor sizing is outside this compare entirely

This is the disclosure that matters most, and it is **wider** than warning 1
above. Warning 1 says the resistor *value* `R` was excluded. It does not say
that the resistor *geometry* was not compared either — but it was not:
KLayout compares only a resistor class's **primary** parameter (`R`), and
`L`/`W` are secondary parameters that never take part in the compare. With
the primary excluded as a placeholder, **both the value and the width/length
of all three resistors sit outside this compare**, and the two sides are
paired on topology alone.

Established by negative control, not inferred, and **committed** as
`lvs-coverage-probe.json` — see the matrix below. Filed generically as
[klayout-tools#2461](https://github.com/2AMLogic/klayout-tools/issues/2461)
(the report should say this itself, rather than leaving it to a claimant to
discover by perturbation testing).

Stated plainly: **the 0.42 µm-vs-0.35 µm drawn-versus-schematic resistor
width delta above is still open, and this `match` is not evidence against
it.** The delta was not absorbed by a tolerance and not waived by an
exclusion — `parameter_tolerance: null` and `compare_parameters: null` in the
committed envelope are klt's own defaults. But "it is simply not a dimension
this tool compares, for anybody" would be too strong: klt *can* compare it,
via `options.compare_parameters`, and when asked it reports the delta as an
error. That is what the forced rows below measure, and it is why item 4 is
not claimed. Closing the delta needs a re-draw at 0.35 µm once a klt release
carries klayout-tools#2436 — not a parameter scope chosen to make today's run
pass.

### What the `match` actually covers — `lvs-coverage-probe.json`

An LVS envelope states its verdict, not its reach. `lvs-coverage-probe.json`
is the negative-control matrix `gen_comparator.py` runs beside the signoff
compare (`emit_lvs_coverage_probe`): one extra `klt lvs` run per row against
a **perturbed scratch copy** of the reference netlist — the committed netlist
is never written to — each asserting the verdict that perturbation must
produce, with the compared-parameter numbers behind it recorded in the row's
`property_findings`. The generator refuses to commit anything if a row
disagrees. A check that cannot fail grades nothing (`sim/selftest.sh`'s
stage-4 discipline), and a signoff artifact is exactly where that matters.

| Probe | Perturbation | Verdict | Reads as |
| --- | --- | --- | --- |
| `mos_width` | M_PINN W 13 → 12 µm | `mismatch` | MOSFET width **is** compared |
| `mos_length` | M_PINN L 0.5 → 0.6 µm | `mismatch` | MOSFET length **is** compared |
| `connectivity` | M_RST_N drain OUTN → OUTP | `mismatch` | connectivity **is** compared |
| `res_width_as_schematic` | resistors restated at their real `w=0.35` µm against the drawn 0.42 µm | `match` | at the default parameter scope the width delta is **not** detected |
| `res_width_10x` | resistors restated at `w=3.5` µm | `match` | resistor width takes **no part** in the default compare — the delta is not merely inside some tolerance |
| `res_length_2x` | R_LP L 22 → 44 µm | `match` | resistor length is not compared either |
| `res_width_forced_schematic` | as `res_width_as_schematic`, plus `options.compare_parameters: {"res_high_po": ["L", "W"]}` | **`mismatch`** | asked for, the compare **does** report it — `device.property` `w_um`, layout **0.42** vs reference **0.35**, on all three resistors |
| `res_width_forced_drawn` | the forced compare with the reference restated at the **drawn** `w=0.42` µm | `match` | attribution control: the forced mismatch is the width delta itself, not an artifact of forcing parameters in |

A mismatch row's `property_findings` also record the rows klt lists
*alongside* a mismatched pair to explain it (`as`/`ad`/`ps`/`pd` on a MOS,
`r`/`a`/`p` on a resistor) — the subckt-call conversion emits only `L`/`W`
onto a MOS card and a placeholder `0` value onto a resistor card, so those
read `0` on the reference side. They are reported for an already-mismatched
pair, not themselves the cause, which is why the clean run carries none of
them. On the two forced rows they are also the second half of what
klayout-tools#2461 also records: the same run emits `device.parameter_excluded`
warnings saying `A`/`P`/`R` were excluded and then error-severity findings on
those same parameters.

### Why item 4 is left uncited

`manifests/design-evidence-tiers.md` item 4 is "**LVS clean**". This layout is
not: its three poly resistors are 20 % wider than the devices
`design/comparator.sch` specifies, the difference is recorded above, and
`res_width_forced_schematic` shows the tool itself calls that a
`device.property` error the moment the parameter is in scope. A `met` row
would tell a fleet integrator this block's layout matches its schematic,
which is not true.

Item 3's precedent does not reach this case. There, a *disclosed coverage
hole* (rule-free layers, skipped rules) sits behind a `clean` verdict with
nothing known to be wrong inside it. Here a **known defect** sits inside the
hole. Disclosure is the remedy for the first; it is not a remedy for the
second.

The row is not blocked forever:
[klayout-tools#2436](https://github.com/2AMLogic/klayout-tools/pull/2436)
(merged upstream, not yet in a released `klt`) adds a per-flavour `res_array`
width floor that accepts `width_um >= 0.35` for sky130's `high`/`xhigh`
flavours. Once that lands in a released pin, re-drawing the three resistors
at 0.35 µm removes the delta rather than disclosing it, and item 4 becomes
citable from a `match` with nothing hiding behind it — a one-line manifest
change plus a regenerated record. That is the sequence to follow.

### Reproducing it

`gen_comparator.py` refreshes the request, the envelope and the coverage
probe with every other deliverable (`emit_lvs_evidence`,
`emit_lvs_coverage_probe`), from the **repo root** against the emitted GDS —
so the envelope records the relative paths `scripts/check-t1-signoff.py`
resolves and the hash a citation would pin. Standalone:

```sh
klt lvs - --format json < layout/lvs-request.json > layout/lvs-report.json
klt lvs --check layout/lvs-report.json          # re-hash the committed report
```

The **stdin** form is load-bearing: relative paths inside a request *file*
resolve against that file's own directory, while the stdin form resolves them
against the current working directory. Run it from the repo root.

That second command is also a CI step (`.github/workflows/t1-signoff.yml`,
job `signoff`), because it closes a rot hole no manifest citation could see:
**a manifest pins an envelope's layout-side hash only.** A change to
`design/comparator.sch` — and so to `design/netlist.sh`'s output, the
compare's *reference* side — would leave this envelope describing a compare
that no longer describes the design (and would silently do so behind a `met`
row, the day item 4 is citable). `klt lvs --check` re-hashes both sides plus
the extraction deck and exits 3 on drift; verified by appending one comment
line to the reference netlist, which flips it to
`[DRIFTED] environment.reference_sha256`. Cheap mode on purpose: `--rerun`
reconstructs the request from the report's own echoed fields, which omit
`reference.form`/`reference.device_map`, so it fails on reconstruction rather
than on real drift (klayout-tools#2459 again).

`lvs-request.json` carries one thing worth explaining. sky130 spells its poly
resistor twice — the geometry-parameterised primitive
`sky130_fd_pr__res_high_po` (`l`/`w` at the call site) and fixed-width
wrappers that bake the width into the *name*
(`sky130_fd_pr__res_high_po_0p35` is literally `x0 r0 r1 sub
sky130_fd_pr__res_high_po l=l w=0.35`). The schematic uses the wrapper; klt's
extraction deck curates only the primitive, so `reference.device_map` binds
one to the other. `length_param`/`width_param` then point at a parameter name
no call site carries, which makes the conversion carry **no** geometry for
that class. That is not a convenience: klt 0.6.0 rejects a call supplying one
of L/W without the other (*"both 'L' and 'W' must be given together"*), and a
fixed-width wrapper structurally cannot supply W, so without it the compare
does not run at all. It is verdict-neutral at the scope this envelope was
produced under — `res_width_as_schematic` hands the compare the resistors'
real `w=0.35` geometry and gets the identical `match`. Filed generically as
[klayout-tools#2459](https://github.com/2AMLogic/klayout-tools/issues/2459).

### What would strengthen this

Item 4 notes that "a second, independent engine's concurring verdict
strengthens this from 'one toolchain agrees with itself' to a cross-checked
result". `klt lvs` supports `engine: "netgen"`; running it is not attempted
here (netgen is not in this repo's pinned toolchain) and is its own issue.

## What is deliberately not attempted here

Per #3's one-at-a-time convention, each of these is its own issue:

- **A second, independent LVS engine** (item 4's cross-check strengthener):
  the committed verdict is KLayout's alone. Also **plain-element-form
  resistor `R` comparison**, which would need a reference netlist carrying
  real resistances rather than the schematic's PDK subcircuit calls.
- **Post-layout re-simulation** (T1 item 7) and **ERC / power delivery**
  (T1 item 11).

`manifests/sky130-comparator.json` / `manifests/t1-signoff-report.json`
still carry exactly one citation — item 3's. Item 4's envelope is committed
and passing but deliberately uncited; see "Why item 4 is left uncited"
above. **T1 item 2 (Layout) stays
`unmet` / `no_evidence`** even though the GDS it describes is committed:
items 1, 2, 9 and 10 have no `klt` verb behind them, so citing *any*
passing envelope would render them `met` on no topical basis at all
(`klayout-tools` `docs/cli/signoff.md` → "Items 1, 2, 9, and 10: `klt
signoff` cannot check topical relevance"). Leaving it uncited is the honest
row, per `manifests/README.md`. `manifests/integrator-view.json`'s
`gds.path` / `measured_area` are the layout's own record there, validated by
`scripts/check-integrator-view.py`.
