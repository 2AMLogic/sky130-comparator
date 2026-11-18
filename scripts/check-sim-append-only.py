#!/usr/bin/env python3
"""CI gate: sim/ evidence is append-only against the Git base (issue #138).

    python3 scripts/check-sim-append-only.py gate --event pull_request --base-ref origin/main
    python3 scripts/check-sim-append-only.py gate --event push --before <sha> [--head <sha>]
    python3 scripts/check-sim-append-only.py gate --event workflow_dispatch [--base <sha>]
    python3 scripts/check-sim-append-only.py gate --event merge_group --base <sha> [--head <sha>]
    python3 scripts/check-sim-append-only.py selftest

sim/README.md forbids editing or deleting committed evidence, even for typo
fixes. The freshness guard (scripts/characterization-envelope.py) cannot
enforce that: `--update` re-pins whatever is on disk, so an edited record
plus a re-pin passes it. This gate compares against Git history instead.

Protected scope (derived from the "Directory / naming convention" in
sim/README.md): every path matching

    sim/<experiment-slug>/{records,corners,mc-draws,netlist-snapshots}/**

i.e. summary records, raw per-corner logs, raw Monte Carlo logs and frozen
netlist snapshots. `testbench/`, harness code, and the derived
sim/characterization-report.md + sim/characterization-envelope.json are NOT
protected (the README documents the latter two as rewritten on purpose).

Rule: a protected path that exists at the comparison base must be byte- and
mode-identical at head. Added paths pass. Modification (M), removal (D) and
file-type change (T) fail; the diff is taken with rename detection OFF, so a
rename shows up as a removal of the old path and fails by name.

Comparison semantics (the base must be explicit; an unavailable base is a
FAILURE, never a pass):
  pull_request       head vs `git merge-base <base-ref> <head>`
  push               `--before` (event.before) vs head (event.after)
  workflow_dispatch  no event base exists: `--base <sha>` is required,
                     otherwise the gate fails rather than claim verification
  merge_group        the merge queue's trial merge: `--base <sha>` (the
                     event's merge_group.base_sha) vs head (--head); like
                     workflow_dispatch, an absent or unavailable base fails
  all-zero --before  (branch creation / first commit) has no base: fails
The checkout must supply history (actions/checkout `fetch-depth: 0`).

Waivers (issue #326, DR-011): a protected path whose only change is a REMOVAL
(D) may be waived by an entry in manifests/append-only-waivers.json
(`{"waivers": [{"decision_record", "paths", "base_sha"}]}`, exact paths, no
globs). The manifest is read from head (a PR adds its own entry), but the
cited record's `Status` is read at the comparison BASE, so a PR cannot ratify
its own waiver; the path's blob at the base must equal its blob at the
entry's `base_sha`. M and T are never waivable. A malformed manifest fails.

To correct a recorded result, do not edit it: mint a NEW record under the
same experiment and cite the old one in its `Supersedes` field (see
sim/README.md, "Summary record format").

Stdlib + git only. Exit codes: 0 pass, 1 failure, 2 usage error.
"""

import argparse
import contextlib
import io
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _gate_common import (FAILURES, dispatch, fail, ok,  # noqa: E402
                          report_cases, reset)

PROTECTED_RE = re.compile(
    r"^sim/[^/]+/(?:records|corners|mc-draws|netlist-snapshots)/.+")
ZERO_SHA = "0" * 40
WAIVER_MANIFEST = "manifests/append-only-waivers.json"
DR_DIR = "spec/decision-records/"
STATUS_RE = re.compile(r"^- \*\*Status\*\*:\s*(.*)$", re.M)
STATUS_NAMES = {"M": "modified", "D": "removed", "T": "file-type changed"}


def git(repo, *args):
    """Run git in `repo`; return (returncode, stdout bytes)."""
    proc = subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True)
    return proc.returncode, proc.stdout


def resolve_commit(repo, rev):
    rc, out = git(repo, "rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}")
    return out.decode().strip() if rc == 0 else None


