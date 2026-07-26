"""Import von LogFile_*.csv in den SQLite-Cache."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

from config import IMPORT_ERRORS_PATH, LOG_FILE_PATTERN, LOG_FILES_DIR
from data.parser import is_log_file, parse_log_file
from data.store import DataStore


@dataclass
class ImportResult:
    imported: int = 0
    skipped: int = 0
    failed: int = 0
    rows_added: int = 0
    errors: list[str] = field(default_factory=list)


def _log_error(message: str) -> None:
    IMPORT_ERRORS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(IMPORT_ERRORS_PATH, "a", encoding="utf-8") as f:
        f.write(message + "\n")


def discover_log_files(directory: Path) -> list[Path]:
    return sorted(directory.glob(LOG_FILE_PATTERN))


def import_files(
    store: DataStore,
    paths: Iterable[Path],
    *,
    force: bool = False,
    progress: Callable[[int, int, str], None] | None = None,
) -> ImportResult:
    result = ImportResult()
    paths = [Path(p) for p in paths if is_log_file(Path(p))]
    total = len(paths)

    for i, path in enumerate(paths):
        if progress:
            progress(i + 1, total, path.name)

        if not force and not store.needs_import(path):
            result.skipped += 1
            continue

        try:
            df = parse_log_file(path)
            mtime = path.stat().st_mtime
            n = store.insert_dataframe(df, path.name, mtime)
            if n > 0 or df.empty:
                result.imported += 1
            result.rows_added += n
        except Exception as exc:
            msg = f"{path.name}: {exc}"
            result.errors.append(msg)
            result.failed += 1
            _log_error(msg)

    return result


def import_directory(
    store: DataStore,
    directory: Path | None = None,
    *,
    force: bool = False,
    only_new: bool = True,
    progress: Callable[[int, int, str], None] | None = None,
) -> ImportResult:
    directory = Path(directory or LOG_FILES_DIR)
    paths = discover_log_files(directory)
    if only_new and not force:
        paths = [p for p in paths if store.needs_import(p)]
    return import_files(store, paths, force=force, progress=progress)
