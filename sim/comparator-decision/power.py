"""`power`: supply energy and average power at a stated clock (issue #134).

One of the experiment modules `run.py` drives. Integrates the energy the
supply DELIVERS over complete, settled clock periods and reports average
power, energy per decision and the reset / evaluate split.

CONDITIONS (also written into every record):

  SIGN CONVENTION  ngspice reports i(Vdd) as the current flowing INTO the
                   source's + terminal, so a supply that delivers power has
                   i(Vdd) < 0. Delivered energy is E = -VDD * integral(i dt),
                   positive when the supply delivers. A positive-looking
                   `integral(i)` is therefore a sign error and is refused.
  PERIOD WINDOW    period k is [t0 + k*P, t0 + (k+1)*P), t0 = the first
                   rising clock edge's start. Within it, EVALUATE is
                   [rise start, rise start + duty*P) and RESET is the rest,
                   so the two sub-windows partition the period exactly.
  SETTLING         the first `settle` periods are excluded (start-up energy
                   -- bias network, node charging from the DC operating
                   point -- is not steady-state power). The retained periods
                   must converge: max relative spread of per-period energy
                   about its mean <= `conv_tol`; otherwise the run lists a
                   CONVERGENCE problem and its record is marked FAIL (the
                   figures are still tabulated, but not as a clean result).
  STIMULUS         a fixed differential DC input (default +10 mV about VCM);
                   outputs loaded by `cload_ff` each. Every value is a
                   recorded experiment condition, NOT a ratified clock rate
                   or load. This mode selects no spec bound.
"""

from __future__ import annotations

import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

_EXPERIMENT_DIR = str(Path(__file__).resolve().parent)
if _EXPERIMENT_DIR not in sys.path:
    sys.path.insert(0, _EXPERIMENT_DIR)

import _shared  # noqa: E402  -- `_shared._run` is the patch seam
from _shared import (  # noqa: E402
    RESET_TR_NS,
    VCM,
    VDD,
    _begin_dut_record,
    _deck_preamble,
    _dut_lines,
    _finalize_record,
    _input_split_stimulus,
    _record_header,
)
from harness import evidence, pdk, toolchain  # noqa: E402

POWER_PERIOD_NS = 10.0      # 100 MHz -- an experiment condition, not ratified
POWER_DUTY = 0.5            # evaluate fraction of the period
POWER_VINDIFF_MV = 10.0
POWER_CLOAD_FF = 10.0       # per output node
POWER_N_PERIODS = 8
POWER_SETTLE_PERIODS = 3
POWER_CONV_TOL = 0.01       # per-period energy spread, relative to the mean
POWER_SUM_TOL = 1e-9        # reset + evaluate vs full period, relative
POWER_STEP_NS = 0.005


def _interp(t: list[float], y: list[float], x: float) -> float:
    if x <= t[0]:
        return y[0]
    if x >= t[-1]:
        return y[-1]
    lo, hi = 0, len(t) - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if t[mid] <= x:
            lo = mid
        else:
            hi = mid
    if t[hi] == t[lo]:
        return y[hi]
    return y[lo] + (y[hi] - y[lo]) * (x - t[lo]) / (t[hi] - t[lo])


def integrate(t: list[float], y: list[float], a: float, b: float) -> float:
    """Trapezoidal integral of y(t) over [a, b], interpolating the window
    edges linearly. Refuses a window outside the sampled span (a silent
    clamp would integrate a shorter window than asked for)."""
    if b < a:
        raise ValueError("integration window is reversed")
    if a < t[0] - 1e-18 or b > t[-1] + 1e-18:
        raise ValueError(f"window [{a}, {b}] outside sampled span [{t[0]}, {t[-1]}]")
    pts_t = [a] + [x for x in t if a < x < b] + [b]
    pts_y = [_interp(t, y, a)] + [yy for x, yy in zip(t, y) if a < x < b] + [_interp(t, y, b)]
    return sum(
        0.5 * (pts_y[i] + pts_y[i + 1]) * (pts_t[i + 1] - pts_t[i])
        for i in range(len(pts_t) - 1)
    )


