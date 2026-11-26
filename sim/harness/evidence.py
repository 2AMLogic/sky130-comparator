"""Evidence-record helpers shared by the PVT corner runner and the Monte
Carlo runner -- see sim/README.md for the append-only convention this
implements: every record pins PDK version, ngspice version, the DUT
netlist's SHA-256, the repo commit + dirty flag, and (for MC records) the
seed + sample count. A re-run never edits a prior record; it mints a new
<record-id> and, if it corrects or replaces a prior one, names it via
"Supersedes".

Ported (issue #8) from 2AMLogic/sky130-sar-adc's sim/harness/evidence.py
(commit b80c144efbf467a586f728726cabb25c1eb5a1f2) -- unchanged logic.
`run_klt_yield()` is carried over for future use (this repo has no
yield-reporting caller yet, per CLAUDE.md's "no claim without a
testbench" -- it becomes live once a statistical spec row and a
klt-yield-consuming experiment driver both exist here).
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


@dataclass
class GitInfo:
    commit: str
    branch: str
    dirty: bool


class GitProvenanceError(RuntimeError):
    """git_info() could not establish honest provenance, so no record may
    be stamped (issue #358's fail-closed contract: a missing or synthetic
    identity is an error, never a placeholder commit)."""


# The `branch` value recorded for the repo-script batch route (issue #127's
# supported execution route for sim/comparator-decision). A job tree is
# `git archive` of exactly RS_SOURCE_COMMIT -- there is no branch there, and
# the harness's synthetic local HEAD (RS_SYNTHETIC_HEAD=1) is not the source
# commit -- so the record states the route by name instead of inventing a
# branch, and `dirty` is False because an archive of one commit cannot
# differ from it.
BATCH_ROUTE_BRANCH = "repo-script-archive"

# The batch route's provenance variables (infra/aws/repo-script-job-run.sh
# exports them to the job script: the submitted commit or empty, and 1 when
# the job tree's git HEAD is the synthetic local commit).
ENV_SOURCE_COMMIT = "RS_SOURCE_COMMIT"
ENV_SYNTHETIC_HEAD = "RS_SYNTHETIC_HEAD"

# A full commit ID: exactly 40 lowercase ASCII hexadecimal characters
# (issue #365). The batch route's job tree is a `git archive` of one
# commit, so the objects needed to expand an abbreviation are typically
# absent there -- the variable must carry the FULL ID.
_SOURCE_COMMIT_RE = re.compile(r"[0-9a-f]{40}")


def _env_get(name: str, env: dict[str, str] | None = None) -> str:
    return (os.environ if env is None else env).get(name, "")


def _batch_source_commit(env: dict[str, str] | None = None) -> str | None:
    """RS_SOURCE_COMMIT validated as a full commit ID, or None when
    unset/empty (issue #365).

    The RAW value is checked once, before any trimming or slicing: only an
    unset variable or the empty string takes the missing-value path
    (#363's checkout / synthetic-HEAD / fail-closed behaviour). Every other
    value must be exactly 40 lowercase hex characters -- a `git archive`
    job tree lacks the Git objects to expand a short sha, so an
    abbreviation, a symbolic ref, uppercase hex, or any padded/whitespace
    value is refused rather than stamped. This matters doubly because the
    record ID slices this value into artifact paths, so what is stamped
    must be the exact commit."""
    value = _env_get(ENV_SOURCE_COMMIT, env)
    if value == "":
        return None
    if _SOURCE_COMMIT_RE.fullmatch(value) is None:
        raise GitProvenanceError(
            f"{ENV_SOURCE_COMMIT}={value!r} is not a full commit ID "
            "(40 lowercase hex characters); refusing to stamp it onto an "
            "evidence record (supply the full 40-character commit on the "
            "batch route, or unset the variable to use a checkout)"
        )
    return value


def git_info(repo_root: Path | None = None, env: dict[str, str] | None = None) -> GitInfo:
    """The provenance triple every evidence record stamps.

    Three cases, in precedence order (issue #358):

    1. **Batch route** -- ``RS_SOURCE_COMMIT`` set: the commit comes from
       the variable, never from ``git rev-parse`` in the job tree. A
       repo-script job runs from a ``git archive`` of one commit; the
       harness may also stage a synthetic local HEAD so path-resolving
       tools work (``RS_SYNTHETIC_HEAD=1``), and that HEAD is NOT the
       source commit. The variable wins over both. Its value must be a
       full 40-character lowercase hex commit ID (see
       ``_batch_source_commit``): a malformed nonempty value raises
       ``GitProvenanceError`` here rather than being stamped -- including
       when a usable local HEAD exists, since the variable, not the tree,
       is the provenance source on this route. ``branch`` is the fixed
       ``BATCH_ROUTE_BRANCH`` marker naming the route (an archive has no
       branch to report), and ``dirty`` is False because the tree is an
       archive of exactly that commit.
    2. **Job tree without a source commit** -- ``RS_SYNTHETIC_HEAD`` set
       but ``RS_SOURCE_COMMIT`` empty: fails closed. The only git identity
       available is the synthetic one, and stamping it would misattribute
       the record.
    3. **Ordinary checkout** -- neither variable set: the pre-existing
       ``git -C <repo root>`` calls, behaviour unchanged. A missing or
       unusable git tree here also fails closed with a clear message; no
       placeholder commit is ever returned.

    ``repo_root``/``env`` are test seams (defaults: this repo's root and the
    process environment); callers pass nothing.
    """
    root = REPO_ROOT if repo_root is None else repo_root

    source = _batch_source_commit(env)
    if source is not None:
        return GitInfo(commit=source, branch=BATCH_ROUTE_BRANCH, dirty=False)
    if _env_get(ENV_SYNTHETIC_HEAD, env).strip():
        raise GitProvenanceError(
            f"{ENV_SYNTHETIC_HEAD} is set but {ENV_SOURCE_COMMIT} is empty: the "
            "job tree's git HEAD is synthetic (not the source commit) and no "
            "submitted commit is known; refusing to stamp provenance"
        )

    def _run(*args: str) -> str:
        return subprocess.run(
            ["git", "-C", str(root), *args],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    try:
        commit = _run("rev-parse", "HEAD")
        branch = _run("rev-parse", "--abbrev-ref", "HEAD")
        dirty = _run("status", "--porcelain") != ""
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        raise GitProvenanceError(
            f"no usable git tree at {root} and {ENV_SOURCE_COMMIT} is unset; "
            "refusing to stamp a placeholder commit onto an evidence record "
            "(set RS_SOURCE_COMMIT on the batch route, or run from a checkout)"
        ) from exc
    return GitInfo(commit=commit, branch=branch, dirty=dirty)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_text(path.read_text())


def _utcnow() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


def _short_sha(env: dict[str, str] | None = None) -> str:
    """The record-ID commit suffix, from the SAME source git_info() uses
    (issue #358): RS_SOURCE_COMMIT's first 7 hex chars on the batch route
    (never the job tree's synthetic HEAD), and "nogit" whenever no honest
    commit is available -- including the synthetic-HEAD-without-source-
    commit case, which git_info() treats as fail-closed. Issue #365: the
    value is validated by the shared ``_batch_source_commit()`` helper, so
    a malformed nonempty RS_SOURCE_COMMIT raises here too instead of
    leaking into record-ID paths."""
    source = _batch_source_commit(env)
    if source is not None:
        return source[:7]
    if _env_get(ENV_SYNTHETIC_HEAD, env).strip():
        return "nogit"
    try:
        return subprocess.run(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "--short", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "nogit"


def new_record_id() -> str:
    """<YYYYMMDD>-<HHMMSS>-<short-git-sha> -- gf180-sar-adc's sim/README.md
    <record-id> scheme, unchanged (see sim/README.md "Provenance").

    This only *proposes* an ID; it reserves nothing. Writers must claim it
    with reserve_record() before writing any artifact."""
    return f"{_utcnow().strftime('%Y%m%d-%H%M%S')}-{_short_sha()}"


def _next_record_id(record_id: str) -> str:
    """The next valid ID: same shape, timestamp advanced one second."""
    date, time, rest = record_id.split("-", 2)
    ts = _dt.datetime.strptime(f"{date}-{time}", "%Y%m%d-%H%M%S") + _dt.timedelta(seconds=1)
    return f"{ts.strftime('%Y%m%d-%H%M%S')}-{rest}"


RESERVATION_MARKER = "<!-- evidence-reservation: incomplete run, record not yet published -->"
MAX_RESERVE_ATTEMPTS = 120


class RecordCollisionError(RuntimeError):
    """No free record-id namespace could be reserved."""


@dataclass
class Reservation:
    record_id: str
    record_path: Path
    log_dirs: dict[str, Path]


def write_new_text(path: Path, text: str) -> None:
    """Exclusive-create write: raises FileExistsError rather than ever
    truncating existing evidence."""
    with open(path, "x") as f:
        f.write(text)


def reserve_record(
    experiment_dir: Path,
    log_subdirs: tuple[str, ...] = (),
    record_id: str | None = None,
) -> Reservation:
    """Atomically claim a record-id namespace under <experiment_dir>.

    The claim is an O_EXCL-created records/<id>.md stub (so concurrent
    processes cannot both own an ID), after which the netlist snapshot path
    and every <experiment_dir>/<subdir>/<id>/ log directory must be unused;
    log directories are created with a non-idempotent mkdir. If the ID is
    taken or its namespace is already populated (even partially), the next
    valid ID (timestamp + 1 s, same format) is tried, up to
    MAX_RESERVE_ATTEMPTS. Existing files are never modified; a stub left by
    a crashed run keeps its ID reserved and is identifiable by
    RESERVATION_MARKER."""
    records_dir = experiment_dir / "records"
    records_dir.mkdir(parents=True, exist_ok=True)
    candidate = record_id or new_record_id()
    first = candidate
    for _ in range(MAX_RESERVE_ATTEMPTS):
        record_path = records_dir / f"{candidate}.md"
        try:
            write_new_text(record_path, f"{RESERVATION_MARKER}\n")
        except FileExistsError:
            candidate = _next_record_id(candidate)
            continue
        snapshot = experiment_dir / "netlist-snapshots" / f"{candidate}.spice"
        dirs = {sub: experiment_dir / sub / candidate for sub in log_subdirs}
        made: list[Path] = []
        try:
            if snapshot.exists():
                raise FileExistsError(snapshot)
            for d in dirs.values():
                d.parent.mkdir(parents=True, exist_ok=True)
                d.mkdir()  # exclusive: FileExistsError if populated
                made.append(d)
        except FileExistsError:
            # Namespace partially used by someone else: back out only what
            # this attempt created (empty dirs + our own stub).
            for d in made:
                d.rmdir()
            record_path.unlink()
            candidate = _next_record_id(candidate)
            continue
        return Reservation(candidate, record_path, dirs)
    raise RecordCollisionError(
        f"could not reserve a free record id under {experiment_dir} after "
        f"{MAX_RESERVE_ATTEMPTS} attempts starting from {first}; "
        "existing evidence was left untouched -- inspect records/, "
        "netlist-snapshots/ and the log directories for incomplete runs."
    )


def publish_record(record_path: Path, text: str) -> Path:
    """Replace our reservation stub with the final record. Refuses to touch
    a file that is not an unpublished reservation stub."""
    try:
        current = record_path.read_text()
    except FileNotFoundError:
        raise RecordCollisionError(f"{record_path} was not reserved") from None
    if not current.startswith(RESERVATION_MARKER):
        raise RecordCollisionError(
            f"{record_path} is already a published record; refusing to overwrite"
        )
    tmp = record_path.with_name(record_path.name + f".tmp{os.getpid()}")
    write_new_text(tmp, text)
    os.replace(tmp, record_path)
    return record_path


def environment_block(
    pdk_line: str,
    ngspice_line: str,
    netlist_sha256: str,
    extra: dict[str, str] | None = None,
) -> list[str]:
    git = git_info()
    lines = [
        "## Environment",
        "",
        f"- PDK: {pdk_line}",
        f"- ngspice: {ngspice_line}",
        f"- Harness: sim/harness {_harness_version()}",
        f"- git: `{git.commit}` on `{git.branch}`" + (" (dirty)" if git.dirty else " (clean)"),
        f"- DUT netlist sha256: `{netlist_sha256}`",
    ]
    if extra:
        for k, v in extra.items():
            lines.append(f"- {k}: {v}")
    return lines


def _harness_version() -> str:
    from . import __version__

    return __version__


def write_netlist_snapshot_text(experiment_dir: Path, record_id: str, netlist_text: str) -> Path:
    """Text-accepting sibling of write_netlist_snapshot(), for netlists that
    are generated text (e.g. a derived reduced sub-model deck) rather than a
    static on-disk fragment. Snapshot the netlist under
    <experiment_dir>/netlist-snapshots/ and set up <experiment_dir>/records/,
    returning the path the caller's evidence record should be written to."""
    snapshots_dir = experiment_dir / "netlist-snapshots"
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    write_new_text(snapshots_dir / f"{record_id}.spice", netlist_text)

    records_dir = experiment_dir / "records"
    records_dir.mkdir(parents=True, exist_ok=True)
    return records_dir / f"{record_id}.md"


def write_netlist_snapshot(experiment_dir: Path, record_id: str, netlist_fragment: Path) -> Path:
    """Snapshot the DUT netlist under <experiment_dir>/netlist-snapshots/ and
    set up <experiment_dir>/records/, returning the path the caller's
    evidence record should be written to. Shared by both write_evidence()
    implementations (PVT corner runner and Monte Carlo runner) -- see
    module docstring."""
    return write_netlist_snapshot_text(experiment_dir, record_id, netlist_fragment.read_text())


def run_klt_yield(measurements: list[dict], out_json_path: Path) -> dict | None:
    """Invoke `klt yield` against an already-built `measurements` list (each
    caller constructs its own `"name"`/`"unit"`/`"samples"`/`"limits"`
    entries -- see 2AMLogic/sky130-sar-adc's sim/cdac-array-transfer/run_mc.py
    and sim/enob-estimate/run_enob.py for that repo's two callers; this repo
    has no caller yet -- ported ahead of one existing so a future
    statistical-row experiment driver here has this plumbing available
    without a second port pass), writing the scratch sample file to a
    tempfile and the parsed report to `out_json_path`. Returns the parsed
    JSON report, or None if `klt` / its native yield extension is
    unavailable, its output isn't valid JSON, or the report itself carries
    an `"error"` key (recorded as an honest gap in the calling record
    rather than silently skipped).

    Extracted (sky130-sar-adc issue #131) from the two byte-identical
    `_run_klt_yield` private helpers that repo's PR #130 introduced
    independently in both callers -- only
    this tempfile/subprocess/parse/cleanup plumbing was shared; each
    caller's own `measurements`-list construction stays at its call site."""
    doc = {"measurements": measurements}
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(doc, f)
        sample_path = Path(f.name)
    try:
        proc = subprocess.run(
            ["klt", "yield", str(sample_path), "--format", "json"],
            capture_output=True, text=True, timeout=60,
        )
        try:
            report = json.loads(proc.stdout)
        except json.JSONDecodeError:
            return None
        out_json_path.parent.mkdir(parents=True, exist_ok=True)
        out_json_path.write_text(json.dumps(report, indent=2))
        if "error" in report:
            return None
        return report
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    finally:
        sample_path.unlink(missing_ok=True)


def footer_lines(written_by: str, supersedes: str) -> list[str]:
    """The **Supersedes** + append-only boilerplate every evidence record
    ends with, parameterized by the calling script's path (e.g.
    `sim/run_corners.py` or `sim/monte_carlo.py`)."""
    return [
        f"- **Supersedes**: {supersedes or '(none)'}",
        "",
        (
            f"Written by `{written_by}`. Append-only: never edit or delete "
            "this file -- a re-run or correction mints a new record-id and "
            "points back here via **Supersedes** (see `sim/README.md`)."
        ),
        "",
    ]
