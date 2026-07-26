"""SQLite-Speicher für Messdaten."""
from __future__ import annotations

import sqlite3
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from config import (
    CACHE_DB_PATH,
    MEASUREMENT_COLUMNS,
    SOURCE_FILE_COL,
    TIMESTAMP_COL,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS measurements (
    timestamp TEXT NOT NULL,
    source_file TEXT NOT NULL,
    fahrten_gesamt REAL,
    gesamtrunden REAL,
    tages_zaehler REAL,
    oel_fuellstand REAL,
    oel_temperatur_tank REAL,
    oel_temperatur_kuehler REAL,
    temperatur_leistungsschrank REAL,
    temepratur_steuerschrank REAL,
    temp_aggregat_lager_a REAL,
    temp_aggregat_lager_b REAL,
    PRIMARY KEY (timestamp, source_file)
);
CREATE INDEX IF NOT EXISTS idx_measurements_timestamp ON measurements(timestamp);

CREATE TABLE IF NOT EXISTS imported_files (
    filename TEXT PRIMARY KEY,
    mtime REAL NOT NULL,
    row_count INTEGER NOT NULL,
    imported_at TEXT NOT NULL
);
"""

# Mapping DB-Spalte <-> DataFrame-Spalte
_DB_COL_MAP = {
    "Fahrten Gesamt": "fahrten_gesamt",
    "Gesamtrunden": "gesamtrunden",
    "Tages Zähler": "tages_zaehler",
    "Öl Füllstand": "oel_fuellstand",
    "Öl Temperatur Tank": "oel_temperatur_tank",
    "Öl Temperatur Kühler": "oel_temperatur_kuehler",
    "Temperatur Leistungsschrank": "temperatur_leistungsschrank",
    "Temepratur Steuerschrank": "temepratur_steuerschrank",
    "Temp. Aggregat Lager A": "temp_aggregat_lager_a",
    "Temp. Aggregat Lager B": "temp_aggregat_lager_b",
}
_REVERSE_MAP = {v: k for k, v in _DB_COL_MAP.items()}


class DataStore:
    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = Path(db_path or CACHE_DB_PATH)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def is_empty(self) -> bool:
        row = self._conn.execute("SELECT COUNT(*) FROM measurements").fetchone()
        return row[0] == 0

    def row_count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) FROM measurements").fetchone()
        return row[0]

    def imported_file_count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) FROM imported_files").fetchone()
        return row[0]

    def get_imported_file(self, filename: str) -> sqlite3.Row | None:
        return self._conn.execute(
            "SELECT * FROM imported_files WHERE filename = ?", (filename,)
        ).fetchone()

    def needs_import(self, path: Path) -> bool:
        existing = self.get_imported_file(path.name)
        if existing is None:
            return True
        return path.stat().st_mtime > existing["mtime"]

    def clear_all(self) -> None:
        self._conn.execute("DELETE FROM measurements")
        self._conn.execute("DELETE FROM imported_files")
        self._conn.commit()

    def _df_to_db_rows(self, df: pd.DataFrame) -> list[tuple]:
        rows = []
        for _, row in df.iterrows():
            ts = row[TIMESTAMP_COL]
            if isinstance(ts, pd.Timestamp):
                ts_str = ts.isoformat(sep=" ")
            else:
                ts_str = str(ts)
            values = [ts_str, row[SOURCE_FILE_COL]]
            for col in MEASUREMENT_COLUMNS:
                db_col = _DB_COL_MAP[col]
                val = row.get(col)
                values.append(None if pd.isna(val) else float(val))
            rows.append(tuple(values))
        return rows

    def insert_dataframe(self, df: pd.DataFrame, filename: str, mtime: float) -> int:
        if df.empty:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO imported_files (filename, mtime, row_count, imported_at)
                VALUES (?, ?, 0, ?)
                """,
                (filename, mtime, datetime.now().isoformat(timespec="seconds")),
            )
            self._conn.commit()
            return 0

        cols = ["timestamp", "source_file"] + list(_DB_COL_MAP.values())
        placeholders = ",".join("?" * len(cols))
        sql = f"""
            INSERT OR REPLACE INTO measurements ({",".join(cols)})
            VALUES ({placeholders})
        """
        rows = self._df_to_db_rows(df)
        self._conn.executemany(sql, rows)
        self._conn.execute(
            """
            INSERT OR REPLACE INTO imported_files (filename, mtime, row_count, imported_at)
            VALUES (?, ?, ?, ?)
            """,
            (filename, mtime, len(rows), datetime.now().isoformat(timespec="seconds")),
        )
        self._conn.commit()
        return len(rows)

    def load_measurements(
        self,
        date_from: date | datetime | None = None,
        date_to: date | datetime | None = None,
    ) -> pd.DataFrame:
        """Lädt Messdaten; bei doppeltem Timestamp gewinnt neuere source_file (höheres mtime)."""
        query = "SELECT * FROM measurements WHERE 1=1"
        params: list = []

        if date_from is not None:
            query += " AND timestamp >= ?"
            params.append(_to_iso_start(date_from))
        if date_to is not None:
            query += " AND timestamp <= ?"
            params.append(_to_iso_end(date_to))

        query += " ORDER BY timestamp, source_file"
        raw = pd.read_sql_query(query, self._conn, params=params)
        if raw.empty:
            return _empty_df()

        df = _db_to_df(raw)
        # Duplikate: pro Timestamp letzte Zeile (sortiert nach source_file ~ Dateiname)
        df = df.drop_duplicates(subset=[TIMESTAMP_COL], keep="last")
        df = df.sort_values(TIMESTAMP_COL).reset_index(drop=True)
        df["Datum"] = df[TIMESTAMP_COL].dt.date
        return df

    def time_range(self) -> tuple[datetime | None, datetime | None]:
        row = self._conn.execute(
            "SELECT MIN(timestamp), MAX(timestamp) FROM measurements"
        ).fetchone()
        if row[0] is None:
            return None, None
        return pd.to_datetime(row[0]).to_pydatetime(), pd.to_datetime(row[1]).to_pydatetime()

    def daily_rides(
        self,
        date_from: date | datetime | None = None,
        date_to: date | datetime | None = None,
    ) -> pd.DataFrame:
        df = self.load_measurements(date_from=date_from, date_to=date_to)
        if df.empty or "Tages Zähler" not in df.columns:
            return pd.DataFrame(columns=["Datum", "Tages Zähler"])

        max_per_day = df.groupby("Datum")["Tages Zähler"].max().reset_index()
        min_d = max_per_day["Datum"].min()
        max_d = max_per_day["Datum"].max()
        all_days = pd.date_range(min_d, max_d, freq="D")
        all_days_df = pd.DataFrame(all_days, columns=["Datum"])
        all_days_df["Datum"] = all_days_df["Datum"].dt.date
        max_per_day["Datum"] = pd.to_datetime(max_per_day["Datum"]).dt.date

        full = pd.merge(all_days_df, max_per_day, on="Datum", how="left").fillna(0)
        full["Tages Zähler"] = full["Tages Zähler"].astype(int)
        return full

    def empty_import_files(self, limit: int = 50) -> pd.DataFrame:
        query = """
            SELECT filename, mtime, imported_at
            FROM imported_files
            WHERE row_count = 0
            ORDER BY filename
            LIMIT ?
        """
        df = pd.read_sql_query(query, self._conn, params=[limit])
        if df.empty:
            return pd.DataFrame(columns=["filename", "mtime", "imported_at"])
        return df

    def large_time_gaps(self, min_hours: float = 12.0, limit: int = 25) -> pd.DataFrame:
        ts_df = pd.read_sql_query(
            "SELECT timestamp, source_file FROM measurements ORDER BY timestamp",
            self._conn,
        )
        if ts_df.empty:
            return pd.DataFrame(
                columns=["from_timestamp", "to_timestamp", "from_file", "to_file", "gap_hours"]
            )

        ts_df["timestamp"] = pd.to_datetime(ts_df["timestamp"])
        ts_df["from_timestamp"] = ts_df["timestamp"].shift(1)
        ts_df["from_file"] = ts_df["source_file"].shift(1)
        ts_df["gap_hours"] = (
            (ts_df["timestamp"] - ts_df["from_timestamp"]).dt.total_seconds() / 3600.0
        )
        gaps = ts_df[ts_df["gap_hours"] > min_hours].copy()
        if gaps.empty:
            return pd.DataFrame(
                columns=["from_timestamp", "to_timestamp", "from_file", "to_file", "gap_hours"]
            )

        gaps = gaps.rename(
            columns={"timestamp": "to_timestamp", "source_file": "to_file"}
        )
        gaps = gaps[
            ["from_timestamp", "to_timestamp", "from_file", "to_file", "gap_hours"]
        ]
        gaps = gaps.sort_values("gap_hours", ascending=False).head(limit).reset_index(drop=True)
        return gaps


def _to_iso_start(d: date | datetime) -> str:
    if isinstance(d, date) and not isinstance(d, datetime):
        return datetime.combine(d, datetime.min.time()).isoformat(sep=" ")
    if isinstance(d, datetime):
        return d.isoformat(sep=" ")
    return str(d)


def _to_iso_end(d: date | datetime) -> str:
    if isinstance(d, date) and not isinstance(d, datetime):
        return datetime.combine(d, datetime.max.time()).replace(microsecond=0).isoformat(sep=" ")
    if isinstance(d, datetime):
        return d.isoformat(sep=" ")
    return str(d)


def _db_to_df(raw: pd.DataFrame) -> pd.DataFrame:
    df = pd.DataFrame()
    df[TIMESTAMP_COL] = pd.to_datetime(raw["timestamp"])
    df[SOURCE_FILE_COL] = raw["source_file"]
    for display, db_col in _DB_COL_MAP.items():
        if db_col in raw.columns:
            df[display] = raw[db_col]
    return df


def _empty_df() -> pd.DataFrame:
    cols = [TIMESTAMP_COL, SOURCE_FILE_COL, "Datum"] + MEASUREMENT_COLUMNS
    return pd.DataFrame(columns=cols)
