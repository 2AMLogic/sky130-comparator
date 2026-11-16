"""Shared evidence-record plumbing for the two sim/harness runners --
sim/harness/runner.py (PVT corner sweeps) and sim/harness/mc_runner.py
(Monte Carlo draws) -- plus the fail-closed artifact-store gates their
CLIs (sim/harness/cli.py, sim/harness/mc_cli.py) wrap the runs in.

``begin_record()`` / ``finalize_record()`` are the harness counterpart of
sim/comparator-decision/_shared.py's ``_begin_dut_record()`` /
``_finalize_record()`` pair, extracted (issue #240) from the two
byte-identical heads and tails of the runners' ``write_evidence()``
bodies -- the pre-extraction copies were porting residue (issue #8,
"unchanged logic") from 2AMLogic/sky130-sar-adc. As with
scripts/_gate_common.py's ratified rationale ("so the gates cannot
drift"), a record header, environment block, footer attribution or
fail-closed message can now only change in one place; sim/tests/
test_harness.py pins the emitted record text byte-for-byte against
goldens captured from the pre-extraction code.

Deliberately NOT changed: the reservation strategy. Both runners go
through ``evidence_store.free_record_id()`` + ``store_run()``, a
documented alternative to ``evidence.reserve_record()`` +
``publish_record()`` for the artifact-store path (issue #198) -- these
helpers keep that path verbatim and never migrate either runner onto the
other's.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable, Protocol

from . import evidence, evidence_store, pdk, testbench, toolchain


class RecordRun(Protocol):
    """The slice of ``runner.RunResult`` / ``mc_runner.McResult`` the
    record helpers touch (duck-typed so this module need not import
    either runner)."""

    manifest: testbench.Manifest
    record_id: str
    netlist_sha256: str


def begin_record(result: RecordRun, title: str) -> tuple[pdk.PdkInfo, list[str]]:
    """Shared head of both harness runners' ``write_evidence()``: reserve a
    free record id (advancing ``result.record_id`` in place if the proposed
    one is taken), resolve the PDK, and open the record with its five-line
    header -- ``# <title> <record_id>``, **Record ID**, **Claim**,
    **Netlist provenance** -- byte-identical to the pre-extraction copies.

    Returns ``(info, lines)``; ``info`` feeds ``finalize_record()`` so the
    PDK is resolved exactly once per record, and the caller appends its
    bench-specific middle onto ``lines`` (re-deriving ``lines.append`` if
    it uses the ``a`` shorthand).
    """
    repo_root = evidence.REPO_ROOT
    manifest = result.manifest
    experiment_dir = manifest.experiment_dir
    rid = evidence_store.free_record_id(repo_root, experiment_dir, result.record_id)
    if rid != result.record_id:
        print(f"  record id {result.record_id} was taken; using {rid}")
        result.record_id = rid
    info = pdk.resolve()

    lines = [
        f"# {title} {result.record_id}",
        "",
        f"- **Record ID**: {result.record_id}",
        f"- **Claim**: {manifest.claim}",
        "- **Netlist provenance**: schematic "
        f"(`{manifest.netlist_fragment.relative_to(evidence.REPO_ROOT)}`)",
    ]
    return info, lines


def finalize_record(
    result: RecordRun,
    lines: list[str],
    *,
    info: pdk.PdkInfo,
    blobs: dict[str, str],
    attribution: str,
    extra: dict[str, str] | None = None,
    supersedes: str = "",
) -> Path:
    """Shared tail: append the netlist-snapshot blob (both runners keep it
    last in the artifact-store blob order, as the pre-extraction code
    did), the environment block, the append-only footer, and store the
    record through ``evidence_store.store_run()`` -- byte-identical to the
    pre-extraction copies. ``blobs`` carries the caller's per-bench raw
    outputs, keyed with the post-reservation ``result.record_id``;
    ``attribution`` is the "Written by" script path (e.g.
    ``sim/run_corners.py``); ``extra`` feeds ``environment_block``'s
    extra-lines mapping (the MC runner's seed/N bullets). Returns the
    record path the CLI prints.
    """
    manifest = result.manifest
    experiment_dir = manifest.experiment_dir
    blobs[f"netlist-snapshots/{result.record_id}.spice"] = manifest.netlist_fragment.read_text()
    record_path = experiment_dir / "records" / f"{result.record_id}.md"

    lines.extend(evidence.environment_block(
        pdk_line=f"{info.variant} @ {pdk.resolved_commit(info)}",
        ngspice_line=toolchain._ngspice_version() or "unknown",
        netlist_sha256=result.netlist_sha256,
        extra=extra,
    ))
    lines.append("")
    lines.extend(evidence.footer_lines(attribution, supersedes))

    evidence_store.store_run(
        repo_root=evidence.REPO_ROOT, experiment_dir=experiment_dir,
        record_id=result.record_id, blobs=blobs, record_text="\n".join(lines),
    )
    return record_path


def record_preflight() -> int:
    """Fail-closed gate for ``--record`` runs (issue #198): run the
    artifact-store preflight BEFORE spending simulation time, so a store
    that cannot take the raw outputs refuses the run up front. Returns 0
    when the store is usable; otherwise prints the user-facing refusal to
    stderr and returns the exit code 10."""
    try:
        evidence_store.preflight(evidence.REPO_ROOT)
    except evidence_store.StoreError as e:
        print(f"EVIDENCE CANNOT BE STORED -- nothing run, nothing written: {e}", file=sys.stderr)
        return 10
    return 0


def store_record_fail_closed(write: Callable[[], Path]) -> Path | int:
    """Run ``write()`` (a runner's ``write_evidence()`` call), returning
    its record path; on :class:`evidence_store.StoreError` print the
    fail-closed notice to stderr and return the exit code 10 instead --
    nothing is committed on that path, and the CLI returns the code
    verbatim."""
    try:
        return write()
    except evidence_store.StoreError as e:
        print(f"EVIDENCE NOT STORED -- nothing committed (fail closed): {e}", file=sys.stderr)
        return 10
