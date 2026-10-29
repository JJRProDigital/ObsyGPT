"""Copies a plugin project template into a managed project folder."""

import shutil
from pathlib import Path

MAX_TEMPLATE_FILES = 500
MAX_TEMPLATE_BYTES = 20 * 1024 * 1024
SKIPPED_NAMES = {".git", "__pycache__", "node_modules"}


class TemplateCopyError(RuntimeError):
    pass


def copy_template_tree(source: Path, destination: Path) -> int:
    """Copies regular files and folders, skipping symlinks and heavy caches. Returns the file count."""
    source = source.resolve()
    if not source.is_dir():
        raise TemplateCopyError(f"Template folder not found: {source}")
    destination.mkdir(parents=True, exist_ok=False)

    file_count = 0
    total_bytes = 0
    for item in sorted(source.rglob("*")):
        relative = item.relative_to(source)
        if any(part in SKIPPED_NAMES for part in relative.parts):
            continue
        if item.is_symlink():
            continue
        target = destination / relative
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        if not item.is_file():
            continue

        file_count += 1
        total_bytes += item.stat().st_size
        if file_count > MAX_TEMPLATE_FILES or total_bytes > MAX_TEMPLATE_BYTES:
            shutil.rmtree(destination, ignore_errors=True)
            raise TemplateCopyError("Template is too large.")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(item, target)

    return file_count
