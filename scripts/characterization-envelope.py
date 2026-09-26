#!/usr/bin/env python3
"""T1 item 8's evidence envelope, with the freshness check run live (issue #86).

    python3 scripts/characterization-envelope.py             # emit the envelope
    python3 scripts/characterization-envelope.py --update    # re-pin after an edit
    python3 scripts/characterization-envelope.py --selftest  # hermetic negative controls

`klt signoff` grades T1 item 8 from a **command-backed** manifest entry --
`"8": {"command": ["python3", "scripts/characterization-envelope.py"]}` --
and grades it against *this* run's own stdout. So the envelope this script
prints is not a committed file being read back: it is computed on the spot,
and its `status` reports whether `sim/characterization-report.md` and every
artifact that report's "Evidence index" names are still byte-for-byte the
ones the pins in `sim/characterization-envelope.json` were taken from.

Why a command and not a file
----------------------------
`klt signoff --manifest` reports `input_verified` on every `met` citation --
"was the pinned hash checked against the artifact itself, or only against
another claim?". For a `"kind": "generic"` envelope (the only kind T1 item 8
accepts) the pinned `klt` 0.6.0 lists no input-artifact field, so that answer
is structurally always `null` and the grader cannot anchor the citation's
freshness to anything. Filed upstream, generically, as
2AMLogic/klayout-tools#2403 (closed there against an unreleased build; the
pinned 0.6.0 still has the gap). The three file-backed shapes each fail a
different way:

- pinned `content_hash`, no matching envelope provenance -> `unmet` /
  `unverifiable_provenance`;
- pinned `content_hash` + matching provenance -> `met`, but
  `scripts/check-t1-signoff.py` rule 3 then warns on *every* run, forever;
- no pinned `content_hash` -> `met`, no warning, and **no freshness anchor at
  all** -- a rotted report would keep grading `met`, which
  `manifests/design-evidence-tiers.md`'s "Staleness is failure" forbids.

Running the hash comparison here, live, gives the anchor without the standing
warning: the emitted envelope deliberately carries **no `provenance` block**,
so the citation's `content_hash` is `null` and rule 3 never fires, while
drift still renders the item `unmet` because it changes this envelope's
`status`.

The drift signal is the `status` field, NOT the exit code
---------------------------------------------------------
`klt signoff`'s `_grade_evidence` parses a command-backed entry's stdout
*before* it inspects `exit_status`, and "if stdout parses, the envelope flows
into `_classify`/`_check_passed` regardless of `exit_status`". A guard that
exited 1 while still printing `status: "pass"` would therefore grade `met`
anyway. This script derives its exit code *from* the status (never the other
way round) and the selftest asserts that invariant directly.

Stdout discipline: in emit mode stdout carries the envelope JSON and nothing
else. Diagnostics go to stderr.

Stdlib only, no virtualenv required. `report_cases` is shared with the other
`scripts/*.py` gates via `_gate_common.py` so the selftest output convention
cannot drift.
"""

import argparse
import hashlib
import json
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _gate_common import report_cases  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]

REPORT_REL = "sim/characterization-report.md"
PINS_REL = "sim/characterization-envelope.json"

#: `klt signoff` requires `schema_version`, `kind` and `status` on a generic
#: envelope (`_GenericRequired`); everything else below is optional and is
#: never read by any grading rule.
ENVELOPE_SCHEMA_VERSION = 1

#: Where the report's machine-readable citation list starts. Everything after
#: this heading is the index; nothing before it is parsed as one, so the
#: per-row measurement tables (whose first column is a corner name, not a
#: path) can never be mistaken for citations.
INDEX_HEADING = "## Evidence index"

#: An index row: a Markdown table row whose first cell is a backticked
#: repo-relative path.
_INDEX_ROW_RE = re.compile(r"^\|\s*`([^`|]+)`\s*\|")

#: Any evidence record the report mentions *anywhere*. Used for the
#: under-indexing check: a figure cited in a row table but forgotten in the
#: index would otherwise be unpinned, and could rot unnoticed.
_RECORD_PATH_RE = re.compile(
    r"sim/comparator-decision/records/[0-9]{8}-[0-9]{6}-[0-9a-f]+\.md"
)


