"""layout/evidence_emit.py -- signoff evidence for the *already emitted* GDS.

This module re-runs the signoff ``klt`` checks (``klt drc`` / ``klt lvs`` /
``klt erc``) against the *already emitted* ``layout/comparator.gds`` and
writes the seven committed evidence artifacts -- ``drc-report.json``,
``lvs-request.json`` + ``lvs-report.json``, ``lvs-coverage-probe.json``,
``erc-spec.json`` + ``erc-report.json`` + ``erc-coverage-probe.json``.  It
never draws geometry: the GDS and its four generator deliverables belong to
``layout/gen_comparator.py`` (the single reviewable source, and the only
CLI), which imports the five ``emit_*`` entry points from here.

``drc-report.json`` is what ``manifests/sky130-comparator.json`` cites for
T1 item 3; ``lvs-report.json`` is cited for item 4 (issue #123: the resistors
are drawn at the schematic's 0.35um and the request compares resistor L/W
explicitly -- layout/README.md's "Why item 4 is cited"); the ``erc-*`` trio
plus ``lvs-report.json`` back the item-11 citation ("Why item 11 is cited" in
the same file).
"""
from __future__ import annotations

import hashlib
import json
import re
import tempfile
from pathlib import Path

# The one seam back to the generator: the layer-table-derived ERC tuples
# stay beside the layer table (their literals read it on import), and the
# shape helpers this module's probes reuse live there too.
from gen_comparator import (ERC_STACKUP, ERC_VIAS, KLT_PIN, L_DIFF,
                            L_LICON, L_MET1_PIN, L_NWELL, L_TAP, NWELL_BOX,
                            TAPS, run)

# --- T1 item 4 (LVS) request -------------------------------------------------
# The reference side is the schematic's own derivation product -- what
# ``design/netlist.sh`` writes out of ``design/comparator.sch``, never
# hand-edited (``./design/netlist.sh --check`` asserts exactly that).  It is
# the item-1 netlist ``manifests/design-evidence-tiers.md`` item 4 requires the
# compare to run against.
LVS_REFERENCE = "sim/comparator-decision/testbench/comparator_core.spice"
LVS_TOP = "gen_compose_0"

# sky130 spells its poly resistor two ways: the geometry-parameterised
# primitive ``sky130_fd_pr__res_high_po`` (``l``/``w`` at the call site) and a
# family of fixed-width wrappers that instantiate it with the width baked into
# the *name* -- ``sky130_fd_pr__res_high_po_0p35`` is literally
# ``x0 r0 r1 sub sky130_fd_pr__res_high_po l=l w=0.35``.  The schematic uses
# the wrapper; klt's extraction deck curates only the primitive, so
# ``reference.device_map`` binds one to the other.  The object form is
# required because this is a 3-terminal resistor, not a 4-terminal MOS.
#
# Through klt 0.6.0 this mapping instead pointed at a parameter no call
# site carried, so the compare carried no resistor geometry; see
# ``layout/README.md`` -> "LVS signoff" (#123).
LVS_RESISTOR_WRAPPER = "sky130_fd_pr__res_high_po_0p35"
#: The width the wrapper name bakes in (``..._0p35``), um.
LVS_RESISTOR_WRAPPER_WIDTH_UM = 0.35

LVS_REQUEST = {
    "engine": "klayout",
    "layout": {
        "file": "layout/comparator.gds",
        "deck": "sky130",
        "top": LVS_TOP,
    },
    "reference": {
        "netlist": LVS_REFERENCE,
        "form": "subckt-call",
        "deck": "sky130",
        # klt 0.7.0 (klayout-tools#2459): a fixed-geometry wrapper states its
        # name-baked dimension through ``width_um``; ``l`` stays a real
        # call-site parameter (the schematic's L=22 / L=1.75), so the
        # reference side now carries BOTH L and W and the geometry can be
        # compared rather than discarded.
        "device_map": {
            LVS_RESISTOR_WRAPPER: {
                "kind": "resistor",
                "class": "res_high_po",
                "width_um": LVS_RESISTOR_WRAPPER_WIDTH_UM,
            },
        },
    },
    # The layout folds the input pair into two W=6.5um legs per device (the
    # common-centroid cross-quad); the schematic states one W=13um device.
    # combine_devices is what reconciles the two -- the same fold
    # extract-device-count.json's "merged_counts" already records.
    #
    # compare_parameters forces the resistor class's L and W into the compare.
    # KLayout's default scope compares only a resistor's primary parameter R,
    # which the reference form excludes as a placeholder, so without this a
    # drawn width/length that disagrees with the schematic still grades
    # ``match`` (measured in layout/lvs-coverage-probe.json).
    "options": {"combine_devices": True,
                "compare_parameters": {"res_high_po": ["L", "W"]}},
}

# --- T1 item 11 (ERC, power delivery *structural*) supply spec ----------------
# ``klt erc``'s spec document, built by :func:`build_erc_spec` and committed as
# ``layout/erc-spec.json``.  Item 11 asks one question -- "is the supply
# connected to what it powers?" -- and grades it on: at least one
# ``"kind": "supply"`` net declared, at least one ``ties[]`` entry declared and
# actually checked (not skipped as degenerate), and no supply-side finding.
# IR drop and electromigration (``klt power``) are explicitly outside it.
#
# The supply-spec run is the *structural* half only.  What it is NOT is a claim
# about the antenna verdict it also carries, or about T1 item 4 -- see
# layout/README.md -> "ERC: supply-spec run, committed -- and why T1 item 11 is
# still not claimed".
ERC_SPEC_PATH = "layout/erc-spec.json"
ERC_REPORT_PATH = "layout/erc-report.json"
ERC_PROBE_PATH = "layout/erc-coverage-probe.json"

#: ``klt erc``'s antenna-ratio limit *table* name (not the PDK variant): the
#: flag selects a curated limit table and needs no PDK install, unlike
#: ``klt drc --pdk sky130A --pdk-root ...``.
ERC_ANTENNA_PDK = "sky130"

#: The curated extraction deck whose own device-body markers are carved out of
#: the matching conductor role (klayout-tools#2183/#2204).  Without it the
#: three poly resistor *bodies* read as plain poly wires and VDD conducts
#: through them into OUTP1/OUTN1 -- the false-positive caveat the item-11
#: checklist text requires be checked before a finding is believed.  With it,
#: ``provenance.devices[]`` records the carve-out (``res_high_po``, 66/20) so
#: the narrowing is stated in the evidence rather than applied silently.
ERC_DECK = "sky130"

#: The supplies whose continuity item 11 is about, in the order the spec
#: declares them.  Both are labelled on met1.pin by the router (``PIN_NETS``).
ERC_SUPPLY_NETS = ("VDD", "GND")


def layer_id(layer: tuple[int, int]) -> str:
    """One GDS layer/datatype pair in klt's ``"<layer>/<datatype>"`` spelling."""
    return f"{layer[0]}/{layer[1]}"