def resolve_base(repo, event, base_ref=None, before=None, base=None,
                 head="HEAD"):
    """Return (base_sha, head_sha); raise ValueError if no base exists."""
    head_sha = resolve_commit(repo, head)
    if head_sha is None:
        raise ValueError(f"head commit {head!r} is not available")
    if event == "pull_request":
        if not base_ref:
            raise ValueError("pull_request needs --base-ref (e.g. origin/main)")
        base_sha = resolve_commit(repo, base_ref)
        if base_sha is None:
            raise ValueError(
                f"base ref {base_ref!r} is not available in this checkout "
                "(fetch it, and use actions/checkout fetch-depth: 0)")
        rc, out = git(repo, "merge-base", base_sha, head_sha)
        if rc != 0 or not out.strip():
            raise ValueError(
                f"no merge-base between {base_ref!r} and {head!r}: history is "
                "shallow or unrelated; use actions/checkout fetch-depth: 0")
        return out.decode().strip(), head_sha
    if event == "push":
        if not before or set(before) == {"0"}:
            raise ValueError(
                "push has no 'before' commit (branch creation / first commit): "
                "there is no base to compare against, so append-only cannot "
                "be verified")
        base_sha = resolve_commit(repo, before)
        if base_sha is None:
            raise ValueError(
                f"push 'before' commit {before} is not available (force-push "
                "or shallow checkout?); append-only cannot be verified")
        return base_sha, head_sha
    if event == "workflow_dispatch":
        if not base:
            raise ValueError(
                "manual dispatch has no event base: re-run with an explicit "
                "base commit input; refusing to claim append-only was verified")
        base_sha = resolve_commit(repo, base)
        if base_sha is None:
            raise ValueError(f"base commit {base!r} is not available")
        return base_sha, head_sha
    if event == "merge_group":
        if not base:
            raise ValueError(
                "merge_group has no event base (github.event.merge_group."
                "base_sha empty?): re-run with an explicit base commit; "
                "refusing to claim append-only was verified")
        base_sha = resolve_commit(repo, base)
        if base_sha is None:
            raise ValueError(f"base commit {base!r} is not available")
        return base_sha, head_sha
    raise ValueError(f"unknown event {event!r}")


def violations(repo, base_sha, head_sha):
    """Return sorted [(path, status)] of protected paths changed M/D/T."""
    rc, out = git(repo, "diff", "--raw", "-z", "--no-renames", "--no-abbrev",
                  base_sha, head_sha, "--", "sim")
    if rc != 0:
        raise ValueError(f"git diff {base_sha[:12]}..{head_sha[:12]} failed")
    toks = out.decode("utf-8", "surrogateescape").split("\0")
    found = []
    i = 0
    while i + 1 < len(toks) and toks[i].startswith(":"):
        status = toks[i].split()[-1][0]
        path = toks[i + 1]
        i += 2
        if status in STATUS_NAMES and PROTECTED_RE.match(path):
            found.append((path, status))
    return sorted(found)


