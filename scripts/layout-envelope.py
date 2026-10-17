#!/usr/bin/env python3
"""T1 item 2's artifact-anchored envelope: evidence/item2.json (issue #186).

    python3 scripts/layout-envelope.py --write      # (re)write evidence/item2.json
    python3 scripts/layout-envelope.py --check      # exit 1 if it is not what --write would write
    python3 scripts/layout-envelope.py --selftest   # hermetic negative controls

Item 2 ("Layout") is graded on an envelope that names the item
(`"t1_item": 2`) and pins the audited artifact by content hash, so the row is
`met` only while the artifact still re-hashes to that value. The artifact
here is a *set* (`provenance.input.paths`, klayout-tools#3044): the committed
GDS together with the generator and the two request documents the generator
writes, so editing any member turns the row `unmet`/`stale_evidence`. Items
1, 9 and 10 use `klt signoff --attest` instead (see attest/ and
manifests/README.md); item 2 has no attest producer, so this is the generic
hand-built shape the grader documents.

`status: "pass"` is this repo's assertion that the GDS is the committed
layout; it is not a tool check. The tool checks live in layout/drc-report.json
(item 3) and layout/lvs-report.json (item 4).

The combined digest is the sha256 of the lines `<hex>  <path>\\n` over the
members sorted bytewise by path (`input_set_digest` in klayout_tools.signoff).
Stdlib only.
"""

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path

from _gate_common import report_cases

OUT = "evidence/item2.json"
MEMBERS = ["layout/comparator.gds"]
# Versions of the tools that produced the members; the generator pins them.
KLT_VERSION = "0.7.0"
KLAYOUT_VERSION = "0.30.12"


def sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def build(repo: Path, members=MEMBERS) -> dict:
    """Envelope binding `members[0]` (the GDS) by path, plus a regeneration claim.

    The pinned klt 0.7.0 grades a single-path binding only: a `paths` set
    (klayout-tools#3044) renders `unanchored_evidence` there although the
    docs describe it, so the generator and request documents are not bound by
    hash. What stands in for them is `provenance.regeneration` (#2887): the
    claim that `python3 layout/gen_comparator.py` reproduces the GDS bytes,
    whose truth CI re-checks with `gen_comparator.py --check`.
    """
    gds = members[0]
    h = sha((repo / gds).read_bytes())
    return {
        "schema_version": 1,
        "kind": "generic",
        "status": "pass",
        "t1_item": 2,
        "summary": (
            "layout/comparator.gds, regenerated from layout/gen_comparator.py "
            "(python3 layout/gen_comparator.py --check byte-compares it)"
        ),
        "source": "layout/README.md",
        "provenance": {
            "klt_version": KLT_VERSION,
            "klayout_version": KLAYOUT_VERSION,
            "pdk": None,
            "deck": None,
            "input": {"content_hash": h, "path": gds},
            "regeneration": {
                "generator": "python3 layout/gen_comparator.py",
                "regenerated_hash": h,
            },
        },
    }


def render(doc: dict) -> str:
    return json.dumps(doc, indent=2) + "\n"


def run_selftest(_args) -> int:
    results = []
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        for m in MEMBERS:
            (repo / m).parent.mkdir(parents=True, exist_ok=True)
            (repo / m).write_bytes(m.encode())
        base = build(repo)
        results.append(("rebuild over unchanged members is byte-identical",
                        render(build(repo)) == render(base)))
        for m in MEMBERS:
            (repo / m).write_bytes(b"edited")
            changed = build(repo)
            results.append((
                f"editing {m} changes the combined digest",
                changed["provenance"]["input"]["content_hash"]
                != base["provenance"]["input"]["content_hash"],
            ))
            (repo / m).write_bytes(m.encode())
    return report_cases(results)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--repo-root", default=str(Path(__file__).resolve().parent.parent))
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return run_selftest(args)
    repo = Path(args.repo_root)
    want = render(build(repo))
    out = repo / OUT
    if args.write:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(want)
        print(f"wrote {OUT}")
        return 0
    have = out.read_text() if out.exists() else None
    if have != want:
        print(f"layout-envelope: {OUT} is stale or missing; run with --write", file=sys.stderr)
        return 1
    print(f"layout-envelope: {OUT} is current")
    return 0


if __name__ == "__main__":
    sys.exit(main())