def sha256_file(path: Path) -> str | None:
    """`sha256:<hex>` for `path`, or None when it cannot be read."""
    digest = hashlib.sha256()
    try:
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 16), b""):
                digest.update(chunk)
    except OSError:
        return None
    return f"sha256:{digest.hexdigest()}"


def parse_index(report_text: str) -> list[str]:
    """The repo-relative artifact paths listed in the report's Evidence index,
    in document order, de-duplicated.

    Raises `ValueError` when the heading is absent -- a report with no index
    cites nothing checkable, which must not read as "nothing drifted".
    """
    marker = report_text.find(INDEX_HEADING)
    if marker < 0:
        raise ValueError(
            f"{REPORT_REL} has no '{INDEX_HEADING}' section -- there is "
            "nothing to pin"
        )
    seen: list[str] = []
    for line in report_text[marker:].splitlines():
        match = _INDEX_ROW_RE.match(line)
        if match:
            path = match.group(1).strip()
            if path not in seen:
                seen.append(path)
    if not seen:
        raise ValueError(f"{REPORT_REL}'s '{INDEX_HEADING}' section lists no paths")
    return seen


def mentioned_records(report_text: str) -> set[str]:
    return set(_RECORD_PATH_RE.findall(report_text))


def compute_pins(root: Path) -> dict:
    """The freshness block for the *current* tree -- what `--update` writes."""
    report_path = root / REPORT_REL
    report_text = report_path.read_text(encoding="utf-8")
    artifacts = []
    for rel in parse_index(report_text):
        artifacts.append({"path": rel, "content_hash": sha256_file(root / rel)})
    return {
        "generator": ["python3", "scripts/characterization-envelope.py"],
        "report": {
            "path": REPORT_REL,
            "content_hash": sha256_file(report_path),
        },
        "artifacts": artifacts,
    }


