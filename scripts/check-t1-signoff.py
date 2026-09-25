#!/usr/bin/env python3
"""CI gate for the T1 signoff manifest (issue #31).

    python3 scripts/check-t1-signoff.py gate
    python3 scripts/check-t1-signoff.py selftest

`gate` re-runs `klt signoff --manifest` against the committed block
manifest and compares the fresh tier report to the committed evidence
record so a manifest whose cited artifact drifted (stale/unreadable/
wrong-kind) FAILS here rather than rotting. T1 not being reached yet is
the honest current state for this block and does NOT fail this gate;
per-citation rot and against-record regressions do.

`selftest` exercises the compare logic against hermetic fixtures (no
network, no `klt` binary, no PDK) so the gate's own behavior is itself a
recorded, repeatable check -- including the negative controls that prove
the rot detector actually bites (sim/selftest.sh's stage-4 discipline: a
monitor that cannot fail grades nothing).

Stdlib only, no virtualenv required. Provenance: the two-path (gate /
selftest) shape mirrors sim/selftest.sh's "acceptance stages" convention.
The gate-output convention (`fail`/`warn`/`ok`/`load_json`) is imported from
scripts/_gate_common.py, shared with scripts/check-integrator-view.py so the
two gates cannot drift (issue #56).
The report fields compared here are the documented `klt signoff --manifest
--format json` contract (klayout-tools docs/cli/signoff.md, "Tier-report
JSON schema"). Field access tolerates absent newer fields (`input_verified`,
`build`, `build_t1_item_count`) because the committed record is
byte-for-byte what the pinned klt emitted, not what a later klt would emit
(those fields are additive upstream, never removals).

Exit codes: 0 gate pass (warnings allowed), 1 gate failure, 2 usage error.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _gate_common import (  # noqa: E402
    FAILURES,
    WARNINGS,
    fail,
    load_json,
    ok,
    reset,
    warn,
)

REPO_DEFAULTS = {
    "manifest": "manifests/sky130-comparator.json",
    "tiers_doc": "manifests/design-evidence-tiers.md",
    "committed": "manifests/t1-signoff-report.json",
}

KLT_BIN = "klt"


def item_key(item: dict) -> tuple:
    """Identity for a report row: (tier, id, partition).

    T2-T4 ladder rows carry id=None and never count toward met-set
    comparisons; the gate skips them.
    """
    return (item.get("tier"), item.get("id"), item.get("partition"))


def t1_items(report: dict) -> list:
    return [
        it
        for it in report.get("items", [])
        if it.get("tier") == "T1" and isinstance(it.get("id"), int)
    ]


def validate_report(report: dict, what: str) -> None:
    """Structural checks shared by the fresh and committed reports."""
    if not isinstance(report.get("items"), list) or not report["items"]:
        raise ValueError(f"{what} report has no items[] array")
    if not isinstance(report.get("t1_item_count"), int) or report["t1_item_count"] < 1:
        raise ValueError(f"{what} report t1_item_count is missing or invalid")
    for it in report["items"]:
        if "status" not in it:
            raise ValueError(f"{what} report item missing 'status': {it!r}")
        if it.get("status") not in ("met", "unmet"):
            raise ValueError(f"{what} report item has invalid status: {it!r}")
        if it.get("status") == "unmet" and not it.get("reason"):
            raise ValueError(f"{what} unmet item missing 'reason': {it!r}")
    if len(t1_items(report)) != report["t1_item_count"]:
        raise ValueError(
            f"{what} report t1_item_count={report['t1_item_count']} but "
            f"{len(t1_items(report))} T1 rows present"
        )


def compare(manifest: dict, committed: dict, fresh: dict) -> None:
    """The gate proper. Records failures in FAILURES; returns nothing."""
    c_block, c_kind = committed.get("block"), committed.get("kind")
    f_block, f_kind = fresh.get("block"), fresh.get("kind")

    if c_block is not None and f_block is not None and c_block != f_block:
        fail(
            f"block changed between committed report ({c_block!r}) and "
            f"fresh run ({f_block!r}) -- regenerate the committed report"
        )
    if c_kind != f_kind:
        fail(
            f"kind changed between committed report ({c_kind!r}) and fresh "
            f"run ({f_kind!r}) -- regenerate the committed report"
        )

    c_count = committed.get("t1_item_count")
    f_count = fresh.get("t1_item_count")
    if c_count != f_count:
        warn(
            f"T1 item count changed between committed report ({c_count}) "
            f"and fresh run ({f_count}) -- the checklist doc moved; "
            "regenerate the committed report with the pinned command"
        )

    # Later klt releases report how many items their own grading knows
    # (build_t1_item_count); compare when the field is present.
    fb = fresh.get("build_t1_item_count")
    if fb is not None and f_count is not None and fb < f_count:
        warn(
            f"grading build knows only {fb} of {f_count} checklist items -- "
            "item rows beyond the build's list render ungradeable when "
            "cited; track a klt upgrade (see manifests/README.md)"
        )

    committed_met = {
        item_key(it): it for it in t1_items(committed) if it["status"] == "met"
    }
    fresh_met = {item_key(it): it for it in t1_items(fresh) if it["status"] == "met"}

    evidence = manifest.get("evidence") or {}
    if not isinstance(evidence, dict):
        fail(f"manifest 'evidence' is not a JSON object: {evidence!r}")
        evidence = {}
    fresh_t1_keys = {item_key(it): it for it in t1_items(fresh)}

    # Rule 1: every CITED item must be met, freshly. This is the
    # rot-killer: a pinned artifact that changed, vanished, or was replaced
    # renders its item unmet (stale_evidence / unreadable_evidence /
    # wrong_kind / check_failed ...) and CI goes red instead of silently
    # grading yesterday's evidence.
    for key in sorted(evidence):
        stem = key.split(".", 1)[0]
        matched = [
            item_key(it) for it in t1_items(fresh)
            if it.get("id") is not None and str(it["id"]) == stem
        ]
        if not matched:
            fail(
                f"manifest cites item '{key}' but the fresh report has no "
                "such T1 item"
            )
            continue
        for k in matched:
            if k not in fresh_met:
                fresh_row = fresh_t1_keys[k]
                fail(
                    f"cited item {key!r} is unmet in the fresh run (reason: "
                    f"{fresh_row.get('reason')}) -- a cited check must stay "
                    "met; regenerate the evidence or uncite"
                )
            else:
                ok(f"cited item {key} is met fresh")

    # Rule 2: anti-rot regression vs the committed record. Evidence that
    # was met when the record was committed cannot silently degrade.
    for k in sorted(committed_met):
        if k not in fresh_met:
            fresh_row = fresh_t1_keys.get(k)
            reason = (
                fresh_row.get("reason") if fresh_row
                else "item vanished from the report"
            )
            fail(
                f"T1 {k[1]} was met in the committed report but unmet fresh "
                f"(reason: {reason}) -- regenerate the evidence record, or "
                "the manifest is grading stale evidence"
            )

    # Rule 3: a met citation must actually have been re-verified against
    # the artifact where the grading build supports it (klayout-tools
    # #2196, input_verified). false = re-hash disagreed = fail; null with
    # a recorded hash = warn (investigate rather than pass silently --
    # issue #31 curator note).
    for k in sorted(fresh_met):
        cite = fresh_met[k].get("citation")
        if not isinstance(cite, dict):
            continue
        iv = cite.get("input_verified")
        if iv is False:
            fail(
                f"T1 {k[1]} citation re-hash disagreed with the envelope's "
                "recorded input hash (input_verified: false)"
            )
        elif iv is None and cite.get("content_hash"):
            warn(
                f"T1 {k[1]} citation carries a content_hash the grading "
                "build did not re-hash (input_verified: null) -- "
                "investigate rather than pass silently (issue #31 curator note)"
            )

    # Rule 4: a new pass must not pass silently the other way -- the
    # committed record is the tracker's verdict of record.
    for k in sorted(fresh_met):
        if k not in committed_met:
            warn(
                f"T1 {k[1]} is met fresh but unmet in the committed report "
                "-- regenerate the committed record so the tracker's "
                "verdict of record matches"
            )

    if not FAILURES:
        ok(
            f"gate clean: {len(fresh_met)}/{f_count} T1 items met, "
            f"{len(evidence)} citation(s), no rot or regression"
        )


def run_gate(args: argparse.Namespace) -> int:
    repo = Path(args.repo_root).resolve()
    manifest_path = repo / args.manifest
    committed_path = repo / args.committed
    tiers_doc = repo / args.tiers_doc

    manifest = load_json(manifest_path, "manifest")
    if not isinstance(manifest.get("block"), str) or not isinstance(
        manifest.get("kind"), str
    ):
        raise ValueError(
            f"manifest is structurally invalid (needs 'block' and 'kind'): "
            f"{manifest_path}"
        )

    cmd = [
        KLT_BIN, "signoff",
        "--manifest", str(manifest_path),
        "--tiers-doc", str(tiers_doc),
        "--format", "json",
    ]
    if args.fresh_report:
        fresh = load_json(Path(args.fresh_report), "fresh")
        print(f"gate: using pre-generated fresh report: {args.fresh_report}")
    else:
        print(f"gate: running: {' '.join(cmd)}")
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True)
        except FileNotFoundError as exc:
            fail(f"{KLT_BIN} binary not found on PATH: {exc}")
            return 1
        if proc.returncode == 1:
            # klt exit 1 = manifest/flag/tier-doc parse error: structural,
            # always a gate failure.
            fail(
                "klt signoff could not run (exit 1): "
                f"{(proc.stderr or proc.stdout).strip()}"
            )
            return 1
        if proc.returncode == 2:
            fail(
                f"klt signoff usage error (exit 2): {(proc.stderr or '').strip()}"
            )
            return 1
        # Exit 3 = tier not met yet (honest pre-T1 state), exit 0 = T1:
        # both are successful grader runs whose output this gate grades.
        if proc.returncode not in (0, 3):
            fail(
                f"klt signoff exited {proc.returncode}: "
                f"{(proc.stderr or proc.stdout).strip()}"
            )
            return 1
        try:
            fresh = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            fail(f"klt signoff stdout was not valid JSON: {exc}")
            return 1
    validate_report(fresh, "fresh")

    committed = load_json(committed_path, "committed")
    validate_report(committed, "committed")

    compare(manifest, committed, fresh)
    if FAILURES:
        print(
            f"gate: {len(FAILURES)} failure(s), {len(WARNINGS)} warning(s) "
            "-- see above"
        )
        return 1
    print(f"gate: PASS ({len(WARNINGS)} warning(s))")
    return 0


_UNSET = object()  # sentinel distinct from None (a legitimate field value)


def _fixture_report(block="fx-block", kind="analog", statuses=None,
                    t1_count=3, input_verified_override=_UNSET):
    statuses = statuses or {}
    items = []
    for i in range(1, t1_count + 1):
        st = statuses.get(i, "unmet")
        citation = None
        if st == "met":
            citation = {
                "file": f"fx{i}.json",
                "kind": "drc",
                "check_status": "clean",
                "content_hash": "sha256:fx",
                "input_verified": True,
                "exit_status": 0,
            }
            if input_verified_override is not _UNSET:
                citation["input_verified"] = input_verified_override
        items.append({
            "tier": "T1", "id": i, "title": f"fx item {i}",
            "partition": None, "text": "fixture", "notes": [],
            "status": st,
            "reason": None if st == "met" else "no_evidence",
            "citation": citation,
        })
    items.append({
        "tier": "T2", "id": None, "title": "T2 row", "partition": None,
        "text": None, "notes": [], "status": "unmet",
        "reason": "tier_not_supported", "citation": None,
    })
    met = sum(1 for it in items if it["tier"] == "T1" and it["status"] == "met")
    return {
        "schema_version": 1, "block": block, "kind": kind,
        "tier": "T1" if met == t1_count else None,
        "t1_item_count": t1_count, "t1_met_count": met,
        "source_doc": "fixture-doc.md", "items": items,
    }


def run_selftest(_args: argparse.Namespace) -> int:
    case_results = []

    def check(name, expect_fail, expect_substr, manifest, committed, fresh,
              expect_warn=None):
        # reset() clears the shared tallies in place -- rebinding them here
        # would detach them from the lists fail()/warn() append to
        # (_gate_common).
        reset()
        compare(manifest, committed, fresh)
        blob = "\n".join(FAILURES)
        warn_blob = "\n".join(WARNINGS)
        passed = (len(FAILURES) > 0) == expect_fail
        if expect_substr is not None:
            passed = passed and expect_substr in blob
        if expect_warn is not None:
            passed = passed and expect_warn in warn_blob
        case_results.append((name, passed))

    empty_ev = {"evidence": {}}
    cite2 = {"evidence": {"2": "fx2.json"}}

    # Positive: identical all-unmet, no citations.
    check("clean all-unmet", expect_fail=False, expect_substr=None,
          manifest=empty_ev,
          committed=_fixture_report(),
          fresh=_fixture_report())

    # Negative controls -- the rot detector must actually bite.
    check("regression vs committed record",
          expect_fail=True,
          expect_substr="was met in the committed report but unmet fresh",
          manifest=empty_ev,
          committed=_fixture_report(statuses={2: "met"}),
          fresh=_fixture_report())

    check("cited item unmet fresh", expect_fail=True,
          expect_substr="cited item '2' is unmet in the fresh run",
          manifest=cite2,
          committed=_fixture_report(statuses={2: "met"}),
          fresh=_fixture_report())

    check("citation for unknown item", expect_fail=True,
          expect_substr="no such T1 item",
          manifest={"evidence": {"9": "fx9.json"}},
          committed=_fixture_report(),
          fresh=_fixture_report())

    check("input_verified false fails", expect_fail=True,
          expect_substr="input_verified: false",
          manifest=cite2,
          committed=_fixture_report(statuses={2: "met"}),
          fresh=_fixture_report(statuses={2: "met"}, input_verified_override=False))

    # Pass-with-warning cases.
    check("input_verified null warns but passes", expect_fail=False,
          expect_substr=None,
          expect_warn="did not re-hash",
          manifest=cite2,
          committed=_fixture_report(statuses={2: "met"}),
          fresh=_fixture_report(statuses={2: "met"}, input_verified_override=None))

    check("doc checklist grew warns but passes", expect_fail=False,
          expect_substr=None,
          expect_warn="item count changed",
          manifest=empty_ev,
          committed=_fixture_report(t1_count=3),
          fresh=_fixture_report(t1_count=4))

    # build_t1_item_count behind the parsed doc -> warn, not fail.
    fresh_outrun = _fixture_report(t1_count=4)
    fresh_outrun["build_t1_item_count"] = 3
    check("build outrunning doc warns but passes", expect_fail=False,
          expect_substr=None,
          expect_warn="knows only 3 of 4",
          manifest=empty_ev,
          committed=_fixture_report(t1_count=4),
          fresh=fresh_outrun)

    check("new pass warns to regenerate record", expect_fail=False,
          expect_substr=None,
          expect_warn="regenerate the committed record",
          manifest=empty_ev,
          committed=_fixture_report(),
          fresh=_fixture_report(statuses={2: "met"}))

    # Structural validation must reject mangled reports.
    bad = _fixture_report()
    bad["t1_item_count"] = 99
    try:
        validate_report(bad, "fx")
        case_results.append(("validate_report catches count mismatch", False))
    except ValueError:
        case_results.append(("validate_report catches count mismatch", True))

    bad2 = _fixture_report()
    del bad2["items"][0]["status"]
    try:
        validate_report(bad2, "fx")
        case_results.append(("validate_report catches missing status", False))
    except ValueError:
        case_results.append(("validate_report catches missing status", True))

    bad3 = _fixture_report()
    bad3["items"][0]["status"] = "unmet"
    bad3["items"][0]["reason"] = None
    try:
        validate_report(bad3, "fx")
        case_results.append(("validate_report catches reasonless unmet", False))
    except ValueError:
        case_results.append(("validate_report catches reasonless unmet", True))

    failed = [name for name, passed in case_results if not passed]
    for name, passed in case_results:
        print(f"selftest: {'ok' if passed else 'FAIL'}: {name}")
    if failed:
        print(f"selftest: {len(failed)} case(s) failed")
        return 1
    print(f"selftest: all {len(case_results)} cases passed")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="T1 signoff CI gate for manifests/sky130-comparator.json"
    )
    sub = parser.add_subparsers(dest="mode", required=True)

    p_gate = sub.add_parser(
        "gate", help="re-run klt signoff and compare to the committed record"
    )
    p_gate.add_argument(
        "--repo-root", default=str(Path(__file__).resolve().parents[1])
    )
    p_gate.add_argument("--manifest", default=REPO_DEFAULTS["manifest"])
    p_gate.add_argument("--tiers-doc", default=REPO_DEFAULTS["tiers_doc"])
    p_gate.add_argument("--committed", default=REPO_DEFAULTS["committed"])
    p_gate.add_argument(
        "--fresh-report",
        help="use a pre-generated fresh report JSON instead of running klt",
    )

    sub.add_parser("selftest", help="hermetic fixture test of the gate logic")

    args = parser.parse_args(argv)
    try:
        if args.mode == "gate":
            return run_gate(args)
        return run_selftest(args)
    except ValueError as exc:
        print(f"gate: FAIL: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
