#!/usr/bin/env python3
"""Toolchain-pin CI gate (issues #245, #271, #275): neither the workflow's
install lines nor the committed evidence envelopes' recorded producer nor
the restated sky130 PDK pin values can drift from their single sources of
truth.

    python3 scripts/check-toolchain-pin.py gate
    python3 scripts/check-toolchain-pin.py selftest

Two pins, three checked surfaces:

klt / klayout (issue #245): the pin used to be restated as five Python
constants across three modules plus one hand-maintained `pip install` line
per CI job. The constants now live only in `layout/gen_comparator.py`
(`KLT_VERSION` / `KLAYOUT_VERSION`, and the composite `KLT_PIN` derived
from them); `layout/extract_pex.py` and `scripts/layout-envelope.py` import
them. `gate` re-derives the pin from `gen_comparator.py` and fails if ANY
`klayout-tools==` / `klayout==` occurrence in `.github/workflows/
t1-signoff.yml` disagrees with it, or if the pin has vanished from the
workflow entirely.

sky130 PDK (issue #275): `sim/pdk.json` is the named source of truth for
the PDK pin -- its structured keys (`open_pdks_commit`, `ciel_version`) are
authority, and `install_command` is a gate-checked derivative of them --
yet the values were restated by hand in three load-bearing places: the
workflow's three `ciel==` installs and three `ciel enable` hashes (each
`ciel enable` step is even NAMED "(sim/pdk.json)"), `sim/toolchain.json`'s
`open_pdks` (a second structured copy whose own `_comment` says it must
match `sim/pdk.json`, unchecked until now), and
`docs/environment-setup.md`'s version table and install walkthrough.
`gate` fails if ANY `ciel==` or 40-hex-hash occurrence in the workflow or
the docs disagrees with `sim/pdk.json`, if `sim/toolchain.json`'s
`open_pdks` differs from `sim/pdk.json`'s `open_pdks_commit` (the value the
harness grades against and the value every record cites must be ONE value),
or if `install_command` stops containing `ciel=={ciel_version}` and
`{open_pdks_commit}`. When the two JSONs disagree the gate says so FIRST
and skips the per-occurrence hash comparisons -- comparing against a
contested pin is noise.

Committed evidence (issue #271): the same gate also fails if any committed
`evidence/*.json` records a `provenance.klt_version` other than the pin:
`klt signoff --check` compares an envelope's checks and content hashes but
never its recorded producer, so an envelope attributed to a dev build -- or
to a version that does not exist -- passes CI silently, and `evidence/`
being append-only makes the wrong producer permanent once merged. The
envelope scan is glob-driven (no hardcoded item list, same discipline as
the workflow scan) and fail-closed: an envelope with no `provenance` block
or no `klt_version` fails rather than passes silently, and so does an empty
envelope set, because `evidence/` is this repo's product rather than an
optional one.

The scan is deliberately job-count-agnostic -- the files are scanned line
by line with `#`-comment lines skipped, so a job added later is covered
without touching this gate (occurrence counts are reported, never
asserted).

`selftest` is hermetic (stdlib file reads only, no klt, no PDK, no
network): it proves the composite `KLT_PIN` derivation still renders the
string the committed artifacts carry byte for byte, that the scanners
accept matching multi-line texts, and that they reject every drift shape
above -- a partial bump of one line's either pin, each pin vanishing, the
toolchain/pdk authority disagreement, an `install_command` inconsistent
with the structured keys, and the 64-char SHA-256 false-positive hazard in
`docs/environment-setup.md` (an unanchored `[0-9a-f]{40}` matches the
first 40 of its 64 chars; the word-bounded pattern below does not) -- and
that the envelope check rejects its drift shapes too: the fabricated
producer `99.99.99.dev666+gdeadbeefcafe`, a real dev build, a `.dev`
suffix on the pin itself, a missing `klt_version`, a missing `provenance`
block, an unparseable or non-object envelope, and an empty envelope set.

Same `_gate_common` convention as the other gates in this directory, and
the same cross-directory import precedent as
`check-layout-device-count.py` importing its counter from
`layout/gen_comparator.py`.

Stdlib only, no virtualenv required.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "layout"))

from _gate_common import (FAILURES, dispatch, fail, load_json,  # noqa: E402
                          ok, report_cases, reset)
from gen_comparator import KLAYOUT_VERSION, KLT_PIN, KLT_VERSION  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = Path(".github/workflows/t1-signoff.yml")
EVIDENCE_DIR = Path("evidence")
#: The committed artifact whose `tool.klt_pin` the composite is asserted
#: against byte for byte (re-asserted in CI by check-layout-device-count.py).
KLT_PIN_ARTIFACT = Path("layout/extract-device-count.json")
#: Authority for the sky130 PDK pin (issue #275): its structured keys are
#: the source of truth; everything else is a checked restatement.
PDK_JSON = Path("sim/pdk.json")
#: The harness-graded copy of the open_pdks hash (toolchain.check_env()
#: reads it); must equal sim/pdk.json's open_pdks_commit -- its own
#: `_comment` asserts that in prose, this gate asserts it mechanically.
TOOLCHAIN_JSON = Path("sim/toolchain.json")
#: Mirrors the PDK pin in prose (version table + install walkthrough).
DOCS = Path("docs/environment-setup.md")

TOOLS_RE = re.compile(r"klayout-tools==([^\s\"'`]+)")
ENGINE_RE = re.compile(r"\bklayout==([^\s\"'`]+)")
CIEL_RE = re.compile(r"\bciel==([^\s\"'`]+)")
#: Word-bounded on purpose (issue #275): an UNanchored `[0-9a-f]{40}`
#: false-positives on the first 40 chars of the 64-char ngspice-tarball
#: SHA-256 recorded in docs/environment-setup.md (measured: 2 distinct
#: matches unanchored, 1 anchored). Every pattern must expose the captured
#: value as group 1 -- scan_text() reads group(1) uniformly.
OPEN_PDKS_RE = re.compile(r"\b([0-9a-f]{40})\b")

#: Every pattern scan_text() looks for, per scanned file. The patterns
#: cannot cross-match: `klayout-tools==` does not contain `klayout==` (the
#: `klayout` there is followed by `-tools==`), and `ciel==` matches
#: different text than the bare 40-hex hash.
PATTERNS = {
    "klayout-tools": TOOLS_RE,
    "klayout": ENGINE_RE,
    "ciel": CIEL_RE,
    "open_pdks": OPEN_PDKS_RE,
}


def scan_text(text: str) -> dict[str, list[tuple[int, str]]]:
    """Every occurrence of each pattern, as {name: [(lineno, value), ...]}.

    Line-by-line on purpose (issues #245, #275): no job parsing, no
    occurrence-count assumption, so jobs added later are covered for free.
    `#`-comment lines are skipped: comment prose may mention a pin without
    pinning it.
    """
    found: dict[str, list[tuple[int, str]]] = {name: [] for name in PATTERNS}
    for lineno, line in enumerate(text.splitlines(), start=1):
        if line.lstrip().startswith("#"):
            continue  # comment prose may mention the pin without pinning it
        for name, rex in PATTERNS.items():
            found[name].extend((lineno, m.group(1)) for m in rex.finditer(line))
    return found


def check_workflow(text: str, name: str) -> None:
    """The klt/klayout half (issue #245): workflow vs gen_comparator.py."""
    found = scan_text(text)
    tools, engine = found["klayout-tools"], found["klayout"]
    if not tools:
        fail(f"{name}: no `klayout-tools==` install line found -- the klt pin "
             "has vanished from CI")
    if not engine:
        fail(f"{name}: no `klayout==` install line found -- the klayout engine "
             "pin has vanished from CI")
    for lineno, version in tools:
        if version != KLT_VERSION:
            fail(f"{name}:{lineno}: installs klayout-tools=={version}, but the "
                 f"single source of truth (layout/gen_comparator.py) pins "
                 f"klayout-tools=={KLT_VERSION}")
    for lineno, version in engine:
        if version != KLAYOUT_VERSION:
            fail(f"{name}:{lineno}: installs klayout=={version}, but the "
                 f"single source of truth (layout/gen_comparator.py) pins "
                 f"klayout=={KLAYOUT_VERSION}")
    if not FAILURES:
        ok(f"{name}: all {len(tools)} klayout-tools== and {len(engine)} "
           f"klayout== install line(s) match the pin "
           f"{KLT_VERSION} / {KLAYOUT_VERSION}")


def check_pdk_authority(pdk: dict) -> tuple[str | None, str | None]:
    """sim/pdk.json's structured keys are authority; validate and return them.

    Returns (ciel_version, open_pdks_commit), with a None entry (and a
    failure already recorded) for any missing/empty key -- a clear message,
    never a KeyError traceback.
    """
    ciel_version = pdk.get("ciel_version")
    commit = pdk.get("open_pdks_commit")
    if not isinstance(ciel_version, str) or not ciel_version:
        fail(f"{PDK_JSON}: carries no usable ciel_version key -- the "
             "structured keys (open_pdks_commit, ciel_version) are authority; "
             "add ciel_version set to the version install_command's "
             "`ciel==` installs")
        ciel_version = None
    if not isinstance(commit, str) or not commit:
        fail(f"{PDK_JSON}: carries no usable open_pdks_commit key -- the "
             "structured keys are authority; every ciel enable and doc "
             "mirror is checked against it")
        commit = None
    return ciel_version, commit


def check_authority(toolchain: dict, commit: str | None) -> bool:
    """The sim/toolchain.json vs sim/pdk.json open_pdks invariant.

    Returns True when the authority is CONTESTED (the two files disagree):
    the caller then skips the per-occurrence hash comparisons -- failing
    four more times against a pin that is itself questioned is noise; the
    disagreement failure printed here is the one that matters.
    """
    if commit is None:
        return False  # authority itself unusable; already failed above
    tc = toolchain.get("open_pdks")
    if tc == commit:
        return False
    if tc is None:
        fail(f"{TOOLCHAIN_JSON} disables the open_pdks check (null), but the "
             f"single source of truth ({PDK_JSON}) pins open_pdks_commit "
             f"{commit} -- the harness would grade against no hash while "
             f"every record cites one; restore the hash (its own _comment "
             "says the two must match)")
    else:
        fail(f"{TOOLCHAIN_JSON} pins open_pdks {tc}, but the single source "
             f"of truth ({PDK_JSON}) pins open_pdks_commit {commit} -- the "
             "value the harness grades against and the value every record "
             "cites disagree; unify the two files first (hash comparisons "
             "below are suppressed until they agree)")
    return True


def check_install_command(pdk: dict, ciel_version: str | None,
                          commit: str | None) -> None:
    """install_command is a derivative: must contain both structured values.

    One regex-equivalent remains in the repo's PDK pin handling, but it is
    a containment check AGAINST authority, never a parse FOR authority --
    a hand-edited install_command fails here instead of silently becoming
    a fourth pin.
    """
    cmd = pdk.get("install_command")
    if not isinstance(cmd, str) or not cmd:
        fail(f"{PDK_JSON}: carries no usable install_command -- "
             "sim/harness/toolchain.py prints it verbatim as the operator's "
             "install instruction")
        return
    if ciel_version is not None and f"ciel=={ciel_version}" not in cmd:
        fail(f"{PDK_JSON}'s install_command does not install "
             f"ciel=={ciel_version} -- install_command is a gate-checked "
             "derivative of the structured keys; update it to match "
             "ciel_version")
    if commit is not None and commit not in cmd:
        fail(f"{PDK_JSON}'s install_command does not contain its own "
             f"open_pdks_commit {commit} -- install_command is a "
             "gate-checked derivative of the structured keys; update it to "
             "match")


def check_pdk_text(text: str, name: str, ciel_version: str | None,
                   commit: str | None, hash_contested: bool = False,
                   require_present: bool = True) -> dict[str, list[tuple[int, str]]]:
    """ciel== / open_pdks-hash occurrences in one file vs sim/pdk.json.

    `require_present` is True for the workflow (a vanished pin there means
    CI installs or enables an unpinned PDK) and False for the docs (this
    gate checks disagreement, not doc layout). `hash_contested` (the
    check_authority disagreement) suppresses the per-occurrence hash
    comparisons -- the authority failure already fails the gate and says
    so. Returns the scan so the caller can report counts.
    """
    found = scan_text(text)
    ciel, hashes = found["ciel"], found["open_pdks"]
    if require_present:
        if not ciel:
            fail(f"{name}: no `ciel==` install line found -- the ciel pin "
                 "has vanished from CI")
        if not hashes:
            fail(f"{name}: no 40-hex open_pdks hash found -- the PDK pin "
                 "has vanished from CI")
    if ciel_version is not None:
        for lineno, version in ciel:
            if version != ciel_version:
                fail(f"{name}:{lineno}: installs ciel=={version}, but the "
                     f"single source of truth ({PDK_JSON}) pins "
                     f"ciel_version {ciel_version}")
    if commit is not None and not hash_contested:
        for lineno, hash_ in hashes:
            if hash_ != commit:
                fail(f"{name}:{lineno}: enables open_pdks {hash_}, but the "
                     f"single source of truth ({PDK_JSON}) pins "
                     f"open_pdks_commit {commit}")
    return found


def check_evidence_provenance(envelopes: list[tuple[str, object]], name: str) -> None:
    """Assert every committed evidence envelope names the pinned producer.

    Each envelope is a `(path, doc)` pair with `doc` either the parsed JSON
    object or the `ValueError` the parse produced, so the selftest can drive
    the whole matrix -- malformed and non-object files included -- without
    touching the filesystem (the same separation that makes
    `scan_text`/`check_workflow` selftestable). Fail-closed on every
    degenerate shape (issue #271): a missing producer is not a passing
    producer, and neither is an empty envelope set -- `evidence/` is the
    repo's product, so its absence is a gate failure, not a vacuous pass.
    """
    if not envelopes:
        fail(f"{name}: no committed envelopes found -- an empty evidence "
             "tree is not a passing one")
        return
    for path, doc in envelopes:
        if isinstance(doc, ValueError):
            fail(f"{path}: unreadable envelope, cannot check its producer "
                 f"({doc})")
            continue
        if not isinstance(doc, dict):
            fail(f"{path}: envelope is not a JSON object, cannot check its "
                 f"producer")
            continue
        provenance = doc.get("provenance")
        if not isinstance(provenance, dict):
            fail(f"{path}: records no provenance block -- a committed "
                 "envelope must name its producer")
            continue
        recorded = provenance.get("klt_version")
        if not isinstance(recorded, str) or not recorded:
            fail(f"{path}: provenance records no klt_version -- a missing "
                 "producer is not a passing producer")
            continue
        if recorded != KLT_VERSION:
            fail(f"{path}: records provenance.klt_version {recorded}, but "
                 f"the single source of truth (layout/gen_comparator.py) "
                 f"pins klayout-tools=={KLT_VERSION}")
    if not FAILURES:
        ok(f"{name}: all {len(envelopes)} envelope(s) record "
           f"provenance.klt_version {KLT_VERSION}")


def run_gate(args: argparse.Namespace) -> int:
    repo = Path(args.repo_root).resolve()
    # Authority first (issue #275): both structured copies, and the
    # cross-file invariant, before any per-occurrence comparison.
    pdk = load_json(repo / PDK_JSON, PDK_JSON.as_posix())
    toolchain = load_json(repo / TOOLCHAIN_JSON, TOOLCHAIN_JSON.as_posix())
    ciel_version, commit = check_pdk_authority(pdk)
    check_install_command(pdk, ciel_version, commit)
    hash_contested = check_authority(toolchain, commit)

    path = repo / WORKFLOW
    try:
        wf_text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        fail(f"workflow not found: {path}")
        return 1
    check_workflow(wf_text, str(WORKFLOW))
    wf_found = check_pdk_text(wf_text, str(WORKFLOW), ciel_version, commit,
                              hash_contested, require_present=True)

    # (path, doc) pairs: doc is the parsed envelope, or the ValueError the
    # parse produced so the pure check reports it as a gate failure instead
    # of a traceback. Glob, not a list: an envelope committed later is
    # covered without editing this gate.
    envelopes: list[tuple[str, object]] = []
    for env_path in sorted((repo / EVIDENCE_DIR).glob("*.json")):
        try:
            doc = json.loads(env_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            doc = ValueError(f"{type(exc).__name__}: {exc}")
        envelopes.append((str(env_path.relative_to(repo)), doc))
    check_evidence_provenance(envelopes, f"{EVIDENCE_DIR}/*.json")

    try:
        docs_text = (repo / DOCS).read_text(encoding="utf-8")
    except FileNotFoundError:
        fail(f"docs not found: {repo / DOCS}")
        return 1
    docs_found = check_pdk_text(docs_text, str(DOCS), ciel_version, commit,
                                hash_contested, require_present=False)

    if not FAILURES:
        authority = f"ciel_version {ciel_version}"
        if commit is not None:
            authority += f", open_pdks_commit {commit[:12]}..."
        ok(f"all {len(wf_found['ciel'])} ciel== and "
           f"{len(wf_found['open_pdks'])} open_pdks-hash workflow "
           f"occurrence(s) plus {len(docs_found['ciel'])} / "
           f"{len(docs_found['open_pdks'])} docs occurrence(s) match "
           f"{PDK_JSON} ({authority}); {TOOLCHAIN_JSON} agrees")
    if FAILURES:
        print(f"gate: {len(FAILURES)} failure(s) -- see above")
        return 1
    return 0


def run_selftest(args: argparse.Namespace) -> int:
    repo = Path(getattr(args, "repo_root", str(REPO_ROOT))).resolve()
    case_results = []

    # Step 2 of the issue: the composite must render, byte for byte, the
    # string the committed artifacts carry -- the derivation moving a single
    # character would silently re-brand committed provenance.
    try:
        doc = json.loads((repo / KLT_PIN_ARTIFACT).read_text(encoding="utf-8"))
        committed_pin = doc["tool"]["klt_pin"]
        case_results.append((
            f"derived KLT_PIN renders {KLT_PIN_ARTIFACT}'s committed "
            "tool.klt_pin byte for byte",
            KLT_PIN == committed_pin,
        ))
    except (FileNotFoundError, KeyError, json.JSONDecodeError) as exc:
        case_results.append((f"reading {KLT_PIN_ARTIFACT} for the "
                             f"byte-for-byte assertion ({exc})", False))

    def check(name, expect_fail, text):
        # reset() clears the shared tally in place -- rebinding FAILURES here
        # would detach it from the list fail() appends to (_gate_common).
        reset()
        check_workflow(text, "fx-workflow")
        case_results.append((name, (len(FAILURES) > 0) == expect_fail))

    good_line = (f'        run: python -m pip install '
                 f'"klayout-tools=={KLT_VERSION}" '
                 f'"klayout=={KLAYOUT_VERSION}"\n')
    # Multi-line on purpose: the scanner must not care how many jobs install.
    check("accepts a workflow with three matching install lines",
          False, "# jobs a, b, c\n" + good_line * 3)
    check("accepts an unquoted install line matching the pin",
          False, f"run: pip install klayout-tools=={KLT_VERSION} "
                 f"klayout=={KLAYOUT_VERSION}\n")
    bumped_tools = ('        run: python -m pip install "klayout-tools==9.9.9" '
                    f'"klayout=={KLAYOUT_VERSION}"\n')
    check("rejects one bumped klayout-tools== line among matching ones",
          True, good_line + bumped_tools + good_line)
    bumped_engine = (f'        run: python -m pip install '
                     f'"klayout-tools=={KLT_VERSION}" "klayout==0.0.1"\n')
    check("rejects one bumped klayout== line among matching ones",
          True, good_line + good_line + bumped_engine)
    check("rejects a workflow where the klt pin has vanished",
          True, f'        run: python -m pip install "klayout=={KLAYOUT_VERSION}"\n')
    check("rejects a workflow where the klayout engine pin has vanished",
          True, f'        run: python -m pip install "klayout-tools=={KLT_VERSION}"\n')
    check("rejects a workflow with no install lines at all",
          True, "# nothing pinned here\n")
    check("ignores comment prose that mentions a different pin",
          False, "# bump the klayout-tools==9.9.9 line below\n" + good_line)
    check("still scans install lines when comments are present",
          True, "# prose\n" + good_line + "# more prose klayout==0.0.1\n"
                + bumped_tools)

    # ---- PDK half (issue #275) ------------------------------------------
    # Fixture authority comes from the committed sim/pdk.json (stdlib file
    # read, still hermetic): the synthetic texts below then exercise the
    # scanner against the repo's real pin shapes.
    pdk_doc = None
    try:
        pdk_doc = load_json(repo / PDK_JSON, PDK_JSON.as_posix())
    except ValueError as exc:
        case_results.append(
            (f"reading {PDK_JSON} for the pdk-pin fixture authority ({exc})",
             False))

    if pdk_doc is not None:
        ciel, commit = pdk_doc.get("ciel_version"), pdk_doc.get("open_pdks_commit")

        def check_pdk(name, expect_fail, text, *, cv=ciel, cm=commit,
                      contested=False, require_present=True):
            reset()
            check_pdk_text(text, "fx-pdk", cv, cm,
                           hash_contested=contested,
                           require_present=require_present)
            case_results.append((name, (len(FAILURES) > 0) == expect_fail))

        if not isinstance(ciel, str) or not isinstance(commit, str):
            case_results.append(
                (f"committed {PDK_JSON} carries usable ciel_version and "
                 "open_pdks_commit keys", False))
        else:
            case_results.append(
                (f"committed {PDK_JSON} carries usable ciel_version and "
                 "open_pdks_commit keys", True))
            good_pdk = (f"        run: python -m pip install ciel=={ciel}\n"
                        f"        run: ciel enable --pdk-family sky130 -l "
                        f"sky130_fd_pr {commit}\n")
            other_hash = "d" * 40

            check_pdk("accepts a workflow with three matching ciel== and "
                      "hash lines", False, "# jobs\n" + good_pdk * 3)
            check_pdk("accepts a single-job workflow (job-count-agnostic)",
                      False, good_pdk)
            bumped_ciel = (f"        run: python -m pip install ciel==9.9.9\n"
                           f"        run: ciel enable --pdk-family sky130 -l "
                           f"sky130_fd_pr {commit}\n")
            check_pdk("rejects one bumped ciel== line among matching ones",
                      True, good_pdk + bumped_ciel + good_pdk)
            bumped_hash = (f"        run: python -m pip install ciel=={ciel}\n"
                           f"        run: ciel enable --pdk-family sky130 -l "
                           f"sky130_fd_pr {other_hash}\n")
            check_pdk("rejects one bumped open_pdks hash line among matching "
                      "ones", True, good_pdk + bumped_hash)
            check_pdk("rejects a workflow where the ciel== pin has vanished",
                      True,
                      f"        run: ciel enable --pdk-family sky130 -l "
                      f"sky130_fd_pr {commit}\n")
            check_pdk("rejects a workflow where the open_pdks hash has "
                      "vanished",
                      True, f"        run: python -m pip install ciel=={ciel}\n")
            check_pdk("rejects a workflow with neither PDK pin",
                      True, "# nothing pinned here\n")
            check_pdk("ignores comment prose mentioning different PDK pins",
                      False,
                      f"# bump the ciel==9.9.9 line; old hash was {other_hash}\n"
                      + good_pdk)
            # The measured false-positive hazard: docs carry a 64-char
            # SHA-256 (the ngspice tarball). An unanchored [0-9a-f]{40}
            # matches its first 40 chars; the word-bounded pattern must not.
            sha256_line = ("SHA-256 "
                           "a0d1699af1940b06649276dcd6ff5a566c8c0cad01b2f7b5"
                           "e99dedbb4d64c19b, verified before extraction\n")
            check_pdk("does not read a 64-char SHA-256 as an open_pdks hash "
                      "(docs false-positive control)",
                      False, sha256_line + f"pip install ciel=={ciel}\n"
                      f"ciel enable --pdk-family sky130 -l sky130_fd_pr "
                      f"{commit}\n", require_present=False)
            check_pdk("still rejects a wrong 40-hex hash in docs-like text "
                      "beside the SHA-256",
                      True, sha256_line
                      + f"ciel enable --pdk-family sky130 -l sky130_fd_pr "
                        f"{other_hash}\n", require_present=False)

            # Authority semantics, in isolation.
            reset()
            contested = check_authority({"open_pdks": commit}, commit)
            case_results.append(
                ("check_authority: agrees when sim/toolchain.json matches "
                 "sim/pdk.json", not contested and len(FAILURES) == 0))
            reset()
            contested = check_authority({"open_pdks": other_hash}, commit)
            case_results.append(
                ("check_authority: contests (and fails) a "
                 "sim/toolchain.json / sim/pdk.json disagreement",
                 contested and len(FAILURES) > 0))
            reset()
            contested = check_authority({"open_pdks": None}, commit)
            case_results.append(
                ("check_authority: contests (and fails) a null "
                 "sim/toolchain.json open_pdks", contested
                 and len(FAILURES) > 0))
            # While contested, per-occurrence hash noise is suppressed.
            check_pdk("suppresses per-occurrence hash failures while the "
                      "authority is contested",
                      False, bumped_hash, cm=commit, contested=True)

            # install_command is a gate-checked derivative.
            reset()
            check_install_command(pdk_doc, ciel, commit)
            case_results.append(
                (f"committed {PDK_JSON}'s install_command contains both "
                 "structured values", len(FAILURES) == 0))
            for field, broken, needle in (
                    ("ciel_version", f"pip install ciel==9.9.9 && ciel enable "
                                     f"--pdk-family sky130 -l sky130_fd_pr "
                                     f"{commit}", f"ciel=={ciel}"),
                    ("open_pdks_commit", f"pip install ciel=={ciel} && ciel "
                                         f"enable --pdk-family sky130 -l "
                                         f"sky130_fd_pr {other_hash}", commit)):
                reset()
                check_install_command({"install_command": broken}, ciel,
                                      commit)
                case_results.append(
                    (f"rejects an install_command inconsistent with "
                     f"{field}", len(FAILURES) > 0))
            reset()
            check_install_command({}, ciel, commit)
            case_results.append(
                ("rejects a missing install_command with a clear message, "
                 "not a traceback", len(FAILURES) > 0))

            # Missing ciel_version key: clear failure, never a KeyError.
            reset()
            got_ciel, got_commit = check_pdk_authority(
                {"open_pdks_commit": commit})
            case_results.append(
                ("check_pdk_authority: a missing ciel_version key fails "
                 "with a clear message (no KeyError)",
                 got_ciel is None and got_commit == commit
                 and len(FAILURES) > 0))
            reset()
            got_ciel, got_commit = check_pdk_authority({})
            case_results.append(
                ("check_pdk_authority: both keys missing fails cleanly",
                 got_ciel is None and got_commit is None
                 and len(FAILURES) > 0))

    # ---- envelope provenance half (issue #271) --------------------------
    def check_env(name, expect_fail, envelopes):
        # Same reset() contract as `check` above: the tally is shared by
        # identity with _gate_common, clearing must stay in place.
        reset()
        check_evidence_provenance(envelopes, "fx-evidence")
        case_results.append((name, (len(FAILURES) > 0) == expect_fail))

    def good_env(item):
        # Built from the imported pin, never a literal in this file.
        return (f"evidence/item{item}.json",
                {"provenance": {"klt_version": KLT_VERSION,
                                "klayout_version": KLAYOUT_VERSION}})

    check_env("accepts four envelopes all recording the pin", False,
              [good_env(n) for n in (1, 2, 9, 10)])
    check_env("rejects the fabricated producer 99.99.99.dev666+gdeadbeefcafe "
              "among matching envelopes", True,
              [good_env(1), good_env(2), good_env(9),
               ("evidence/item10.json",
                {"provenance": {"klt_version":
                                "99.99.99.dev666+gdeadbeefcafe"}})])
    check_env("rejects the real dev build 0.9.3.dev3+gd5d57daf9a14 "
              "(the PR #256 shape)", True,
              [good_env(1),
               ("evidence/item10.json",
                {"provenance": {"klt_version":
                                "0.9.3.dev3+gd5d57daf9a14"}})])
    check_env(f"rejects a dev suffix on the pin itself "
              f"({KLT_VERSION}.dev1+gdeadbeef)", True,
              [good_env(1),
               ("evidence/item2.json",
                {"provenance": {"klt_version":
                                f"{KLT_VERSION}.dev1+gdeadbeef"}})])
    check_env("rejects an envelope whose provenance lacks klt_version", True,
              [good_env(1),
               ("evidence/item2.json",
                {"provenance": {"klayout_version": KLAYOUT_VERSION}})])
    check_env("rejects an envelope with no provenance block at all", True,
              [good_env(1), ("evidence/junk.json", {"checks": []})])
    check_env("rejects an unparseable envelope with a reported error", True,
              [good_env(1),
               ("evidence/bad.json",
                ValueError("JSONDecodeError: Expecting value"))])
    check_env("rejects a non-object envelope (a JSON array)", True,
              [good_env(1), ("evidence/list.json", [1, 2])])
    check_env("rejects an empty envelope set -- evidence/ must not be empty",
              True, [])

    return report_cases(case_results)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Toolchain-pin CI gate: the t1-signoff workflow's "
        "klayout-tools==/klayout== install lines vs the pin's single source "
        "of truth in layout/gen_comparator.py (issue #245), the committed "
        "evidence/*.json envelopes' provenance.klt_version vs the same pin "
        "(issue #271), and the sky130 PDK restatements (workflow "
        "ciel==/open_pdks hash, sim/toolchain.json, "
        "docs/environment-setup.md) vs sim/pdk.json (issue #275)"
    )
    sub = parser.add_subparsers(dest="mode", required=True)

    p_gate = sub.add_parser(
        "gate", help="fail if any workflow/docs pin restatement or "
        "committed evidence envelope producer disagrees with its "
        "single source of truth"
    )
    p_gate.add_argument("--repo-root", default=str(REPO_ROOT))

    return dispatch(parser, sub, argv, run_gate, run_selftest)


if __name__ == "__main__":
    raise SystemExit(main())