def verify(root: Path) -> tuple[str, dict, list[str]]:
    """Re-hash the report and its cited artifacts against the committed pins.

    Returns `(status, verification, failures)` where `status` is `"pass"`
    only when `failures` is empty. Every anticipated problem -- a missing
    pins file, an unparsable one, a vanished report -- is reported as a
    failure here rather than raised, so the caller always has a well-formed
    envelope to print: an unparsable stdout would render
    `unreadable_evidence`/`command_failed`, which is also `unmet` but says
    less about why.
    """
    failures: list[str] = []
    verification: dict = {
        "report": {"path": REPORT_REL, "pinned": None, "actual": None, "match": False},
        "artifacts": {
            "pinned": 0,
            "verified": 0,
            "drifted": [],
            "missing": [],
        },
        "index": {"unpinned": [], "stale_pins": [], "unindexed_records": []},
    }

    pins_path = root / PINS_REL
    try:
        pins_doc = json.loads(pins_path.read_text(encoding="utf-8"))
    except OSError:
        failures.append(f"pins file not readable: {PINS_REL}")
        return "fail", verification, failures
    except json.JSONDecodeError as exc:
        failures.append(f"pins file is not valid JSON: {PINS_REL}: {exc}")
        return "fail", verification, failures
    if not isinstance(pins_doc, dict):
        failures.append(f"pins file is not a JSON object: {PINS_REL}")
        return "fail", verification, failures

    freshness = pins_doc.get("freshness")
    if not isinstance(freshness, dict):
        failures.append(f"pins file has no 'freshness' object: {PINS_REL}")
        return "fail", verification, failures

    pinned_report = (freshness.get("report") or {}).get("content_hash")
    pinned_artifacts = freshness.get("artifacts")
    if not isinstance(pinned_artifacts, list):
        failures.append(f"pins file has no 'freshness.artifacts' array: {PINS_REL}")
        return "fail", verification, failures

    report_path = root / REPORT_REL
    actual_report = sha256_file(report_path)
    verification["report"]["pinned"] = pinned_report
    verification["report"]["actual"] = actual_report
    if actual_report is None:
        failures.append(f"report not readable: {REPORT_REL}")
    elif actual_report != pinned_report:
        failures.append(
            f"{REPORT_REL} drifted: pinned {pinned_report}, actual "
            f"{actual_report} -- re-run with --update"
        )
    else:
        verification["report"]["match"] = True

    pinned_paths = []
    verification["artifacts"]["pinned"] = len(pinned_artifacts)
    for entry in pinned_artifacts:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            failures.append(f"malformed pin entry in {PINS_REL}: {entry!r}")
            continue
        rel = entry["path"]
        pinned_paths.append(rel)
        actual = sha256_file(root / rel)
        if actual is None:
            verification["artifacts"]["missing"].append(rel)
            failures.append(f"cited artifact missing or unreadable: {rel}")
        elif actual != entry.get("content_hash"):
            verification["artifacts"]["drifted"].append(rel)
            failures.append(
                f"cited artifact drifted: {rel} (pinned "
                f"{entry.get('content_hash')}, actual {actual}) -- re-run "
                "with --update"
            )
        else:
            verification["artifacts"]["verified"] += 1

    # The index must agree with the pins in BOTH directions, and the report
    # body must not cite an evidence record the index forgot: a pin set that
    # is merely a subset of what the report leans on is not a freshness
    # anchor for the parts it omits.
    if actual_report is not None:
        report_text = report_path.read_text(encoding="utf-8")
        try:
            indexed = parse_index(report_text)
        except ValueError as exc:
            failures.append(str(exc))
            indexed = []
        unpinned = [rel for rel in indexed if rel not in pinned_paths]
        stale = [rel for rel in pinned_paths if rel not in indexed]
        unindexed = sorted(mentioned_records(report_text) - set(indexed))
        verification["index"]["unpinned"] = unpinned
        verification["index"]["stale_pins"] = stale
        verification["index"]["unindexed_records"] = unindexed
        for rel in unpinned:
            failures.append(
                f"{REPORT_REL} indexes {rel} but the pins do not cover it "
                "-- re-run with --update"
            )
        for rel in stale:
            failures.append(
                f"pins cover {rel} but {REPORT_REL}'s index no longer lists "
                "it -- re-run with --update"
            )
        for rel in unindexed:
            failures.append(
                f"{REPORT_REL} cites evidence record {rel} in its body but "
                "does not list it in the Evidence index -- it would go "
                "unpinned"
            )

    return ("pass" if not failures else "fail"), verification, failures


def build_envelope(status: str, verification: dict, failures: list[str]) -> dict:
    """The `"kind": "generic"` envelope `klt signoff` grades item 8 on.

    Deliberately carries **no `provenance` block**: `klt` 0.6.0 would read a
    `provenance.input.content_hash` into the citation without ever
    re-hashing it (`generic` has no `_INPUT_ARTIFACT_FIELDS` entry), which is
    exactly the `input_verified: null` + non-empty `content_hash` shape
    `scripts/check-t1-signoff.py` rule 3 warns on. The hashes live under
    `verification` instead, where no grading rule reads them and no gate rule
    mistakes them for a grader-verified pin.
    """
    verified = verification["artifacts"]["verified"]
    pinned = verification["artifacts"]["pinned"]
    if status == "pass":
        summary = (
            f"sky130-comparator characterization report: all five target-spec "
            f"rows aggregated; {REPORT_REL} and {verified}/{pinned} cited "
            "artifacts re-hashed and current. Asserts aggregation and "
            "currency only -- not that any bound is met (the Input-referred "
            "noise row's compliance basis is re-opened by DR-006, and the "
            "Supply/power row is DRAFT/OPEN with no ratified bound)."
        )
    else:
        summary = (
            f"STALE OR INCOMPLETE: {len(failures)} freshness failure(s) "
            f"against {REPORT_REL}; the aggregated characterization report "
            "no longer matches the evidence it cites."
        )
    envelope = {
        "schema_version": ENVELOPE_SCHEMA_VERSION,
        "kind": "generic",
        "status": status,
        "summary": summary,
        "source": REPORT_REL,
        "verification": verification,
    }
    if failures:
        envelope["verification"]["failures"] = failures
    return envelope


