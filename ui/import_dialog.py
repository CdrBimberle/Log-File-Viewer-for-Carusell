"""Import-Fortschritt und Ordnerauswahl."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QLabel,
    QMessageBox,
    QProgressDialog,
    QVBoxLayout,
)

from config import IMPORT_ERRORS_PATH, LOG_FILES_DIR
from data.importer import ImportResult, import_directory, import_files
from data.store import DataStore


def run_import_with_progress(
    parent,
    store: DataStore,
    directory: Path | None = None,
    file_paths: list[Path] | None = None,
    *,
    force: bool = False,
    only_new: bool = True,
) -> ImportResult:
    if file_paths:
        paths = file_paths
        title = "Log-Dateien importieren"
    else:
        directory = Path(directory or LOG_FILES_DIR)
        from data.importer import discover_log_files

        paths = discover_log_files(directory)
        if only_new and not force:
            paths = [p for p in paths if store.needs_import(p)]
        title = f"Import aus {directory.name}"

    if not paths:
        QMessageBox.information(
            parent,
            "Import",
            "Keine neuen Log-Dateien zum Importieren gefunden.",
        )
        return ImportResult()

    progress = QProgressDialog(title, "Abbrechen", 0, len(paths), parent)
    progress.setWindowModality(Qt.WindowModality.WindowModal)
    progress.setMinimumDuration(0)

    def on_progress(current: int, total: int, name: str) -> None:
        progress.setMaximum(total)
        progress.setValue(current)
        progress.setLabelText(f"{current}/{total}: {name}")
        if progress.wasCanceled():
            raise InterruptedError("Import abgebrochen")

    try:
        if file_paths:
            result = import_files(
                store, paths, force=force, progress=on_progress
            )
        else:
            result = import_directory(
                store,
                directory,
                force=force,
                only_new=only_new,
                progress=on_progress,
            )
    except InterruptedError:
        result = ImportResult()
        result.errors.append("Import vom Benutzer abgebrochen.")
    finally:
        progress.close()

    return result


def show_import_summary(parent, result: ImportResult) -> None:
    lines = [
        f"Importiert: {result.imported} Datei(en)",
        f"Übersprungen: {result.skipped}",
        f"Fehlgeschlagen: {result.failed}",
        f"Messzeilen: {result.rows_added}",
    ]
    if result.errors:
        lines.append("")
        lines.append("Fehler (Auszug):")
        lines.extend(result.errors[:5])
        if len(result.errors) > 5:
            lines.append(f"… und {len(result.errors) - 5} weitere")
        lines.append(f"\nVollständiges Protokoll: {IMPORT_ERRORS_PATH}")

    QMessageBox.information(parent, "Import abgeschlossen", "\n".join(lines))


class FirstImportDialog(QDialog):
    """Dialog beim ersten Start ohne Cache."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Erster Import")
        self.selected_directory: Path | None = None

        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                "Es sind noch keine Messdaten im Cache.\n"
                f"Standard-Ordner:\n{LOG_FILES_DIR}\n\n"
                "Möchten Sie jetzt Log-Dateien importieren?"
            )
        )

        buttons = QDialogButtonBox()
        import_default = buttons.addButton(
            "Standard-Ordner importieren", QDialogButtonBox.ButtonRole.AcceptRole
        )
        choose_btn = buttons.addButton(
            "Ordner wählen…", QDialogButtonBox.ButtonRole.ActionRole
        )
        skip_btn = buttons.addButton(
            "Später", QDialogButtonBox.ButtonRole.RejectRole
        )
        import_default.clicked.connect(self._use_default)
        choose_btn.clicked.connect(self._choose_folder)
        skip_btn.clicked.connect(self.reject)
        layout.addWidget(buttons)

    def _use_default(self) -> None:
        self.selected_directory = LOG_FILES_DIR
        self.accept()

    def _choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Log-Ordner wählen", str(LOG_FILES_DIR)
        )
        if folder:
            self.selected_directory = Path(folder)
            self.accept()
