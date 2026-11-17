"""sky130 PVT corner definitions used by the harness.

Ported (issue #8) from 2AMLogic/sky130-sar-adc's sim/harness/corners.py
(commit b80c144efbf467a586f728726cabb25c1eb5a1f2) -- unchanged logic;
same PDK (sky130), same OAT-grid convention.

Deliberately does NOT hardcode a supply nominal or a pass/fail threshold
anywhere in this module -- this is a generic harness module, so a
testbench manifest (tb.json) must supply its own nominal_supply_v,
process corners, temperatures, and supply tolerance; per CLAUDE.md,
agents do not relax the ratified spec to make results pass, so any
pass/fail line belongs to the manifest, not to a shared harness default.
This module only supplies PDK-derived helpers (mismatch-corner lookup,
corner-id formatting, supply-point spreading) and repo-convention-level
grading helpers (the shared per-axis spread metric and its floor/ceiling
failure strings, graded identically by every bench -- see
spread_pct/spread_failures below), which are properties of the PDK and
of repo convention, not of this block's own spec.
"""

from __future__ import annotations

import statistics

from .pdk import load_pdk_json


def default_mismatch_corners() -> list[str]:
    return list(load_pdk_json()["mismatch_corners"])


def mismatch_corner_for(process_corner: str) -> str:
    """tt -> tt_mm, ss -> ss_mm, ... -- the local-mismatch switch for a
    given base process corner (sim/pdk.json's "mismatch_corners" note)."""
    mm = f"{process_corner}_mm"
    if mm not in default_mismatch_corners():
        raise ValueError(
            f"no mismatch corner for process corner '{process_corner}' -- "
            f"available: {default_mismatch_corners()}"
        )
    return mm


def corner_id(process_corner: str, temp_c: float, supply_v: float) -> str:
    """<process>_<temp>c_<supply>v, e.g. ss_-40c_1.62v (gf180-sar-adc's
    sim/README.md naming convention, unchanged)."""
    temp_str = f"{temp_c:g}"
    supply_str = f"{supply_v:.2f}"
    return f"{process_corner}_{temp_str}c_{supply_str}v"


def supply_points(nominal_v: float, tolerance: float) -> list[float]:
    if tolerance <= 0:
        return [nominal_v]
    lo = round(nominal_v * (1 - tolerance), 6)
    hi = round(nominal_v * (1 + tolerance), 6)
    # De-dup in case rounding collapses lo/hi onto nominal (tolerance ~ 0).
    points = sorted({lo, nominal_v, hi})
    return points


def spread_pct(values: list[float]) -> float:
    """Relative (max - min) spread of one OAT-axis slice, in percent: the
    per-axis sensitivity metric every grading path shares
    (sim/harness/runner.py and the comparator-regeneration ladder --
    issue #235 consolidated the ladder's copy here). An empty slice
    spreads 0.0."""
    if not values:
        return 0.0
    lo, hi = min(values), max(values)
    denom = abs(statistics.fmean(values)) or 1e-30
    return abs(hi - lo) / denom * 100.0


def min_max_failures(name: str, checks: dict, value: float) -> list[str]:
    """Per-point min/max limit failures for one measurement, as unprefixed
    strings -- callers add any per-point prefix of their own (the harness
    adds none; the ladder prefixes the corner id)."""
    failures = []
    if "min" in checks and value < checks["min"]:
        failures.append(f"{name}={value:.6g} < min {checks['min']}")
    if "max" in checks and value > checks["max"]:
        failures.append(f"{name}={value:.6g} > max {checks['max']}")
    return failures


def spread_failures(
    name: str, checks: dict, axis_spreads: dict[str, float]
) -> list[str]:
    """Per-axis spread floor/ceiling failures for one measurement (`checks`
    is that measurement's entry in a manifest's `checks`), as unprefixed
    strings byte-identical across every grading path so committed records
    keep reading the same. An axis named in a floor/ceiling but absent
    from `axis_spreads` is skipped (the guard sim/harness/runner.py has
    always used; issue #235 unified the ladder's KeyError on it)."""
    failures = []
    for axis, floor in checks.get("min_spread_pct_by_axis", {}).items():
        spread = axis_spreads.get(axis)
        if spread is not None and spread < floor:
            failures.append(
                f"{name}: {axis}-axis spread {spread:.4g}% below floor {floor}%"
            )
    for axis, ceiling in checks.get("max_spread_pct_by_axis", {}).items():
        spread = axis_spreads.get(axis)
        if spread is not None and spread > ceiling:
            failures.append(
                f"{name}: {axis}-axis spread {spread:.4g}% above ceiling {ceiling}%"
            )
    return failures


SPREAD_AXES = frozenset({"process", "temperature", "supply"})