def load_waivers(repo, head_sha):
    """Return {path: [(decision_record, base_sha)]} from the head manifest.

    Absent manifest or empty list = no waivers. Malformed raises ValueError.
    """
    rc, out = git(repo, "show", f"{head_sha}:{WAIVER_MANIFEST}")
    if rc != 0:
        return {}
    try:
        doc = json.loads(out.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{WAIVER_MANIFEST} is not valid JSON: {exc}") from None
    entries = doc.get("waivers") if isinstance(doc, dict) else None
    if not isinstance(entries, list):
        raise ValueError(
            f'{WAIVER_MANIFEST} must be an object with a "waivers" list')
    waivers = {}
    for n, ent in enumerate(entries):
        where = f"{WAIVER_MANIFEST} waivers[{n}]"
        if not isinstance(ent, dict):
            raise ValueError(f"{where} is not an object")
        rec, sha, paths = (ent.get("decision_record"), ent.get("base_sha"),
                           ent.get("paths"))
        if not (isinstance(rec, str) and rec.startswith(DR_DIR)
                and ".." not in rec.split("/")):
            raise ValueError(f"{where}: decision_record must be a path under "
                             f"{DR_DIR}")
        if not (isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{40}", sha)):
            raise ValueError(f"{where}: base_sha must be a full 40-hex SHA")
        if not (isinstance(paths, list) and paths
                and all(isinstance(x, str) for x in paths)):
            raise ValueError(f"{where}: paths must be a non-empty list of "
                             "strings")
        for path in paths:
            if not PROTECTED_RE.match(path) or any(c in path for c in "*?[]"):
                raise ValueError(f"{where}: {path!r} is not an exact "
                                 "protected path (no globs)")
            waivers.setdefault(path, []).append((rec, sha))
    return waivers


def record_ratified_at(repo, base_sha, record):
    """Return (ratified, reason) for `record` read at `base_sha`."""
    rc, out = git(repo, "show", f"{base_sha}:{record}")
    if rc != 0:
        return False, f"record {record} is missing at the base"
    m = STATUS_RE.search(out.decode("utf-8", "replace"))
    status = m.group(1).replace("*", "").strip().lower() if m else ""
    if not status.startswith("ratified"):
        return False, (f"record {record} is not ratified at the base "
                       f"(Status: {status or 'absent'})")
    return True, ""


def waiver_verdict(repo, base_sha, path, entries):
    """Return (applied_record, None) or (None, reason) for a removed path."""
    reasons = []
    for rec, sha in entries:
        good, why = record_ratified_at(repo, base_sha, rec)
        if not good:
            reasons.append(why)
            continue
        rc_b, blob_b = git(repo, "rev-parse", "--verify", "--quiet",
                           f"{base_sha}:{path}")
        rc_w, blob_w = git(repo, "rev-parse", "--verify", "--quiet",
                           f"{sha}:{path}")
        if rc_b == 0 and rc_w == 0 and blob_b == blob_w:
            return rec, None
        reasons.append(f"bytes at the base differ from base_sha {sha[:12]} "
                       "(or the path is absent there)")
    return None, "; ".join(reasons)


def check(repo, event, **kw):
    """Run the comparison; record results via ok()/fail()."""
    try:
        base_sha, head_sha = resolve_base(repo, event, **kw)
        found = violations(repo, base_sha, head_sha)
        waivers = load_waivers(repo, head_sha) if found else {}
    except ValueError as exc:
        fail(str(exc))
        return
    applied = []
    unwaived = []
    for path, status in found:
        if status == "D" and path in waivers:
            rec, why = waiver_verdict(repo, base_sha, path, waivers[path])
            if rec:
                applied.append((path, rec))
                continue
            fail(f"protected evidence removed: {path} (waiver rejected: "
                 f"{why})")
            unwaived.append(path)
            continue
        fail(f"protected evidence {STATUS_NAMES[status]}: {path}"
             + (" (listed in the waiver manifest, but only removals are "
                "waivable)" if path in waivers else
                " (no waiver entry)" if status == "D" else ""))
        unwaived.append(path)
    if unwaived:
        print("gate: sim/ evidence is append-only (sim/README.md). Do not "
              "edit, delete or rename committed records, corner logs, "
              "mc-draws or netlist snapshots; add a NEW record under the "
              "same experiment and cite the old one in its `Supersedes` "
              "field. Re-pinning the characterization envelope does not "
              "make such an edit acceptable. A removal ruled on by a "
              f"ratified decision record may be waived in {WAIVER_MANIFEST} "
              "(DR-011).")
    else:
        span = f"{base_sha[:12]}..{head_sha[:12]}"
        if applied:
            ok(f"protected sim/ evidence unchanged except waived removals "
               f"({span}): " + "; ".join(f"{p} (per {r})" for p, r in applied))
        else:
            ok(f"no protected sim/ evidence changed ({span})")


def run_gate(args):
    reset()
    check(args.repo, args.event, base_ref=args.base_ref, before=args.before,
          base=args.base, head=args.head)
    return 1 if FAILURES else 0


# --- selftest -------------------------------------------------------------

def _g(repo, *a):
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t",
                    "-c", "user.email=t@t", "-c", "commit.gpgsign=false", *a],
                   check=True, capture_output=True)


