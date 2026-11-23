#!/usr/bin/env python3
"""Stored-evidence manifests: schema guard and no-committed-blob check (issue #198).

New simulation evidence no longer lands in git. Its bytes go to the fleet
artifact store through ``klt artifact put`` (``sim/harness/evidence_store.py``,
``sim/run_store_evidence.py``) and git keeps a **manifest** per run under
``manifests/artifacts/<bench>-<run-id>.manifest.json`` plus the run's Markdown
summary under ``sim/<bench>/``. Evidence bytes are private; manifests are
public (operator decision 1.1, 2026-10-22). This script is the git-side check
of that contract; the manifest schema it applies is
``sim/harness/manifest_schema.py``, shared with the writer so the two cannot
disagree (issue #389). Two subcommands:

``check --tree REV``
    Reads every manifest committed in ``REV`` (blob contents via git, so a
    sparse working tree does not matter) and fails if one is malformed: wrong
    schema, an unknown or missing field, a ``uri`` that is not the logical
    ``artifact:<key>`` (an ``s3`` bucket uri or any other scheme is refused),
    a key that does not end in the entry's sha256, a ``name`` that is not a
    canonical ``sim/...`` path, or a duplicate name. It also fails if any entry's ``name`` is a tracked
    path in ``REV``: the point of a manifest is that the bytes are *not*
    committed, so a blob beside its own manifest is the fallback this repo
    forbids. ``check`` never contacts the broker and says so: schema-valid
    is not hash-verified. Out-of-band hash verification is
    ``klt artifact verify <manifest>`` with ``$KLT_ARTIFACT_BROKER`` set.

``selftest``
    Hermetic negative controls for ``check`` (throwaway git repos): a gate
    that cannot fail proves nothing.

Exit codes: 0 ok; 1 a manifest is invalid or names a committed blob;
2 usage or git error.

Stdlib only; ``check`` needs ``git`` on PATH.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "sim"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _gate_common import report_cases  # noqa: E402
from harness.manifest_schema import KIND, SCHEMA_VERSION, manifest_problems  # noqa: E402

MANIFEST_DIR = "manifests/artifacts/"
MANIFEST_RE = re.compile(r"^manifests/artifacts/[A-Za-z0-9][A-Za-z0-9._-]*\.manifest\.json$")
DIR_FILES_ALLOWED = {"manifests/artifacts/README.md"}
ENV_BROKER = "KLT_ARTIFACT_BROKER"

EXIT_OK, EXIT_INVALID, EXIT_ERROR = 0, 1, 2


class ToolError(Exception):
    """Git failure: exit 2, fail closed."""


# --------------------------------------------------------------------------
# check: committed manifests in a tree
# --------------------------------------------------------------------------


def git(repo: str, *args: str) -> bytes:
    try:
        p = subprocess.run(["git", "-C", repo, *args], stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, check=False,
                           env={**os.environ, "GIT_NO_LAZY_FETCH": "1"})
    except OSError as exc:
        raise ToolError(f"cannot run git: {exc}") from exc
    if p.returncode != 0:
        raise ToolError(f"git {' '.join(args)} failed: "
                        f"{p.stderr.decode('utf-8', 'replace').strip()}")
    return p.stdout


def tracked_paths(repo: str, tree: str) -> dict[str, tuple[str, str]]:
    """``{path: (mode, type)}`` of every entry in ``tree`` (recursive)."""
    out = {}
    for rec in git(repo, "ls-tree", "-r", "-z", tree).split(b"\0"):
        if not rec:
            continue
        meta, _, name = rec.partition(b"\t")
        mode, typ, _ = meta.decode().split(" ")
        out[name.decode("utf-8", "surrogateescape")] = (mode, typ)
    return out


def check(repo: str, rev: str) -> int:
    if rev.startswith("-"):
        raise ToolError(f"invalid revision {rev!r}")
    tree = git(repo, "rev-parse", "--verify", "--quiet", "--end-of-options",
               f"{rev}^{{tree}}").decode().strip()
    if not tree:
        raise ToolError(f"revision {rev!r} is unavailable")
    paths = tracked_paths(repo, tree)
    errors: list[str] = []
    manifests = 0
    entries = 0
    for path in sorted(p for p in paths if p.startswith(MANIFEST_DIR)):
        mode, typ = paths[path]
        if path in DIR_FILES_ALLOWED:
            continue
        if not MANIFEST_RE.match(path) or typ != "blob" or mode == "120000":
            errors.append(f"{path}: only <bench>-<run-id>.manifest.json files (and "
                          "README.md) belong in manifests/artifacts/")
            continue
        try:
            manifest = json.loads(git(repo, "show", f"{tree}:{path}").decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            errors.append(f"{path}: not valid JSON: {exc}")
            continue
        problems = manifest_problems(manifest)
        errors += [f"{path}: {p}" for p in problems]
        if problems:
            continue
        manifests += 1
        for entry in manifest["entries"]:
            entries += 1
            if entry["name"] in paths:
                errors.append(
                    f"{path}: {entry['name']} is committed in the tree; stored "
                    "evidence bytes must not also be committed (no blob fallback)")
    if errors:
        print(f"FAIL: {len(errors)} stored-evidence manifest problem(s) in {rev}:",
              file=sys.stderr)
        for e in errors:
            print(f"  {e}", file=sys.stderr)
        return EXIT_INVALID
    print(f"OK: {manifests} manifest(s), {entries} entr{'y' if entries == 1 else 'ies'} "
          f"in {MANIFEST_DIR} of {rev}: schema valid, no stored bytes committed. "
          "Bytes NOT hash-verified here (no broker contact); run "
          f"`klt artifact verify <manifest>` with ${ENV_BROKER} set.")
    return EXIT_OK


# --------------------------------------------------------------------------
# selftest: hermetic negative controls (a gate that never fails proves nothing)
# --------------------------------------------------------------------------

_ST_SHA = "a" * 64
_ST_NAME = "sim/bench/corners/20261023-000000-abc1234/tt.log"


def _st_entry(**over) -> dict:
    entry = {
        "sha256": _ST_SHA, "size": 10, "kind": KIND,
        "producer": {"tool": "klt", "version": "0", "loom.repo": "o/r", "commit": None},
        "uri": f"artifact:evidence/o__r/aa/{_ST_SHA}",
        "name": _ST_NAME,
    }
    entry.update(over)
    return entry


def _st_run(files: dict[str, str]) -> int:
    """Commit ``files`` into a throwaway repo and run ``check`` over HEAD."""
    import contextlib
    import io
    import tempfile
    with tempfile.TemporaryDirectory(prefix="artifact-manifests-selftest-") as tmp:
        def g(*a):
            subprocess.run(["git", "-C", tmp, "-c", "user.name=t", "-c", "user.email=t@t",
                            *a], check=True, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
        g("init", "-q")
        for rel, text in files.items():
            path = os.path.join(tmp, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
        g("add", "-A")
        g("commit", "-q", "-m", "x")
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return check(tmp, "HEAD")


def selftest() -> int:
    def mf(*entries) -> dict[str, str]:
        doc = {"schema_version": SCHEMA_VERSION, "entries": list(entries)}
        return {MANIFEST_DIR + "bench-run.manifest.json": json.dumps(doc)}

    cases = [
        ("valid manifest passes", mf(_st_entry()), EXIT_OK),
        ("no manifests passes", {"README.md": "x"}, EXIT_OK),
        ("s3 uri is refused",
         mf(_st_entry(uri=f"s3://bucket/evidence/o__r/aa/{_ST_SHA}")), EXIT_INVALID),
        ("non-artifact uri is refused",
         mf(_st_entry(uri=f"https://example.invalid/{_ST_SHA}")), EXIT_INVALID),
        ("uri key not ending in the sha256 is refused",
         mf(_st_entry(uri="artifact:evidence/o__r/aa/" + "b" * 64)), EXIT_INVALID),
        ("unknown field is refused", mf(_st_entry(extra=1)), EXIT_INVALID),
        ("non-sim name is refused", mf(_st_entry(name="../x.log")), EXIT_INVALID),
        ("duplicate name is refused", mf(_st_entry(), _st_entry()), EXIT_INVALID),
        ("stored bytes also committed is refused",
         {**mf(_st_entry()), _ST_NAME: "raw log\n"}, EXIT_INVALID),
        ("stray file in manifests/artifacts is refused",
         {**mf(_st_entry()), MANIFEST_DIR + "notes.txt": "x"}, EXIT_INVALID),
    ]
    case_results = []
    for label, files, want in cases:
        got = _st_run(files)
        case_results.append((f"{label} (exit {got}, want {want})", got == want))
    return report_cases(case_results)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="schema + no-committed-blob guard for a tree")
    c.add_argument("--tree", required=True, help="commit or tree (e.g. HEAD)")
    c.add_argument("--repo", default=".", help="repository path (default .)")
    sub.add_parser("selftest", help="hermetic negative controls for check")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "selftest":
            return selftest()
        return check(args.repo, args.tree)
    except ToolError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
