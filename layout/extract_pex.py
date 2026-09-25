#!/usr/bin/env python3
"""Produce the post-layout (extracted, parasitics-included) DUT netlists that
`sim/comparator-decision/run.py --dut extracted` simulates (issue #57, T1
checklist item 7).

WHY THIS SCRIPT EXISTS -- and why not `klt pex`
------------------------------------------------
`klt pex` is klayout-tools' canonical post-layout path: it runs
`klt extract --parasitics` internally, then re-runs one or more **`klt sim`
request JSON** testbenches once against the schematic DUT and once against the
extracted netlist, emitting per-corner `delta[]` rows. Its stated contract
(`docs/cli/pex.md`) is that each testbench's netlist carries exactly one
`.include`/`.inc` line naming the schematic DUT, which `klt pex` re-points at
the extracted netlist.

This repo's comparator-decision harness does not meet that contract, and the
mismatch is NOT the missing `.include` line -- that part is trivially fixable.
It is that `run.py`'s five measurements are not `klt sim` requests at all:

  * `regen`   sweeps Vindiff and post-processes the raw waveform in Python to
              find a threshold crossing (no `.meas` card expresses "first
              crossing after the evaluate edge, sign-corrected per point").
  * `offset`  fits a zero-intercept gain line through an ideal-device
              calibration sweep, then divides a per-`rndseed` Monte Carlo
              pick-off statistic by that fitted gain.
  * `noise`   runs an AC `.noise` analysis on a loop-broken SUB-MODEL that is
              assembled in Python from a subset of the DUT's own device lines
              -- there is no single netlist file to `.include`-swap.
  * `noise-tran` injects calibrated `TRNOISE()` equivalent sources at nodes
              derived from the DUT's own device lines and inverts a
              pair-symmetric decision-probability estimator.
  * `reset`   builds counterfactual variants by re-emitting DUT device lines
              onto substituted nodes.

Adding an `.include` line would therefore let `klt pex` *rewrite* a file it
still could not *drive*. So this issue takes the second of the two paths
issue #57 sanctions: `klt extract --parasitics` (the same extraction engine
`klt pex` calls) plus a documented, committed swap into `run.py`. That is also
the precedent `2AMLogic/gf180-sar-adc`'s `sim/comparator-regeneration/` set,
per `2AMLogic/gf180-comparator#23`.

WHAT THIS SCRIPT EMITS
----------------------
1. `layout/extract-parasitics.json` -- the `klt extract --parasitics` JSON
   envelope, verbatim. This is the evidence artifact: RC totals, per-net
   parasitics, provenance, tool pin.
2. `layout/comparator.extract.spice` -- the extractor's own output, verbatim
   and unedited. Committed so the transform below can always be re-derived
   and audited against its input.
3. `layout/comparator.pex.spice` -- (2) rewritten into a FLAT device-level
   fragment with SCHEMATIC net and instance names, drop-in
   interchangeable with `sim/comparator-decision/testbench/comparator_core.spice`.
4. `layout/comparator.pex-preamp.spice` -- the preamp partition of (3), the
   post-layout counterpart of the `noise` sub-command's loop-broken AC
   sub-model.

THE REWRITE IN (3), STEP BY STEP -- every step is name-level only; no R, C or
device parameter value is ever altered:

  a. `.SUBCKT`/`.ENDS`/`* pin` wrapper removed, so the result inlines exactly
     where `comparator_core.spice` inlines today. `run.py` therefore needs one
     new code path (which fragment text to inline), not five new deck
     builders, and the schematic-side decks stay BYTE-IDENTICAL to the ones
     that produced the committed schematic-level records -- which is what
     makes the schematic-vs-extracted delta an apples-to-apples comparison.
  b. Internal extracted net names (`\\$3`, `\\$4`, `\\$6`, `\\$7`, `\\$10`) are
     renamed to their schematic counterparts (`CLKT`, `TAILP`, `OUTP1`,
     `TAIL2`, `OUTN1`) using the net correspondence in the COMMITTED
     `layout/lvs-report.json` -- i.e. the mapping is the LVS tool's own 12/12
     net pairing, not a hand transcription. The extractor's per-terminal star
     leg nets (`\\$10__t3`) carry the rename through their prefix
     (`OUTN1__t3`). Consequence: every probe in every existing deck
     (`v(OUTP)`, `v(TAILP)`, `v(OUTP1)`) resolves unchanged on the
     post-layout DUT.
  c. Device instances are renamed from the extractor's positional `$N` to the
     schematic instance name they pair with, matched STRUCTURALLY (model
     class + gate/body net + the drain/source net pair as an unordered set,
     since a MOS's S/D assignment is not observable from layout). Where the
     layout splits one schematic device into parallel fingers the halves get
     `__a`/`__b` suffixes -- the two W=6.5 halves of each W=13 input-pair
     device, which is why the extractor reports 18 devices where the
     schematic has 16 (`layout/extract-device-count.json` records the same
     11-raw/9-merged nfet split). A device that matches nothing keeps a
     `X_UNPAIRED_<n>` name and is reported as a warning rather than silently
     renamed.
  d. `vsubs` (the extractor's `.GLOBAL` substrate node) is tied to 0 by an
     explicit 0 V source appended to the fragment. The extractor's own output
     ties it only through `Rvsubs_dctie = 1e12`, which is a DC tie but leaves
     the substrate node effectively FLOATING for AC/transient -- every net's
     ground capacitance would then couple net-to-net through vsubs instead of
     to ground, under-counting the loading this whole exercise exists to
     measure. The physical substrate is at GND, so tying it is both correct
     and the conservative choice.

KNOWN DELTA CARRIED THROUGH (do not "fix" it here): the three `res_high_po`
resistors are drawn at w = 0.42 um and the schematic instantiates the
`_0p35` (w = 0.35 um) wrapper. This is the disclosed LVS blind spot from
PR #55 / `layout/lvs-coverage-probe.json`, and it is a REAL electrical
difference (weff 0.4009 vs 0.3262 um -> ~19 % lower load resistance, i.e.
~19 % less preamp gain). The post-layout numbers must show it rather than
paper over it: normalising the extracted width to 0.35 um would make this
script's output stop being a measurement of the committed layout.

THE TOOLCHAIN PIN IS PART OF THE MEASUREMENT (issue #57, PR #67 review)
-----------------------------------------------------------------------
The parasitic R values this script commits are NOT stable across klt/klayout
builds. Measured on this repo's own GDS: klt `0.6.0` on klayout `0.30.10`
(the pin) and klt `0.6.0+g1828313bdf02` on klayout `0.30.12` (an unreleased
dev build) produce BIT-IDENTICAL capacitances but total series resistance
17.52 kohm vs 14.70 kohm -- 1.19x overall and up to 2.30x on an individual
net (CLKT), 1.55-1.86x on OUTP1/OUTN1/VINP/VINN. Those are exactly the nets
the post-layout causal story rests on, so an off-pin extraction silently
changes every downstream number.

`run_extraction()` therefore ASSERTS the pin (`PINNED_KLT_VERSION` /
`PINNED_KLAYOUT_VERSION` below) and refuses to write anything off it, and
`--check` re-asserts it against the committed envelope as well. The pins are
the same ones `docs/environment-setup.md` records and both
`.github/workflows/t1-signoff.yml` jobs install; bumping them is deliberate
and goes in one change, exactly as that workflow's own header prescribes:
bump the doc + both CI installs + these constants, re-run the regeneration,
and commit the refreshed artifacts together.

If the host `klt` is off-pin -- which it may legitimately be; host tooling is
provisioned fleet-wide and must not be changed to suit this repo -- run this
script against a THROWAWAY environment instead:

    uv venv /tmp/pex-pin-env
    uv pip install --python /tmp/pex-pin-env/bin/python \
        "klayout-tools==0.6.0" "klayout==0.30.10"
    PATH=/tmp/pex-pin-env/bin:$PATH python3 layout/extract_pex.py

Usage:

    python3 layout/extract_pex.py             # re-extract and rewrite
    python3 layout/extract_pex.py --check     # verify committed outputs match
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LAYOUT_DIR = REPO_ROOT / "layout"

GDS = LAYOUT_DIR / "comparator.gds"
LVS_REPORT = LAYOUT_DIR / "lvs-report.json"
SCHEMATIC_FRAGMENT = (
    REPO_ROOT / "sim" / "comparator-decision" / "testbench" / "comparator_core.spice"
)

EXTRACT_JSON = LAYOUT_DIR / "extract-parasitics.json"
EXTRACT_SPICE = LAYOUT_DIR / "comparator.extract.spice"
PEX_FRAGMENT = LAYOUT_DIR / "comparator.pex.spice"
PEX_PREAMP_FRAGMENT = LAYOUT_DIR / "comparator.pex-preamp.spice"

DECK = "sky130"
TOP_CELL = "gen_compose_0"
PDK_VARIANT = "sky130A"

# The toolchain this repo pins for every committed layout envelope --
# `docs/environment-setup.md` "Signoff tooling (klt)", and both jobs of
# `.github/workflows/t1-signoff.yml`. Asserted rather than merely recorded,
# because the extracted resistances are not stable across builds (see the
# module docstring). Bump these only together with the doc and both CI
# installs, in the same change that re-commits the regenerated artifacts.
PINNED_KLT_VERSION = "0.6.0"
PINNED_KLAYOUT_VERSION = "0.30.10"

PIN_HINT = (
    "Run against a throwaway environment rather than changing host tooling:\n"
    "  uv venv /tmp/pex-pin-env\n"
    "  uv pip install --python /tmp/pex-pin-env/bin/python "
    f'"klayout-tools=={PINNED_KLT_VERSION}" "klayout=={PINNED_KLAYOUT_VERSION}"\n'
    "  PATH=/tmp/pex-pin-env/bin:$PATH python3 layout/extract_pex.py"
)

# Nets that belong to the clocked LATCH half of the DUT. The `noise`
# sub-command's sub-model is the preamplifier with everything past its outputs
# omitted -- that loop break is expressed here as "drop every device touching
# one of these nets", which is the same partition the schematic-side
# sub-model makes by naming its seven preamp devices explicitly (run.py's
# `_noise_deck`). Stated as nets rather than as instance names so the
# partition is checked against connectivity, not against a name list that
# could drift from the layout.
LATCH_NETS = frozenset({"CLK", "CLKT", "TAIL2", "OUTP", "OUTN"})

# What the preamp partition must contain once LATCH_NETS are removed: the
# preamp tail, both halves of each input-pair device, both poly loads, and
# both OUT1 absorber caps. Asserted, so a layout change that silently moves a
# device across the partition fails loudly here instead of quietly producing a
# different sub-model than the schematic side's.
EXPECTED_PREAMP_DEVICES = 9


def _fail(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    raise SystemExit(1)


# ---------------------------------------------------------------------------
# Netlist parsing helpers
# ---------------------------------------------------------------------------


def _logical_lines(text: str) -> list[tuple[str, list[str]]]:
    """Fold SPICE continuation lines, returning (leading_comments, tokens).

    Comment and blank lines are attached to the instance line that follows
    them, so the extractor's own `* device instance ...` provenance comments
    survive the rewrite next to the device they describe.
    """
    out: list[tuple[str, list[str]]] = []
    pending: list[str] = []
    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("*"):
            pending.append(line)
            continue
        if stripped.startswith("+"):
            if not out:
                _fail("continuation line before any instance line")
            out[-1][1].extend(stripped[1:].split())
            continue
        out.append(("\n".join(pending), stripped.split()))
        pending = []
    if pending:
        out.append(("\n".join(pending), []))
    return out


def _schematic_devices() -> dict[str, tuple[str, tuple[str, ...]]]:
    """{instance name: (model, terminals)} for the schematic DUT fragment."""
    devices: dict[str, tuple[str, tuple[str, ...]]] = {}
    for _, tokens in _logical_lines(SCHEMATIC_FRAGMENT.read_text()):
        if not tokens:
            continue
        name = tokens[0]
        rest = tokens[1:]
        model_idx = next(
            (i for i, t in enumerate(rest) if t.startswith("sky130_fd_pr__")), None
        )
        if model_idx is None:
            _fail(f"schematic instance {name} names no sky130_fd_pr__ model")
        devices[name] = (rest[model_idx], tuple(rest[:model_idx]))
    return devices


def _model_class(model: str) -> str:
    if "res_" in model:
        return "res"
    if "nfet" in model:
        return "nfet"
    if "pfet" in model:
        return "pfet"
    return model


def _signature(model: str, terminals: tuple[str, ...]) -> tuple:
    """A layout-observable connectivity signature for one device.

    MOS: (class, gate, body, {drain, source}) -- the S/D assignment is not
    observable from geometry, so it is compared as an unordered pair.
    Resistor: (class, {t0, t1}, body) -- terminals are symmetric.
    The model NAME is deliberately not part of the signature: the schematic
    instantiates the `_0p35` fixed-width wrapper while the extractor emits the
    parametrised base device, which is the disclosed PR #55 width delta -- a
    real electrical difference, but not an identity difference.
    """
    cls = _model_class(model)
    if cls == "res":
        return (cls, frozenset(terminals[:2]), terminals[2])
    return (cls, terminals[1], terminals[3], frozenset((terminals[0], terminals[2])))


# ---------------------------------------------------------------------------
# The rewrite
# ---------------------------------------------------------------------------


def _net_rename_map() -> dict[str, str]:
    report = json.loads(LVS_REPORT.read_text())
    if report.get("status") != "match":
        _fail(
            f"{LVS_REPORT} status is {report.get('status')!r}, not 'match' -- "
            "the net correspondence this rewrite depends on is only "
            "trustworthy for a matched LVS run"
        )
    mapping: dict[str, str] = {}
    for entry in report.get("net_correspondence", []):
        layout_net, ref_net = entry["layout"], entry["reference"]
        if layout_net.startswith("\\$"):
            mapping[layout_net] = ref_net
        elif layout_net != ref_net:
            _fail(
                f"LVS pairs named layout net {layout_net!r} with differently "
                f"named reference net {ref_net!r}; this rewrite only renames "
                "the extractor's anonymous internal nets"
            )
    if not mapping:
        _fail("LVS net correspondence contains no internal nets to rename")
    return mapping


def _rename_token(token: str, nets: dict[str, str]) -> str:
    """Rename one net token, carrying the extractor's `__tN` star-leg suffix."""
    base, sep, leg = token.partition("__t")
    renamed = nets.get(base, base)
    return f"{renamed}{sep}{leg}" if sep else renamed