def _write(repo, rel, text):
    p = Path(repo) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def _commit(repo, msg="c"):
    _g(repo, "add", "-A")
    _g(repo, "commit", "-q", "--allow-empty", "-m", msg)
    return resolve_commit(repo, "HEAD")


REC = "sim/exp/records/20260101-000000-abc1234.md"
LOG = "sim/exp/corners/20260101-000000-abc1234/tt_27c_1.80v.log"
MC = "sim/exp/mc-draws/20260101-000000-abc1234/draw_0_seed1.log"
NET = "sim/exp/netlist-snapshots/20260101-000000-abc1234.spice"
WS = "sim/exp/records/with space/rec one.md"
REPORT = "sim/characterization-report.md"
ENV = "sim/characterization-envelope.json"


def _fixture():
    tmp = tempfile.TemporaryDirectory()
    repo = Path(tmp.name)
    _g(repo, "init", "-q", "-b", "main")
    for p in (REC, LOG, MC, NET, WS, REPORT, ENV, "sim/exp/testbench/tb.json"):
        _write(repo, p, "v1\n")
    base = _commit(repo, "base")
    _g(repo, "checkout", "-q", "-b", "feature")
    return tmp, repo, base


def _run(mutate, event="pull_request", **kw):
    """Build fixture, apply mutate(repo), return list of failure messages."""
    tmp, repo, base = _fixture()
    with tmp:
        mutate(repo)
        _commit(repo, "change")
        reset()
        if event == "pull_request":
            kw.setdefault("base_ref", "main")
        elif event == "push":
            kw.setdefault("before", base)
        check(repo, event, **kw)
        msgs = list(FAILURES)
        reset()
        return msgs


def _rm(repo, rel):
    (Path(repo) / rel).unlink()