def substrate_boxes(bbox: dict) -> list[list[float]]:
    """The p-substrate region this block asserts for its GND tie: the top
    cell's own extent minus the drawn n-well, as ``[left, bottom, right, top]``
    micrometre boxes.

    sky130 draws no pwell/tub layer for a native-substrate NMOS block -- there
    is nothing to name as ``ties[].well_layer`` -- so the GND tie uses klt's
    native-substrate form (``"well_layer": null`` + ``well_boxes``,
    klayout-tools#2255) and names the region instead.  Derived from the
    composed bbox and ``NWELL_BOX`` rather than transcribed, so a floorplan
    move carries the assertion with it.

    Held to klt's own falsifiability test: an assertion covering the whole
    top-cell extent (to within 1%) is graded *skipped*
    (``degenerate_well_assertion``), not clean, because "the entire die is the
    substrate" makes ``erc.missing_tie`` satisfiable by any contact anywhere.
    Subtracting the n-well leaves 241.5 um^2 of the 3330.0 um^2 extent
    uncovered (7.25%), and the four boxes merge into the one ring-shaped
    polygon the substrate actually is -- which must therefore contain a tap
    that reaches GND.  The ``degenerate_well`` probe row asserts the
    whole-extent form is still rejected.
    """
    if not bbox:
        raise RuntimeError(
            "klt gen-compose reported no composed bbox, so the GND tie has no "
            "top-cell extent to assert its substrate region against")
    x0, y0 = round(bbox["x0"], 3), round(bbox["y0"], 3)
    x1, y1 = round(bbox["x1"], 3), round(bbox["y1"], 3)
    w = NWELL_BOX
    boxes = []
    if w["x0"] > x0:
        boxes.append([x0, y0, w["x0"], y1])
    if w["x1"] < x1:
        boxes.append([w["x1"], y0, x1, y1])
    if w["y0"] > y0:
        boxes.append([w["x0"], y0, w["x1"], w["y0"]])
    if w["y1"] < y1:
        boxes.append([w["x0"], w["y1"], w["x1"], y1])
    if not boxes:
        raise RuntimeError(
            "the drawn n-well covers the whole composed extent, so there is no "
            "p-substrate region to assert for the GND tie")
    return boxes


def build_erc_spec(bbox: dict) -> dict:
    """The ``klt erc`` supply spec for the committed GDS.

    ``tap_is_dedicated: true`` on both ties is the load-bearing declaration:
    klt grades a tie whose tap region is "whatever that layer draws inside the
    well" as *skipped* rather than clean (klayout-tools#2199), because an
    ordinary PMOS source contact would then satisfy it.  sky130's ``tap``
    (65/44) is a tap-only layer by PDK definition, and this stream draws it in
    exactly two places -- the two body-tie structures ``TAPS`` places (``klt
    gen`` blocks draw only nwell/diff/poly/licon1/li1, never tap).  Asserted,
    not assumed: ``emit_erc_evidence`` re-counts 65/44 against ``TAPS`` before
    it will commit the envelope.
    """
    return {
        "stackup": [
            {
                "name": entry["name"],
                "layer": layer_id(entry["layer"]),
                **({"role": entry["role"]} if "role" in entry else {}),
                **({"active_layer": layer_id(entry["active_layer"])}
                   if "active_layer" in entry else {}),
                **({"label_layer": layer_id(entry["label_layer"])}
                   if "label_layer" in entry else {}),
            }
            for entry in ERC_STACKUP
        ],
        "vias": [
            {
                "name": via["name"],
                "layer": layer_id(via["layer"]),
                "between": list(via["between"]),
            }
            for via in ERC_VIAS
        ],
        "nets": [{"name": net, "kind": "supply"} for net in ERC_SUPPLY_NETS],
        "ties": [
            {
                "name": "psub_gnd",
                "well_layer": None,
                "well_boxes": substrate_boxes(bbox),
                "tap_layer": layer_id(L_TAP),
                "tap_is_dedicated": True,
                "connect_to": "li1",
                "net": "GND",
            },
            {
                "name": "nwell_vdd",
                "well_layer": layer_id(L_NWELL),
                "tap_layer": layer_id(L_TAP),
                "tap_is_dedicated": True,
                "connect_to": "li1",
                "net": "VDD",
            },
        ],
    }


def emit_drc_evidence(klt: str, pdk_args: list[str], repo_root: Path) -> None:
    """Re-run the composed DRC against the *emitted* GDS and commit it.

    This is T1 item 3's citable evidence (issue #46), distinct from the
    step-[6/7] run inside ``_gen/``: that one runs with ``cwd=_gen`` on a
    bare ``comparator.gds``, so the envelope it records names a path that
    does not resolve from the repo root where ``klt signoff`` /
    ``scripts/check-t1-signoff.py`` grade it.  Re-running from the repo root
    on ``layout/comparator.gds`` records both the path CI resolves and the
    ``provenance.input.content_hash`` the manifest pins -- so regenerating
    the GDS without refreshing this file renders item 3 ``unmet`` (stale
    evidence) rather than grading a superseded run.

    Unlike step [6/7] this checks the verdict: committing an envelope that
    records violations as *signoff evidence* would be a false claim.
    """
    r = run([klt, "drc", "layout/comparator.gds", "--deck", "sky130"] + pdk_args
            + ["--format", "json"], cwd=repo_root, check=False)
    envelope = json.loads(r.stdout) if r.stdout.strip() else {"error": r.stderr}
    if r.returncode != 0 or envelope.get("status") != "clean":
        raise RuntimeError(
            f"signoff DRC over layout/comparator.gds is not clean "
            f"(rc={r.returncode}, status={envelope.get('status')!r}, "
            f"violations={envelope.get('violation_count')}) -- refusing to "
            "commit it as T1 item 3 evidence"
        )
    (repo_root / "layout" / "drc-report.json").write_text(
        json.dumps(envelope, indent=2) + "\n")
    cov = envelope.get("coverage") or {}
    print("  signoff drc: status=clean, "
          f"layers_in_stream_without_rules={len(cov.get('layers_in_stream_without_rules', []))}, "
          f"rules_skipped={len(cov.get('rules_skipped', []))}, "
          f"deck_scope={len(cov.get('deck_scope', []))} "
          "(disclosure: layout/README.md)")


def _run_lvs(klt: str, request: dict, repo_root: Path) -> tuple[dict, int]:
    """Run one ``klt lvs`` compare from ``repo_root``; return (envelope, rc).

    The request goes in on **stdin** rather than as a file path on purpose:
    relative paths inside a request *file* resolve against that file's own
    directory, while the stdin form resolves them against the current working
    directory.  Running from the repo root with the stdin form is therefore
    what makes the envelope echo repo-root-relative paths
    (``layout/comparator.gds``, ``sim/.../comparator_core.spice``) -- the paths
    CI and ``klt signoff`` resolve -- instead of host-specific absolute ones.
    """
    r = run([klt, "lvs", "-", "--format", "json"], cwd=repo_root, check=False,
            stdin_text=json.dumps(request))
    if not r.stdout.strip():
        raise RuntimeError(f"klt lvs produced no output (rc={r.returncode}): {r.stderr}")
    return json.loads(r.stdout), r.returncode