def _is_parasitic(name: str) -> bool:
    return name[0].upper() in ("R", "C")


@dataclass
class Element:
    """One rewritten netlist element: a device or an extracted parasitic."""

    comments: str
    name: str
    nodes: list[str]          # renamed, star-leg suffixes intact
    tail: list[str]           # model name + parameters (device) or value (RC)
    is_device: bool

    @property
    def hub_nets(self) -> set[str]:
        return {n.partition("__t")[0] for n in self.nodes}

    @property
    def legs(self) -> set[str]:
        return {n for n in self.nodes if "__t" in n}

    def render(self) -> str:
        return " ".join([self.name, *self.nodes, *self.tail])


def _parse_elements(raw_spice: str, nets: dict[str, str]) -> list[Element]:
    """Body of the extracted `.SUBCKT`, with every net token renamed."""
    elements: list[Element] = []
    in_body = False
    for comments, tokens in _logical_lines(raw_spice):
        if not tokens:
            continue
        head = tokens[0].upper()
        if head == ".GLOBAL":
            continue
        if head == ".SUBCKT":
            in_body = True
            continue
        if head == ".ENDS":
            in_body = False
            continue
        if not in_body:
            _fail(f"unexpected card outside .SUBCKT: {' '.join(tokens)}")

        name, rest = tokens[0], tokens[1:]
        if _is_parasitic(name):
            # `<R|C><name> <n1> <n2> <value>`. The extractor's element name
            # embeds the pre-rename net id (`R_10_t0`, `Ccc__10__4`), so it is
            # rebuilt from the renamed nodes -- the committed fragment then
            # reads in schematic terms throughout.
            nodes = [_rename_token(t, nets) for t in rest[:2]]
            new_name = f"{name[0]}_{nodes[0]}_{nodes[1]}".replace("\\", "").replace(
                "$", ""
            )
            elements.append(Element(comments, new_name, nodes, rest[2:], False))
            continue

        model_idx = next(
            (i for i, t in enumerate(rest) if t.startswith("sky130_fd_pr__")), None
        )
        if model_idx is None:
            _fail(f"extracted instance {name} names no sky130_fd_pr__ model")
        elements.append(Element(
            comments, name,
            [_rename_token(t, nets) for t in rest[:model_idx]],
            rest[model_idx:], True,
        ))
    return elements


