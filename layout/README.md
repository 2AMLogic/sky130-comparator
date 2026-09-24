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
