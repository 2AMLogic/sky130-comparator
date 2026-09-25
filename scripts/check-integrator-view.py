#!/usr/bin/env python3
"""CI gate for the rule-9 integrator view (issue #36).

    python3 scripts/check-integrator-view.py gate
    python3 scripts/check-integrator-view.py selftest

`gate` validates the committed manifests/integrator-view.json against this
tree so the view cannot rot silently: required keys must be present, every
non-null cited path must exist in-tree (a stale GDS/netlist/schematic path
FAILS here rather than pointing an integrator at a vanished file), and the
maturity rung must agree with the graded verdict of record
(manifests/t1-signoff-report.json) -- a view claiming "T1" while the
signoff report grades tier null, or vice versa, FAILS. The prose in
`maturity_rung_basis` is held to the same report: it must name the report's
path (so it can never cite a vanished record), and if it states an
`N/M T1 items met` figure, that figure FAILS unless it agrees with the
report's `t1_met_count`/`t1_item_count` (issue #50).

Honest nulls are first-class: `gds.path` and `measured_area.value_um2` are
`null` today (no layout exists), and that is accepted -- but ONLY with the
"not yet produced" note beside them, so an integrator reads a deliberate
absence, never an accidentally-empty field. When layout lands, the fields
flip to real values and the same gate holds them to the same existence
check (issue #36's edge case: "the validator must accept both but never a
stale path").

`selftest` exercises the validation logic against hermetic fixtures (no
network, no klt binary, no PDK) so the gate's own behavior is itself a
recorded, repeatable check -- including the negative controls that prove
the rot detector actually bites (sim/selftest.sh's stage-4 discipline: a
monitor that cannot fail grades nothing).

Stdlib only, no virtualenv required. The two-path (gate / selftest) shape
mirrors scripts/check-t1-signoff.py (issue #31), and the two share one copy
of the gate-output convention (`fail`/`ok`/`load_json`, issue #56) plus the
selftest tally and argv dispatch tails (`report_cases`/`dispatch`, issue
#69) by importing them from scripts/_gate_common.py, so they cannot drift.

Exit codes: 0 gate pass, 1 gate failure, 2 usage error.
"""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _gate_common import (FAILURES, dispatch, fail, load_json,  # noqa: E402
                          ok, report_cases, reset)

REPO_DEFAULTS = {
    "view": "manifests/integrator-view.json",
    "signoff_report": "manifests/t1-signoff-report.json",
}

REQUIRED_KEYS = (
    "schema_version",
    "block",
    "top_cell",
    "ports",
    "netlist",
    "gds",
    "measured_area",
    "maturity_rung",
    "maturity_rung_basis",
    "provenance",
)

PORT_DIRECTIONS = ("input", "output", "inout", "power")

TIER_LADDER = ("T1", "T2", "T3", "T4")


def expected_rung(signoff_report: dict) -> str:
    """Map the graded verdict of record onto the view's rung vocabulary.

    The report's `tier` is null until every T1 item is met (issue #31's
    honest pre-T1 convention); the view says "pre-T1" for that state and
    the tier id itself once the grader awards one.
    """
    tier = signoff_report.get("tier")
    if tier is None:
        return "pre-T1"
    if tier in TIER_LADDER:
        return tier
    raise ValueError(
        f"signoff report carries an unrecognized tier {tier!r} -- expected "
        f"null or one of {TIER_LADDER}; regenerate the report"
    )


def check_path_in_tree(repo: Path, value, what: str) -> None:
    """A cited path must be null or exist in-tree; never dangling."""
    if value is None:
        return
    if not isinstance(value, str) or not value:
        fail(f"{what} must be null or a non-empty string, got {value!r}")
        return
    if not (repo / value).exists():
        fail(
            f"{what} cites '{value}' which does not exist in-tree -- a "
            "cited path must never dangle (fix the view, or restore the "
            "artifact)"
        )


