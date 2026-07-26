"""Interaktives Zeitreihen-Diagramm mit pyqtgraph."""
from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd
import pyqtgraph as pg
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget

from config import COUNTER_CHANNELS, OIL_LEVEL_CHANNELS, TIMESTAMP_COL

_DEFAULT_COLORS = [
    (231, 76, 60),
    (52, 152, 219),
    (46, 204, 113),
    (241, 196, 15),
    (155, 89, 182),
    (230, 126, 34),
    (26, 188, 156),
    (149, 165, 166),
    (192, 57, 43),
    (41, 128, 185),
]


class TimeSeriesPlot(QWidget):
    cursor_moved = Signal(str)
    cursor_values_changed = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._df: pd.DataFrame | None = None
        self._curves: dict[str, tuple[pg.PlotDataItem, str]] = {}
        self._x_numeric: np.ndarray | None = None
        self._region: pg.LinearRegionItem | None = None
        self._x_min: float | None = None
        self._x_max: float | None = None
        self._channel_colors: dict[str, str] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        date_axis = pg.DateAxisItem(orientation="bottom")
        self.plot_widget = pg.PlotWidget(axisItems={"bottom": date_axis})
        self.plot_widget.setBackground("w")
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.plot_widget.getViewBox().setMouseMode(pg.ViewBox.RectMode)
        self.plot_widget.setLabel("bottom", "Zeit")
        self.plot_widget.setLabel("left", "Temperatur / Füllstand")
        self.plot_widget.addLegend(offset=(10, 10))

        self.plot_widget_right = pg.ViewBox()
        self.plot_widget.scene().addItem(self.plot_widget_right)
        self.plot_widget.getAxis("right").linkToView(self.plot_widget_right)
        self.plot_widget_right.setXLink(self.plot_widget)
        self.plot_widget.showAxis("right")
        self.plot_widget.getAxis("right").setLabel("Zähler / Runden")

        self.plot_widget_oil = pg.ViewBox()
        self.plot_widget.scene().addItem(self.plot_widget_oil)
        self.plot_widget_oil.setXLink(self.plot_widget)
        self.axis_oil = pg.AxisItem("right")
        self.plot_widget.plotItem.layout.addItem(self.axis_oil, 2, 3)
        self.axis_oil.linkToView(self.plot_widget_oil)
        self.axis_oil.setLabel("Öl Füllstand")
        self.axis_oil.hide()
        self.plot_widget_oil.setVisible(False)

        self.cursor_line = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen((80, 80, 80), width=1))
        self.cursor_line.hide()
        self.plot_widget.addItem(self.cursor_line, ignoreBounds=True)

        self.cursor_hline = pg.InfiniteLine(angle=0, movable=False, pen=pg.mkPen((80, 80, 80), width=1))
        self.cursor_hline.hide()
        self.plot_widget.addItem(self.cursor_hline, ignoreBounds=True)

        layout.addWidget(self.plot_widget, stretch=1)

        self.plot_widget.getViewBox().sigResized.connect(self._update_view_geometry)
        self._proxy = pg.SignalProxy(
            self.plot_widget.scene().sigMouseMoved,
            rateLimit=30,
            slot=self._on_mouse_moved,
        )

    def _update_view_geometry(self) -> None:
        self.plot_widget_right.setGeometry(
            self.plot_widget.getViewBox().sceneBoundingRect()
        )
        self.plot_widget_right.linkedViewChanged(
            self.plot_widget.getViewBox(), self.plot_widget_right.XAxis
        )
        self.plot_widget_oil.setGeometry(
            self.plot_widget.getViewBox().sceneBoundingRect()
        )
        self.plot_widget_oil.linkedViewChanged(
            self.plot_widget.getViewBox(), self.plot_widget_oil.XAxis
        )

    def set_data(self, df: pd.DataFrame | None) -> None:
        self._df = df
        self._curves.clear()
        self.plot_widget.clear()
        self.plot_widget.addItem(self.cursor_line, ignoreBounds=True)
        self.plot_widget.addItem(self.cursor_hline, ignoreBounds=True)
        self.plot_widget.addLegend(offset=(10, 10))
        self.plot_widget_right.clear()
        self.plot_widget_oil.clear()
        self.cursor_line.hide()
        self.cursor_hline.hide()

        if self._region is not None:
            self.plot_widget.removeItem(self._region)
            self._region = None

        if df is None or df.empty:
            self._x_numeric = None
            self._x_min = None
            self._x_max = None
            return

        self._x_numeric = self._to_epoch_series(df[TIMESTAMP_COL])
        t_min, t_max = float(self._x_numeric.min()), float(self._x_numeric.max())
        self._x_min, self._x_max = t_min, t_max
        self.plot_widget.setXRange(t_min, t_max, padding=0.02)

        self._region = pg.LinearRegionItem(
            values=[t_min, t_max],
            brush=pg.mkBrush(80, 80, 200, 40),
            movable=True,
        )
        self._region.sigRegionChanged.connect(self._on_region_changed)
        self._region.sigRegionChangeFinished.connect(self._on_region_changed)
        self.plot_widget.addItem(self._region, ignoreBounds=True)

        self.update_visible_channels([])

    def update_visible_channels(self, channels: list[str]) -> None:
        if self._df is None or self._x_numeric is None:
            return

        df = self._df
        x = self._x_numeric

        visible_set = set(channels)
        for name in list(self._curves.keys()):
            if name not in visible_set:
                curve, axis_key = self._curves.pop(name)
                if axis_key == "counter":
                    self.plot_widget_right.removeItem(curve)
                elif axis_key == "oil":
                    self.plot_widget_oil.removeItem(curve)
                else:
                    self.plot_widget.removeItem(curve)

        for ch in channels:
            if ch not in df.columns:
                continue
            y = df[ch].astype(float).values
            color = self._color_for_channel(ch)
            pen = pg.mkPen(color=color, width=2)

            if ch in self._curves:
                curve, _axis_key = self._curves[ch]
                curve.setData(x, y)
                curve.setPen(pen)
                curve.setVisible(True)
                continue

            curve = pg.PlotDataItem(x, y, pen=pen, name=ch)
            axis_key = "main"
            if ch in OIL_LEVEL_CHANNELS:
                axis_key = "oil"
                self.plot_widget_oil.addItem(curve)
            elif ch in COUNTER_CHANNELS:
                axis_key = "counter"
                self.plot_widget_right.addItem(curve)
            else:
                self.plot_widget.addItem(curve)
            self._curves[ch] = (curve, axis_key)

        self.plot_widget_oil.setVisible(any(ch in OIL_LEVEL_CHANNELS for ch in channels))
        if self.plot_widget_oil.isVisible():
            self.axis_oil.show()
        else:
            self.axis_oil.hide()

        self._autoscale_y_axes()
        self._update_view_geometry()

    def set_channel_color(self, channel: str, color_hex: str) -> None:
        self._channel_colors[channel] = color_hex
        if channel in self._curves:
            curve, _axis_key = self._curves[channel]
            curve.setPen(pg.mkPen(color=self._color_for_channel(channel), width=2))

    def get_channel_color(self, channel: str) -> str:
        return self._channel_colors.get(channel, self._default_color_for_channel(channel))

    def zoom_to_range(self, t_from: datetime, t_to: datetime) -> None:
        if self._x_min is None or self._x_max is None:
            return
        x0 = self._datetime_to_epoch_seconds(t_from)
        x1 = self._datetime_to_epoch_seconds(t_to)
        x0, x1 = sorted((x0, x1))
        x0 = max(self._x_min, x0)
        x1 = min(self._x_max, x1)
        if x1 <= x0:
            x0, x1 = self._x_min, self._x_max
        self.plot_widget.setXRange(x0, x1, padding=0.02)
        if self._region is not None:
            self._region.blockSignals(True)
            self._region.setRegion([x0, x1])
            self._region.blockSignals(False)

    def reset_zoom(self) -> None:
        if self._x_numeric is None:
            return
        t_min = float(self._x_numeric.min())
        t_max = float(self._x_numeric.max())
        self.plot_widget.setXRange(t_min, t_max, padding=0.02)
        if self._region is not None:
            self._region.blockSignals(True)
            self._region.setRegion([t_min, t_max])
            self._region.blockSignals(False)

    def _on_region_changed(self) -> None:
        if self._region is None:
            return
        lo, hi = self._region.getRegion()
        if self._x_min is not None and self._x_max is not None:
            lo = max(self._x_min, lo)
            hi = min(self._x_max, hi)
        self.plot_widget.setXRange(lo, hi, padding=0)

    def _on_mouse_moved(self, evt) -> None:
        if self._df is None or self._x_numeric is None:
            return
        pos = evt[0]
        if not self.plot_widget.plotItem.vb.sceneBoundingRect().contains(pos):
            self.cursor_line.hide()
            self.cursor_hline.hide()
            self.cursor_values_changed.emit({})
            return
        mouse_point = self.plot_widget.plotItem.vb.mapSceneToView(pos)
        x = mouse_point.x()
        y = mouse_point.y()
        idx = int(np.argmin(np.abs(self._x_numeric - x)))
        if idx < 0 or idx >= len(self._df):
            self.cursor_line.hide()
            self.cursor_hline.hide()
            self.cursor_values_changed.emit({})
            return
        row = self._df.iloc[idx]
        ts = row[TIMESTAMP_COL]
        values: dict[str, float] = {}
        for ch, (curve, _axis_key) in self._curves.items():
            if curve.isVisible() and ch in self._df.columns:
                val = row[ch]
                if pd.notna(val):
                    values[ch] = float(val)

        x_cursor = float(self._x_numeric[idx])
        self.cursor_line.setPos(x_cursor)
        self.cursor_hline.setPos(y)
        self.cursor_line.show()
        self.cursor_hline.show()

        self.cursor_moved.emit(ts.strftime("%Y-%m-%d %H:%M:%S"))
        self.cursor_values_changed.emit(values)

    def _datetime_to_epoch_seconds(self, dt: datetime) -> float:
        return float(pd.Timestamp(dt).value / 10**9)

    def _to_epoch_series(self, series: pd.Series) -> np.ndarray:
        s = pd.to_datetime(series).astype("datetime64[ns]")
        return np.array([float(pd.Timestamp(v).value / 10**9) for v in s])

    def _autoscale_y_axes(self) -> None:
        self._autoscale_for_axis("main", self.plot_widget.plotItem.vb)
        self._autoscale_for_axis("counter", self.plot_widget_right)
        self._autoscale_for_axis("oil", self.plot_widget_oil)

    def _autoscale_for_axis(self, axis_key: str, view_box: pg.ViewBox) -> None:
        ys: list[np.ndarray] = []
        for curve, c_axis_key in self._curves.values():
            if c_axis_key != axis_key:
                continue
            x_data, y_data = curve.getData()
            if y_data is None:
                continue
            y_arr = np.asarray(y_data, dtype=float)
            y_arr = y_arr[~np.isnan(y_arr)]
            if y_arr.size > 0:
                ys.append(y_arr)

        if not ys:
            return

        merged = np.concatenate(ys)
        y_min = float(np.nanmin(merged))
        y_max = float(np.nanmax(merged))
        if y_min == y_max:
            pad = max(abs(y_min) * 0.05, 1.0)
            y_min -= pad
            y_max += pad
        else:
            pad = (y_max - y_min) * 0.08
            y_min -= pad
            y_max += pad

        view_box.setYRange(y_min, y_max, padding=0.0)

    def _color_for_channel(self, channel: str) -> str:
        return self._channel_colors.get(channel, self._default_color_for_channel(channel))

    def _default_color_for_channel(self, channel: str) -> str:
        idx = abs(hash(channel)) % len(_DEFAULT_COLORS)
        rgb = _DEFAULT_COLORS[idx]
        return "#{:02x}{:02x}{:02x}".format(*rgb)