def _pair_device_names(elements: list[Element]) -> list[str]:
    """Warnings; renames every device Element in place to its schematic name."""
    by_signature: dict[tuple, list[str]] = {}
    for name, (model, terminals) in _schematic_devices().items():
        by_signature.setdefault(_signature(model, terminals), []).append(name)

    devices = [e for e in elements if e.is_device]
    matches: list[str | None] = []
    for e in devices:
        bare = tuple(n.partition("__t")[0] for n in e.nodes)
        candidates = by_signature.get(_signature(e.tail[0], bare), [])
        matches.append(candidates[0] if len(candidates) == 1 else None)

    warnings: list[str] = []
    seen: dict[str, int] = {}
    for e, match in zip(devices, matches):
        if match is None:
            e.name = f"X_UNPAIRED_{e.name.lstrip('X$')}"
            warnings.append(
                f"extracted device on nets {'/'.join(sorted(e.hub_nets))} "
                f"({e.tail[0]}) pairs with no single schematic device -- "
                f"emitted as {e.name}"
            )
            continue
        # A schematic device the layout splits into parallel fingers (each
        # W=13 input-pair device is drawn as two W=6.5 fingers) matches more
        # than once; suffix the halves rather than colliding on one name.
        split = matches.count(match) > 1
        index = seen.get(match, 0)
        seen[match] = index + 1
        e.name = f"{match}__{chr(ord('a') + index)}" if split else match
    return warnings


