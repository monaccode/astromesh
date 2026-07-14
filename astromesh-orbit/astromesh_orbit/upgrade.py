"""orbit upgrade — show (and apply) what the current package's templates would change.

Pure filesystem work: no cloud calls, no Terraform. Renders happen in the caller; this module
diffs the freshly-rendered templates against the generated ones and, on apply, mirrors them.
"""

from __future__ import annotations

import difflib
import shutil
from pathlib import Path


def stale_tf_files(new_dir: Path, current_dir: Path) -> list[Path]:
    """*.tf files in current_dir that new_dir no longer renders (sorted by name).

    These are resources a package upgrade has dropped: they must show up as deletions in the
    diff and be pruned on apply, or `orbit plan` would keep provisioning them.
    """
    new_names = {p.name for p in new_dir.glob("*.tf")}
    return sorted(
        (p for p in current_dir.glob("*.tf") if p.name not in new_names),
        key=lambda p: p.name,
    )


def diff_generated(new_dir: Path, current_dir: Path) -> str:
    """Unified diff of every *.tf between new_dir and current_dir. Returns "" when identical.

    A file absent from current_dir shows up as all-additions; a file absent from new_dir (a
    dropped resource) shows up as all-deletions.
    """
    chunks: list[str] = []

    # Added or changed: iterate the newly-rendered files.
    for new_file in sorted(new_dir.glob("*.tf")):
        current_file = current_dir / new_file.name
        current_lines = (
            current_file.read_text().splitlines(keepends=True) if current_file.exists() else []
        )
        new_lines = new_file.read_text().splitlines(keepends=True)
        chunks.extend(
            difflib.unified_diff(
                current_lines,
                new_lines,
                fromfile=f"current/{new_file.name}",
                tofile=f"new/{new_file.name}",
            )
        )

    # Removed: files current_dir has that new_dir no longer renders -> all-deletions.
    for stale in stale_tf_files(new_dir, current_dir):
        chunks.extend(
            difflib.unified_diff(
                stale.read_text().splitlines(keepends=True),
                [],
                fromfile=f"current/{stale.name}",
                tofile="/dev/null",
            )
        )

    return "".join(chunks)


def apply_generated(new_dir: Path, current_dir: Path) -> None:
    """Make current_dir's *.tf match new_dir's: copy the rendered files over, and prune any the
    new render no longer produces so no stale resource is left behind."""
    current_dir.mkdir(parents=True, exist_ok=True)
    for stale in stale_tf_files(new_dir, current_dir):
        stale.unlink()
    for f in new_dir.glob("*.tf"):
        shutil.copy2(f, current_dir / f.name)