def run_selftest(_args):
    cases = []

    def expect(name, msgs, paths=(), clean=False):
        good = (not msgs) if clean else (
            bool(msgs) and all(any(p in " ".join(msgs) for p in [x]) for x in paths))
        cases.append((name, good))

    expect("adding a new record passes",
           _run(lambda r: _write(r, "sim/exp/records/new.md", "n\n")), clean=True)
    expect("adding a whole new experiment passes",
           _run(lambda r: _write(r, "sim/new/corners/x/y.log", "n\n")), clean=True)
    expect("editing the derived report and envelope passes",
           _run(lambda r: (_write(r, REPORT, "v2\n"), _write(r, ENV, "v2\n"))),
           clean=True)
    expect("editing the testbench passes",
           _run(lambda r: _write(r, "sim/exp/testbench/tb.json", "v2\n")),
           clean=True)
    for label, path in (("record", REC), ("corner log", LOG),
                        ("mc raw log", MC), ("netlist snapshot", NET),
                        ("whitespace path", WS)):
        expect(f"modifying a {label} fails and names it",
               _run(lambda r, p=path: _write(r, p, "edited\n")), [path])
        expect(f"deleting a {label} fails and names it",
               _run(lambda r, p=path: _rm(r, p)), [path])
    expect("editing an old record AND re-pinning the envelope still fails",
           _run(lambda r: (_write(r, REC, "typo fix\n"), _write(r, ENV, "re-pin\n"))),
           [REC])

    def rename(r):
        _g(r, "mv", REC, "sim/exp/records/renamed.md")
    expect("renaming a record fails and names the old path",
           _run(rename), [REC])

    def retype(r):
        _rm(r, REC)
        (Path(r) / REC).symlink_to("elsewhere")
    expect("file-type change (file -> symlink) fails and names it",
           _run(retype), [REC])

    def chmod(r):
        (Path(r) / LOG).chmod(0o755)
    expect("mode change of a protected file fails",
           _run(chmod), [LOG])

    expect("push: new record passes",
           _run(lambda r: _write(r, "sim/exp/records/new.md", "n\n"),
                event="push"), clean=True)
    expect("push: edit fails",
           _run(lambda r: _write(r, REC, "x\n"), event="push"), [REC])

    def msg_has(msgs, text):
        return any(text in m for m in msgs)

    m = _run(lambda r: None, event="push", before=ZERO_SHA)
    cases.append(("push with all-zero before fails explicitly",
                  msg_has(m, "no 'before' commit")))
    m = _run(lambda r: None, event="push", before="deadbeef" * 5)
    cases.append(("push with unavailable before fails explicitly",
                  msg_has(m, "not available")))
    m = _run(lambda r: None, event="pull_request", base_ref="origin/nonesuch")
    cases.append(("pull_request with unavailable base ref fails explicitly",
                  msg_has(m, "not available")))
    m = _run(lambda r: None, event="workflow_dispatch")
    cases.append(("manual dispatch without a base fails explicitly",
                  msg_has(m, "manual dispatch")))
    expect("manual dispatch with explicit base compares and passes",
           _run(lambda r: _write(r, "sim/exp/records/new.md", "n\n"),
                event="workflow_dispatch", base="main"), clean=True)
    expect("manual dispatch with explicit base catches an edit",
           _run(lambda r: _write(r, REC, "x\n"), event="workflow_dispatch",
                base="main"), [REC])
    m = _run(lambda r: None, event="merge_group")
    cases.append(("merge_group without a base fails explicitly",
                  msg_has(m, "merge_group")))
    m = _run(lambda r: None, event="merge_group", base="origin/nonesuch")
    cases.append(("merge_group with unavailable base fails explicitly",
                  msg_has(m, "not available")))
    expect("merge_group with explicit base compares and passes",
           _run(lambda r: _write(r, "sim/exp/records/new.md", "n\n"),
                event="merge_group", base="main"), clean=True)
    expect("merge_group with explicit base catches an edit",
           _run(lambda r: _write(r, REC, "x\n"), event="merge_group",
                base="main"), [REC])

    def shallow_unrelated(r):
        _g(r, "checkout", "-q", "--orphan", "other")
        _commit(r, "orphan")
    m = _run(shallow_unrelated, event="pull_request", base_ref="main")
    cases.append(("pull_request with no merge-base fails explicitly",
                  msg_has(m, "no merge-base")))

    # --- waiver manifest (issue #326, DR-011) ---
    DRP = "spec/decision-records/DR-010-x.md"
    DRQ = "spec/decision-records/DR-011-y.md"

    def waiver_fixture(status="**ratified** -- ruled"):
        """Fixture variant: DR committed at base; returns (tmp, repo, base)."""
        tmp, repo, base = _fixture()
        if status is not None:
            _write(repo, DRP, f"# DR\n\n- **Status**: {status}\n")
        _g(repo, "checkout", "-q", "main")
        _commit(repo, "dr at base")
        _g(repo, "checkout", "-q", "feature")
        _g(repo, "merge", "-q", "--ff-only", "main")
        return tmp, repo, resolve_commit(repo, "main")

    def wrun(mutate, manifest=None, **fx):
        tmp, repo, base = waiver_fixture(**fx)
        with tmp:
            if manifest is not None:
                m = manifest(base) if callable(manifest) else manifest
                _write(repo, WAIVER_MANIFEST,
                       m if isinstance(m, str) else json.dumps(m))
            mutate(repo)
            _commit(repo, "change")
            reset()
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                check(repo, "pull_request", base_ref="main")
            out = (list(FAILURES),
                   [x for x in buf.getvalue().splitlines()
                    if x.startswith("gate: ok:")])
            reset()
            return out

    def entry(base, paths=(REC,), rec=DRP):
        return {"waivers": [{"decision_record": rec, "paths": list(paths),
                             "base_sha": base}]}

    def waived_ok(msgs_oks, path):
        msgs, oks = msgs_oks
        return not msgs and any("waived" in o and path in o for o in oks)

    cases.append(("waiver: listed removal with ratified record passes and is "
                  "printed",
                  waived_ok(wrun(lambda r: _rm(r, REC), entry), REC)))
    cases.append(("waiver: empty manifest behaves as today (removal fails)",
                  bool(wrun(lambda r: _rm(r, REC),
                            {"waivers": []})[0])))
    cases.append(("waiver: absent manifest behaves as today (removal fails)",
                  bool(wrun(lambda r: _rm(r, REC))[0])))
    expect("waiver: unlisted removal fails and names it",
           wrun(lambda r: _rm(r, LOG), entry)[0], [LOG])
    expect("waiver: entry citing a proposed record fails",
           wrun(lambda r: _rm(r, REC), entry, status="proposed")[0],
           [REC, "not ratified"])
    expect("waiver: entry citing a record absent at base fails",
           wrun(lambda r: _rm(r, REC),
                lambda b: entry(b, rec=DRQ))[0], [REC, "missing at the base"])

    def self_ratify(r):
        _write(r, DRP, "# DR\n\n- **Status**: ratified\n")
        _rm(r, REC)
    expect("waiver: a PR cannot ratify its own record (status read at base)",
           wrun(self_ratify, entry, status="proposed")[0],
           [REC, "not ratified"])

    def bytes_differ(b):
        return entry("0" * 39 + "1")
    expect("waiver: bytes differing from base_sha fail",
           wrun(lambda r: _rm(r, REC), bytes_differ)[0], [REC, "differ"])
    expect("waiver: a modification of a listed path fails",
           wrun(lambda r: _write(r, REC, "edited\n"), entry)[0],
           [REC, "only removals"])

    def retype_listed(r):
        _rm(r, REC)
        (Path(r) / REC).symlink_to("elsewhere")
    expect("waiver: a type change of a listed path fails",
           wrun(retype_listed, entry)[0], [REC, "only removals"])
    msgs, oks = wrun(lambda r: (_rm(r, REC), _rm(r, LOG)), entry)
    cases.append(("waiver: listed + unlisted removals fail only on the "
                  "unlisted one",
                  len(msgs) == 1 and LOG in msgs[0] and REC not in msgs[0]))
    expect("waiver: malformed manifest JSON fails explicitly",
           wrun(lambda r: _rm(r, REC), "{nope")[0], ["not valid JSON"])
    expect("waiver: manifest without a waivers list fails explicitly",
           wrun(lambda r: _rm(r, REC), {"x": 1})[0], ["waivers"])
    expect("waiver: glob path in an entry fails explicitly",
           wrun(lambda r: _rm(r, REC),
                lambda b: entry(b, paths=("sim/exp/records/*.md",)))[0],
           ["exact protected path"])
    expect("waiver: path with spaces can be waived",
           [] if waived_ok(wrun(lambda r: _rm(r, WS),
                                lambda b: entry(b, paths=(WS,))), WS)
           else ["x"], clean=True)

    return report_cases(cases)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="mode", required=True)
    g = sub.add_parser("gate", help="compare protected sim/ evidence to base")
    g.add_argument("--event", required=True,
                   choices=["pull_request", "push", "workflow_dispatch",
                            "merge_group"])
    g.add_argument("--base-ref", help="PR target ref (merge-base is used)")
    g.add_argument("--before", help="push event's before commit")
    g.add_argument("--base",
                   help="explicit base commit (manual dispatch / merge group)")
    g.add_argument("--head", default="HEAD", help="head commit (default HEAD)")
    g.add_argument("--repo", default=".", help="repository path (default .)")
    return dispatch(parser, sub, argv, run_gate, run_selftest)


if __name__ == "__main__":
    sys.exit(main())
