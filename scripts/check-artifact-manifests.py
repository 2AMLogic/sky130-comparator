#!/usr/bin/env python3
"""Stored-evidence manifests: schema guard and no-committed-blob check (issue #198).

New simulation evidence no longer lands in git. Its bytes go to the fleet
artifact store through ``klt artifact put`` (``sim/harness/evidence_store.py``,
``sim/run_store_evidence.py``) and git keeps a **manifest** per run under
``manifests/artifacts/<bench>-<run-id>.manifest.json`` plus the run's Markdown
summary under ``sim/<bench>/``. Evidence bytes are private; manifests are
public (operator decision 1.1, 2026-10-22). This script is the git-side check
of that contract. Two subcommands:

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
import posixpath
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _gate_common import report_cases  # noqa: E402

MANIFEST_DIR = "manifests/artifacts/"
MANIFEST_RE = re.compile(r"^manifests/artifacts/[A-Za-z0-9][A-Za-z0-9._-]*\.manifest\.json$")
DIR_FILES_ALLOWED = {"manifests/artifacts/README.md"}
ENV_BROKER = "KLT_ARTIFACT_BROKER"

SCHEMA_VERSION = 1
KIND = "evidence"
REQUIRED = ("sha256", "size", "kind", "producer", "uri")
OPTIONAL = ("name", "media_type")
PRODUCER_FIELDS = ("tool", "version", "loom.repo", "commit")

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
#: The manifest ``uri`` is a logical name only the broker resolves,
#: ``artifact:<key>`` (operator ruling H1, 2AMLogic/2am#5553; klayout-tools
#: ``7e3561f``). It names no storage location; any other scheme is refused.
URI_RE = re.compile(r"^artifact:([^/\s]\S*)$")

EXIT_OK, EXIT_INVALID, EXIT_ERROR = 0, 1, 2


class ToolError(Exception):
    """Git failure: exit 2, fail closed."""


# --------------------------------------------------------------------------
# Manifest schema (mirrors klayout_tools.artifact_store.entry_problems, plus
# this repo's own rules: evidence kind only, a canonical sim/ name, unique
# names, and a uri key that names the producer's repo)
# --------------------------------------------------------------------------


def uri_key(uri: str) -> str | None:
    """The broker key of an ``artifact:<key>`` uri, else ``None``."""
    m = URI_RE.match(uri) if isinstance(uri, str) else None
    return m.group(1) if m else None


def repo_from_key(key: str) -> str | None:
    """``owner/name`` from an ``evidence/<owner>__<name>/...`` key."""
    parts = key.split("/")
    if len(parts) < 3 or parts[0] != "evidence" or parts[1].count("__") != 1:
        return None
    return parts[1].replace("__", "/")


def canonical_name(name) -> bool:
    return (isinstance(name, str) and name.startswith("sim/")
            and "\\" not in name and "\0" not in name
            and posixpath.normpath(name) == name
            and not {"", ".", ".."} & set(name.split("/")))


def entry_problems(entry) -> list[str]:
    if not isinstance(entry, dict):
        return ["entry is not an object"]
    problems = []
    missing = [f for f in REQUIRED if f not in entry]
    extra = sorted(set(entry) - set(REQUIRED) - set(OPTIONAL))
    if missing:
        problems.append(f"missing {', '.join(missing)}")
    if extra:
        problems.append(f"unknown field(s) {', '.join(extra)}")
    sha = entry.get("sha256")
    if not isinstance(sha, str) or not SHA256_RE.match(sha):
        problems.append("sha256 must be 64 lowercase hex digits")
    size = entry.get("size")
    if not isinstance(size, int) or isinstance(size, bool) or size < 1:
        problems.append("size must be a positive integer")
    if entry.get("kind") != KIND:
        problems.append(f"kind must be {KIND!r}")
    producer = entry.get("producer")
    if not isinstance(producer, dict) or set(producer) != set(PRODUCER_FIELDS):
        problems.append(f"producer must carry exactly {', '.join(PRODUCER_FIELDS)}")
    else:
        for f in ("tool", "version", "loom.repo"):
            if not isinstance(producer.get(f), str) or not producer[f]:
                problems.append(f"producer.{f} must be a non-empty string")
        if producer.get("commit") is not None and not isinstance(producer["commit"], str):
            problems.append("producer.commit must be a string or null")
    key = uri_key(entry.get("uri"))
    if key is None:
        problems.append("uri must be artifact:<key> (no other scheme)")
    else:
        if key.rsplit("/", 1)[-1] != sha:
            problems.append("uri key does not end in the entry's sha256")
        key_repo = repo_from_key(key)
        if key_repo is None:
            problems.append("uri key is not evidence/<owner>__<name>/...")
        elif isinstance(producer, dict) and producer.get("loom.repo") not in (None, key_repo):
            problems.append("uri key names a different repo than producer.loom.repo")
    if "name" not in entry:
        problems.append("name is required here (the logical sim/ path of the bytes)")
    elif not canonical_name(entry["name"]):
        problems.append("name must be a canonical relative sim/... path")
    if "media_type" in entry and not isinstance(entry["media_type"], str):
        problems.append("media_type must be a string")
    return problems


def manifest_problems(manifest) -> list[str]:
    if not isinstance(manifest, dict) or set(manifest) != {"schema_version", "entries"} \
            or manifest.get("schema_version") != SCHEMA_VERSION \
            or not isinstance(manifest.get("entries"), list):
        return [f"not {{schema_version: {SCHEMA_VERSION}, entries: [...]}}"]
    if not manifest["entries"]:
        return ["has no entries"]
    problems = []
    seen = set()
    for i, entry in enumerate(manifest["entries"]):
        for p in entry_problems(entry):
            problems.append(f"entry {i}: {p}")
        name = entry.get("name") if isinstance(entry, dict) else None
        if isinstance(name, str):
            if name in seen:
                problems.append(f"entry {i}: duplicate name {name!r}")
            seen.add(name)
    return problems


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
