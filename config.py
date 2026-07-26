"""Konfiguration für den Log-Viewer."""
import sys
from pathlib import Path


def _app_dir() -> Path:
    """App-Verzeichnis: bei PyInstaller sys._MEIPASS, sonst Quellordner."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


def resource_path(*parts: str) -> Path:
    """Pfad zu gebündelten Ressourcen (z. B. Markdown, Icons)."""
    return _app_dir().joinpath(*parts)


APP_DIR = Path(__file__).resolve().parent
# Bei gefrorener EXE: Ordner der .exe (für Cache/Logs neben der App)
if getattr(sys, "frozen", False):
    EXE_DIR = Path(sys.executable).resolve().parent
    LOG_FILES_DIR = EXE_DIR
    CACHE_DB_PATH = EXE_DIR / "data" / "cache.db"
    IMPORT_ERRORS_PATH = EXE_DIR / "data" / "import_errors.txt"
else:
    EXE_DIR = APP_DIR
    LOG_FILES_DIR = APP_DIR.parent
    CACHE_DB_PATH = APP_DIR / "data" / "cache.db"
    IMPORT_ERRORS_PATH = APP_DIR / "data" / "import_errors.txt"

HELP_MD_PATH = resource_path("Funktionsbeschreibung.md")
APP_ICON_PATH = resource_path("assets", "app.ico")

LOG_FILE_PATTERN = "LogFile_*.csv"

# Kanonische Spaltennamen (nach Normalisierung)
TIMESTAMP_COL = "Timestamp"
SOURCE_FILE_COL = "source_file"

MEASUREMENT_COLUMNS = [
    "Fahrten Gesamt",
    "Gesamtrunden",
    "Tages Zähler",
    "Öl Füllstand",
    "Öl Temperatur Tank",
    "Öl Temperatur Kühler",
    "Temperatur Leistungsschrank",
    "Temepratur Steuerschrank",
    "Temp. Aggregat Lager A",
    "Temp. Aggregat Lager B",
]

CHANNEL_GROUPS = {
    "Temperaturen": [
        "Öl Temperatur Tank",
        "Öl Temperatur Kühler",
        "Temperatur Leistungsschrank",
        "Temepratur Steuerschrank",
        "Temp. Aggregat Lager A",
        "Temp. Aggregat Lager B",
    ],
    "Betrieb": [
        "Öl Füllstand",
        "Tages Zähler",
        "Fahrten Gesamt",
        "Gesamtrunden",
    ],
}

# Temperaturen links, Zähler/Füllstand rechts (dual Y)
TEMPERATURE_CHANNELS = set(CHANNEL_GROUPS["Temperaturen"])
OIL_LEVEL_CHANNELS = {"Öl Füllstand"}
COUNTER_CHANNELS = set(CHANNEL_GROUPS["Betrieb"]) - OIL_LEVEL_CHANNELS

# Spalten-Aliase: normalisierte Schlüssel -> kanonischer Name
COLUMN_ALIASES = {
    "timestamp": TIMESTAMP_COL,
    "fahrten gesamt": "Fahrten Gesamt",
    "gesamtrunden": "Gesamtrunden",
    "tages zähler": "Tages Zähler",
    "tages zaehler": "Tages Zähler",
    "öl füllstand": "Öl Füllstand",
    "oel fuellstand": "Öl Füllstand",
    "öl temperatur tank": "Öl Temperatur Tank",
    "oel temperatur tank": "Öl Temperatur Tank",
    "öl temperatur kühler": "Öl Temperatur Kühler",
    "oel temperatur kuehler": "Öl Temperatur Kühler",
    "temperatur leistungsschrank": "Temperatur Leistungsschrank",
    "temepratur steuerschrank": "Temepratur Steuerschrank",
    "temperatur steuerschrank": "Temepratur Steuerschrank",
    "temp. aggregat lager a": "Temp. Aggregat Lager A",
    "temp. aggregat lager b": "Temp. Aggregat Lager B",
}

DEFAULT_VISIBLE_CHANNELS = [
    "Öl Temperatur Tank",
    "Öl Temperatur Kühler",
    "Temperatur Leistungsschrank",
    "Tages Zähler",
]
