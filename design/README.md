# design/

Schematic source for this repo's comparator, and the command that turns it
into the netlist `sim/` simulates.

| File | What it is |
|---|---|
| `comparator.sch` | The design. xschem schematic of the dynamic latched comparator. Carries its own topology and sizing-rationale text blocks — read those before changing any `W`/`L`. |
| `netlist.sh` | The derivation. Runs the xschem netlister over `comparator.sch` and writes `sim/comparator-decision/testbench/comparator_core.spice`. |

Nothing else lives here yet — see [What is not here](#what-is-not-here).

## The design

A **static resistive-load NMOS preamplifier ahead of a clocked
StrongARM-class latch**, 16 devices: 13 MOSFETs, all
`sky130_fd_pr__{n,p}fet_01v8` (the 1.8 V core flavour — the only
complementary pair sky130 ships, per the top-level `README.md`'s
"Supply / power" row), plus three `res_high_po` poly resistors (the two
preamp loads and the DR-003 shaper resistor).

The topology class is this schematic's own measured choice, recorded in
[`spec/decision-records/DR-004-comparator-preamp-supersession.md`](../spec/decision-records/DR-004-comparator-preamp-supersession.md)
(issue #34): it supersedes DR-001's "No static preamp" ruling (with the
four-corner headroom evidence DR-001 asked a supersession to carry) after
DR-003's measured option table showed the kickback gap unclosable inside
the single-tail class. The double-tail route was evaluated first and
measured still ~1:1 kickback/speed elastic (committed probe deck under
`spec/dr-004-support/`). DR-001's Decision §3 reset property is carried
onto the latch stage unchanged in mechanism; DR-003's soft-clock shaper
stays on the clock port. The sizing, which DR-001 explicitly left open
and DR-004 re-derived against the noise lever, is below (see
[Sizing](#sizing)).

```
                  VDD (static bias: M_PTAIL gate at VDD)
                   │
                 M_PTAIL                the PREAMP: always on,
                   │                    ~22 µA/side, gain A ≈ 13–18 V/V,
                 TAILP                  output CM ≈ 1.1–1.25 V
              M_PINN  M_PINP            (gates VINN / VINP)
                   │      │
     R_LP ── OUTN1        OUTP1 ── R_LN (poly loads to VDD, ~30 kΩ)
     M_C1N ── GND          GND ── M_C1P (absorber MOS caps at OUTx1)

 CLK ──[R_CLKS]── CLKT ──[M_CLKCAP]── GND   DR-003 soft-clock shaper,
                                            τ = R·C ≈ 250 ps; CLKT drives
                VDD                        the latch tail + reset PMOS
     ┌───────┬───┴───┬───────┬───────┐
   M_LATP_P │       │       │   M_RST_P   (cross-coupled latch PMOS,
     │    M_LATP_N  │       │     │        gated by the opposite
     │       │       │       │   M_RST_N   output; reset PMOS gated by
   OUTP    OUTN     OUTN    OUTP           CLKT)
     │       │       │       │
   M_STN_P (gate OUTP1)   M_STN_N (gate OUTN1)   steering pair, sources
              │                │                  on TAIL2
              └────── TAIL2 ───┘
                       │
                  M_TAIL2 (gate CLKT)
                       │
                      GND
```

**Ports** — flat, top level, so the netlist drops straight into the
testbench harness as a DUT fragment: `VDD`, `GND`, `CLK`, `VINP`, `VINN`,
`OUTP`, `OUTN` — **unchanged from every prior revision** (the preamp is
internally biased; no new port). Internal nodes: `TAILP`, `OUTP1`, `OUTN1`,
`TAIL2`, and `CLKT` — the DR-003 soft-clock node: `R_CLKS` from `CLK` to
`CLKT`, `M_CLKCAP` from `CLKT` to `GND`, τ ≈ 250 ps, driving the latch
tail and the two output precharge PMOS so the evaluate onset stays
slew-limited. Reset rests exactly as DR-003 left it: `CLKT` discharges to
`GND` through `R_CLKS`.

**Polarity**: `Vin,diff = VINP − VINN > 0` ⇒ `OUTP` settles high. (`VINP`
drives `M_PINP`, whose drain `OUTP1` falls; `M_STN_P` (gate `OUTP1`)
weakens, `OUTP` is kept high by `M_LATP_P` (gate `OUTN`) while `M_STN_N`
(gate `OUTN1`, the higher static gate) pulls `OUTN` down.)

**Reset** (`CLK = 0`, `CLKT = 0`): the reset PMOS precharge `OUTP`/`OUTN`
to `VDD` — which are also the cross-coupled PMOS pair's gates, so every
latch PMOS sits at `Vgs = 0` exactly, the loop's gain is zero, and reset
is a stable, all-devices-off state: DR-001 Decision §3's mechanism carried
onto this latch stage. The steering pair's gates sit at the preamp's
static CM but `M_TAIL2` is off, so no supply path exists (`TAIL2` floats
to ~the steering Vth and conduction self-limits). The preamp never
resets — it is statically biased at all times, which is the point. This
is verified rather than assumed — see [Verification](#verification).

**Evaluate** (`CLK = VDD`, shaped): `M_TAIL2` grounds `TAIL2`; the
steering pair — carrying the preamp's differential since long before the
edge — discharges the precharged outputs with an `A·Vin` head start
already present, and the PMOS latch regenerates.

## Sizing

All MOSFETs `L = 0.5 µm`.

| Device group | Devices | `W` (µm) | Set by |
|---|---|---|---|
| Preamp tail | `M_PTAIL` | 0.8 | static current (~22 µA/side; the class's supply cost) |
| Preamp input pair | `M_PINN`, `M_PINP` | 13 | offset budget (Pelgrom) + the noise lever |
| Preamp loads | `R_LP`, `R_LN` (`res_high_po_0p35`, L = 22 µm ≈ 30 kΩ solved) | — | gain `A = gm·R` ≈ 13–18 V/V; output CM ≈ 1.1–1.25 V |
| OUT1 absorber caps | `M_C1P`, `M_C1N` | 40 | kickback: absorb the steering gate kick at the preamp outputs |
| Latch steering pair | `M_STN_P`, `M_STN_N` | 8 | steer strength / offset (2nd, referred ÷`A`) |
| Latch tail | `M_TAIL2` | 8 | output descent + regeneration speed |
| Cross-coupled PMOS | `M_LATP_P`, `M_LATP_N` | 16 | trip point near `VDD`/2 (as DR-001 Amd 1) |
| Output reset PMOS | `M_RST_P`, `M_RST_N` | 8 | reset `τ` ≪ reset window, minimise `C_out` |
| Clock shaper resistor | `R_CLKS` (`res_high_po_0p35`, L = 1.75 µm) | — | kickback (DR-003): `τ = R·C` shapes the evaluate onset |
| Clock shaper MOS cap | `M_CLKCAP` | 20 | kickback (DR-003): gate on `CLKT`, d/s/b at `GND`, ~100 fF |

The full derivation is in `comparator.sch`'s own sizing-rationale text block
(read it in xschem, or just read the `.sch` file — it is plain text), in
[DR-001 Amendment 1](../spec/decision-records/DR-001-comparator-topology.md)
(the offset-budget lever), [DR-003](../spec/decision-records/DR-003-kickback-slew-limited-clock.md)
(the two shaper devices), and
[DR-004](../spec/decision-records/DR-004-comparator-preamp-supersession.md)
(the preamp sizing and its measured headroom/noise/speed evidence,
`spec/dr-004-support/`). The load-bearing pieces, in brief:

- **The offset budget comes from this PDK's own mismatch model, not from
  literature and not from a sibling repo.** The only local-mismatch term
  either 01v8 flavour carries is a threshold shift
  `σ = AVT/sqrt(W·L·mult)`, with `AVT_n = 3.356 mV·µm` and
  `AVT_p = 5.856 mV·µm` read straight out of the installed model library.
  The companion β-mismatch (`deltox`) line is commented out in both device
  subcircuits — on this PDK, local mismatch *is* threshold mismatch, which
  is why the budget has no `Vov`-dependent term to trade against.
  `spec/dr-001-support/avt_probe.py` confirms this empirically.
- **The preamp tail is a gate-at-supply switch-like source, not a cascode.**
  `M_PTAIL`'s gate sits at `VDD` permanently, and it rests in deep triode
  (0.13–0.18 V of drop against a 0.54–0.65 V `Vdsat`, across the four
  DR-004 probe corners) — DR-001 Amd 1's "a switch-like tail's `Vdsat`
  budget is recoverable" finding, transferred to this always-on tail.
- **The preamp stack is SHORTER than what it replaced.** Because the load
  is a resistor hanging from the rail, the input pair's saturation margin
  (`Vds,in − Vdsat,in`) is +0.88…+1.01 V at every probed corner
  (`spec/dr-004-support/preamp_op_probe.spice`) — the headroom clause
  DR-004 supersedes is answered with DR-001's own four-corner discipline.
- **The 13 µm input pair and ~30 kΩ loads are a noise/speed/kickback
  coupled choice, not independent knobs.** The first-cut sizing
  (10 µm / 45 kΩ / ~12 µA per side) measured 0.72 mV input-referred noise
  — inside the ratified 1.0 mV target but over the 0.6 mV stretch bound;
  the committed sizing closes both (0.5704 mV) at unchanged kickback
  margin. Any future re-tuning must re-measure all three rows together
  (DR-004 Consequence 3).
- **The shaper's `τ` is the kickback/decision-time trade, not a matching
  number.** DR-003's measured series (probe-grade, all against this exact
  design) showed the DIP/DIN collapse rate {EM} the source of the kickback
  spike {EM} trades roughly 1:1 into regeneration time however it is
  slowed, so `τ ≈ 250 ps` is picked where the kickback halves-plus
  (144.60 → 85.71 mV post-mitigation record at `tt`/27 °C) while decision
  time at 50 mV overdrive stays under the DRAFT row's 1.5 ns target at
  every probed corner (1.10 ns `tt`, 1.09–1.19 ns `ss`/`ff`). Slower `τ`
  pairs buy more kickback reduction at that ~1:1 rate; DR-003 records the
  measured ladder and stops there deliberately.

**The reset devices are deliberately smaller, relative to the latch, than
the placeholder DUT this design replaced.** Reset speed is nowhere near
binding (`τ` under 100 ps against a 5 ns window); the reset devices' own
drain capacitance sitting on `OUTP`/`OUTN` is what costs regeneration time.

## Regenerating the netlist

`sim/comparator-decision/testbench/comparator_core.spice` is a **build
product** of `comparator.sch` and carries a "do not hand-edit" header. After
any change to the schematic:

```sh
source sim/env.sh
./design/netlist.sh
```

To check the committed netlist is not stale (reads only, exits non-zero on a
mismatch):

```sh
./design/netlist.sh --check
```

The script runs the xschem netlister, strips xschem's `**`-prefixed wrapper
comments and the trailing `.end`, and prepends a provenance header; every
device line is passed through byte-for-byte as the netlister emitted it. It
asserts that exactly 13 MOSFET device lines plus three `XR_` resistor lines
(the DR-004 preamp+latch set, the two preamp loads, and the DR-003 shaper)
came out, so a schematic edit that accidentally drops or duplicates a
device fails loudly instead of silently netlisting.

> **Tooling note.** xschem 3.4.7 exits with status `10` on a *successful*
> batch netlist-and-quit (`-q`) run, so its exit status is not usable as a
> success signal. `netlist.sh` therefore gates on the output instead. This
> is noted here so the next person does not spend an afternoon on it.

## Verification

Every claim about this design traces to a committed, append-only record
under [`sim/comparator-decision/records/`](../sim/comparator-decision/records/).
Regenerate any of them with:

```sh
source sim/env.sh
python3 sim/comparator-decision/run.py --check-env
python3 sim/comparator-decision/run.py reset  --record
python3 sim/comparator-decision/run.py regen  --record
python3 sim/comparator-decision/run.py kickback --record
python3 sim/comparator-decision/run.py regen  --corner ss --temp -40 --record
python3 sim/comparator-decision/run.py noise  --record
python3 sim/comparator-decision/run.py offset --record --n 16 --seed 1
```

`kickback` is the experiment the DR-003 shaper exists for: it drives the
reset→evaluate transient twice {EM} `loaded` (each input through the
target-spec row's own 1 kΩ source impedance {EM} the measurement) and
`ideal` (zero-impedance drive {EM} the control that must collapse to
numerically zero, else the deck is not measuring what it claims). The
DR-002-cited pre-mitigation figure and the DR-003-cited post-mitigation
figure below are same-corner (`tt`/27 °C, 50 mV overdrive) before/after
points of exactly this experiment.

`reset` is the one worth knowing about: it is a reset-integrity **negative
control** paired with a **positive control**. DR-001 Decision §3's
mechanism (a cross-coupled pair whose gate AND source sit at the same rail
during reset has exactly zero loop gain) is carried by the DR-004 latch
stage onto its PMOS pair — the precharged outputs ARE the pair's gates. So
`reset` starts the transient from a deliberately wrong state — outputs
pinned at *opposite rails* — and checks the design rejects it; and it runs
the same check against the `GND`-tied counterfactual (the steering pair's
sources moved from the floated `TAIL2` node to `GND`, nothing else) to
prove the check can actually detect the defect it screens for. The supply
criterion's floor is the preamp's own static current (~42–68 µA across the
matrix), not leakage — the record states this.

## What is not here

- **No xschem symbol** (`comparator.sym`) and no testbench schematics. The
  simulation harness consumes the flat netlist fragment directly, so nothing
  needs a symbol yet; add one when a schematic instantiates this block.
- **No full kickback PVT campaign.** The DR-004 topology pass measured
  three graded PVT anchors (`tt`/27 °C, `ss`/−40 °C, `ff`/125 °C: 1.89 /
  1.86 / 1.77 mV — all inside both the ratified 5 mV target and the 2 mV
  stretch bound), but the `sf`/`fs` skews, a supply sweep, and
  layout-stage re-verification remain open (DR-004 Open items), and the
  stretch margin is thin (1.06–1.13×).
- **The sub-mV overdrive regression at `ss`/−40 °C.** The DR-004 design
  does not resolve a 0.5 mV differential at that corner within any
  measured window (400 ns probe: 11.7 mV separation), where the DR-001
  design resolved it in 2.56 ns. The Decision-time row's bounds are stated
  at 50 mV overdrive and sub-mV decisions sit below the design's own
  ~1.8 mV offset floor in practice — but the trade is recorded, not
  hidden (DR-004 Consequence 4 / Open items).
- **The Supply/power row needs re-anchoring.** The preamp class costs
  ~51–55 µA static plus ~344–564 µA during evaluate (measured,
  `spec/dr-004-support/evaluate_idd_probe.spice`) — ~95 µW static at
  1.8 V against the DRAFT row's 50 µW figure. DR-004 deliberately changes
  no bound; the re-anchoring is an open ratification decision.
- **No ratified spec beyond DR-002's three rows.** The top-level
  `README.md`'s Decision-time and Supply/power rows are DRAFT, so those
  records substantiate no spec row; they are quoted against the DRAFT rows
  only as design intent. DR-004, like DR-001 and DR-003 before it, is
  *proposed* pending PR merge.
