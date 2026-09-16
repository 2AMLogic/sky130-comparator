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
preamp**, 11 devices, all `sky130_fd_pr__{n,p}fet_01v8` (the 1.8 V core
flavour — the only complementary pair sky130 ships, per the top-level
`README.md`'s "Supply / power" row).

The topology and the reset scheme are not this schematic's choices to make:
they were decided, with evidence, in
[`spec/decision-records/DR-001-comparator-topology.md`](../spec/decision-records/DR-001-comparator-topology.md)
(issue #21). This schematic implements that decision. What it *does* decide
is the sizing, which DR-001 explicitly left open — see
[Sizing](#sizing) below.

```
                VDD
     ┌───────┬───┴───┬───────┬───────┐
   M_RST_DIP │     M_LATP_P  │   M_RST_P      (all PMOS gated by CLK,
     │     M_RST_DIN │   M_LATP_N  │            except the cross-coupled
     │       │       │       │     │            latch PMOS, gated by the
    DIP     DIN    OUTP    OUTN    ┘            opposite output)
     │       │       │       │
     │       │    M_LATN_P M_LATN_N            cross-coupled latch NMOS,
     │       │       │       │                 sources on DIP / DIN
     └───────┼───────┘       │
             └───────────────┘
    M_INN (gate VINN) drain DIP  ┐
    M_INP (gate VINP) drain DIN  ┘ sources both on TAIL
                 TAIL
                   │
                M_TAIL (gate CLK)
                   │
                  GND
```

**Ports** — flat, top level, so the netlist drops straight into the
testbench harness as a DUT fragment: `VDD`, `GND`, `CLK`, `VINP`, `VINN`,
`OUTP`, `OUTN`. Internal nodes: `TAIL`, `DIP`, `DIN`.

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

The full derivation is in `comparator.sch`'s own sizing-rationale text block
(read it in xschem, or just read the `.sch` file — it is plain text), and in
[DR-001 Amendment 1](../spec/decision-records/DR-001-comparator-topology.md).
The two load-bearing pieces, in brief:

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
asserts that exactly 11 device lines came out, so a schematic edit that
accidentally drops or duplicates a device fails loudly instead of silently
netlisting.

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
python3 sim/comparator-decision/run.py regen  --corner ss --temp -40 --record
python3 sim/comparator-decision/run.py noise  --record
python3 sim/comparator-decision/run.py offset --record --n 16 --seed 1
```

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
- **No kickback testbench.** Porting-plan "Next steps" item 4, and the one
  DRAFT target-spec row this design has no measurement for at all. Worth
  noting that this sizing makes the input pair wider than the placeholder,
  which increases `Cgd` and therefore kickback — an explicit, unmeasured
  cost of the offset budget above.
- **No ratified spec to grade against.** The top-level `README.md`'s
  target-spec table is DRAFT, so the records above substantiate no spec row;
  they are quoted against the DRAFT rows only as design intent. DR-001 is
  itself still *proposed*, not ratified.
