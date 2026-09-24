# layout/

Physical layout for the comparator block, klayout-tools (`klt`) driven.

## What is committed

| File | What it is |
| --- | --- |
| `comparator.gds` | The composed layout — one top cell `gen_compose_0`, all 16 devices of `sim/comparator-decision/testbench/comparator_core.spice`, all 12 nets (7 ports + 5 internal), body ties drawn. |
| `gen_comparator.py` | The reviewable source of the GDS: `klt gen` per device group, explicit floorplan, a deterministic met1/met2 channel router, `klt draw` + `klt gen-compose` (placer only), and the verification flow (per-block DRC, composed DRC, `klt extract` device count, and the repo-root signoff DRC that writes `drc-report.json`). |
| `compose-report.json` | The `klt gen-compose` response for the committed GDS (evidence). |
| `route-summary.json` | Per-net wiring metrics and the differential wire-area symmetry numbers below. |
| `drc-report.json` | The committed `klt drc` envelope over the committed GDS — T1 item 3's cited evidence (`manifests/sky130-comparator.json`). `status: "clean"`, 0 violations, deck identified by content hash, and the `coverage` block whose three disclosure fields are quoted in "DRC signoff" below. |
| `extract-device-count.json` | The independent device-count check: `klt extract` over the committed GDS re-derives the 16 devices counted by model from the extracted netlist (9 `nfet_01v8`, 4 `pfet_01v8`, 3 `res_high_po`), not from the generator's own parameters. Raw pre-merge counts (11 nfets — the input pair's cross-quad legs) are recorded beside the merged ones. Re-asserted on every push by `scripts/check-layout-device-count.py` (CI job `layout-device-count` in `.github/workflows/t1-signoff.yml`, hermetic selftest included). |

Generation (regenerates the GDS and every evidence file, ~1 min):

```sh
python3 layout/gen_comparator.py           # regenerate + verify + emit
python3 layout/gen_comparator.py --check   # byte-compare against the committed GDS
```

`--check` passes: the flow is deterministic (no randomness, no dict-ordering
dependence), so a re-run at the pinned toolchain reproduces
`comparator.gds` byte-for-byte.

**Toolchain pin.** `klt` (klayout-tools) **0.5.0**, the same pin as
`docs/environment-setup.md` and `.github/workflows/t1-signoff.yml`; PDK
`sky130A` at open_pdks `c6d73a35f5…` (`~/.volare`, per `sim/pdk.json`).
Override the install root with `--pdk-root`.

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

## Body ties

Drawn here even though ERC is graded later (T1 item 11), because a layout
without them is not what item 4's LVS will compare: a p-substrate tap
outside every n-well contacted up to GND, and an n-well tap inside the
merged pfet well contacted up to VDD. `klt extract` over the committed GDS
shows every NMOS body on GND and every PMOS body on VDD as real nets — not
a deck-synthesized proxy. (The first compose attempt had the well tap
straddling the n-well edge — its outside half acted as a substrate tap and
extract reported a single merged `GND|VDD` net; the fix, fully inside the
well, is in the committed geometry.)

## Known drawn-versus-schematic device delta (filed as friction)