#: Negative controls for the LVS compare, each a textual perturbation of the
#: committed reference netlist plus the verdict that perturbation MUST
#: produce.  A compare that cannot fail grades nothing (``sim/selftest.sh``'s
#: stage-4 discipline, applied to a signoff artifact), so ``mos_*`` and
#: ``connectivity`` establish that this one bites.  The ``res_*`` rows go
#: further and measure the compare's *reach*, which is the half that decides
#: whether the verdict may be cited: the signoff request forces the resistor
#: class's L and W into the compare (``options.compare_parameters``) and the
#: ``res_*`` rows show a width or length disagreement is then reported as a
#: ``device.property`` error, while ``res_width_10x_default_scope`` shows the
#: same disagreement is invisible at klt's default parameter scope -- which is
#: why a default-scope match alone would not support T1 item 4.
#:
#: ``reference_width_um`` overrides the wrapper's ``device_map`` ``width_um``
#: (klt 0.7.0), varying the reference width through the real mapping path.
LVS_PROBES = (
    {
        "id": "res_geometry_as_schematic",
        "perturbation": "none -- the signoff request unchanged: wrapper "
                        "width_um 0.35 (the schematic) against the drawn "
                        "0.35um resistors, L and W forced into the compare",
        "rewrite_resistors": None,
        "substitutions": (),
        "expected_status": "match",
        "covers": True,
        "reads": "positive control: with resistor L/W compared and the "
                 "drawn geometry equal to the schematic, the compare matches",
    },
    {
        "id": "res_width_ref_0p42",
        "perturbation": "reference wrapper width_um stated as 0.42um (the "
                        "OLD drawn width) against the drawn 0.35um",
        "rewrite_resistors": None,
        "reference_width_um": 0.42,
        "substitutions": (),
        "expected_status": "mismatch",
        "covers": True,
        "reads": "attribution control: a 0.07um resistor width disagreement "
                 "is detected as device.property 'w_um' (layout 0.35 vs "
                 "reference 0.42) on the resistors, so the match above rests "
                 "on the geometry agreeing, not on W being unasked",
    },
    {
        "id": "res_width_10x",
        "perturbation": "reference wrapper width_um stated as 3.5um, 10x the "
                        "schematic device",
        "rewrite_resistors": None,
        "reference_width_um": 3.5,
        "substitutions": (),
        "expected_status": "mismatch",
        "covers": True,
        "reads": "a gross resistor width disagreement is detected "
                 "(device.property 'w_um', layout 0.35 vs reference 3.5)",
    },
    {
        "id": "res_length_2x",
        "perturbation": "R_LP length doubled, 22um -> 44um",
        "rewrite_resistors": None,
        "substitutions": (("XR_LP OUTN1 VDD GND sky130_fd_pr__res_high_po_0p35 L=22",
                           "XR_LP OUTN1 VDD GND sky130_fd_pr__res_high_po_0p35 L=44"),),
        "expected_status": "mismatch",
        "covers": True,
        "reads": "resistor length IS compared (device.property 'l_um', "
                 "layout 22 vs reference 44)",
    },
    {
        "id": "res_width_10x_default_scope",
        "perturbation": "as res_width_10x (wrapper width_um 3.5um), but "
                        "options.compare_parameters removed -- the default "
                        "parameter scope",
        "rewrite_resistors": None,
        "reference_width_um": 3.5,
        "default_scope": True,
        "substitutions": (),
        "expected_status": "match",
        "covers": False,
        "reads": "why the explicit compare_parameters request is required: "
                 "at the default parameter scope even a 10x resistor width "
                 "disagreement still grades match, so a default-scope match "
                 "alone would not establish geometry agreement",
    },
    {
        "id": "mos_width",
        "perturbation": "M_PINN width 13um -> 12um",
        "rewrite_resistors": None,
        "substitutions": (("VINN TAILP GND sky130_fd_pr__nfet_01v8 L=0.5 W=13",
                           "VINN TAILP GND sky130_fd_pr__nfet_01v8 L=0.5 W=12"),),
        "expected_status": "mismatch",
        "covers": True,
        "reads": "MOSFET width IS compared",
    },
    {
        "id": "mos_length",
        "perturbation": "M_PINN length 0.5um -> 0.6um",
        "rewrite_resistors": None,
        "substitutions": (("VINN TAILP GND sky130_fd_pr__nfet_01v8 L=0.5 W=13",
                           "VINN TAILP GND sky130_fd_pr__nfet_01v8 L=0.6 W=13"),),
        "expected_status": "mismatch",
        "covers": True,
        "reads": "MOSFET length IS compared",
    },
    {
        "id": "connectivity",
        "perturbation": "M_RST_N drain moved from OUTN to OUTP",
        "rewrite_resistors": None,
        "substitutions": (("XM_RST_N OUTN CLKT VDD VDD",
                           "XM_RST_N OUTP CLKT VDD VDD"),),
        "expected_status": "mismatch",
        "covers": True,
        "reads": "connectivity IS compared",
    },
)

#: Matches one ``XR_<name> <n1> <n2> <n3> sky130_fd_pr__res_high_po_0p35 L=<l>``
#: card head in the committed reference netlist.
_RES_CARD_RE = re.compile(
    rf"^(XR_\S+(?:\s+\S+){{3}}\s+){LVS_RESISTOR_WRAPPER}(\s+L=\S+)(.*)$",
    re.MULTILINE)


def _probe_reference(base: str, probe: dict) -> str:
    """Apply one probe's perturbation to the reference netlist text.

    Every substitution must actually bite -- a perturbation that silently
    failed to apply would turn a negative control into a second copy of the
    baseline and quietly assert nothing.
    """
    text = base
    width = probe["rewrite_resistors"]
    if width is not None:
        text, n = _RES_CARD_RE.subn(
            rf"\g<1>sky130_fd_pr__res_high_po\g<2> w={width}\g<3>", text)
        if n != 3:
            raise RuntimeError(
                f"LVS probe {probe['id']}: expected to rewrite 3 resistor "
                f"cards, rewrote {n} -- the reference netlist moved")
    for old, new in probe["substitutions"]:
        if old not in text:
            raise RuntimeError(
                f"LVS probe {probe['id']}: perturbation target not found in "
                f"the reference netlist ({old!r}) -- the netlist moved and "
                "this control would assert nothing")
        text = text.replace(old, new, 1)
    return text