def delivered_energy(t: list[float], idd: list[float], vdd: float, a: float, b: float) -> float:
    """Energy (J) the supply delivers over [a, b]; see the sign convention."""
    return -vdd * integrate(t, idd, a, b)


@dataclass
class PowerResult:
    corner: str
    temp_c: float
    vdd: float
    period_s: float
    duty: float
    settle: int
    period_energy_j: list[float]   # every simulated period, settling included
    reset_energy_j: list[float]
    eval_energy_j: list[float]
    vindiff_mv: float = POWER_VINDIFF_MV   # carried so a record states what was run
    cload_ff: float = POWER_CLOAD_FF
    conv_tol: float = POWER_CONV_TOL
    problems: list[str] = field(default_factory=list)
    log_text: str = ""

    @property
    def kept(self) -> list[int]:
        return list(range(self.settle, len(self.period_energy_j)))

    @property
    def mean_energy_j(self) -> float:
        k = self.kept
        return sum(self.period_energy_j[i] for i in k) / len(k)

    @property
    def mean_reset_j(self) -> float:
        k = self.kept
        return sum(self.reset_energy_j[i] for i in k) / len(k)

    @property
    def mean_eval_j(self) -> float:
        k = self.kept
        return sum(self.eval_energy_j[i] for i in k) / len(k)

    @property
    def convergence(self) -> float:
        """Max |E_k - mean| / |mean| over the retained periods."""
        m = self.mean_energy_j
        if m == 0:
            return float("inf")
        return max(abs(self.period_energy_j[i] - m) for i in self.kept) / abs(m)

    @property
    def average_power_w(self) -> float:
        return self.mean_energy_j / self.period_s

    @property
    def ok(self) -> bool:
        return not self.problems


def analyze_power(
    t: list[float], idd: list[float], *, corner: str = "tt", temp_c: float = 27.0,
    vdd: float = VDD, t0_s: float, period_s: float, duty: float,
    n_periods: int, settle: int, conv_tol: float = POWER_CONV_TOL,
    vindiff_mv: float = POWER_VINDIFF_MV, cload_ff: float = POWER_CLOAD_FF,
    log_text: str = "",
) -> PowerResult:
    """Window one transient's i(Vdd) into per-period / reset / evaluate
    energies and run the self-checks. Problems are listed, never raised, so
    a record can state exactly which check a run failed."""
    if not 0 <= settle < n_periods:
        raise ValueError("settle must leave at least one retained period")
    if not 0 < duty < 1:
        raise ValueError("duty must be in (0, 1)")
    e_full, e_rst, e_eval = [], [], []
    for k in range(n_periods):
        a = t0_s + k * period_s
        mid = a + duty * period_s
        b = a + period_s
        e_eval.append(delivered_energy(t, idd, vdd, a, mid))
        e_rst.append(delivered_energy(t, idd, vdd, mid, b))
        e_full.append(delivered_energy(t, idd, vdd, a, b))
    r = PowerResult(corner, temp_c, vdd, period_s, duty, settle, e_full, e_rst, e_eval,
                    vindiff_mv=vindiff_mv, cload_ff=cload_ff, conv_tol=conv_tol,
                    log_text=log_text)
    if r.mean_energy_j <= 0:
        r.problems.append("SIGN: mean delivered energy is not positive (i(Vdd) sign or window error)")
    for k in range(n_periods):
        scale = max(abs(e_full[k]), 1e-30)
        if abs(e_rst[k] + e_eval[k] - e_full[k]) > POWER_SUM_TOL * scale:
            r.problems.append(f"SUM: reset+evaluate != full period in period {k}")
    if r.convergence > conv_tol:
        r.problems.append(
            f"CONVERGENCE: retained-period spread {r.convergence:.3g} > {conv_tol:g} "
            f"(settle={settle} periods is not enough, or the circuit is not periodic)"
        )
    return r


