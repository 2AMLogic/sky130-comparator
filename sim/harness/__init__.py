"""sim/harness -- PVT corner + Monte Carlo simulation harness for
sky130-comparator.

Ported (issue #8) from 2AMLogic/sky130-sar-adc's sim/harness/ (commit
b80c144efbf467a586f728726cabb25c1eb5a1f2), per spec/porting-plan.md's
"Next steps" item 2. That repo's harness itself adapts the *pattern* of
2AMLogic/gf180-sar-adc's sim/harness/ (commit
f613571aee5b80eff1eea37bdce9dfc88c5cf396) and 2AMLogic/sky130-bandgap's
sim/ scaffolding (commit 1f04e8524cc2d8c2c7154773749b1b2d3be2ce64) to
sky130 -- both same-PDK precedent this port carries forward unchanged,
since sky130-comparator targets the identical PDK (sky130) and toolchain
as sky130-sar-adc.

The module boundaries here were sized for what issue #8 needed to
prove (the PVT/MC plumbing works), not sky130-sar-adc's own
ADC-specific experiment suite -- see sim/README.md "Harness self-test
experiments" for the harness-proof circuits (harness-corner-smoke/,
mc-smoke/), which stay as the regression that proves the harness's own
PVT/MC plumbing, independent of whichever DUT sim/comparator-decision/
currently exercises.
"""

__version__ = "0.1.0"