def _property_findings(envelope: dict) -> list[dict]:
    """Distinct ``device.property`` (parameter, layout, reference) triples.

    One row per distinct compared-parameter disagreement, deduplicated over
    the device instances reporting it -- so the probe record carries the
    numbers a disagreement is actually about (``w_um`` 0.42 vs 0.35), not
    just a category tally.
    """
    seen: list[dict] = []
    for entry in envelope.get("mismatches") or ():
        if entry.get("category") != "device.property":
            continue
        prop = entry.get("property") or {}

        def rounded(value):
            # 9 dp kills float-repr noise (0.35000000000000003) without
            # touching any resolution a device parameter means anything at.
            return round(value, 9) if isinstance(value, float) else value

        row = {"class": (entry.get("device") or {}).get("class"),
               "parameter": prop.get("name"),
               "layout": rounded(prop.get("layout")),
               "reference": rounded(prop.get("reference"))}
        if row not in seen:
            seen.append(row)
    return seen


def _supply_pairing(envelope: dict) -> dict:
    """Whether this compare's ``net_correspondence`` pairs each supply net to a
    reference-side net -- the exact predicate T1 item 11's analog LVS half is
    graded on (``klt signoff``'s ``_lvs_reference_carries_supplies``).

    Measured per probe row because the predicate turns out **not** to be
    independent of the compare's overall verdict: ``net_correspondence`` lists
    only *matched* nets, so every ``match`` pairs both supplies and every
    ``mismatch`` drops at least one -- including ``mos_width``, whose
    perturbation is a transistor width and has nothing to do with the rails.
    Item 11's LVS half therefore carries no information beyond "item 4's
    envelope reports match", which is the measurement behind
    layout/README.md -> "Why item 11 is cited".
    """
    paired = {
        str(row.get("layout")).upper()
        for row in envelope.get("net_correspondence") or ()
        if isinstance(row, dict) and row.get("layout") and row.get("reference")
    }
    return {
        "net_correspondence_rows": len(envelope.get("net_correspondence") or ()),
        "nets_matched": ((envelope.get("counts") or {}).get("nets") or {})
        .get("matched"),
        "supplies_paired": {net: net.upper() in paired
                            for net in ERC_SUPPLY_NETS},
        "all_supplies_paired": all(net.upper() in paired
                                   for net in ERC_SUPPLY_NETS),
    }


def emit_lvs_coverage_probe(klt: str, repo_root: Path, signoff: dict) -> None:
    """Measure what the signoff LVS `match` does and does not cover.

    A `klt lvs` envelope states its verdict, not its reach.  Two things about
    this design's reach have to be stated with any claim and neither is
    readable off the envelope: that the compare can fail at all, and that the
    block's known drawn-versus-schematic resistor width delta (0.42um drawn
    vs the schematic's ``res_high_po_0p35``) sits in a blind spot of it.
    Both are measured here -- one compare per row of ``LVS_PROBES``, each
    against a perturbed **scratch** copy of the reference netlist; the
    committed ``sim/.../comparator_core.spice`` is never written to.

    Writes ``layout/lvs-coverage-probe.json``, and raises if any row's
    observed verdict differs from the one it asserts.
    """
    base = (repo_root / LVS_REFERENCE).read_text()
    rows = []
    with tempfile.TemporaryDirectory(prefix="loom-lvs-probe-") as tmp_str:
        tmp = Path(tmp_str)
        for probe in LVS_PROBES:
            scratch = tmp / f"{probe['id']}.spice"
            scratch.write_text(_probe_reference(base, probe))
            request = json.loads(json.dumps(LVS_REQUEST))
            request["reference"]["netlist"] = str(scratch)
            if probe["rewrite_resistors"] is not None:
                # The cards now name the curated generic device, so the
                # fixed-width wrapper mapping no longer applies.
                request["reference"]["device_map"] = {}
            if probe.get("reference_width_um") is not None:
                request["reference"]["device_map"][LVS_RESISTOR_WRAPPER][
                    "width_um"] = probe["reference_width_um"]
            if probe.get("default_scope"):
                request["options"].pop("compare_parameters", None)
            elif probe.get("compare_parameters") is not None:
                request["options"]["compare_parameters"] = \
                    probe["compare_parameters"]
            envelope, _rc = _run_lvs(klt, request, repo_root)
            observed = envelope.get("status")
            rows.append({
                "id": probe["id"],
                "perturbation": probe["perturbation"],
                "compare_parameters": request["options"].get("compare_parameters"),
                "compare_covers_this": probe["covers"],
                "reads_as": probe["reads"],
                "expected_status": probe["expected_status"],
                "observed_status": observed,
                "error_count": envelope.get("error_count"),
                "category_counts": envelope.get("category_counts"),
                "property_findings": _property_findings(envelope),
                "supply_pairing": _supply_pairing(envelope),
                "pass": observed == probe["expected_status"],
            })
            print(f"    probe {probe['id']}: {observed} "
                  f"(expected {probe['expected_status']}) "
                  f"{'PASS' if rows[-1]['pass'] else 'FAIL'}")
    ok = all(row["pass"] for row in rows)
    evidence = {
        "tool": {"klt_pin": KLT_PIN, "engine": signoff.get("engine"),
                 "engine_version": (signoff.get("environment") or {})
                 .get("engine_version")},
        "method": (
            "negative controls for layout/lvs-report.json: one klt lvs "
            "compare per row, each against a perturbed scratch copy of "
            f"{LVS_REFERENCE} (the committed netlist is never written to) "
            "and the same layout/comparator.gds the signoff run used. A row "
            "with compare_covers_this=true asserts the compare DETECTS that "
            "defect (so the signoff match is not vacuous); a row with "
            "compare_covers_this=false asserts it does NOT -- those are the "
            "holes layout/README.md's LVS section discloses. Each row also "
            "records supply_pairing, the measurement T1 item 11's LVS half is "
            "graded on (klt signoff's _lvs_reference_carries_supplies): see "
            "layout/README.md -> 'Why item 11 is cited'."),
        "signoff_report": "layout/lvs-report.json",
        "signoff_status": signoff.get("status"),
        "signoff_layout_sha256": (signoff.get("environment") or {})
        .get("layout_sha256"),
        "signoff_reference_sha256": (signoff.get("environment") or {})
        .get("reference_sha256"),
        "signoff_supply_pairing": _supply_pairing(signoff),
        "probes": rows,
        "pass": ok,
    }
    (repo_root / "layout" / "lvs-coverage-probe.json").write_text(
        json.dumps(evidence, indent=2) + "\n")
    if not ok:
        raise RuntimeError(
            "LVS coverage probe FAILED -- a negative control did not produce "
            "the verdict it asserts; see layout/lvs-coverage-probe.json")


