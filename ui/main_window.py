"""Hauptfenster der Log-Viewer-App."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

from PySide6.QtCore import QDate, QSettings, Qt
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
    QDateEdit,
)

from config import APP_ICON_PATH, HELP_MD_PATH, IMPORT_ERRORS_PATH, LOG_FILES_DIR
from data.store import DataStore
from ui.channel_panel import ChannelPanel
from ui.daily_rides_plot import DailyRidesPlot
from ui.help_tab import HelpTab
from ui.import_dialog import (
    FirstImportDialog,
    run_import_with_progress,
    show_import_summary,
)
from ui.timeseries_plot import TimeSeriesPlot


class MainWindow(QMainWindow):
    def __init__(self, store: DataStore) -> None:
        super().__init__()
        self.store = store
        self.settings = QSettings("Eis-Greissler", "Log-Viewer")
        self._updating_dates = False
        self._data_min_date: date | None = None
        self._data_max_date: date | None = None
        self._base_status_message = ""
        self.setWindowTitle("Log-Viewer – Rundfahrgeschäft")
        self.resize(1280, 800)
        if APP_ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(APP_ICON_PATH)))

        self._build_menu()
        self._build_ui()
        self._status = QStatusBar()
        self.setStatusBar(self._status)

        self.channel_panel.visibility_changed.connect(self._refresh_plots)
        self.channel_panel.color_changed.connect(self._on_channel_color_changed)
        self.timeseries_plot.cursor_moved.connect(self._status.showMessage)
        self.timeseries_plot.cursor_values_changed.connect(
            self.channel_panel.set_cursor_values
        )
        self.daily_plot.cursor_value_changed.connect(self._show_daily_cursor_status)
        self._restore_channel_colors()
        self._refresh_data_range()

        if self.store.is_empty():
            self._offer_first_import()
        else:
            self._set_date_range_controls_from_data()
            self._reload_data()

    def _build_menu(self) -> None:
        menu = self.menuBar().addMenu("Datei")

        import_dir = QAction("Ordner importieren…", self)
        import_dir.triggered.connect(self._import_directory)
        menu.addAction(import_dir)

        import_new = QAction("Neue Logfiles importieren", self)
        import_new.triggered.connect(self._import_new_only)
        menu.addAction(import_new)

        import_files = QAction("Dateien importieren…", self)
        import_files.triggered.connect(self._import_selected_files)
        menu.addAction(import_files)

        menu.addSeparator()

        reset = QAction("Cache zurücksetzen…", self)
        reset.triggered.connect(self._reset_cache)
        menu.addAction(reset)

        menu.addSeparator()

        show_errors = QAction("Import-Fehlerprotokoll anzeigen", self)
        show_errors.triggered.connect(self._show_error_log)
        menu.addAction(show_errors)

        quality_action = QAction("Datenqualität prüfen…", self)
        quality_action.triggered.connect(self._show_data_quality_dialog)
        menu.addAction(quality_action)

        quit_action = QAction("Beenden", self)
        quit_action.triggered.connect(self.close)
        menu.addAction(quit_action)

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Von:"))
        self.date_from = QDateEdit()
        self.date_from.setCalendarPopup(True)
        self.date_from.setDisplayFormat("dd.MM.yyyy")
        filter_row.addWidget(self.date_from)

        filter_row.addWidget(QLabel("Bis:"))
        self.date_to = QDateEdit()
        self.date_to.setCalendarPopup(True)
        self.date_to.setDisplayFormat("dd.MM.yyyy")
        filter_row.addWidget(self.date_to)

        apply_btn = QPushButton("Filter anwenden")
        apply_btn.clicked.connect(self._reload_data)
        filter_row.addWidget(apply_btn)

        self.preset_combo = QComboBox()
        self.preset_combo.addItems(
            [
                "Zeitraum-Preset…",
                "Heute",
                "Diese Woche",
                "Letzte Woche",
                "Letzter Monat",
                "Letztes halbes Jahr",
                "Letztes Jahr",
                "Letzte 2 Jahre",
                "Letzte 5 Jahre",
                "Alle Daten",
            ]
        )
        self.preset_combo.currentIndexChanged.connect(self._on_preset_changed)
        filter_row.addWidget(self.preset_combo)

        zoom_btn = QPushButton("Auf Zeitraum zoomen")
        zoom_btn.clicked.connect(self._zoom_to_dates)
        filter_row.addWidget(zoom_btn)

        reset_zoom_btn = QPushButton("Zoom zurücksetzen")
        reset_zoom_btn.clicked.connect(self._reset_zoom)
        filter_row.addWidget(reset_zoom_btn)

        filter_row.addStretch()
        main_layout.addLayout(filter_row)

        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)

        # Tab Zeitreihen
        ts_widget = QWidget()
        ts_layout = QHBoxLayout(ts_widget)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.channel_panel = ChannelPanel()
        self.timeseries_plot = TimeSeriesPlot()
        splitter.addWidget(self.channel_panel)
        splitter.addWidget(self.timeseries_plot)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        ts_layout.addWidget(splitter)
        self.tabs.addTab(ts_widget, "Zeitreihen")

        # Tab Fahrten pro Tag
        self.daily_plot = DailyRidesPlot()
        self.tabs.addTab(self.daily_plot, "Fahrten pro Tag")

        # Tab Funktionsbeschreibung (gebündelte Markdown-Datei)
        self.help_tab = HelpTab(HELP_MD_PATH)
        self.tabs.addTab(self.help_tab, "Funktionsbeschreibung")

        self.date_from.dateChanged.connect(self._on_date_changed)
        self.date_to.dateChanged.connect(self._on_date_changed)

    def _qdate_to_date(self, qd: QDate) -> date:
        return date(qd.year(), qd.month(), qd.day())

    def _set_date_range_controls_from_data(self) -> None:
        if self._data_min_date is None:
            today = date.today()
            self._set_date_fields(today, today, reload=False)
            return
        today = date.today()
        date_to = today if today >= self._data_min_date else (self._data_max_date or self._data_min_date)
        self._set_date_fields(self._data_min_date, date_to, reload=False)

    def _set_date_fields(self, d_from: date, d_to: date, *, reload: bool) -> None:
        self._updating_dates = True
        try:
            self.date_from.setDate(QDate(d_from.year, d_from.month, d_from.day))
            self.date_to.setDate(QDate(d_to.year, d_to.month, d_to.day))
        finally:
            self._updating_dates = False
        if reload:
            self._reload_data()

    def _refresh_data_range(self) -> None:
        t_min, t_max = self.store.time_range()
        self._data_min_date = t_min.date() if t_min else None
        self._data_max_date = t_max.date() if t_max else None

    def _get_filter_range(self) -> tuple[date, date]:
        return self._qdate_to_date(self.date_from.date()), self._qdate_to_date(
            self.date_to.date()
        )

    def _reload_data(self) -> None:
        d_from, d_to = self._get_filter_range()
        if d_from > d_to:
            QMessageBox.warning(self, "Filter", "„Von“ muss vor „Bis“ liegen.")
            return

        df = self.store.load_measurements(date_from=d_from, date_to=d_to)
        self.timeseries_plot.set_data(df if not df.empty else None)
        self._refresh_plots()
        self.channel_panel.clear_cursor_values()

        daily = self.store.daily_rides(date_from=d_from, date_to=d_to)
        self.daily_plot.set_data(daily if not daily.empty else None)

        n = len(df)
        self._base_status_message = (
            f"{n} Messpunkte | {self.store.imported_file_count()} importierte Dateien"
        )
        self._status.showMessage(self._base_status_message)

    def _refresh_plots(self) -> None:
        channels = self.channel_panel.visible_channels()
        self.timeseries_plot.update_visible_channels(channels)

    def _on_channel_color_changed(self, channel: str, color_hex: str) -> None:
        self.channel_panel.set_channel_color(channel, color_hex)
        self.timeseries_plot.set_channel_color(channel, color_hex)
        self.settings.setValue(f"channel_colors/{channel}", color_hex)
        self._refresh_plots()

    def _show_daily_cursor_status(self, text: str) -> None:
        if self.tabs.currentWidget() is not self.daily_plot:
            return
        if text:
            self._status.showMessage(f"{self._base_status_message} | {text}")
        else:
            self._status.showMessage(self._base_status_message)

    def _restore_channel_colors(self) -> None:
        for channel in self.channel_panel.all_channels():
            saved_color = self.settings.value(f"channel_colors/{channel}", None)
            if isinstance(saved_color, str) and saved_color:
                self.channel_panel.set_channel_color(channel, saved_color)
                self.timeseries_plot.set_channel_color(channel, saved_color)
            else:
                default_color = self.timeseries_plot.get_channel_color(channel)
                self.channel_panel.set_channel_color(channel, default_color)

    def _zoom_to_dates(self) -> None:
        d_from, d_to = self._get_filter_range()
        t_from = datetime.combine(d_from, datetime.min.time())
        t_to = datetime.combine(d_to, datetime.max.time())
        if self.tabs.currentWidget() is self.daily_plot:
            self.daily_plot.zoom_to_range(t_from, t_to)
        else:
            self.timeseries_plot.zoom_to_range(t_from, t_to)

    def _reset_zoom(self) -> None:
        if self.tabs.currentWidget() is self.daily_plot:
            self.daily_plot.reset_zoom()
        else:
            self.timeseries_plot.reset_zoom()

    def _apply_selected_preset(self) -> None:
        label = self.preset_combo.currentText()
        if label == "Zeitraum-Preset…":
            return
        d_from, d_to = self._calculate_preset_range(label)
        self._set_date_fields(d_from, d_to, reload=True)

    def _on_preset_changed(self, _index: int) -> None:
        self._apply_selected_preset()

    def _on_date_changed(self, _date: QDate) -> None:
        if self._updating_dates:
            return
        self._reload_data()

    def _calculate_preset_range(self, preset: str) -> tuple[date, date]:
        today = date.today()
        if preset == "Heute":
            return self._clamp_to_data(today, today)
        if preset == "Diese Woche":
            monday = today - timedelta(days=today.weekday())
            return self._clamp_to_data(monday, today)
        if preset == "Letzte Woche":
            this_monday = today - timedelta(days=today.weekday())
            last_monday = this_monday - timedelta(days=7)
            last_sunday = this_monday - timedelta(days=1)
            return self._clamp_to_data(last_monday, last_sunday)
        if preset == "Letzter Monat":
            first_this_month = today.replace(day=1)
            last_prev_month = first_this_month - timedelta(days=1)
            first_prev_month = last_prev_month.replace(day=1)
            return self._clamp_to_data(first_prev_month, last_prev_month)
        if preset == "Letztes halbes Jahr":
            return self._clamp_to_data(today - timedelta(days=183), today)
        if preset == "Letztes Jahr":
            return self._clamp_to_data(self._subtract_years(today, 1), today)
        if preset == "Letzte 2 Jahre":
            return self._clamp_to_data(self._subtract_years(today, 2), today)
        if preset == "Letzte 5 Jahre":
            return self._clamp_to_data(self._subtract_years(today, 5), today)
        if preset == "Alle Daten":
            if self._data_min_date is None:
                return today, today
            return self._clamp_to_data(self._data_min_date, today)
        return self._clamp_to_data(today, today)

    def _clamp_to_data(self, d_from: date, d_to: date) -> tuple[date, date]:
        if self._data_min_date is None or self._data_max_date is None:
            return d_from, d_to
        d_from = max(d_from, self._data_min_date)
        upper_bound = max(self._data_max_date, date.today())
        d_to = min(d_to, upper_bound)
        if d_to < d_from:
            d_to = d_from
        return d_from, d_to

    def _subtract_years(self, d: date, years: int) -> date:
        try:
            return d.replace(year=d.year - years)
        except ValueError:
            # 29.02 -> 28.02 im Zieljahr
            return d.replace(month=2, day=28, year=d.year - years)

    def _offer_first_import(self) -> None:
        dlg = FirstImportDialog(self)
        if dlg.exec() == dlg.DialogCode.Accepted and dlg.selected_directory:
            result = run_import_with_progress(
                self, self.store, directory=dlg.selected_directory, only_new=False
            )
            show_import_summary(self, result)
        self._after_import()

    def _after_import(self) -> None:
        self._refresh_data_range()
        self._set_date_range_controls_from_data()
        self._reload_data()

    def _import_directory(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Log-Ordner wählen", str(LOG_FILES_DIR)
        )
        if not folder:
            return
        result = run_import_with_progress(
            self, self.store, directory=Path(folder), only_new=False
        )
        show_import_summary(self, result)
        self._after_import()

    def _import_new_only(self) -> None:
        result = run_import_with_progress(
            self, self.store, directory=LOG_FILES_DIR, only_new=True
        )
        show_import_summary(self, result)
        self._after_import()

    def _import_selected_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Log-Dateien wählen",
            str(LOG_FILES_DIR),
            "CSV Log (*.csv)",
        )
        if not files:
            return
        paths = [Path(f) for f in files]
        result = run_import_with_progress(
            self, self.store, file_paths=paths, force=True
        )
        show_import_summary(self, result)
        self._after_import()

    def _reset_cache(self) -> None:
        reply = QMessageBox.question(
            self,
            "Cache zurücksetzen",
            "Alle importierten Daten werden gelöscht.\nFortfahren?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.store.clear_all()
        if IMPORT_ERRORS_PATH.exists():
            IMPORT_ERRORS_PATH.write_text("", encoding="utf-8")
        QMessageBox.information(self, "Cache", "Cache wurde geleert.")
        self._after_import()

    def _show_error_log(self) -> None:
        if IMPORT_ERRORS_PATH.exists():
            text = IMPORT_ERRORS_PATH.read_text(encoding="utf-8").strip()
        else:
            text = "(Keine Fehler protokolliert.)"
        QMessageBox.information(self, "Import-Fehlerprotokoll", text or "(leer)")

    def _show_data_quality_dialog(self) -> None:
        empty_files = self.store.empty_import_files(limit=30)
        gaps = self.store.large_time_gaps(min_hours=12.0, limit=20)

        lines = []
        lines.append("Importstatus: Alle erkannten LogFile_*.csv wurden importiert.")
        lines.append("")

        lines.append(f"Leerdateien (nur Header, 0 Messzeilen): {len(empty_files)}")
        if not empty_files.empty:
            for name in empty_files["filename"].tolist()[:10]:
                lines.append(f"  - {name}")
            if len(empty_files) > 10:
                lines.append(f"  - ... und {len(empty_files) - 10} weitere")
        else:
            lines.append("  - Keine")

        lines.append("")
        lines.append(f"Zeitlücken > 12h: {len(gaps)}")
        if not gaps.empty:
            for _, row in gaps.head(8).iterrows():
                lines.append(
                    "  - "
                    f"{row['from_timestamp']} ({row['from_file']}) -> "
                    f"{row['to_timestamp']} ({row['to_file']}) | "
                    f"{row['gap_hours']:.1f}h"
                )
            if len(gaps) > 8:
                lines.append(f"  - ... und {len(gaps) - 8} weitere")
        else:
            lines.append("  - Keine")

        lines.append("")
        lines.append(
            "Hinweis: Die Lücken stammen aus den Rohdaten (leer/zeitlich unterbrochen), "
            "nicht von einem generellen Importfehler."
        )

        QMessageBox.information(self, "Datenqualität", "\n".join(lines))