def rewrite(raw_spice: str) -> tuple[str, str, list[str]]:
    """Return (flat DUT fragment, flat preamp partition, warnings)."""
    elements = _parse_elements(raw_spice, _net_rename_map())
    warnings = _pair_device_names(elements)

    # The preamp partition: the same loop break the schematic-side `noise`
    # sub-model makes (omit everything past the preamp outputs), expressed
    # against connectivity instead of against a device-name list.
    preamp_devices = [
        e for e in elements if e.is_device and not (e.hub_nets & LATCH_NETS)
    ]
    if len(preamp_devices) != EXPECTED_PREAMP_DEVICES:
        _fail(
            f"preamp partition holds {len(preamp_devices)} devices, expected "
            f"{EXPECTED_PREAMP_DEVICES} (preamp tail + 4 input-pair fingers + "
            "2 poly loads + 2 absorber caps) -- the layout's partition against "
            f"{sorted(LATCH_NETS)} has changed, so the post-layout `noise` "
            "sub-model would no longer be the schematic sub-model's counterpart"
        )
    live_legs = set().union(*(e.legs for e in preamp_devices))
    preamp = [
        e for e in elements
        if not (e.hub_nets & LATCH_NETS)
        # A star-leg resistor whose device was dropped would otherwise dangle
        # on a one-connection node.
        and e.legs <= live_legs
    ]

    header = _header(raw_spice)
    return (
        _render(header, elements, kind="full"),
        _render(header, preamp, kind="preamp"),
        warnings,
    )