def emit_lvs_evidence(klt: str, repo_root: Path) -> dict:
    """Run the signoff LVS over the *emitted* GDS and commit it.

    Mirrors :func:`emit_drc_evidence`: run from the repo root against
    ``layout/comparator.gds`` so the committed envelope records both the path
    ``scripts/check-t1-signoff.py`` resolves and the
    ``provenance.input.content_hash`` a manifest citation would pin --
    regenerating the GDS without refreshing this file would then render any
    such citation ``unmet`` (stale) rather than grading a superseded run.

    Writes two files.  ``layout/lvs-request.json`` is the request document
    itself, committed because the response echoes ``layout``/``reference``/
    ``options`` but **not** ``reference.form`` or ``reference.device_map`` --
    without it the committed envelope would not record the device-class
    mapping the compare was reached through.  ``layout/lvs-report.json`` is
    the envelope.

    **The envelope is cited for T1 item 4** (issue #123).  The request forces
    the resistor class's L and W into the compare, the layout draws the
    resistors at the schematic's 0.35um, and
    :func:`emit_lvs_coverage_probe` measures that a width or length
    disagreement is detected while the default parameter scope would miss it;
    layout/README.md's "Why item 4 is cited" carries the reasoning.

    The verdict guard fires after the envelope is on disk, so a failing run
    leaves the evidence to read rather than nothing: the result must be the
    one item 4 is graded on, ``status: "match"`` **and**
    ``power_connectivity.status != "mismatch"``
    (``manifests/design-evidence-tiers.md`` item 4).  Whether the compare can
    fail at all is no longer asserted here -- ``emit_lvs_coverage_probe``'s
    ``mos_*``/``connectivity`` rows are the same assertion, generalised, and
    run immediately after.
    """
    (repo_root / "layout" / "lvs-request.json").write_text(
        json.dumps(LVS_REQUEST, indent=2) + "\n")

    envelope, rc = _run_lvs(klt, LVS_REQUEST, repo_root)
    (repo_root / "layout" / "lvs-report.json").write_text(
        json.dumps(envelope, indent=2) + "\n")

    status = envelope.get("status")
    power = (envelope.get("power_connectivity") or {}).get("status")
    warnings = [m for m in envelope.get("mismatches", [])
                if m.get("severity") != "error"]
    print(f"  signoff lvs: status={status}, power_connectivity={power}, "
          f"errors={envelope.get('error_count')}, warnings={len(warnings)} "
          "(disclosure: layout/README.md)")
    for w in warnings:
        print(f"    warning [{w.get('category')}]: "
              f"{str(w.get('description'))[:100]}")

    if status != "match" or power == "mismatch":
        raise RuntimeError(
            f"signoff LVS over layout/comparator.gds is not clean "
            f"(rc={rc}, status={status!r}, power_connectivity={power!r}, "
            f"errors={envelope.get('error_count')}) -- the envelope was "
            "written for inspection, but layout/README.md's LVS section "
            "describes a clean match, so both it and any manifest citation "
            "must be revisited before this verdict is committed"
        )
    return envelope


def _run_erc(klt: str, layout: str, spec: str, repo_root: Path,
             ) -> tuple[dict, int]:
    """One ``klt erc`` run from the repo root; returns (envelope, rc).

    Run from ``repo_root`` with repo-relative paths so the envelope echoes
    ``file``/``spec`` exactly as ``klt signoff`` and CI resolve them -- the
    same reason :func:`_run_lvs` uses the stdin form.  ``klt erc``'s own exit
    code is 3 for findings and 4 for "nothing graded", both of which are
    *successful* runs; the caller gates on the payload.
    """
    r = run([klt, "erc", layout, spec, "--deck", ERC_DECK,
             "--pdk", ERC_ANTENNA_PDK, "--format", "json"],
            cwd=repo_root, check=False)
    if not r.stdout.strip():
        raise RuntimeError(f"klt erc produced no output (rc={r.returncode}): "
                           f"{r.stderr}")
    return json.loads(r.stdout), r.returncode


def _erc_skip_reasons(envelope: dict) -> list[str]:
    """Every ``erc_coverage.skipped[].reason`` the run recorded, sorted.

    This is the field that separates "the tie check ran and came back clean"
    from "the tie declaration could not be answered" -- klt records a
    degenerate tap declaration (klayout-tools#2199) or a whole-die substrate
    assertion (#2255) here, and ``erc_status`` then reads ``clean_partial``
    rather than ``clean``.  A signoff citation built on such a run renders
    ``supply_spec_incomplete``, never ``met``.
    """
    return sorted({
        str(entry.get("reason"))
        for entry in (envelope.get("erc_coverage") or {}).get("skipped") or []
    })


def _erc_rules(envelope: dict) -> list[str]:
    """The distinct ``erc_findings[].rule`` tokens a run reported, sorted."""
    return sorted({str(f.get("rule")) for f in envelope.get("erc_findings") or []})