`res_array` rejects `width_um < 0.42`, so the netlist's 0.35 µm-wide
`res_high_po_0p35` variant is not expressible: the three resistors are drawn
at the generator floor, **0.42 µm**, at the schematic's lengths (22 µm
loads, 1.75 µm shaper). The extraction deck consequently classifies them
`res_high_po` (`w=0.42`), and the extraction deck consequently classifies them
`res_high_po` (`w=0.42`), and the drawn sheet-count differs from the 0.35 µm
device's. Filed generically per CLAUDE.md's friction protocol as
[2AMLogic/klayout-tools#2407](https://github.com/2AMLogic/klayout-tools/issues/2407);
if a narrower width becomes drawable, the loads should be re-drawn at 0.35 µm
and this README updated.

## DRC signoff, and the coverage gaps behind "clean" (T1 item 3)

`drc-report.json` is the committed `klt drc` envelope
`manifests/sky130-comparator.json` cites for T1 item 3: `status: "clean"`,
`violation_count: 0`, exit status 0, deck `sky130` identified by content
hash `sha256:a903acb1…`, over `layout/comparator.gds` at
`sha256:cad5ad55…` — the input hash the manifest **pins**, so a regenerated
GDS renders item 3 `unmet` (stale evidence) instead of silently grading
yesterday's run.

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
- **`rules_skipped`** (28): `capm.{enclosing.via3.1,separation.via3.1,space.1,width.1}`,
  `capm2.{enclosing.via4.1,separation.via4.1,space.1,width.1}`,
  `met2.enclosing.via2.1`,
  `met3.{enclosing.capm.1,enclosing.via2.1,enclosing.via3.1,space.1,width.1}`,
  `met4.{enclosing.capm2.1,enclosing.via3.1,enclosing.via4.1,space.1,width.1}`,
  `met5.{enclosing.via4.1,space.1,width.1}`,
  `via2.{space.1,width.1}`, `via3.{space.1,width.1}`, `via4.{space.1,width.1}`.
  Each was skipped because a layer it reads is absent from this stream —
  top metal here is met2 and no MIM capacitor is drawn — i.e. "no geometry
  to check", not "checked and waived". The unabridged list is in
  `drc-report.json`.
- **`deck_scope`** (17): `cap2m, capm, ct, difftap, li, licon, m1, m2, m3,
  m4, m5, nwell, poly, via, via2, via3, via4`. sky130's source decks
  (`sky130.lydrc` / `sky130A_mr.drc`) have no numbered DRM sections to cite,
  so `deck_scope` is the rule-id prefix family each rule claims
  (`klayout-tools` `docs/cli/drc.md` → `coverage.deck_scope`). What it does
  not name matters as much as what it does: **no** implant (`nsdm`/`psdm`),
  density/`areaid`, antenna, or latchup/tap-distance family appears — the
  deck does not attempt those DRM chapters at all, for any layout.

Two positive statements belong beside the gaps. `coverage.layers_checked`
is 9 of the deck's 17 layers — `64/20, 65/20, 66/20, 66/44, 67/20, 67/44,
68/20, 68/44, 69/20` (nwell, diff, poly, licon1, li1, mcon, met1, via,
met2): the entire stack this layout actually draws for connectivity, width,
space and enclosure. And `coverage.voltage_domain_warnings` is empty — no
`hvi` (75/20) medium-voltage marker is drawn, so no checked geometry was
graded against the wrong threshold column.

**What the pinned grader cannot show.** klt 0.5.0 predates
`klayout-tools` #2002 (`citation.coverage` passthrough) and #2196
(`input_verified`), so `manifests/t1-signoff-report.json` records item 3's
citation with neither field, and `scripts/check-t1-signoff.py` rule 3 emits
its documented `input_verified: null` **warning** rather than an
affirmative re-hash (gate passes, loudly). Re-graded out-of-band at klt
0.6.0 the identical manifest returns the same `met` verdict with
`input_verified: true` and the `coverage` block above echoed into the
citation. Bumping the repo-wide pin is #47, deliberately not done here.

## What is deliberately not attempted here

Per #3's one-at-a-time convention, each of these is its own issue:

- **LVS-clean** (T1 item 4): not run — no `klt lvs` verdict is claimed. The
  extracted netlist in `_gen/comparator.extract.spice` matches the
  schematic's device list pin-for-pin (verified when generating), which is
  what item 4 will start from.
- **Post-layout re-simulation** (T1 item 7) and **ERC / power delivery**
  (T1 item 11).

`manifests/sky130-comparator.json` / `manifests/t1-signoff-report.json`
carry exactly one citation — item 3's, above. **T1 item 2 (Layout) stays
`unmet` / `no_evidence`** even though the GDS it describes is committed:
items 1, 2, 9 and 10 have no `klt` verb behind them, so citing *any*
passing envelope would render them `met` on no topical basis at all
(`klayout-tools` `docs/cli/signoff.md` → "Items 1, 2, 9, and 10: `klt
signoff` cannot check topical relevance"). Leaving it uncited is the honest
row, per `manifests/README.md`. `manifests/integrator-view.json`'s
`gds.path` / `measured_area` are the layout's own record there, validated by
`scripts/check-integrator-view.py`.
