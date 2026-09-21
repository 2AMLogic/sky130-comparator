# design/

Schematic source for this repo's comparator, and the command that turns it
into the netlist `sim/` simulates.

| File | What it is |
|---|---|
| `comparator.sch` | The design. xschem schematic of the dynamic latched comparator. Carries its own topology and sizing-rationale text blocks — read those before changing any `W`/`L`. |
| `netlist.sh` | The derivation. Runs the xschem netlister over `comparator.sch` and writes `sim/comparator-decision/testbench/comparator_core.spice`. |

Nothing else lives here yet — see [What is not here](#what-is-not-here).

## The design

A **single-tail, bottom-tail NMOS-input dynamic latch with no static
preamp**, 13 devices: 12 MOSFETs, all `sky130_fd_pr__{n,p}fet_01v8` (the
1.8 V core flavour — the only complementary pair sky130 ships, per the
top-level `README.md`'s "Supply / power" row), plus one `res_high_po` poly
resistor. The 11-device MOSFET core is DR-001's topology+reset set
unchanged; the extra MOSFET (`M_CLKCAP`) and the poly resistor (`R_CLKS`)
are the DR-003 soft-clock shaper (issue #30) that hangs off the clock port
to reduce input kickback.

The topology and the reset scheme are not this schematic's choices to make:
they were decided, with evidence, in
[`spec/decision-records/DR-001-comparator-topology.md`](../spec/decision-records/DR-001-comparator-topology.md)
(issue #21). This schematic implements that decision. The kickback
mitigation approach (slew-limiting the evaluate onset, rather than the
other candidate families DR-002 listed) IS this design's own measured
choice — recorded in
[`spec/decision-records/DR-003-kickback-slew-limited-clock.md`](../spec/decision-records/DR-003-kickback-slew-limited-clock.md)
with the rejected alternatives' numbers. The sizing, which DR-001
explicitly left open, is below (see [Sizing](#sizing)).

```
 CLK ──[R_CLKS]── CLKT ──[M_CLKCAP]── GND      DR-003 soft-clock shaper,
                                            τ = R·C ≈ 250 ps; CLKT drives
                VDD                          ALL five clocked gates below
     ┌───────┬───┴───┬───────┬───────┐
   M_RST_DIP │     M_LATP_P  │   M_RST_P      (precharge PMOS gated by
     │     M_RST_DIN │   M_LATP_N  │            CLKT, except the cross-
     │       │       │       │     │             coupled latch PMOS,
    DIP     DIN    OUTP    OUTN    ┘             gated by the opposite
     │       │       │       │                   output)
     │       │    M_LATN_P M_LATN_N            cross-coupled latch NMOS,
     │       │       │       │                 sources on DIP / DIN
     └───────┼───────┘       │
             └───────────────┘
    M_INN (gate VINN) drain DIP  ┐
    M_INP (gate VINP) drain DIN  ┘ sources both on TAIL
                 TAIL
                   │
                M_TAIL (gate CLKT)
                   │
                  GND
```

**Ports** — flat, top level, so the netlist drops straight into the
testbench harness as a DUT fragment: `VDD`, `GND`, `CLK`, `VINP`, `VINN`,
`OUTP`, `OUTN`. Internal nodes: `TAIL`, `DIP`, `DIN`, and `CLKT` — the
DR-003 soft-clock node: `R_CLKS` from `CLK` to `CLKT`, `M_CLKCAP` from
`CLKT` to `GND`, τ ≈ 250 ps, and **all five clocked gates (the tail switch
plus the four precharge PMOS) connect to `CLKT`, not `CLK`**, so the whole
evaluate onset together — precharge release and tail turn-on — is
slew-limited by that RC rather than by the 100 ps edge the testbench
drives. Reset rests identically to DR-001's scheme: `CLKT` discharges to
`GND` through `R_CLKS`, so during `CLK = 0` every gate sits exactly where
the pre-DR-003 design put it.

**Polarity**: `Vin,diff = VINP − VINN > 0` ⇒ `OUTP` settles high. (`VINP`
drives `M_INP`, whose drain is `DIN`; `DIN` falls faster, `M_LATN_N` turns
on first and pulls `OUTN` down, leaving `OUTP` at `VDD`.)

**Reset** (`CLK = 0`): all four reset PMOS conduct, precharging **both** the
output nodes **and** the latch NMOS pair's own source nodes `DIP`/`DIN` to
`VDD`. Every latch NMOS is then at `Vgs = 0` exactly, so the
positive-feedback loop's gain is zero and reset is a stable, all-devices-off
state. This is DR-001 Decision §3, and it is verified rather than assumed —
see [Verification](#verification).

**Evaluate** (`CLK = VDD`): reset PMOS off, tail switch on; the input pair
discharges `DIP`/`DIN` at rates set by the inputs, the latch NMOS sources
fall, loop gain rises through unity, and the pair regenerates to the rails.

## Sizing

All devices `L = 0.5 µm`.

| Device group | Devices | `W` (µm) | Set by |
|---|---|---|---|
| Tail switch | `M_TAIL` | 20 | headroom — `Ron` drop at the worst corner |
| Input pair | `M_INN`, `M_INP` | 10 | offset budget (Pelgrom, 70 % of the variance) |
| Cross-coupled NMOS | `M_LATN_P`, `M_LATN_N` | 8 | offset budget (remaining 30 %) |
| Cross-coupled PMOS | `M_LATP_P`, `M_LATP_N` | 16 | `2 × W_latn` ⇒ trip point near `VDD`/2 |
| Output reset PMOS | `M_RST_P`, `M_RST_N` | 8 | reset `τ` ≪ reset window, minimise `C_out` |
| Internal reset PMOS | `M_RST_DIP`, `M_RST_DIN` | 6 | reset `τ` ≪ reset window, minimise `C_DI` |
| Clock shaper resistor | `R_CLKS` (`res_high_po_0p35`, L = 1.75 µm ≈ 2.4 kΩ) | — | kickback (DR-003): `τ = R·C` shapes the evaluate onset |
| Clock shaper MOS cap | `M_CLKCAP` | 20 | kickback (DR-003): gate on `CLKT`, d/s/b and bulk at `GND`, ~100 fF |

The full derivation is in `comparator.sch`'s own sizing-rationale text block
(read it in xschem, or just read the `.sch` file — it is plain text), in
[DR-001 Amendment 1](../spec/decision-records/DR-001-comparator-topology.md),
and, for the two shaper devices, in
[DR-003](../spec/decision-records/DR-003-kickback-slew-limited-clock.md).
The load-bearing pieces, in brief:

- **The offset budget comes from this PDK's own mismatch model, not from
  literature and not from a sibling repo.** The only local-mismatch term
  either 01v8 flavour carries is a threshold shift
  `σ = AVT/sqrt(W·L·mult)`, with `AVT_n = 3.356 mV·µm` and
  `AVT_p = 5.856 mV·µm` read straight out of the installed model library.
  The companion β-mismatch (`deltox`) line is commented out in both device
  subcircuits — on this PDK, local mismatch *is* threshold mismatch, which
  is why the budget has no `Vov`-dependent term to trade against.
  `spec/dr-001-support/avt_probe.py` confirms this empirically.
- **The tail is a switch, not a current source.** Its gate swings rail to
  rail with `CLK`, so it sits in deep triode (18–28 mV of drop against a
  500–610 mV `Vdsat`, across all four DR-001 corners). That is what recovers
  the 125 mV DR-001's planning convention had reserved for `V_dsat,tail`,
  and it is what closes the −58.5 mV `ss`/−40 °C deficit DR-001 flagged as
  this sizing pass's job.
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
asserts that exactly 12 MOSFET device lines plus one `XR_` resistor line
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
control** paired with a **positive control**. DR-001 Decision §3 derives
that a latch whose NMOS sources sit at `GND` during reset leaves the
feedback loop live and the reset state unstable, and cites same-PDK prior
art where exactly that defect was found the hard way, after the fact, at 3
of 9 corners. So `reset` starts the transient from a deliberately wrong
state — outputs pinned at *opposite rails* — and checks the design rejects
it; and it runs the same check against the `GND`-tied counterfactual to
prove the check can actually detect the defect it screens for.

## What is not here

- **No layout, and no `.mag`/GDS.** T1 checklist items 2–4 (issue #3).
- **No xschem symbol** (`comparator.sym`) and no testbench schematics. The
  simulation harness consumes the flat netlist fragment directly, so nothing
  needs a symbol yet; add one when a schematic instantiates this block.
- **No kickback PVT sweep, and no full compliance.** The kickback testbench
  itself exists (issue #26) and DR-002 ratified the row against its
  144.60 mV `tt`/27 °C measurement; the DR-003 pass-1 shaper brings that to
  85.71 mV at the same point ({EM} still ~17× the 5 mV target, so the row
  stays annotated non-compliant in the top-level README). What remains open,
  by DR-003's own record: kickback PVT coverage (the graded record is
  single-corner, like-for-like with the DR-002 citation; DR-003's probe
  matrix brackets `ss`/`ff` at ~80–86 mV), and closing the rest of the gap
  {EM} measured candidates that reach 5 mV all regress a ratified row or
  the draft decision-time row, and the route that does not needs the
  preamplifier/double-tail class DR-001 explicitly scoped out.
- **No ratified spec to grade against.** The top-level `README.md`'s
  target-spec table is DRAFT, so the records above substantiate no spec row;
  they are quoted against the DRAFT rows only as design intent. DR-001 is
  itself still *proposed*, not ratified.
