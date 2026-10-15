"""Resolve the sky130 PDK install the harness should run against.

Ported (issue #8) from 2AMLogic/sky130-sar-adc's sim/harness/pdk.py
(commit b80c144efbf467a586f728726cabb25c1eb5a1f2) -- unchanged logic;
same PDK (sky130), same resolution convention.

Resolution order (env wins over the committed default, matching
sim/pdk.json's own convention and gf180-sar-adc's sim/harness/pdk.py):

  1. $PDK_ROOT / $PDK, if both set.
  2. sim/pdk.json's "default_pdk_root" (~/.ciel) / "variant" (sky130A).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parent.parent


@dataclass
class PdkInfo:
    root: Path
    variant: str
    variant_dir: Path
    ngspice_lib: Path
    xschem_rc: Path
    open_pdks_commit_expected: str
    found: bool
    error: str = ""


def load_pdk_json() -> dict:
    with (SIM_DIR / "pdk.json").open() as f:
        return json.load(f)


def resolve() -> PdkInfo:
    cfg = load_pdk_json()
    root_env = os.environ.get("PDK_ROOT", "").strip()
    variant_env = os.environ.get("PDK", "").strip()

    root = Path(root_env).expanduser() if root_env else Path(cfg["default_pdk_root"]).expanduser()
    variant = variant_env or cfg["variant"]
    variant_dir = root / variant
    ngspice_lib = variant_dir / cfg["ngspice_lib"]
    xschem_rc = variant_dir / cfg["xschem_pdk_rc"]

    if not variant_dir.is_dir():
        error = f"no PDK variant directory at {variant_dir}"
    elif not ngspice_lib.is_file():
        error = f"no ngspice model library at {ngspice_lib}"
    else:
        error = ""

    return PdkInfo(
        root=root,
        variant=variant,
        variant_dir=variant_dir,
        ngspice_lib=ngspice_lib,
        xschem_rc=xschem_rc,
        open_pdks_commit_expected=cfg["open_pdks_commit"],
        found=not error,
        error=error,
    )


def _commit_from_path(variant_dir: Path) -> str | None:
    """The 40-hex open_pdks commit ciel encodes into the resolved variant
    symlink's path (.../ciel/sky130/versions/<commit>/sky130A), or None if
    variant_dir does not resolve through that shape. A SECONDARY signal only:
    the path says which version directory the symlink points at, not what
    that tree was built from -- see _commit_from_sources().
    """
    try:
        resolved = variant_dir.resolve()
    except OSError:
        return None
    for part in resolved.parts:
        if len(part) == 40 and all(c in "0123456789abcdef" for c in part):
            return part
    return None


def _commit_from_sources(variant_dir: Path) -> str | None:
    """The open_pdks commit recorded in <variant_dir>/SOURCES (a line
    "open_pdks <sha>"), or None when SOURCES is missing, unreadable or has
    no such line. This is the PRIMARY provenance signal: a stray tree at a
    different revision cannot pass it by sitting at a lookalike path.
    """
    try:
        text = (variant_dir / "SOURCES").read_text()
    except OSError:
        return None
    for line in text.splitlines():
        fields = line.split()
        if len(fields) == 2 and fields[0] == "open_pdks":
            sha = fields[1].lower()
            if len(sha) == 40 and all(c in "0123456789abcdef" for c in sha):
                return sha
    return None


def resolved_commit_verified(info: PdkInfo) -> str | None:
    """The open_pdks commit actually installed at info.variant_dir, IFF its
    provenance can be verified -- None otherwise.

    Reads the variant's SOURCES file first. The resolved path's version hash
    is only a secondary signal: if both are present and disagree the install
    is unverifiable (None), and a missing/unreadable SOURCES is unverifiable
    too (fail closed), even when the path looks right.

    Callers that must fail closed on unverifiable provenance (e.g.
    toolchain.check_env()'s pin-drift gate) use this, not resolved_commit()
    below: resolved_commit() folds the unverifiable case into a *display*
    string (for evidence records, where "some string, honestly labeled" is
    the right answer), and that string must never be mistaken for a
    confirmed pin match -- see the fallback string's "(unverified -- ...)"
    suffix, which previously happened to `startswith()` the pin and so
    satisfied the drift gate for an install of unknown provenance.
    """
    from_sources = _commit_from_sources(info.variant_dir)
    if from_sources is None:
        return None
    from_path = _commit_from_path(info.variant_dir)
    if from_path is not None and from_path != from_sources:
        return None
    return from_sources


def resolved_commit(info: PdkInfo) -> str:
    """Best-effort open_pdks commit actually installed at info.variant_dir,
    for DISPLAY in evidence records and summaries.

    A SOURCES/path disagreement or a SOURCES-less tree is reported loudly,
    never as a clean commit. The fallback is a display convenience only --
    it must never be treated as proof the install is on pin; use
    resolved_commit_verified() for that decision.
    """
    from_sources = _commit_from_sources(info.variant_dir)
    from_path = _commit_from_path(info.variant_dir)
    if from_sources is not None and (from_path is None or from_path == from_sources):
        return from_sources
    if from_sources is not None:
        return (f"{from_sources} (UNVERIFIED -- SOURCES disagrees with path "
                f"version {from_path})")
    if from_path is not None:
        return f"{from_path} (UNVERIFIED -- no readable SOURCES file)"
    return info.open_pdks_commit_expected + " (unverified -- no SOURCES file)"


def resolve_or_raise() -> PdkInfo:
    """resolve(), raising RuntimeError instead of returning an unfound
    PdkInfo. For callers that treat an unresolvable PDK as a hard error
    rather than something they can report a CLI exit code for themselves --
    see toolchain.check_env() / each script's own `--check-env` handling
    for the exit-code convention used where a graceful, non-raising report
    is wanted instead."""
    info = resolve()
    if not info.found:
        raise RuntimeError(f"PDK not resolvable: {info.error}")
    return info


def print_env(info: PdkInfo) -> str:
    """Eval-able shell export lines, for `source sim/env.sh`."""
    return f'export PDK_ROOT="{info.root}"\nexport PDK="{info.variant}"\n'