def validate_view(view: dict, signoff_report: dict, repo: Path, what: str) -> None:
    """The gate proper. Records failures in FAILURES; returns nothing."""
    # Rule 1: required keys present.
    for key in REQUIRED_KEYS:
        if key not in view:
            fail(f"{what} is missing required key '{key}'")

    # Rule 2: top cell names a source that exists in-tree.
    top = view.get("top_cell")
    if isinstance(top, dict):
        if not isinstance(top.get("name"), str) or not top["name"]:
            fail(f"{what} top_cell.name must be a non-empty string")
        check_path_in_tree(repo, top.get("source"), f"{what} top_cell.source")
    elif "top_cell" in view:
        fail(f"{what} top_cell must be a JSON object with 'name'/'source'")

    # Rule 3: port list is a non-empty list of named, directed, unique ports.
    ports = view.get("ports")
    if isinstance(ports, list):
        if not ports:
            fail(f"{what} ports list is empty -- the view exists to state the port set")
        seen = set()
        for p in ports:
            if not isinstance(p, dict):
                fail(f"{what} port entry is not an object: {p!r}")
                continue
            name = p.get("name")
            if not isinstance(name, str) or not name:
                fail(f"{what} port entry missing 'name': {p!r}")
            elif name in seen:
                fail(f"{what} duplicate port name {name!r}")
            else:
                seen.add(name)
            direction = p.get("direction")
            if direction not in PORT_DIRECTIONS:
                fail(
                    f"{what} port {name!r} direction must be one of "
                    f"{PORT_DIRECTIONS}, got {direction!r}"
                )
    elif "ports" in view:
        fail(f"{what} ports must be a JSON array")

    # Rule 4: netlist is mandatory today -- the committed artifact exists --
    # and everything cited must exist in-tree.
    netlist = view.get("netlist")
    if isinstance(netlist, dict):
        if not isinstance(netlist.get("path"), str) or not netlist["path"]:
            fail(
                f"{what} netlist.path must be a non-empty string (the "
                "committed netlist artifact exists -- an honest null here "
                "would hide it)"
            )
        else:
            check_path_in_tree(repo, netlist["path"], f"{what} netlist.path")
        if (
            not isinstance(netlist.get("regeneration_command"), str)
            or not netlist["regeneration_command"]
        ):
            fail(
                f"{what} netlist.regeneration_command must be a non-empty "
                "string (issue #36: publish the regeneration command)"
            )
    elif "netlist" in view:
        fail(f"{what} netlist must be a JSON object with 'path'")

    # Rule 5: honest nulls. gds and measured_area accept null (not yet
    # produced) ONLY with the note that says so; a non-null gds path must
    # exist in-tree; a non-null area must be a positive number.
    gds = view.get("gds")
    if isinstance(gds, dict):
        if gds.get("path") is None:
            if not (isinstance(gds.get("note"), str) and gds["note"]):
                fail(
                    f"{what} gds.path is null without a 'not yet produced' "
                    "note -- an integrator must read a deliberate absence, "
                    "not an accidentally-empty field"
                )
        else:
            check_path_in_tree(repo, gds.get("path"), f"{what} gds.path")
    elif "gds" in view:
        fail(f"{what} gds must be a JSON object with 'path'/'note'")

    area = view.get("measured_area")
    if isinstance(area, dict):
        value = area.get("value_um2")
        if value is None:
            if not (isinstance(area.get("note"), str) and area["note"]):
                fail(
                    f"{what} measured_area.value_um2 is null without a "
                    "'not yet produced' note"
                )
        elif (
            not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0
        ):
            fail(
                f"{what} measured_area.value_um2 must be null or a positive "
                f"number, got {value!r} -- never a placeholder"
            )
    elif "measured_area" in view:
        fail(f"{what} measured_area must be a JSON object with 'value_um2'/'note'")

    # Rule 6: the rung agrees with the graded verdict of record.
    rung = view.get("maturity_rung")
    want = expected_rung(signoff_report)
    if rung != want:
        fail(
            f"{what} maturity_rung is {rung!r} but the signoff report "
            f"({REPO_DEFAULTS['signoff_report']}) grades {want!r} -- the "
            "view must agree with the graded verdict of record"
        )

    # Rule 8: the basis prose cannot contradict the report it names (#50).
    basis = view.get("maturity_rung_basis")
    if not isinstance(basis, str) or not basis:
        fail(f"{what} maturity_rung_basis must be a non-empty string")
    else:
        report_rel = REPO_DEFAULTS["signoff_report"]
        if report_rel not in basis:
            fail(
                f"{what} maturity_rung_basis must name '{report_rel}' -- "
                "the basis can never cite a report other than the one it "
                "is graded against"
            )
        else:
            check_path_in_tree(
                repo, report_rel, f"{what} maturity_rung_basis cited report"
            )
        m = re.search(r"(\d+)\s*/\s*(\d+)\s+T1 items met", basis)
        if m:
            got_met, got_count = int(m.group(1)), int(m.group(2))
            want_met = signoff_report.get("t1_met_count")
            want_count = signoff_report.get("t1_item_count")
            if (got_met, got_count) != (want_met, want_count):
                fail(
                    f"{what} maturity_rung_basis states "
                    f"{got_met}/{got_count} T1 items met but the signoff "
                    f"report ({report_rel}) carries "
                    f"t1_met_count={want_met!r}, t1_item_count={want_count!r} "
                    "-- the basis must not disagree with the record"
                )

    # Rule 7: provenance names its generated-from sources, in-tree.
    prov = view.get("provenance")
    if isinstance(prov, dict):
        sources = prov.get("generated_from")
        if not isinstance(sources, list) or not sources:
            fail(
                f"{what} provenance.generated_from must be a non-empty "
                "array of in-tree paths"
            )
        else:
            for src in sources:
                check_path_in_tree(repo, src, f"{what} provenance.generated_from entry")
    elif "provenance" in view:
        fail(f"{what} provenance must be a JSON object")