def _power_deck(
    info: pdk.PdkInfo, corner: str, temp_c: float, log_name: str, *,
    period_ns: float, duty: float, vindiff_mv: float, cload_ff: float, n_periods: int,
    vdd: float = VDD,
) -> str:
    # Rising edge begins at td = period_ns (one full reset phase first), so
    # period k's window starts at td + k*period.
    pw_ns = duty * period_ns - RESET_TR_NS
    # The final window's right edge is t0 + n*P = (n+1)*P; the extra 1% of a
    # period keeps the sampled span past it even if the last written sample
    # falls short of tstop, so analyze_power cannot raise out of a run whose
    # record should have named the problem (issue #427).
    tstop = period_ns * (n_periods + 1) + 0.01 * period_ns
    lines = [
        *_deck_preamble(
            info, corner, temp_c,
            f"* comparator-decision supply-energy run -- corner={corner} temp={temp_c}C "
            f"period={period_ns}ns duty={duty} vdd={vdd}V (issue #134)",
            vdd=vdd,
        ),
        f"Vclk CLK 0 PULSE(0 {{vdd_val}} {period_ns}n {RESET_TR_NS}n {RESET_TR_NS}n {pw_ns}n {period_ns}n)",
        *_input_split_stimulus(vindiff_mv / 1000.0),
        f"Cloadp OUTP 0 {cload_ff}f",
        f"Cloadn OUTN 0 {cload_ff}f",
        "",
        _dut_lines(),
        "",
        ".control",
        f"tran {POWER_STEP_NS}n {tstop}n",
        f"wrdata {log_name}.csv i(Vdd)",
        ".endc",
        ".end",
    ]
    return "\n".join(lines) + "\n"


DEFAULT_POWER_CORNERS = [("tt", 27.0), ("ss", -40.0), ("ff", 125.0)]  # the three PVT anchors


def run_power(
    points: list[tuple[str, float]] | None = None, *, period_ns: float = POWER_PERIOD_NS,
    duty: float = POWER_DUTY, vindiff_mv: float = POWER_VINDIFF_MV,
    cload_ff: float = POWER_CLOAD_FF, n_periods: int = POWER_N_PERIODS,
    settle: int = POWER_SETTLE_PERIODS, quiet: bool = False, vdd: float = VDD,
) -> list[PowerResult]:
    info = pdk.resolve_or_raise()
    results: list[PowerResult] = []
    with tempfile.TemporaryDirectory(prefix="comparator-decision-power-") as scratch:
        for corner, temp_c in points or DEFAULT_POWER_CORNERS:
            safe_t = str(temp_c).replace("-", "neg").replace(".", "p")
            log_name = f"power_{corner}_{safe_t}c"
            deck = _power_deck(
                info, corner, temp_c, log_name, period_ns=period_ns, duty=duty,
                vindiff_mv=vindiff_mv, cload_ff=cload_ff, n_periods=n_periods,
                vdd=vdd,
            )
            log_text = _shared._run(deck, Path(scratch), log_name)
            t, idd = toolchain.read_wrdata_csv(Path(scratch) / f"{log_name}.csv", 1)
            r = analyze_power(
                t, idd, corner=corner, temp_c=temp_c, vdd=vdd, t0_s=period_ns * 1e-9,
                period_s=period_ns * 1e-9, duty=duty, n_periods=n_periods,
                settle=settle, vindiff_mv=vindiff_mv, cload_ff=cload_ff,
                log_text=log_text,
            )
            results.append(r)
            if not quiet:
                print(
                    f"  {corner}/{temp_c}C@{vdd:g}V: E/period={r.mean_energy_j * 1e12:.4g}pJ "
                    f"(reset {r.mean_reset_j * 1e12:.4g} + eval {r.mean_eval_j * 1e12:.4g}) "
                    f"P={r.average_power_w * 1e6:.4g}uW conv={r.convergence:.3g} "
                    f"-> {'OK' if r.ok else '; '.join(r.problems)}"
                )
    return results


def _distinct(values: list[float]) -> str:
    """Distinct values in first-seen order, joined; one value reads plainly."""
    return "/".join(f"{v:g}" for v in dict.fromkeys(values))