def emit_erc_evidence(klt: str, repo_root: Path, bbox: dict) -> dict:
    """Write the ERC supply spec and run it over the *emitted* GDS.

    T1 item 11 ("Power delivery (structural)") is the **structural** supply
    question only: is each declared supply one electrical island, and is every
    well/substrate region tied to the supply that biases it?  IR drop and
    electromigration (``klt power``) are outside it.

    Writes ``layout/erc-spec.json`` (the spec document, committed because the
    envelope echoes its *path* and its content hash but not its declarations --
    without it nobody can read which nets were declared ``supply``) and
    ``layout/erc-report.json`` (the envelope), both from the repo root against
    ``layout/comparator.gds`` for the same path/hash reason
    :func:`emit_drc_evidence` and :func:`emit_lvs_evidence` do.

    **The envelope is cited for T1 item 11 together with
    ``layout/lvs-report.json``** (issue #123), the item's LVS half, which is
    only an independent statement now that item 4 is itself supported -- see
    layout/README.md -> "ERC: supply-spec run, committed -- and why T1 item 11
    is claimed".

    Four guards, each refusing to commit a run that would not support the claim
    the README makes:

    1. the two ties this spec declares must be the only 65/44 geometry in the
       stream, so ``tap_is_dedicated: true`` is a measured fact rather than an
       assumption;
    2. ``erc_status`` must be ``clean`` with zero findings -- and, separately,
       ``erc_coverage.skipped`` must be **empty**: a degenerate tie reports
       zero ``erc.missing_tie`` findings for a reason that has nothing to do
       with taps, and ``clean`` alone cannot tell the two apart;
    3. every declared supply and every declared tie must appear in
       ``erc_coverage.checked``, so "the check ran" is read off the envelope
       rather than inferred from the absence of a finding;
    4. the envelope's own ``provenance.spec.content_hash`` must equal the
       sha256 of the committed spec file.  ``klt signoff``'s item-11 path
       re-reads that spec document from disk to find the declared supply nets
       and does **not** verify it against this hash (klt 0.6.0), so an edited
       spec would otherwise silently change what a citation is graded on.
    """
    spec = build_erc_spec(bbox)
    spec_text = json.dumps(spec, indent=2) + "\n"
    (repo_root / ERC_SPEC_PATH).write_text(spec_text)

    taps = json.loads(
        run([klt, "layers", "layout/comparator.gds", "--format", "json"],
            cwd=repo_root).stdout)
    drawn_taps = sum(entry["shapes"] for entry in taps["layers"]
                     if (entry["layer"], entry["datatype"]) == L_TAP)
    if drawn_taps != len(TAPS):
        raise RuntimeError(
            f"{layer_id(L_TAP)} (tap) carries {drawn_taps} shape(s) but this "
            f"spec's ties assert it is drawn only by the {len(TAPS)} body-tie "
            "structures in TAPS -- 'tap_is_dedicated: true' would no longer be "
            "a measured fact, so refusing to commit it")

    envelope, rc = _run_erc(klt, "layout/comparator.gds", ERC_SPEC_PATH, repo_root)
    (repo_root / ERC_REPORT_PATH).write_text(json.dumps(envelope, indent=2) + "\n")

    coverage = envelope.get("erc_coverage") or {}
    checked = set(coverage.get("checked") or [])
    skipped = _erc_skip_reasons(envelope)
    print(f"  signoff erc: erc_status={envelope.get('erc_status')}, "
          f"findings={envelope.get('erc_finding_count')}, "
          f"skipped={skipped or 'none'}, "
          f"antenna={envelope.get('status')} "
          f"({len((envelope.get('coverage') or {}).get('checked') or [])} level(s) "
          "checked) (disclosure: layout/README.md)")

    if envelope.get("erc_status") != "clean" or envelope.get("erc_finding_count"):
        raise RuntimeError(
            f"signoff ERC over layout/comparator.gds is not clean "
            f"(rc={rc}, erc_status={envelope.get('erc_status')!r}, "
            f"findings={_erc_rules(envelope)}) -- the envelope was written for "
            "inspection, but check the item-11 checklist's two documented "
            "false-positive caveats (klayout-tools#2180 diffusion/well "
            "continuity, #2183 device bodies read as wires) before treating a "
            "supply finding as a real defect")
    if skipped:
        raise RuntimeError(
            f"signoff ERC recorded skipped work {skipped} -- a declared tie klt "
            "could not answer grades 'supply_spec_incomplete', not 'met', so "
            "this envelope must not be committed as item-11 evidence")
    missing = sorted(
        identity for identity in
        [f'erc.net_connectivity:["{net}"]' for net in ERC_SUPPLY_NETS]
        + [f'erc.missing_tie:["{tie["name"]}"]' for tie in spec["ties"]]
        if identity not in checked)
    if missing:
        raise RuntimeError(
            f"signoff ERC did not record {missing} as checked work -- item 11 "
            "requires the supply and tie checks to have actually run, not "
            "merely to have reported nothing")
    spec_hash = "sha256:" + hashlib.sha256(spec_text.encode()).hexdigest()
    recorded = ((envelope.get("provenance") or {}).get("spec") or {}).get(
        "content_hash")
    if recorded != spec_hash:
        raise RuntimeError(
            f"the committed spec hashes to {spec_hash} but the envelope records "
            f"{recorded} -- klt signoff re-reads layout/erc-spec.json without "
            "checking that hash, so the two must not be allowed to diverge")
    return envelope


def _erc_probe_tie_wrong_net(spec: dict, _repo_root: Path, _tmp: Path) -> None:
    for tie in spec["ties"]:
        if tie["name"] == "nwell_vdd":
            tie["net"] = "GND"


def _erc_probe_tap_boxes_no_geometry(spec: dict, _repo_root: Path,
                                     _tmp: Path) -> None:
    for tie in spec["ties"]:
        if tie["name"] == "psub_gnd":
            tie["tap_boxes"] = [[5.0, 5.0, 6.0, 6.0]]


def _erc_probe_psub_split_untapped(spec: dict, _repo_root: Path,
                                   _tmp: Path) -> None:
    boxes = spec["ties"][0]["well_boxes"]
    left = min(boxes, key=lambda b: b[0])
    right = max(boxes, key=lambda b: b[0])
    for tie in spec["ties"]:
        if tie["name"] == "psub_gnd":
            tie["well_boxes"] = [left, right]


def _erc_probe_rail_split_no_via(spec: dict, _repo_root: Path,
                                 _tmp: Path) -> None:
    spec["vias"] = [v for v in spec["vias"] if v["name"] != "via"]


def _erc_probe_supply_short_via_diff(spec: dict, _repo_root: Path,
                                     _tmp: Path) -> None:
    spec["stackup"].insert(1, {"name": "diff", "layer": layer_id(L_DIFF)})
    spec["vias"].insert(0, {"name": "licon1_diff", "layer": layer_id(L_LICON),
                            "between": ["diff", "li1"]})


def _erc_probe_degenerate_tap(spec: dict, _repo_root: Path, _tmp: Path) -> None:
    for tie in spec["ties"]:
        tie.pop("tap_is_dedicated", None)


def _erc_probe_degenerate_well(spec: dict, _repo_root: Path, _tmp: Path) -> None:
    boxes = spec["ties"][0]["well_boxes"]
    extent = [min(b[0] for b in boxes), min(b[1] for b in boxes),
              max(b[2] for b in boxes), max(b[3] for b in boxes)]
    for tie in spec["ties"]:
        if tie["name"] == "psub_gnd":
            tie["well_boxes"] = [extent]


def _erc_probe_undeclared_supply_name(spec: dict, _repo_root: Path,
                                      _tmp: Path) -> None:
    spec["nets"].append({"name": "VPWR", "kind": "supply"})


def _erc_probe_stream_second_vdd_label(spec: dict, repo_root: Path,
                                       tmp: Path) -> str:
    """Perturb the *stream*, not the spec: duplicate a supply label onto a
    second, disconnected electrical island.

    Writes a scratch copy of the committed GDS with one extra ``VDD`` text on
    met1.pin, placed on top of the ``CLK`` label the router already drew -- so
    ``VDD`` names two islands that never touch.  The committed
    ``layout/comparator.gds`` is never written to (the same discipline
    :func:`emit_lvs_coverage_probe` applies to the reference netlist).

    This is the only row that exercises the *multi-island* branch of
    ``erc.unconnected_net``, which is the rule item 11's own wording is about
    ("every declared supply resolves to exactly one electrical island").  It
    also bounds what that rule can see: the island count klt reports is the
    number of islands **carrying the declared label**, so this stream -- which
    draws exactly one text per net -- can report zero islands or two-with-a-
    second-label, but never a rail physically split into a labelled piece and
    an unlabelled orphan.  That split shows up on the *tie* rule instead
    (``rail_split_no_via``), which is why item 11 needs both.
    """
    import klayout.db as kdb

    layout = kdb.Layout()
    layout.read(str(repo_root / "layout" / "comparator.gds"))
    pin_layer = layout.layer(*L_MET1_PIN)
    donor = None
    for cell in layout.each_cell():
        for shape in cell.shapes(pin_layer).each():
            if shape.is_text() and shape.text.string == "CLK":
                donor = (cell, shape.text.x, shape.text.y)
                break
        if donor is not None:
            break
    if donor is None:
        raise RuntimeError(
            "no 'CLK' met1.pin label in layout/comparator.gds -- the "
            "stream probe needs a non-supply labelled island to duplicate "
            "a supply label onto")
    cell, x, y = donor
    cell.shapes(pin_layer).insert(
        kdb.Text(ERC_SUPPLY_NETS[0], kdb.Trans(kdb.Vector(x, y))))
    scratch = tmp / "second-vdd-label.gds"
    layout.write(str(scratch))
    return str(scratch)


