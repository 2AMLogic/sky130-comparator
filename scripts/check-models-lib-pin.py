#!/usr/bin/env python3
"""Models-lib pin CI gate (issue #282): a committed klt sim request's
models.lib cannot silently drift from sim/pdk.json's ngspice_lib.

    python3 scripts/check-models-lib-pin.py gate
    python3 scripts/check-models-lib-pin.py selftest

`sim/pdk.json`'s `ngspice_lib` (`libs.tech/combined/sky130.lib.spice`) is
this repo's declared reproducibility pin for every record under `sim/` --
the file's own notes say so -- but nothing checked that a committed
`klt sim` request honours it. The reports' own
`environment.models_lib_comparison: {"status": "match"}` compares the
client's library hash against the runner's, not the request against
`sim/pdk.json`, so a green `match` says nothing about this mismatch class.
It happened and was missed twice: four merged `{kickback,pex}-request-*.json`
named `libs.tech/ngspice/...` while the repo grades on `libs.tech/combined/
...` (#244), and the written guidance PR #228 added was missed by the PEX
pilot that landed concurrently -- measured cost +5.12 % on `regen` decision
time at `ss`/-40 C. This gate is the mechanical version of that guidance.

`gate` selects structurally -- every `sim/**/*.json` whose payload is an
object with a top-level `models` object carrying a `lib` key (requests and
only requests: the `report-*.json` start `schema_version`/`netlist`/`status`
and the `dry-run-*.json` use a top-level `models_lib` string, so both fall
outside the rule by construction) -- and fails when `models.lib` differs
from `pdk.json`'s `ngspice_lib` unless the path is allowlisted in
`DELIBERATE_MISMATCHES`. The count of scanned requests is reported, never
assumed, so a pilot added later under a new `sim/<bench>/` is covered for
free. The allowlist is itself rot-checked: an entry naming a path with no
request, or whose request now matches the pin, fails -- without that the
allowlist silently becomes a list of permanently-granted exemptions, the
same failure class this gate exists to prevent, one level up.

`selftest` is hermetic (stdlib data fixtures only, no klt, no PDK, no
network): it drives the selector and the checker on parsed payloads --
proving arrays and `models`-without-`lib` objects are skipped, that an
un-allowlisted mismatch, a missing allowlist target and a now-matching one
each fail, and that an all-matching tree and a mismatching-but-allowlisted
request pass.

Same `_gate_common` convention as the other gates in this directory (see
`check-toolchain-pin.py`, whose `gate`/`selftest` pair and `dispatch()` tail
this file copies). Stdlib only, no virtualenv required.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _gate_common import (FAILURES, dispatch, fail, load_json,  # noqa: E402
                          ok, report_cases, reset)

REPO_ROOT = Path(__file__).resolve().parents[1]
PDK_JSON = Path("sim/pdk.json")

#: Committed requests that name a library other than sim/pdk.json's
#: ngspice_lib ON PURPOSE. Each entry is a reviewed act: the gate names any
#: unlisted mismatch, and adding a line here -- with a reason, in the PR
#: that introduces the request -- is how you answer it. The gate fails if
#: an entry names a path with no request or one that no longer mismatches,
#: so the map cannot rot into permanently-granted exemptions.
DELIBERATE_MISMATCHES = {
    "sim/comparator-decision/klt-pilot/regen-request-bdiff-ngspicelib.json":
        "deliberate A/B control: the ngspice-library leg of the regen bdiff "
        "library comparison (#228) -- the two sky130A model libraries are "
        "not interchangeable (+5.12 % on decision time at ss/-40 C), and "
        "this leg is the run that measured it.",
    "sim/comparator-decision/klt-pilot/kickback-request-ideal.json":
        "grandfathered (#244): ran against libs.tech/ngspice before the "
        "mismatch was found; the run really happened that way and "
        "report-ideal.json pins that library's models_lib_sha256 "
        "(17c208a6...). Never rewritten.",
    "sim/comparator-decision/klt-pilot/kickback-request-loaded.json":
        "grandfathered (#244): ran against libs.tech/ngspice before the "
        "mismatch was found; report-loaded.json pins that library's "
        "models_lib_sha256 (17c208a6...). Never rewritten.",
    "sim/comparator-decision/klt-pilot/pex-request-ideal.json":
        "grandfathered (#244): ran against libs.tech/ngspice before the "
        "mismatch was found; report-pex-ideal.json pins that library's "
        "models_lib_sha256 (17c208a6...). Never rewritten.",
    "sim/comparator-decision/klt-pilot/pex-request-loaded.json":
        "grandfathered (#244): ran against libs.tech/ngspice before the "
        "mismatch was found; report-pex-loaded.json pins that library's "
        "models_lib_sha256 (17c208a6...). Never rewritten.",
}


def request_lib(doc) -> str | None:
    """`models["lib"]` if `doc` is request-shaped, else None.

    Request-shaped is structural, never name-based (issue #282): a dict
    carrying a top-level `models` dict with a `lib` key. Reports (no
    `models`), dry-run payloads (top-level `models_lib` string) and arrays
    all return None, as does a `models.lib` that is not a string -- a
    request like that cannot have run on the fleet, so there is no run to
    mis-grade.
    """
    if not isinstance(doc, dict):
        return None
    models = doc.get("models")
    if not isinstance(models, dict) or "lib" not in models:
        return None
    lib = models["lib"]
    return lib if isinstance(lib, str) else None


def pinned_lib(pdk_doc: dict) -> str:
    """`ngspice_lib` out of a parsed sim/pdk.json, failing closed.

    A pdk.json missing the key (or carrying a non-string) is a broken
    reproducibility pin -- the gate must refuse to grade anything against
    it, not silently pass every request.
    """
    lib = pdk_doc.get("ngspice_lib")
    if not isinstance(lib, str) or not lib:
        raise ValueError(f"{PDK_JSON} has no ngspice_lib string -- the "
                         "reproducibility pin every request is graded "
                         "against is missing, so nothing can be checked")
    return lib


def check_tree(pin: str, requests: dict[str, str],
               allowlist: dict[str, str]) -> None:
    """Compare every scanned request's models.lib against the pin.

    `requests` is repo-relative path -> models.lib for the structurally
    selected files (what `scan_requests()` returns); `allowlist` is the
    path -> reason map to hold against it. Parsed data on purpose, so the
    selftest can drive the exact gate logic on fixtures.
    """
    for path in sorted(requests):
        lib = requests[path]
        if lib == pin or path in allowlist:
            continue
        fail(f"{path}: models.lib is {lib!r}, but {PDK_JSON}'s ngspice_lib "
             f"pins {pin!r} -- {PDK_JSON} is the reproducibility pin for "
             "every record under sim/, so this request graded its run "
             "against a different model library than the repo declares "
             "(when this happened by accident, #244, it moved regen "
             "decision time by 5.12 % at ss/-40 C). Deliberate A/B "
             "control? Add the path to DELIBERATE_MISMATCHES with a "
             "reason. Accident? Fix the request and re-run the pilot.")
    for path in sorted(allowlist):
        if path not in requests:
            fail(f"DELIBERATE_MISMATCHES names {path}, but no committed "
                 "request with a top-level models.lib exists there -- the "
                 "allowlist entry has rotted; delete it")
        elif requests[path] == pin:
            fail(f"DELIBERATE_MISMATCHES names {path}, but its models.lib "
                 f"now matches {PDK_JSON}'s ngspice_lib {pin!r} -- the "
                 "exemption is stale; delete it")
    if not FAILURES:
        mismatched = [p for p in sorted(requests) if requests[p] != pin]
        ok(f"{len(requests)} request file(s) scanned under sim/**/*.json; "
           f"{len(mismatched)} mismatch(es) vs {PDK_JSON} ngspice_lib "
           f"{pin!r}, all deliberate (DELIBERATE_MISMATCHES)")


def scan_requests(repo_root: Path) -> dict[str, str]:
    """Repo-relative path -> models.lib for every selected sim/**/*.json."""
    requests: dict[str, str] = {}
    for path in sorted((repo_root / "sim").rglob("*.json")):
        rel = path.relative_to(repo_root).as_posix()
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            # Fail closed: an unparseable file under sim/ that this gate
            # cannot classify might be a request it cannot check.
            raise ValueError(f"sim/ JSON file is not readable JSON: "
                             f"{rel}: {exc}") from None
        lib = request_lib(doc)
        if lib is not None:
            requests[rel] = lib
    return requests


def run_gate(args: argparse.Namespace) -> int:
    repo = Path(args.repo_root).resolve()
    pin = pinned_lib(load_json(repo / PDK_JSON, str(PDK_JSON)))
    check_tree(pin, scan_requests(repo), DELIBERATE_MISMATCHES)
    if FAILURES:
        print(f"gate: {len(FAILURES)} failure(s) -- see above")
        return 1
    return 0


def run_selftest(args: argparse.Namespace) -> int:
    case_results = []
    pin = "libs.tech/combined/sky130.lib.spice"
    other = "libs.tech/ngspice/sky130.lib.spice"

    # The selector is structural (issue #282): these parsed payloads are
    # every shape under sim/ that is NOT a request and must be skipped.
    for name, doc, expected in [
        ("selects a request object (top-level models with a lib key)",
         {"netlist": "body.spice", "engine": "ngspice",
          "models": {"pdk": "sky130A", "lib": other}}, other),
        ("skips a JSON array (not a request, not a crash)",
         [{"models": {"lib": other}}], None),
        ("skips an object whose models has no lib key",
         {"models": {"pdk": "sky130A"}}, None),
        ("skips a dry-run object (top-level models_lib, absolute path)",
         {"models_lib": "/home/ubuntu/.ciel/sky130A/libs.tech/combined/"
                        "sky130.lib.spice"}, None),
        ("skips a report-shaped object (no models at all)",
         {"schema_version": 1, "netlist": "body.spice", "status": "pass"},
         None),
    ]:
        case_results.append((name, request_lib(doc) == expected))

    def check(name, expect_fail, requests, allowlist):
        # reset() clears the shared tally in place -- rebinding FAILURES
        # here would detach it from the list fail() appends to
        # (_gate_common).
        reset()
        check_tree(pin, requests, allowlist)
        case_results.append((name, (len(FAILURES) > 0) == expect_fail))

    check("accepts an all-matching tree", False,
          {"sim/bench/klt-pilot/a-request.json": pin,
           "sim/bench/klt-pilot/b-request.json": pin}, {})
    check("accepts a mismatching request that is allowlisted", False,
          {"sim/bench/klt-pilot/a-request.json": pin,
           "sim/bench/klt-pilot/ctl-request.json": other},
          {"sim/bench/klt-pilot/ctl-request.json":
           "deliberate A/B control fixture"})
    check("rejects an un-allowlisted mismatching request", True,
          {"sim/bench/klt-pilot/a-request.json": pin,
           "sim/bench/klt-pilot/b-request.json": other}, {})
    check("rejects an allowlist entry naming a path with no request", True,
          {"sim/bench/klt-pilot/a-request.json": pin},
          {"sim/bench/klt-pilot/gone-request.json": "pilot was deleted"})
    check("rejects an allowlist entry whose request now matches the pin",
          True,
          {"sim/bench/klt-pilot/a-request.json": pin,
           "sim/bench/klt-pilot/ctl-request.json": pin},
          {"sim/bench/klt-pilot/ctl-request.json":
           "was deliberate, request since fixed"})

    # Legibility: the failure must name the offending path, both library
    # values, and the way out (the allowlist), or it cannot be acted on.
    reset()
    check_tree(pin, {"sim/bench/klt-pilot/b-request.json": other}, {})
    msg = " ".join(FAILURES)
    case_results.append((
        "failure text names path, both libraries, DELIBERATE_MISMATCHES",
        "sim/bench/klt-pilot/b-request.json" in msg and pin in msg
        and other in msg and "DELIBERATE_MISMATCHES" in msg))

    # The pin itself is validated: a pdk.json without ngspice_lib must fail
    # closed rather than vacuously pass every request.
    try:
        pinned_lib({"family": "sky130", "variant": "sky130A"})
        case_results.append(("rejects a pdk.json with no ngspice_lib "
                             "(fails closed)", False))
    except ValueError:
        case_results.append(("rejects a pdk.json with no ngspice_lib "
                             "(fails closed)", True))

    return report_cases(case_results)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Models-lib pin CI gate: every committed klt sim "
        "request's models.lib vs sim/pdk.json's ngspice_lib (issue #282)"
    )
    sub = parser.add_subparsers(dest="mode", required=True)

    p_gate = sub.add_parser(
        "gate", help="fail if any sim/**/ request's models.lib disagrees "
        "with sim/pdk.json's ngspice_lib outside DELIBERATE_MISMATCHES"
    )
    p_gate.add_argument("--repo-root", default=str(REPO_ROOT))

    return dispatch(parser, sub, argv, run_gate, run_selftest)


if __name__ == "__main__":
    raise SystemExit(main())
