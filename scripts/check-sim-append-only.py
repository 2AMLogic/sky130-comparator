#!/usr/bin/env python3
"""CI gate: sim/ evidence is append-only against the Git base (issue #138).

    python3 scripts/check-sim-append-only.py gate --event pull_request --base-ref origin/main
    python3 scripts/check-sim-append-only.py gate --event push --before <sha> [--head <sha>]
    python3 scripts/check-sim-append-only.py gate --event workflow_dispatch [--base <sha>]
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
  all-zero --before  (branch creation / first commit) has no base: fails
The checkout must supply history (actions/checkout `fetch-depth: 0`).

To correct a recorded result, do not edit it: mint a NEW record under the
same experiment and cite the old one in its `Supersedes` field (see
sim/README.md, "Summary record format").

Stdlib + git only. Exit codes: 0 pass, 1 failure, 2 usage error.
"""

import argparse
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


def check(repo, event, **kw):
    """Run the comparison; record results via ok()/fail()."""
    try:
        base_sha, head_sha = resolve_base(repo, event, **kw)
    except ValueError as exc:
        fail(str(exc))
        return
    found = violations(repo, base_sha, head_sha)
    for path, status in found:
        fail(f"protected evidence {STATUS_NAMES[status]}: {path}")
    if found:
        print("gate: sim/ evidence is append-only (sim/README.md). Do not "
              "edit, delete or rename committed records, corner logs, "
              "mc-draws or netlist snapshots; add a NEW record under the "
              "same experiment and cite the old one in its `Supersedes` "
              "field. Re-pinning the characterization envelope does not "
              "make such an edit acceptable.")
    else:
        ok(f"no protected sim/ evidence changed ({base_sha[:12]}..{head_sha[:12]})")


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

    def shallow_unrelated(r):
        _g(r, "checkout", "-q", "--orphan", "other")
        _commit(r, "orphan")
    m = _run(shallow_unrelated, event="pull_request", base_ref="main")
    cases.append(("pull_request with no merge-base fails explicitly",
                  msg_has(m, "no merge-base")))

    return report_cases(cases)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="mode", required=True)
    g = sub.add_parser("gate", help="compare protected sim/ evidence to base")
    g.add_argument("--event", required=True,
                   choices=["pull_request", "push", "workflow_dispatch"])
    g.add_argument("--base-ref", help="PR target ref (merge-base is used)")
    g.add_argument("--before", help="push event's before commit")
    g.add_argument("--base", help="explicit base commit (manual dispatch)")
    g.add_argument("--head", default="HEAD", help="head commit (default HEAD)")
    g.add_argument("--repo", default=".", help="repository path (default .)")
    return dispatch(parser, sub, argv, run_gate, run_selftest)


if __name__ == "__main__":
    sys.exit(main())