#: Negative controls for the ERC supply check, each a perturbation of a
#: **scratch copy** of the spec (or, for the last row, of the stream) plus the
#: findings and coverage classification that perturbation MUST produce.  A
#: check that cannot fail grades nothing -- ``sim/selftest.sh``'s stage-4
#: discipline, and the bar ``lvs-coverage-probe.json`` already set for item 4.
#:
#: Read together they establish four things the committed envelope's own
#: ``erc_status: "clean"`` cannot state on its own: that the tie check bites
#: (four independent ways), that the supply-short rule bites, that the
#: one-island-per-supply rule bites, and that klt's two *unfalsifiability*
#: rejections (a tap indistinguishable from a source/drain contact; a
#: substrate assertion indistinguishable from the whole die) both fire against
#: this very spec the moment its narrowing is removed -- so the committed run's
#: empty ``erc_coverage.skipped`` is a result, not a default.
ERC_PROBES = (
    {
        "id": "tie_wrong_net",
        "perturbation": "the n-well tie declares net GND instead of VDD",
        "mutate": _erc_probe_tie_wrong_net,
        "expect_rules": ["erc.missing_tie"],
        "expect_skipped": [],
        "reads": "the tie check verifies WHICH net the tap reaches, not merely "
                 "that a tap exists",
    },
    {
        "id": "tap_boxes_no_geometry",
        "perturbation": "the substrate tie's tap narrowed by tap_boxes to a "
                        "1x1um region with no tap geometry in it",
        "mutate": _erc_probe_tap_boxes_no_geometry,
        "expect_rules": ["erc.missing_tie"],
        "expect_skipped": [],
        "reads": "a tap assertion matching no drawn geometry is an honest 'no "
                 "tap' finding, not a silent pass",
    },
    {
        "id": "psub_split_untapped",
        "perturbation": "the asserted substrate region split into two "
                        "disjoint bands, only one of which holds the tap",
        "mutate": _erc_probe_psub_split_untapped,
        "expect_rules": ["erc.missing_tie"],
        "expect_skipped": [],
        "reads": "EVERY asserted substrate polygon must independently contain "
                 "a tap that reaches the net -- one tap does not cover the die",
    },
    {
        "id": "rail_split_no_via",
        "perturbation": "the met1<->met2 via role removed from the stackup, "
                        "cutting both rails at every layer change",
        "mutate": _erc_probe_rail_split_no_via,
        "expect_rules": ["erc.missing_tie"],
        "expect_skipped": [],
        "reads": "a rail severed between met1 and met2 is caught -- and caught "
                 "on the TIE rule, because the label-bearing island survives "
                 "(see stream_second_vdd_label)",
    },
    {
        "id": "supply_short_via_diff",
        "perturbation": "diff (65/20) declared as a conductor role, so every "
                        "MOS source conducts to its own drain",
        "mutate": _erc_probe_supply_short_via_diff,
        "expect_rules": ["erc.supply_short"],
        "expect_skipped": [],
        "reads": "the supply-short rule bites: VDD and GND resolving to one "
                 "island is reported, so the committed run's two islands are a "
                 "measurement",
    },
    {
        "id": "undeclared_supply_name",
        "perturbation": "a third supply net 'VPWR' declared, which nothing in "
                        "the stream labels",
        "mutate": _erc_probe_undeclared_supply_name,
        "expect_rules": ["erc.unconnected_net"],
        "expect_skipped": [],
        "reads": "a declared supply matching no labelled geometry is reported "
                 "rather than passing vacuously",
    },
    {
        "id": "degenerate_tap",
        "perturbation": "tap_is_dedicated dropped from both ties, leaving the "
                        "tap region 'whatever 65/44 draws inside the well'",
        "mutate": _erc_probe_degenerate_tap,
        "expect_rules": [],
        "expect_skipped": ["degenerate_tap_declaration"],
        "reads": "klayout-tools#2199's unfalsifiability rejection fires "
                 "against THIS spec -- zero findings, but the work is recorded "
                 "as skipped and item 11 would render supply_spec_incomplete",
    },
    {
        "id": "degenerate_well",
        "perturbation": "the asserted substrate region widened to the whole "
                        "top-cell extent",
        "mutate": _erc_probe_degenerate_well,
        "expect_rules": [],
        "expect_skipped": ["degenerate_well_assertion"],
        "reads": "klayout-tools#2255's counterpart rejection: 'the entire die "
                 "is the substrate' is skipped work, not a clean tie",
    },
    {
        "id": "stream_second_vdd_label",
        "perturbation": "a second VDD label drawn on met1.pin over the CLK "
                        "label, in a scratch copy of the GDS",
        "mutate": _erc_probe_stream_second_vdd_label,
        "perturbs_stream": True,
        "expect_rules": ["erc.unconnected_net"],
        "expect_skipped": [],
        "reads": "the multi-island branch bites -- and bounds the rule: klt "
                 "counts islands CARRYING THE LABEL, so a one-label rail can "
                 "never report a labelled/orphan split",
    },
)


#: The compound item-11 manifest entry (layout/README.md -> "Why item 11 is
#: cited").  Probed rather than asserted: :func:`_erc_grade_if_cited` writes it
#: into a scratch manifest and records what ``klt signoff`` makes of it, so
#: the prose claim "the grader renders met" is a measurement a reader can
#: re-run.
ERC_ITEM_11_PARTS = (ERC_REPORT_PATH, "layout/lvs-report.json")

TIERS_DOC = "manifests/design-evidence-tiers.md"
MANIFEST = "manifests/sky130-comparator.json"