def validate_spread_checks(
    label: str, measure: dict, checks: dict, spreads_graded: bool = True
) -> None:
    """Load-time validation of one manifest block's spread checks (issue
    #274): raises ValueError for (a) an axis key in
    min/max_spread_pct_by_axis outside SPREAD_AXES -- a misspelled axis is
    silently ungraded by spread_failures()'s runtime skip -- and (b) a
    spread-carrying checks entry whose name is absent from the block's
    `measure` (no axis spread is ever computed for a name nothing
    measures, so the entry would be silently ungraded). `label` names the
    manifest path and block so the error is fixable without reading the
    source. Only spread-carrying entries are in scope: min/max/min_stdev
    keys and entries without spread blocks pass untouched, and
    spread_failures() itself is unchanged.

    A block whose checks are never spread-graded (the ladder.json
    reverse_ladder: grade_reverse() reads per-point min/max only, DR-008
    "reported, never scored") passes spreads_graded=False so any spread
    floor/ceiling there fails the load too instead of sitting ungraded
    (issue #295). Default stays graded, so every existing call site is
    unchanged."""
    for name, chk in checks.items():
        for key in ("min_spread_pct_by_axis", "max_spread_pct_by_axis"):
            for axis in chk.get(key, {}):
                if axis not in SPREAD_AXES:
                    raise ValueError(
                        f"{label}: check '{name}': unknown axis '{axis}' in "
                        f"'{key}' -- valid axes are {sorted(SPREAD_AXES)}; "
                        f"the grader would silently skip it"
                    )
        if not spreads_graded and (
            "min_spread_pct_by_axis" in chk or "max_spread_pct_by_axis" in chk
        ):
            raise ValueError(
                f"{label}: check '{name}' carries a spread floor/ceiling "
                f"but this block's checks are report-only -- no grader "
                f"reads spreads here, so it would be silently ungraded; "
                f"remove the spread key"
            )
        if name not in measure and (
            "min_spread_pct_by_axis" in chk or "max_spread_pct_by_axis" in chk
        ):
            raise ValueError(
                f"{label}: check '{name}' carries a spread floor/ceiling "
                f"but is absent from this block's 'measure' -- no axis "
                f"spread is computed for it, so the check would be "
                f"silently ungraded"
            )


def corner_matrix_summary_line(
    process_corners: list, temps_c: list, supplies_v: list, n_points: int
) -> str:
    """The "Corner matrix run" evidence-record bullet line shared by every
    experiment driver's OAT-corner-campaign record writer -- see
    sim/README.md's one-at-a-time convention. (sky130-sar-adc, the repo
    this module is ported from, shares this exact line across several of
    its own ADC-specific experiment drivers; this repo has none of those
    yet, but the line format is unchanged, so records written through this
    helper stay comparable with that repo's.) Callers still do their own
    sorted-unique extraction of the axis values (the input *shapes* differ
    per site -- dicts vs. dataclass attributes) and pass the resulting
    lists in here; only the final formatted string is centralized."""
    return (
        f"- **Corner matrix run**: process={process_corners}, "
        f"temperature_c={temps_c}, supply_v={supplies_v} "
        f"({n_points} points, one-at-a-time per sim/README.md)"
    )


def oat_grid(
    baseline_process: str,
    baseline_temp: float,
    baseline_supply: float,
    process_corners: list[str],
    temperatures_c: list[float],
    supply_voltages: list[float],
) -> list[tuple[str, float, float]]:
    """Build a one-at-a-time (OAT / "star") PVT grid: the baseline point
    plus, for each axis in turn, every OTHER value on that axis with the
    remaining two axes held at baseline -- deduplicated, in the order the
    baseline/process/temperature/supply points are first encountered.

    This is deliberately NOT a full factorial |process|x|temp|x|supply|
    grid: it is exactly the set a per-axis sensitivity computation needs
    (each axis's spread is only ever computed from points held at baseline
    on the other two axes), and for a sky130 combined-library ngspice
    invocation (~15-20s each on this toolchain -- PDK model-library load
    dominates, not simulation time) a full grid would cost minutes per
    experiment for no additional signal. E.g. len(process)=5, len(temp)=3,
    len(supply)=3 costs 9 OAT runs instead of 45 full-factorial ones.
    """
    seen: set[tuple[str, float, float]] = set()
    grid: list[tuple[str, float, float]] = []

    def _add(pc: str, tc: float, sv: float) -> None:
        key = (pc, tc, sv)
        if key not in seen:
            seen.add(key)
            grid.append(key)

    _add(baseline_process, baseline_temp, baseline_supply)
    for process_corner in process_corners:
        _add(process_corner, baseline_temp, baseline_supply)
    for temp_c in temperatures_c:
        _add(baseline_process, temp_c, baseline_supply)
    for supply_v in supply_voltages:
        _add(baseline_process, baseline_temp, supply_v)

    return grid