def run_gate(args: argparse.Namespace) -> int:
    repo = Path(args.repo_root).resolve()
    view_path = repo / args.view
    report_path = repo / args.signoff_report

    view = load_json(view_path, "view")
    signoff_report = load_json(report_path, "signoff report")

    try:
        validate_view(view, signoff_report, repo, f"{view_path.name}")
    except ValueError as exc:
        # expected_rung raises on an unrecognizable report tier.
        fail(str(exc))
        return 1

    if FAILURES:
        print(f"gate: {len(FAILURES)} failure(s) -- see above")
        return 1
    ok(
        f"gate clean: {len(view.get('ports', []))} ports, rung "
        f"{view.get('maturity_rung')!r} agrees with the signoff report, "
        "all cited paths resolve"
    )
    return 0


def _fixture_view(
    block="fx-block",
    ports=None,
    netlist_path="fx.spice",
    gds_path=None,
    gds_note="not yet produced: fixture",
    area_value=None,
    area_note="not yet produced: fixture",
    rung="pre-T1",
    basis="manifests/t1-signoff-report.json: tier null, 0/11 T1 items met -- fixture",
    drop_key=None,
    provenance=None,
):
    view = {
        "schema_version": 1,
        "block": block,
        "kind": "analog",
        "top_cell": {"name": "fx", "source": "fx.sch"},
        "ports": ports
        if ports is not None
        else [
            {"name": "VDD", "direction": "power", "type": "supply"},
            {"name": "IN", "direction": "input", "type": "analog"},
            {"name": "OUT", "direction": "output", "type": "digital"},
        ],
        "netlist": {
            "path": netlist_path,
            "regeneration_command": "./fx/netlist.sh",
        },
        "gds": {"path": gds_path, "note": gds_note},
        "measured_area": {"value_um2": area_value, "note": area_note},
        "maturity_rung": rung,
        "maturity_rung_basis": basis,
        "provenance": provenance
        if provenance is not None
        else {
            "generated_from": ["fx.sch"],
            "refresh_rule": "fixture",
        },
    }
    if drop_key is not None:
        view.pop(drop_key, None)
    return view


