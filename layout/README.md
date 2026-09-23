# layout/

Physical layout for the comparator block, klayout-tools (`klt`) driven.

## What is committed

| File | What it is |
| --- | --- |
| `comparator.gds` | The composed layout — one top cell `gen_compose_0`, all 16 devices of `sim/comparator-decision/testbench/comparator_core.spice`, all 12 nets (7 ports + 5 internal), body ties drawn. |
| `gen_comparator.py` | The reviewable source of the GDS: `klt gen` per device group, explicit floorplan, a deterministic met1/met2 channel router, `klt draw` + `klt gen-compose` (placer only), and the verification flow (per-block DRC, composed DRC, `klt extract` device count). |
| `compose-report.json` | The `klt gen-compose` response for the committed GDS (evidence). |
| `route-summary.json` | Per-net wiring metrics and the differential wire-area symmetry numbers below. |
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

## What is deliberately not attempted here

Per #3's one-at-a-time convention, each of these is its own issue:

- **DRC-clean signoff** (T1 item 3): the composed layout is DRC-clean under
  `klt drc --deck sky130` today (0 violations, recorded in `_gen/drc.json`
  at generation time), but item 3's graded evidence requires a `klt`
  envelope citation, not an incidental pass.
- **LVS-clean** (T1 item 4): not run — no `klt lvs` verdict is claimed. The
  extracted netlist in `_gen/comparator.extract.spice` matches the
  schematic's device list pin-for-pin (verified when generating), which is
  what item 4 will start from.
- **Post-layout re-simulation** (T1 item 7) and **ERC / power delivery**
  (T1 item 11).

`manifests/sky130-comparator.json` / `manifests/t1-signoff-report.json` are
deliberately **not** decorated by this issue: T1 item 2 stays `unmet` /
`no_evidence` until a `klt` envelope citation exists, per
`manifests/README.md`. Only `manifests/integrator-view.json`'s honest nulls
(`gds.path`, `measured_area`) flip, validated by
`scripts/check-integrator-view.py`.
