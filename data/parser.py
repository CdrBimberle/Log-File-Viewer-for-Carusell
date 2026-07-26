"""CSV-Parser für LogFile_*.csv."""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import pandas as pd

from config import (
    COLUMN_ALIASES,
    MEASUREMENT_COLUMNS,
    SOURCE_FILE_COL,
    TIMESTAMP_COL,
)

LOG_FILE_RE = re.compile(r"^LogFile_.*\.csv$", re.IGNORECASE)


def is_log_file(path: Path) -> bool:
    return LOG_FILE_RE.match(path.name) is not None


def _normalize_column_name(name: str) -> str:
    key = name.strip().lower()
    return COLUMN_ALIASES.get(key, name.strip())


def _read_csv_with_encoding(path: Path) -> pd.DataFrame:
    raw_head = path.read_bytes()[:4]
    if raw_head.startswith(b"\xef\xbb\xbf"):
        encodings = ("utf-8-sig", "utf-8", "latin1", "cp1252")
    else:
        encodings = ("latin1", "utf-8-sig", "cp1252")
    last_error: Exception | None = None
    for encoding in encodings:
        try:
            df = pd.read_csv(path, sep=";", encoding=encoding)
            if len(df.columns) >= 1:
                df.columns = [c.lstrip("\ufeff").strip() for c in df.columns]
            return df
        except UnicodeDecodeError as exc:
            last_error = exc
            continue
    raise UnicodeDecodeError(
        "csv", b"", 0, 1, f"Keine passende Kodierung für {path.name}: {last_error}"
    )


def parse_log_file(path: Path) -> pd.DataFrame:
    """Liest eine Log-CSV und liefert normalisierten DataFrame."""
    if not is_log_file(path):
        raise ValueError(f"Keine gültige Log-Datei: {path.name}")

    raw = _read_csv_with_encoding(path)
    raw.columns = [_normalize_column_name(c) for c in raw.columns]

    if TIMESTAMP_COL not in raw.columns:
        raise ValueError(f"Spalte '{TIMESTAMP_COL}' fehlt in {path.name}")

    df = pd.DataFrame()
    df[TIMESTAMP_COL] = pd.to_datetime(raw[TIMESTAMP_COL], errors="coerce")
    df = df.dropna(subset=[TIMESTAMP_COL])

    for col in MEASUREMENT_COLUMNS:
        if col in raw.columns:
            df[col] = pd.to_numeric(raw[col], errors="coerce")

    mtime = path.stat().st_mtime
    df[SOURCE_FILE_COL] = path.name
    df["_file_mtime"] = mtime
    df["_imported_at"] = datetime.now().isoformat(timespec="seconds")

    return df.reset_index(drop=True)