def _fixture_report(tier=None):
    return {
        "tier": tier,
        "t1_item_count": 11,
        "t1_met_count": 11 if tier == "T1" else 0,
        "items": [],
    }


def _tree_with(*existing):
    """A repo double: (tree / path).exists() is membership in `existing`."""

    class _P:
        def __init__(self, exists):
            self._exists = exists

        def exists(self):
            return self._exists

    class Repo:
        def __init__(self, existing):
            self.existing = set(existing)

        def __truediv__(self, rel):
            return _P(rel in self.existing)

    return Repo(existing)


def run_selftest(_args: argparse.Namespace) -> int:
    case_results = []

    def check(name, expect_fail, expect_substr, view, report, tree):
        # reset() clears the shared tally in place -- rebinding FAILURES here
        # would detach it from the list fail() appends to (_gate_common).
        reset()
        validate_view(view, report, tree, "fx-view")
        blob = "\n".join(FAILURES)
        passed = (len(FAILURES) > 0) == expect_fail
        if expect_substr is not None:
            passed = passed and expect_substr in blob
        case_results.append((name, passed))

    tree_ok = _tree_with(
        "fx.sch", "fx.spice", "fx.gds", "manifests/t1-signoff-report.json"
    )

    # Positive: the honest pre-T1 shape -- nulls WITH notes, all paths real.
    check(
        "clean pre-T1 view with honest nulls",
        expect_fail=False,
        expect_substr=None,
        view=_fixture_view(),
        report=_fixture_report(tier=None),
        tree=tree_ok,
    )

    # Positive: post-layout shape -- real gds path + measured area accepted.
    check(
        "post-layout view with real gds and area",
        expect_fail=False,
        expect_substr=None,
        view=_fixture_view(gds_path="fx.gds", area_value=123.4),
        report=_fixture_report(tier=None),
        tree=tree_ok,
    )

    # Positive: rung tracks a graded T1 report. Needs its own basis (trap 3,
    # issue #50): _fixture_report(tier="T1") carries t1_met_count=11, so the
    # default "0/11" basis text would now disagree with the report.
    check(
        "rung agrees when report grades T1",
        expect_fail=False,
        expect_substr=None,
        view=_fixture_view(
            rung="T1",
            basis="manifests/t1-signoff-report.json: tier T1, 11/11 T1 items met -- fixture",
        ),
        report=_fixture_report(tier="T1"),
        tree=tree_ok,
    )

    # Negative control 1 (issue #36): missing required key fails.
    check(
        "missing required key fails",
        expect_fail=True,
        expect_substr="missing required key 'maturity_rung'",
        view=_fixture_view(drop_key="maturity_rung"),
        report=_fixture_report(tier=None),
        tree=tree_ok,
    )

    # Negative control 2 (issue #36): dangling cited path fails.
    check(
        "dangling netlist path fails",
        expect_fail=True,
        expect_substr="netlist.path cites 'gone.spice' which does not exist",
        view=_fixture_view(netlist_path="gone.spice"),
        report=_fixture_report(tier=None),
        tree=tree_ok,
    )

    # Negative control 2b: a stale gds path fails the same way.
    check(
        "stale gds path fails",
        expect_fail=True,
        expect_substr="gds.path cites 'gone.gds' which does not exist",
        view=_fixture_view(gds_path="gone.gds"),
        report=_fixture_report(tier=None),
        tree=tree_ok,
    )

    # Negative control 3 (issue #36): rung/report mismatch fails.
    check(
        "rung disagrees with report fails",
        expect_fail=True,
        expect_substr="maturity_rung is 'T1' but the signoff report",
        view=_fixture_view(rung="T1"),
        report=_fixture_report(tier=None),
        tree=tree_ok,
    )

    # Negative control 4 (issue #50): a basis whose stated count disagrees
    # with the report's t1_met_count/t1_item_count fails.
    check(
        "maturity_rung_basis count disagrees with report",
        expect_fail=True,
        expect_substr=(
            "maturity_rung_basis states 5/11 T1 items met but the signoff "
            "report"
        ),
        view=_fixture_view(
            basis="manifests/t1-signoff-report.json: 5/11 T1 items met -- fixture"
        ),
        report=_fixture_report(tier=None),
        tree=tree_ok,
    )

    # Negative control 5 (issue #50): an absent maturity_rung_basis fails on
    # the missing required key -- a check that no-ops when the field is
    # deleted is not a check.
    check(
        "missing maturity_rung_basis fails",
        expect_fail=True,
        expect_substr="missing required key 'maturity_rung_basis'",
        view=_fixture_view(drop_key="maturity_rung_basis"),
        report=_fixture_report(tier=None),
        tree=tree_ok,
    )

    # Positive (issue #50): a count-free basis naming the report path
    # passes -- no duplicated fact, so nothing left to drift.
    check(
        "count-free maturity_rung_basis naming the report passes",
        expect_fail=False,
        expect_substr=None,
        view=_fixture_view(
            basis="manifests/t1-signoff-report.json: see the report for "
            "per-item T1 status -- fixture"
        ),
        report=_fixture_report(tier=None),
        tree=tree_ok,
    )

    # Nulls are only honest WITH the note.
    check(
        "null gds without note fails",
        expect_fail=True,
        expect_substr="gds.path is null without",
        view=_fixture_view(gds_note=""),
        report=_fixture_report(tier=None),
        tree=tree_ok,
    )

    check(
        "null area without note fails",
        expect_fail=True,
        expect_substr="measured_area.value_um2 is null without",
        view=_fixture_view(area_note=""),
        report=_fixture_report(tier=None),
        tree=tree_ok,
    )

    # A placeholder area is never acceptable.
    check(
        "placeholder area number fails",
        expect_fail=True,
        expect_substr="measured_area.value_um2 must be null or a positive",
        view=_fixture_view(area_value=-1.0, area_note="x"),
        report=_fixture_report(tier=None),
        tree=tree_ok,
    )

    # Port-list rot: duplicate and mis-directed entries fail.
    check(
        "duplicate port name fails",
        expect_fail=True,
        expect_substr="duplicate port name 'IN'",
        view=_fixture_view(
            ports=[
                {"name": "IN", "direction": "input"},
                {"name": "IN", "direction": "output"},
            ]
        ),
        report=_fixture_report(tier=None),
        tree=tree_ok,
    )

    check(
        "invalid port direction fails",
        expect_fail=True,
        expect_substr="direction must be one of",
        view=_fixture_view(ports=[{"name": "CLK", "direction": "clock"}]),
        report=_fixture_report(tier=None),
        tree=tree_ok,
    )

    # Provenance rot: an empty generated_from fails.
    check(
        "empty provenance sources fail",
        expect_fail=True,
        expect_substr="provenance.generated_from must be a non-empty",
        view=_fixture_view(provenance={"generated_from": []}),
        report=_fixture_report(tier=None),
        tree=tree_ok,
    )

    # An unrecognizable report tier is a hard error, not a silent pass.
    try:
        expected_rung({"tier": "T9"})
        case_results.append(("expected_rung rejects unknown tier", False))
    except ValueError:
        case_results.append(("expected_rung rejects unknown tier", True))

    return report_cases(case_results)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Rule-9 integrator-view CI gate for "
        "manifests/integrator-view.json (issue #36)"
    )
    sub = parser.add_subparsers(dest="mode", required=True)

    p_gate = sub.add_parser(
        "gate", help="validate the committed integrator view against this tree"
    )
    p_gate.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    p_gate.add_argument("--view", default=REPO_DEFAULTS["view"])
    p_gate.add_argument("--signoff-report", default=REPO_DEFAULTS["signoff_report"])

    return dispatch(parser, sub, argv, run_gate, run_selftest)


if __name__ == "__main__":
    raise SystemExit(main())