def _erc_grade_if_cited(klt: str, repo_root: Path, tmp: Path,
                        content_hash: str) -> dict:
    """What ``klt signoff`` would make of an item-11 citation of the committed
    ERC + LVS envelopes -- graded against a **scratch** manifest, so
    ``manifests/sky130-comparator.json`` is not touched.

    This exists because "the citation grades met" is a measurement, not an
    assertion.  It also rots loudly in the useful
    direction: if a future klt changes item 11's rules so this set no longer
    grades ``met``, the generator fails here and whoever bumps the pin has to
    revisit the README's reasoning instead of leaving stale prose behind.
    """
    manifest = json.loads((repo_root / MANIFEST).read_text())
    manifest["evidence"]["11"] = [
        {"file": part, "content_hash": content_hash}
        for part in ERC_ITEM_11_PARTS
    ]
    scratch = tmp / "manifest-with-item-11.json"
    scratch.write_text(json.dumps(manifest, indent=2) + "\n")
    r = run([klt, "signoff", "--manifest", str(scratch),
             "--tiers-doc", TIERS_DOC, "--format", "json"],
            cwd=repo_root, check=False)
    if not r.stdout.strip():
        raise RuntimeError(f"klt signoff produced no output (rc={r.returncode}): "
                           f"{r.stderr}")
    report = json.loads(r.stdout)
    row = next(item for item in report["items"] if item["id"] == 11)
    power = (row.get("citation") or {}).get("power_delivery") or {}
    result = {
        "method": (
            "klt signoff --manifest <scratch copy of "
            f"{MANIFEST} with an item-11 citation of "
            f"{' + '.join(ERC_ITEM_11_PARTS)}> --tiers-doc {TIERS_DOC}. The "
            "committed manifest is NOT modified: this row records what the "
            "grader says for the citation the committed manifest carries (or "
            "would carry), so the item-11 verdict is a re-runnable "
            "measurement. The reasoning is in layout/README.md -> 'Why item "
            "11 is cited'."),
        "cited_parts": list(ERC_ITEM_11_PARTS),
        "item_11_status": row.get("status"),
        "item_11_reason": row.get("reason"),
        "t1_met_count_if_cited": report.get("t1_met_count"),
        "t1_item_count": report.get("t1_item_count"),
        "supply_nets_graded": power.get("supply_nets"),
        "power_connectivity_status": power.get("power_connectivity_status"),
        "ties_checked_by_well_assertion": power.get(
            "ties_checked_by_well_assertion"),
        "committed_manifest_cites_item_11": "11" in json.loads(
            (repo_root / MANIFEST).read_text())["evidence"],
    }
    if result["item_11_status"] != "met":
        raise RuntimeError(
            "the item-11 citation no longer grades "
            f"'met' (got {result['item_11_status']!r}, reason "
            f"{result['item_11_reason']!r}) -- layout/README.md's 'Why item 11 "
            "is cited' argues from the premise that it does, so that "
            "reasoning and the manifest citation must be revisited rather "
            "than silently outlived")
    return result


def emit_erc_coverage_probe(klt: str, repo_root: Path, bbox: dict,
                            signoff: dict) -> None:
    """Measure whether the committed ERC supply check can fail.

    ``layout/erc-report.json`` states ``erc_status: "clean"`` with an empty
    ``erc_coverage.skipped``.  Neither field says whether the check *could*
    have said anything else, and for a supply check that is the whole
    question: klt computes ``erc.unconnected_net``/``erc.supply_short`` only
    for nets the spec declares and ``erc.missing_tie`` only for ties it
    declares, so an under-declared spec reports a clean supply for the same
    reason a rule-free DRC deck reports zero violations.

    One ``klt erc`` run per row of :data:`ERC_PROBES`, each against a
    perturbed **scratch** copy of the spec -- or, for the stream row, of the
    GDS.  Neither committed artifact is written to.  Writes
    ``layout/erc-coverage-probe.json`` and raises if any row's observed
    findings or coverage classification differ from the ones it asserts.
    """
    base = build_erc_spec(bbox)
    rows = []
    with tempfile.TemporaryDirectory(prefix="loom-erc-probe-") as tmp_str:
        tmp = Path(tmp_str)
        for probe in ERC_PROBES:
            spec = json.loads(json.dumps(base))
            layout = "layout/comparator.gds"
            perturbed = probe["mutate"](spec, repo_root, tmp)
            if probe.get("perturbs_stream"):
                layout = perturbed
            spec_path = tmp / f"{probe['id']}.json"
            spec_path.write_text(json.dumps(spec, indent=2) + "\n")
            envelope, rc = _run_erc(klt, layout, str(spec_path), repo_root)
            rules = _erc_rules(envelope)
            skipped = _erc_skip_reasons(envelope)
            ok = (rules == sorted(probe["expect_rules"])
                  and skipped == sorted(probe["expect_skipped"]))
            rows.append({
                "id": probe["id"],
                "perturbation": probe["perturbation"],
                "perturbs": "stream" if probe.get("perturbs_stream") else "spec",
                "reads_as": probe["reads"],
                "expected_rules": sorted(probe["expect_rules"]),
                "observed_rules": rules,
                "expected_skipped_reasons": sorted(probe["expect_skipped"]),
                "observed_skipped_reasons": skipped,
                "erc_status": envelope.get("erc_status"),
                "erc_finding_count": envelope.get("erc_finding_count"),
                "exit_status": rc,
                "findings": [
                    {k: v for k, v in finding.items()
                     if k in ("rule", "net", "other_net", "description")}
                    for finding in envelope.get("erc_findings") or []
                ],
                "pass": ok,
            })
            print(f"    probe {probe['id']}: {envelope.get('erc_status')} "
                  f"rules={rules or 'none'} skipped={skipped or 'none'} "
                  f"{'PASS' if ok else 'FAIL'}")
        grade = _erc_grade_if_cited(
            klt, repo_root, tmp,
            ((signoff.get("provenance") or {}).get("input") or {})
            .get("content_hash"))
        print(f"    item 11 citation grades {grade['item_11_status']} "
              f"({grade['t1_met_count_if_cited']}/{grade['t1_item_count']} T1 "
              "items), see layout/README.md")
    ok = all(row["pass"] for row in rows)
    evidence = {
        "tool": {"klt_pin": KLT_PIN,
                 "klt_version": (signoff.get("provenance") or {}).get("klt_version"),
                 "klayout_version": (signoff.get("provenance") or {})
                 .get("klayout_version"),
                 "antenna_pdk": ERC_ANTENNA_PDK, "deck": ERC_DECK},
        "method": (
            "negative controls for layout/erc-report.json: one klt erc run per "
            "row against a perturbed scratch copy of layout/erc-spec.json (or, "
            f"for the {'/'.join(p['id'] for p in ERC_PROBES if p.get('perturbs_stream'))}"
            " row, of layout/comparator.gds) -- neither committed artifact is "
            "written to. Each row asserts the exact set of erc_findings rules "
            "AND the exact set of erc_coverage.skipped reasons that "
            "perturbation must produce, because a supply check reports nothing "
            "both when it is clean and when it was never asked."),
        "signoff_report": ERC_REPORT_PATH,
        "signoff_spec": ERC_SPEC_PATH,
        "signoff_erc_status": signoff.get("erc_status"),
        "signoff_skipped_reasons": _erc_skip_reasons(signoff),
        "signoff_layout_content_hash": ((signoff.get("provenance") or {})
                                        .get("input") or {}).get("content_hash"),
        "signoff_spec_content_hash": ((signoff.get("provenance") or {})
                                      .get("spec") or {}).get("content_hash"),
        "probes": rows,
        "signoff_if_cited": grade,
        "pass": ok,
    }
    (repo_root / ERC_PROBE_PATH).write_text(json.dumps(evidence, indent=2) + "\n")
    if not ok:
        raise RuntimeError(
            "ERC coverage probe FAILED -- a negative control did not produce "
            f"the findings it asserts; see {ERC_PROBE_PATH}")