def write_power_evidence(
    results: list[PowerResult], *, note: str = "", supersedes: str = "",
) -> Path:
    # Clock / stimulus / load come from the results themselves, never from this
    # writer's own defaults, so a record cannot state conditions it did not run
    # (issue #423).
    period_ns = _distinct([r.period_s * 1e9 for r in results])
    freq_mhz = _distinct([1e-6 / r.period_s for r in results])
    duty = _distinct([r.duty for r in results])
    vindiff_mv = _distinct([r.vindiff_mv for r in results])
    cload_ff = _distinct([r.cload_ff for r in results])
    supply_v = _distinct([r.vdd for r in results])
    info, record_id, netlist_sha, record_path, corners_dir = _begin_dut_record("corners")
    for r in results:
        safe = f"{r.corner}_{str(r.temp_c).replace('-', 'neg').replace('.', 'p')}c"
        if r.vdd != VDD:
            safe += f"_{r.vdd:g}v".replace(".", "p")
        evidence.write_new_text(corners_dir / f"power_{safe}.log", r.log_text)
    a_lines: list[str] = []
    a = a_lines.append
    a_lines += _record_header(record_id)
    a(f"- **Corner matrix run**: " + ", ".join(f"{r.corner}/{r.temp_c}C" for r in results)
      + f" at supply_v=[{supply_v}] ({len(results)} PVT point(s) run; "
      f"coverage is exactly the points listed, not the full graded matrix)")
    a(f"- **Clock**: period {period_ns}ns ({freq_mhz} MHz), evaluate duty {duty}; "
      f"an experiment condition, NOT a ratified clock rate")
    a(f"- **Stimulus / load**: differential DC input {vindiff_mv}mV about VCM={VCM}V; "
      f"{cload_ff}fF on each of OUTP/OUTN")
    a("- **Integration window and sign**: delivered energy E = -VDD * integral(i(Vdd) dt) "
      "over complete periods [t0+k*P, t0+(k+1)*P); evaluate = first duty*P of each period "
      "(from rising-edge start), reset = remainder; trapezoidal, window edges interpolated")
    if results:
        settle = _distinct([r.settle for r in results])
        n_sim = _distinct([len(r.period_energy_j) for r in results])
        conv_tol = _distinct([r.conv_tol for r in results])
        a(f"- **Settling exclusion**: first {settle} of {n_sim} periods excluded; "
          f"convergence = max retained-period spread / mean, tolerance {conv_tol}")
    a("- **Spec status**: no bound selected or changed; DRAFT/OPEN power row remains "
      "unratified. These are comparison figures, not compliance limits.")
    if note:
        a(f"- **Note**: {note}")
    a(f"- **Overall**: {'PASS' if all(r.ok for r in results) else 'FAIL'} "
      f"({sum(r.ok for r in results)}/{len(results)} corners pass all self-checks)")
    a("")
    a("| Corner | Temp | Supply | E/period (pJ) | reset (pJ) | evaluate (pJ) | reset+eval-full (J) "
      "| P_avg (uW) | E/decision (pJ) | convergence | Result |")
    a("|---|---|---|---|---|---|---|---|---|---|---|")
    for r in results:
        resid = r.mean_reset_j + r.mean_eval_j - r.mean_energy_j
        a(f"| {r.corner} | {r.temp_c}C | {r.vdd:g}V | {r.mean_energy_j * 1e12:.5g} | {r.mean_reset_j * 1e12:.5g} "
          f"| {r.mean_eval_j * 1e12:.5g} | {resid:.2g} | {r.average_power_w * 1e6:.5g} "
          f"| {r.mean_energy_j * 1e12:.5g} | {r.convergence:.3g} "
          f"| {'OK' if r.ok else '; '.join(r.problems)} |")
    a("")
    a("One decision is made per clock period, so energy per decision equals "
      "energy per period. Average power = mean period energy / period.")
    return _finalize_record(a_lines, record_path, info, netlist_sha, "power", supersedes=supersedes)
