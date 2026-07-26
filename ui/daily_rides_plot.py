"""Diagramm „Fahrten pro Tag“."""
from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd
import pyqtgraph as pg
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from config import LOG_FILES_DIR


class DailyRidesPlot(QWidget):
    cursor_value_changed = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._df: pd.DataFrame | None = None

        layout = QVBoxLayout(self)
        toolbar = QHBoxLayout()
        self.export_btn = QPushButton("Als CSV exportieren…")
        self.export_btn.clicked.connect(self._export_csv)
        self.export_btn.setEnabled(False)
        toolbar.addWidget(self.export_btn)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        date_axis = pg.DateAxisItem(orientation="bottom")
        self.plot_widget = pg.PlotWidget(axisItems={"bottom": date_axis})
        self.plot_widget.setBackground("w")
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.plot_widget.getViewBox().setMouseMode(pg.ViewBox.RectMode)
        self.plot_widget.setLabel("bottom", "Datum")
        self.plot_widget.setLabel("left", "Tages Zähler (max)")
        self.plot_widget.setTitle("Fahrten pro Tag")
        layout.addWidget(self.plot_widget, stretch=1)

        self._bar_item: pg.BarGraphItem | None = None
        self._line_item: pg.PlotDataItem | None = None
        self._x_min: float | None = None
        self._x_max: float | None = None
        self._x_values: np.ndarray | None = None
        self._y_values: np.ndarray | None = None

        self.cursor_line = pg.InfiniteLine(
            angle=90, movable=False, pen=pg.mkPen((80, 80, 80), width=1)
        )
        self.cursor_line.hide()
        self.plot_widget.addItem(self.cursor_line, ignoreBounds=True)

        self.cursor_hline = pg.InfiniteLine(
            angle=0, movable=False, pen=pg.mkPen((80, 80, 80), width=1)
        )
        self.cursor_hline.hide()
        self.plot_widget.addItem(self.cursor_hline, ignoreBounds=True)

        self._proxy = pg.SignalProxy(
            self.plot_widget.scene().sigMouseMoved,
            rateLimit=30,
            slot=self._on_mouse_moved,
        )

    def set_data(self, df: pd.DataFrame | None) -> None:
        self._df = df
        self.plot_widget.clear()
        self.plot_widget.addItem(self.cursor_line, ignoreBounds=True)
        self.plot_widget.addItem(self.cursor_hline, ignoreBounds=True)
        self._bar_item = None
        self._line_item = None
        self.export_btn.setEnabled(df is not None and not df.empty)
        self.cursor_line.hide()
        self.cursor_hline.hide()
        self.plot_widget.setLabel("left", "Tages Zähler (max)")

        if df is None or df.empty:
            self._x_min = None
            self._x_max = None
            self._x_values = None
            self._y_values = None
            return

        x = self._to_epoch_series(df["Datum"])
        y = df["Tages Zähler"].astype(float).values
        self._x_values = np.asarray(x, dtype=float)
        self._y_values = np.asarray(y, dtype=float)

        self._line_item = self.plot_widget.plot(
            x, y, pen=pg.mkPen(41, 128, 185, width=2), symbol="o", symbolSize=7
        )
        day_seconds = 86400.0
        point_count = len(x)
        bar_width = day_seconds * (0.65 if point_count <= 2 else 0.85)
        self._bar_item = pg.BarGraphItem(
            x=x,
            height=y,
            width=bar_width,
            brush=pg.mkBrush(52, 152, 219, 80),
            pen=pg.mkPen(52, 152, 219, 120),
        )
        self.plot_widget.addItem(self._bar_item)

        x_min = float(x.min())
        x_max = float(x.max())
        self._x_min = x_min
        self._x_max = x_max
        if point_count == 1:
            padding = day_seconds
        else:
            padding = day_seconds * 0.6
        self.plot_widget.setXRange(x_min - padding, x_max + padding, padding=0.0)

    def _export_csv(self) -> None:
        if self._df is None or self._df.empty:
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Fahrten pro Tag exportieren",
            str(LOG_FILES_DIR / "fahrten_pro_tag.csv"),
            "CSV (*.csv)",
        )
        if path:
            export = self._df.copy()
            export["Datum"] = export["Datum"].astype(str)
            export.to_csv(path, sep=";", index=False, encoding="utf-8-sig")

    def _to_epoch_series(self, series: pd.Series) -> pd.Series:
        s = pd.to_datetime(series)
        return pd.Series([float(pd.Timestamp(v).value / 10**9) for v in s])

    def zoom_to_range(self, date_from: datetime, date_to: datetime) -> None:
        if self._x_min is None or self._x_max is None:
            return
        x0 = float(pd.Timestamp(date_from).value / 10**9)
        x1 = float(pd.Timestamp(date_to).value / 10**9)
        x0, x1 = sorted((x0, x1))
        x0 = max(self._x_min, x0)
        x1 = min(self._x_max, x1)
        if x1 <= x0:
            x0, x1 = self._x_min, self._x_max
        self.plot_widget.setXRange(x0, x1, padding=0.02)

    def reset_zoom(self) -> None:
        if self._x_min is None or self._x_max is None:
            return
        padding = 86400.0 * 0.6
        if self._x_min == self._x_max:
            padding = 86400.0
        self.plot_widget.setXRange(
            self._x_min - padding,
            self._x_max + padding,
            padding=0.0,
        )

    def _on_mouse_moved(self, evt) -> None:
        if self._df is None or self._x_values is None or self._y_values is None:
            return
        pos = evt[0]
        if not self.plot_widget.plotItem.vb.sceneBoundingRect().contains(pos):
            self.cursor_line.hide()
            self.cursor_hline.hide()
            self.plot_widget.setLabel("left", "Tages Zähler (max)")
            self.cursor_value_changed.emit("")
            return

        mouse_point = self.plot_widget.plotItem.vb.mapSceneToView(pos)
        x = mouse_point.x()
        y = mouse_point.y()
        idx = int(np.argmin(np.abs(self._x_values - x)))
        if idx < 0 or idx >= len(self._x_values):
            self.cursor_line.hide()
            self.cursor_hline.hide()
            self.plot_widget.setLabel("left", "Tages Zähler (max)")
            self.cursor_value_changed.emit("")
            return

        x_cursor = float(self._x_values[idx])
        y_cursor = float(self._y_values[idx])

        self.cursor_line.setPos(x_cursor)
        self.cursor_hline.setPos(y)
        self.cursor_line.show()
        self.cursor_hline.show()
        date_text = pd.to_datetime(self._df.iloc[idx]["Datum"]).strftime("%Y-%m-%d")
        self.plot_widget.setLabel("left", f"Tages Zähler (max): {int(round(y_cursor))}")
        self.cursor_value_changed.emit(
            f"{date_text} | Tages Zähler: {int(round(y_cursor))}"
        )