def run_emit(root: Path, stream=None, quiet: bool = False) -> int:
    status, verification, failures = verify(root)
    envelope = build_envelope(status, verification, failures)
    print(json.dumps(envelope, indent=2), file=stream or sys.stdout)
    if not quiet:
        for line in failures:
            print(f"characterization-envelope: FAIL: {line}", file=sys.stderr)
    # Derived FROM the status, never the other way round -- see the module
    # docstring: klt parses stdout before it looks at the exit code.
    return 0 if status == "pass" else 1


def run_update(root: Path, quiet: bool = False) -> int:
    pins_path = root / PINS_REL
    try:
        existing = json.loads(pins_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        existing = {}
    freshness = compute_pins(root)
    missing = [a["path"] for a in freshness["artifacts"] if a["content_hash"] is None]
    if freshness["report"]["content_hash"] is None:
        print(
            f"characterization-envelope: cannot read {REPORT_REL}", file=sys.stderr
        )
        return 1
    if missing:
        for rel in missing:
            print(
                f"characterization-envelope: FAIL: indexed artifact does not "
                f"exist: {rel}",
                file=sys.stderr,
            )
        return 1
    doc = {
        "schema_version": ENVELOPE_SCHEMA_VERSION,
        "kind": "generic",
        "status": "pass",
        "summary": existing.get("summary")
        or (
            "Reference shape for T1 item 8's generic evidence envelope, and "
            "the freshness pins scripts/characterization-envelope.py checks "
            "against. NOT cited directly by manifests/sky130-comparator.json "
            "-- the manifest cites the command, so the hash comparison "
            "happens live."
        ),
        "source": REPORT_REL,
        "freshness": freshness,
    }
    pins_path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    if not quiet:
        print(
            f"characterization-envelope: re-pinned {PINS_REL} "
            f"({len(freshness['artifacts'])} artifact(s) + the report)",
            file=sys.stderr,
        )
    return 0


# --------------------------------------------------------------------------- #
# Hermetic selftest -- the negative controls that prove the drift guard bites
# --------------------------------------------------------------------------- #

_FIXTURE_REPORT = """# Fixture characterization report

Row 1 rests on `sim/comparator-decision/records/20260101-000000-abc1234.md`.

## Evidence index

| Artifact | Row(s) | What it carries |
|---|---|---|
| `sim/comparator-decision/records/20260101-000000-abc1234.md` | 1 | fixture |
| `spec/decision-records/DR-000-fixture.md` | 1 | fixture |
"""


def _make_fixture(tmp: Path, report_text: str = _FIXTURE_REPORT) -> Path:
    root = tmp
    (root / "sim" / "comparator-decision" / "records").mkdir(parents=True)
    (root / "spec" / "decision-records").mkdir(parents=True)
    (root / REPORT_REL).write_text(report_text, encoding="utf-8")
    (
        root / "sim/comparator-decision/records/20260101-000000-abc1234.md"
    ).write_text("fixture record\n", encoding="utf-8")
    (root / "spec/decision-records/DR-000-fixture.md").write_text(
        "fixture DR\n", encoding="utf-8"
    )
    run_update(root, quiet=True)
    return root


def _emit(root: Path) -> tuple[int, dict]:
    """Run the emit path exactly as `klt signoff` would, capturing stdout."""
    import io

    buf = io.StringIO()
    code = run_emit(root, stream=buf, quiet=True)
    return code, json.loads(buf.getvalue())


def run_selftest() -> int:
    cases: list[tuple[str, bool]] = []
    invariant_holds = True

    def scenario(name, mutate, expect_status):
        nonlocal invariant_holds
        with tempfile.TemporaryDirectory() as td:
            root = _make_fixture(Path(td))
            mutate(root)
            code, env = _emit(root)
        passed = env.get("status") == expect_status
        passed = passed and (code == 0) == (expect_status == "pass")
        # The invariant this whole design rests on: klt reads stdout before
        # exit_status, so a nonzero exit must NEVER be accompanied by
        # `status: "pass"`.
        if code != 0 and env.get("status") == "pass":
            invariant_holds = False
        cases.append((name, passed))
        return env

    def noop(_root):
        pass

    env = scenario("drift-free tree emits status: pass", noop, "pass")

    cases.append(
        (
            "envelope carries the three _GenericRequired fields",
            isinstance(env.get("schema_version"), int)
            and env.get("kind") == "generic"
            and isinstance(env.get("status"), str),
        )
    )
    cases.append(
        (
            "envelope carries NO provenance block (rule-3 warning guard)",
            "provenance" not in env,
        )
    )

    scenario(
        "edited report emits status: fail",
        lambda root: (root / REPORT_REL).write_text(
            _FIXTURE_REPORT + "\nan unpinned edit\n", encoding="utf-8"
        ),
        "fail",
    )

    scenario(
        "missing cited record emits status: fail",
        lambda root: (
            root / "sim/comparator-decision/records/20260101-000000-abc1234.md"
        ).unlink(),
        "fail",
    )

    scenario(
        "modified cited record emits status: fail",
        lambda root: (
            root / "sim/comparator-decision/records/20260101-000000-abc1234.md"
        ).write_text("tampered\n", encoding="utf-8"),
        "fail",
    )

    scenario(
        "record cited in the body but absent from the index emits status: fail",
        lambda root: _repin_without_index_entry(root),
        "fail",
    )

    scenario(
        "missing pins file emits status: fail (and still valid JSON)",
        lambda root: (root / PINS_REL).unlink(),
        "fail",
    )

    scenario(
        "unparsable pins file emits status: fail",
        lambda root: (root / PINS_REL).write_text("{not json", encoding="utf-8"),
        "fail",
    )

    scenario(
        "pin for an artifact the index no longer lists emits status: fail",
        _add_stale_pin,
        "fail",
    )

    cases.append(
        ("no failing path ever printed status: pass on a nonzero exit", invariant_holds)
    )

    # And the live tree: the committed report and pins must agree, or the
    # committed manifest's item-8 citation is already stale.
    live_status, _, live_failures = verify(REPO_ROOT)
    cases.append(
        (
            f"committed tree verifies clean ({'; '.join(live_failures) or 'no drift'})",
            live_status == "pass",
        )
    )

    return report_cases(cases)


def _repin_without_index_entry(root: Path) -> None:
    """Drop one record from the index, then re-pin, leaving the report body
    still citing it -- the under-indexing case."""
    text = (root / REPORT_REL).read_text(encoding="utf-8")
    trimmed = "\n".join(
        line
        for line in text.splitlines()
        if "20260101-000000-abc1234.md` | 1 | fixture" not in line
    )
    (root / REPORT_REL).write_text(trimmed + "\n", encoding="utf-8")
    run_update(root, quiet=True)


def _add_stale_pin(root: Path) -> None:
    """Pin an artifact the index does not list -- the stale-pin case."""
    extra = root / "spec/decision-records/DR-001-fixture.md"
    extra.write_text("another fixture DR\n", encoding="utf-8")
    doc = json.loads((root / PINS_REL).read_text(encoding="utf-8"))
    doc["freshness"]["artifacts"].append(
        {
            "path": "spec/decision-records/DR-001-fixture.md",
            "content_hash": sha256_file(extra),
        }
    )
    (root / PINS_REL).write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Emit T1 item 8's generic evidence envelope, with the report's "
            "freshness checked live."
        )
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--update",
        action="store_true",
        help="re-pin sim/characterization-envelope.json from the current report",
    )
    group.add_argument(
        "--selftest",
        action="store_true",
        help="hermetic fixture test of the drift guard (no klt, no network)",
    )
    parser.add_argument(
        "--repo-root",
        default=str(REPO_ROOT),
        help="tree to verify (default: this script's repository)",
    )
    args = parser.parse_args(argv)

    if args.selftest:
        return run_selftest()
    root = Path(args.repo_root).resolve()
    if args.update:
        return run_update(root)
    return run_emit(root)


if __name__ == "__main__":
    raise SystemExit(main())
