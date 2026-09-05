# sky130-comparator — agent instructions

Open-source canary block: a dynamic latched comparator on skywater sky130,
on SkyWater sky130, a 130 nm open CMOS PDK, designed and verified by AI agents.

- **PDK**: SkyWater sky130 (https://github.com/google/skywater-pdk). Open-source flow: xschem + ngspice for
  design/sim, klayout-tools (`klt`) for layout work.
- **New standalone block; twin** of gf180-comparator and sg13g2-comparator
  — identical bench structure, sky130 numbers only.
- **1.8 V headroom is the design constraint**: document the stack-height
  choices and their offset/speed consequences as findings.
- **Statistical basis first**: establish and commit what sky130 ships for
  mismatch modeling before any sigma is claimed.
- **Cross-pollination protocol**: findings affecting sky130-sar-adc's
  embedded comparator are filed on that repo.
- **Friction protocol (the canary's job)**: every time klayout-tools is
  awkward, missing a capability, or wrong for what you need, file an issue at
  `2AMLogic/klayout-tools` describing the tool gap generically — that tracker
  is scoped to the tool, so keep design-specific detail out of it and
  describe the gap, not the design.
- **Verification is the product**: no claim without a testbench; PVT corners
  on every recorded result; `sim/` results are append-only evidence.
- Spec changes go through `spec/` with a decision record; agents do not
  relax the ratified spec to make results pass.

<!-- BEGIN LOOM ORCHESTRATION -->
This repository uses [Loom](https://github.com/rjwalters/loom) for AI-powered development orchestration — see the Loom repository for the full guide (roles, labels, worktrees, configuration). When installed, Loom also writes a locally-substituted copy of that guide to `.loom/CLAUDE.md`.
<!-- END LOOM ORCHESTRATION -->
