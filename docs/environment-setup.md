# Environment setup

Bootstrap steps for the open-source analog flow this repo's `sim/` harness
drives: xschem (schematic capture / netlisting) + ngspice (simulation)
against the sky130 PDK, fetched/managed via
[volare](https://github.com/efabless/volare).

This doc is meant to be followed from a shell on a machine that already has
the xschem/ngspice/volare binaries installed — a from-scratch build/install
recipe for those three tools is out of scope here (see "Toolchain versions"
below for what to do if one is genuinely missing). There is no `layout/`
tree or `klt` (klayout-tools) integration in this repo yet, so unlike its
two sibling docs below, this one has no layout/DRC/LVS section.

**Provenance**: this document's structure is adapted from
`2AMLogic/sky130-sar-adc`'s and `2AMLogic/sky130-bandgap`'s own
`docs/environment-setup.md` (both target the identical sky130 PDK — see
`sim/README.md`'s own provenance table for the harness this doc bootstraps
for). The toolchain versions, PDK pin, and paths below are this repo's own,
re-recorded against its own install and `sim/pdk.json` / `sim/toolchain.json`
— only the document shape is carried over, not the numbers.

## Toolchain versions (recorded 2026-09-09)

| Tool | Version | Install path |
| --- | --- | --- |
| xschem | `XSCHEM V3.4.7` | `/usr/local/bin/xschem` |
| ngspice | `ngspice-46` | `/home/ubuntu/.local/bin/ngspice` |
| volare | `Volare v0.20.6` | `/home/ubuntu/.local/bin/volare` |
| python3 | `Python 3.12.3` | `/usr/bin/python3` |

Recorded by running each tool's own version command on the machine doing
this pass — this is a snapshot, not a durable fact; re-run these on your own
machine rather than trusting the table above:

```sh
xschem -v          # -> XSCHEM V3.4.7 ...
ngspice --version   # -> ngspice-46 : Circuit level simulation program ...
volare --version    # -> Volare v0.20.6 ...
python3 --version   # -> Python 3.12.3
```

`sim/toolchain.json` is the machine-checked pin this repo's harness actually
enforces (`sim/harness/toolchain.py`'s `check_env()`, driven by
`python3 sim/run_corners.py --check-env` — see step 4 below): `ngspice_min_major:
46` is a **floor** (newer is fine, older is refused), `xschem_tag: "3.4.7"`
is checked but only ever produces a **warning** on drift (every evidence
record already pins its own netlist by SHA-256, so an xschem difference
doesn't invalidate anything — see `sim/harness/toolchain.py`'s module
docstring), and `python_min: "3.9"` is a floor. `volare`'s own version isn't
pin-checked by the harness at all; it only needs to be new enough to fetch
and enable the `open_pdks` commit pinned below.

If a tool is genuinely missing on your machine, this repo does not document
a from-scratch build recipe for it — install via your platform's package
manager (Homebrew, apt, pipx for `volare`, etc.) and re-run the version
commands above before continuing.

## 1. Verify xschem works headlessly

A bare sanity check that doesn't need any PDK wiring at all — netlist one of
xschem's own stock examples (ships alongside the binary; the exact path
depends on your install, e.g. `/usr/share/doc/xschem/examples/` on a
Debian/Ubuntu package install):

```sh
mkdir -p /tmp/xschem_check
xschem -n -q -x /usr/share/doc/xschem/examples/cmos_inv.sch -o /tmp/xschem_check
ls /tmp/xschem_check   # -> cmos_inv.spice
```

Verified on this pass: exits 0 and writes `cmos_inv.spice` with no
`error`/`warning` lines. If your install doesn't ship that particular
example, substitute any other `.sch` under the same examples directory —
this step only proves the xschem binary itself runs headlessly, not
anything sky130-specific.

## 2. Fetch + enable the sky130 PDK via volare

Use this repo's own `sim/pdk.json` `install_command` verbatim:

```sh
volare fetch  --pdk sky130 c6d73a35f524070e85faff4a6a9eef49553ebc2b
volare enable --pdk sky130 c6d73a35f524070e85faff4a6a9eef49553ebc2b
```

**Why this specific `open_pdks` commit, not "newest available":**
`sim/pdk.json`'s own `notes` field states it is kept identical to
`sky130-bandgap`'s and `sky130-sar-adc`'s pin, specifically so PVT/model
provenance is comparable across every sky130 canary in this workspace — a
newer commit would silently make this repo's numbers incomparable with its
siblings'.

After `volare enable`, `~/.volare` contains PDK variant symlinks:

```sh
ls -la ~/.volare | grep sky130
# sky130A -> volare/sky130/versions/c6d73a35f524070e85faff4a6a9eef49553ebc2b/sky130A
# sky130B -> volare/sky130/versions/c6d73a35f524070e85faff4a6a9eef49553ebc2b/sky130B
```

This repo standardizes on the **`sky130A`** variant (`sim/pdk.json`'s
`variant` field), matching its sky130 siblings.

## 3. Environment convention: `PDK_ROOT` / `PDK`

Rather than hand-exporting `PDK_ROOT`/`PDK` yourself, this repo already
ships `sim/env.sh`, which resolves both by calling `sim/run_corners.py
--print-env` (`sim/env.sh` lines 19-24) — the same resolution the harness
itself uses for every simulation run, so an interactive xschem/ngspice
session sees exactly the PDK the corner runner and Monte Carlo runner would
use:

```sh
source sim/env.sh
# -> sky130: PDK_ROOT=/home/you/.volare PDK=sky130A
```

If it instead prints `sky130: PDK not found -- run 'python3
sim/run_corners.py --check-env'`, the PDK from step 2 above hasn't been
enabled yet (or was enabled at a different commit than `sim/pdk.json`
pins).

## 4. Final verification

Run the harness's own environment check — it exercises the exact same
toolchain/PDK pins as every other step above, in one command:

```sh
python3 sim/run_corners.py --check-env
```

Exit codes (see `sim/README.md`'s "Quick start" and
`sim/harness/toolchain.py`'s own docstring for the full rationale):

- **0** — everything installed and within pin (warnings, e.g. an xschem
  version drift, may still print but don't fail the check).
- **1** — a pinned tool is installed but has **drifted** from
  `sim/toolchain.json` / `sim/pdk.json` (e.g. ngspice below the
  `ngspice_min_major` floor, or a different `open_pdks` commit than pinned)
  — a real problem, because results from a drifted toolchain aren't
  comparable with the evidence already committed under `sim/`.
- **3** — a required tool (ngspice) or the PDK itself is simply **missing**
  — expected and skippable on a machine that hasn't been bootstrapped yet;
  go back to steps 1–2 above.

Once `--check-env` exits 0, the next step is `sim/selftest.sh` — this
repo's one-command harness acceptance test (unit tests, the environment
check again, an end-to-end PVT sweep and Monte Carlo run, and a negative
control that must fail on purpose). See `sim/README.md`'s "The harness
acceptance test" section for what each of its four stages proves and how
long it takes.
