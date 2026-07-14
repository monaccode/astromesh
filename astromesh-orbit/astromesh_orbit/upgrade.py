"""orbit upgrade — show what the current package's templates would change.

Pure filesystem work: no cloud calls, no Terraform. Renders happen in the caller; this module
only diffs.
"""

from __future__ import annotations

import difflib
from pathlib import Path


def diff_generated(new_dir: Path, current_dir: Path) -> str:
    """Unified diff of every *.tf in new_dir against its counterpart in current_dir.

    A file absent from current_dir shows up as all-additions. Returns "" when nothing differs.
    """
    chunks: list[str] = []
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
    return "".join(chunks)