def _header(raw_spice: str) -> list[str]:
    """The extractor's own parasitic-model disclosure, preserved verbatim."""
    out: list[str] = []
    for raw in raw_spice.splitlines():
        if not raw.startswith("*"):
            break
        out.append(raw)
    return out


def _render(header: list[str], elements: list[Element], kind: str) -> str:
    what = (
        "the FULL post-layout comparator"
        if kind == "full"
        else "the post-layout PREAMPLIFIER PARTITION of the comparator"
    )
    extra = (
        ""
        if kind == "full"
        else (
            "*\n* PARTITION: every device touching one of the latch nets\n"
            f"* ({', '.join(sorted(LATCH_NETS))}) is omitted, together with that\n"
            "* net's own parasitics and any star-leg resistor left dangling.\n"
            "* What remains is the DR-004 preamplifier -- tail, both fingers of\n"
            "* each input-pair device, both poly loads, both OUT1 absorber caps\n"
            "* -- WITH its extracted parasitics. This is the post-layout\n"
            "* counterpart of run.py `noise`'s loop-broken AC sub-model, built\n"
            "* by the same loop break (omit everything past the preamp outputs)\n"
            "* applied to the extracted netlist instead of to the schematic\n"
            "* fragment's device lines.\n"
        )
    )
    preamble = f"""* GENERATED FILE -- do not hand-edit. Regenerate with
* `python3 layout/extract_pex.py`; `--check` verifies the committed copy.
*
* {what}, as a FLAT device-level fragment
* interchangeable with sim/comparator-decision/testbench/comparator_core.spice.
* Derived from layout/comparator.extract.spice (`klt extract --parasitics`
* over layout/comparator.gds) by a name-level rewrite only: nets renamed to
* their schematic counterparts via layout/lvs-report.json's 12/12 net
* correspondence, device instances renamed to the schematic instance they
* pair with structurally. No R, C, or device parameter value is altered.
* See layout/extract_pex.py's module docstring for the full derivation, for
* why `klt pex` is not the path here, and for the disclosed res_high_po
* w=0.42um-drawn vs w=0.35um-schematic delta this fragment deliberately
* carries through.
{extra}*
* --- extractor's own parasitic-model disclosure, verbatim ---
"""
    body: list[str] = [preamble.rstrip("\n")]
    body.extend(header)
    body.append("*")
    body.append("* --- netlist ---")
    for element in elements:
        if element.comments:
            body.append(element.comments)
        body.append(element.render())
    body.append("*")
    body.append(
        "* Substrate tie: the extractor grounds `vsubs` only through a 1e12 ohm\n"
        "* DC tie, which leaves it floating for AC/transient and would couple\n"
        "* every net's ground capacitance net-to-net instead of to ground.\n"
        "* The physical substrate is at GND, so tie it."
    )
    body.append("Vvsubs vsubs 0 dc 0")
    return "\n".join(body) + "\n"


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def _assert_pinned(report: dict, where: str) -> None:
    """Refuse an extraction envelope produced off the documented tool pin.

    Capacitances are reproducible across builds; resistances are not (see the
    module docstring), so an off-pin envelope is not a cosmetic provenance
    difference -- it is a different measurement.
    """
    provenance = report.get("provenance") or {}
    klt_version = provenance.get("klt_version")
    klayout_version = provenance.get("klayout_version")
    if (klt_version, klayout_version) != (
        PINNED_KLT_VERSION, PINNED_KLAYOUT_VERSION
    ):
        _fail(
            f"{where} records klt {klt_version!r} on klayout "
            f"{klayout_version!r}, but this repo pins klt "
            f"{PINNED_KLT_VERSION!r} on klayout {PINNED_KLAYOUT_VERSION!r} "
            "(docs/environment-setup.md, .github/workflows/t1-signoff.yml). "
            "Extracted resistances differ by up to 2.3x per net between "
            f"builds, so this would be a different measurement.\n{PIN_HINT}"
        )


def run_extraction(out_spice: Path, out_json: Path) -> None:
    if shutil.which("klt") is None:
        _fail("klt not found on PATH")
    cmd = [
        "klt", "extract", str(GDS),
        "--parasitics",
        "--deck", DECK,
        "--top", TOP_CELL,
        "--pdk", PDK_VARIANT,
        "-o", str(out_spice),
        "--format", "json",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        _fail(f"klt extract failed ({proc.returncode}):\n{proc.stderr}")
    report = json.loads(proc.stdout)
    if report.get("status") != "extracted":
        _fail(f"klt extract status is {report.get('status')!r}")
    _assert_pinned(report, "this klt extract run")
    # The netlist path is an absolute host path in the envelope; normalise it
    # to the repo-relative committed location so the JSON carries no home dir
    # (the same rule `klt env-provenance --lint` enforces on committed
    # envelopes elsewhere in this repo).
    report["netlist_path"] = str(EXTRACT_SPICE.relative_to(REPO_ROOT))
    report["file"] = str(GDS.relative_to(REPO_ROOT))
    out_json.write_text(json.dumps(report, indent=2) + "\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--check", action="store_true",
        help="re-derive into a scratch dir and diff against the committed "
             "outputs instead of overwriting them; exit 3 on drift",
    )
    args = ap.parse_args(argv)

    with tempfile.TemporaryDirectory(prefix="extract-pex-") as scratch:
        scratch_dir = Path(scratch)
        raw_spice_path = scratch_dir / "comparator.extract.spice"
        raw_json_path = scratch_dir / "extract-parasitics.json"
        run_extraction(raw_spice_path, raw_json_path)
        raw_spice = raw_spice_path.read_text()
        dut, preamp, warnings = rewrite(raw_spice)

        produced = {
            EXTRACT_SPICE: raw_spice,
            PEX_FRAGMENT: dut,
            PEX_PREAMP_FRAGMENT: preamp,
        }
        for w in warnings:
            print(f"warning: {w}", file=sys.stderr)

        if args.check:
            # The JSON envelope carries a fresh timestamp, so only the
            # verdict-bearing netlists are diffed here -- but the committed
            # envelope's TOOL PIN is checked, because a netlist match against
            # an off-pin fresh extraction would be the wrong kind of "OK".
            if not EXTRACT_JSON.exists():
                _fail(f"{EXTRACT_JSON} is missing")
            _assert_pinned(
                json.loads(EXTRACT_JSON.read_text()),
                f"the committed {EXTRACT_JSON.relative_to(REPO_ROOT)}",
            )
            drift = [p.name for p, text in produced.items()
                     if not p.exists() or p.read_text() != text]
            if drift:
                print(f"DRIFT: {', '.join(drift)} differ from a fresh extraction")
                return 3
            print(
                "OK: committed post-layout netlists match a fresh extraction "
                f"on the pinned klt {PINNED_KLT_VERSION} / klayout "
                f"{PINNED_KLAYOUT_VERSION}"
            )
            return 0

        for path, text in produced.items():
            path.write_text(text)
        EXTRACT_JSON.write_text(raw_json_path.read_text())
        report = json.loads(EXTRACT_JSON.read_text())
        par = report["parasitics"]
        print(f"wrote {EXTRACT_SPICE.relative_to(REPO_ROOT)}")
        print(f"wrote {EXTRACT_JSON.relative_to(REPO_ROOT)}")
        print(f"wrote {PEX_FRAGMENT.relative_to(REPO_ROOT)}")
        print(f"wrote {PEX_PREAMP_FRAGMENT.relative_to(REPO_ROOT)}")
        print(
            f"  devices={report['device_count']} nets={report['net_count']} "
            f"R={par['r_count']} C={par['c_count']} Cc={par['cc_count']} "
            f"total_C={par['total_capacitance_ff']:.2f}fF "
            f"total_R={par['total_resistance_ohm']:.1f}ohm"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
