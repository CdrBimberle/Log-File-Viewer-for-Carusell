"""Checkbox-Panel für Kanalauswahl."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QColorDialog,
    QCheckBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from config import (
    CHANNEL_GROUPS,
    COUNTER_CHANNELS,
    DEFAULT_VISIBLE_CHANNELS,
    MEASUREMENT_COLUMNS,
    OIL_LEVEL_CHANNELS,
    TEMPERATURE_CHANNELS,
)


class ChannelPanel(QWidget):
    visibility_changed = Signal()
    color_changed = Signal(str, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._checkboxes: dict[str, QCheckBox] = {}
        self._color_buttons: dict[str, QPushButton] = {}
        self._value_labels: dict[str, QLabel] = {}
        self._channel_colors: dict[str, str] = {}
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(220)
        inner = QWidget()
        inner_layout = QVBoxLayout(inner)

        btn_row = QWidget()
        btn_layout = QVBoxLayout(btn_row)
        btn_layout.setContentsMargins(0, 0, 0, 0)
        all_on = QPushButton("Alle an")
        all_off = QPushButton("Alle aus")
        all_on.clicked.connect(self.select_all)
        all_off.clicked.connect(self.select_none)
        btn_layout.addWidget(all_on)
        btn_layout.addWidget(all_off)
        inner_layout.addWidget(btn_row)

        for group_name, channels in CHANNEL_GROUPS.items():
            box = QGroupBox(group_name)
            box_layout = QVBoxLayout(box)
            for ch in channels:
                if ch not in MEASUREMENT_COLUMNS:
                    continue
                row = QWidget()
                row_layout = QHBoxLayout(row)
                row_layout.setContentsMargins(0, 0, 0, 0)

                cb = QCheckBox(ch)
                cb.setChecked(ch in DEFAULT_VISIBLE_CHANNELS)
                cb.stateChanged.connect(self._on_changed)
                self._checkboxes[ch] = cb

                value_label = QLabel("-")
                value_label.setMinimumWidth(86)
                value_label.setStyleSheet("color: #ffffff;")
                self._value_labels[ch] = value_label

                color_btn = QPushButton("Farbe…")
                color_btn.setMaximumWidth(70)
                color_btn.clicked.connect(
                    lambda _checked=False, channel=ch: self._choose_color(channel)
                )
                self._color_buttons[ch] = color_btn
                self._set_button_color(ch, "#000000")

                row_layout.addWidget(cb, stretch=1)
                row_layout.addWidget(value_label, stretch=0)
                row_layout.addWidget(color_btn, stretch=0)
                box_layout.addWidget(row)
            inner_layout.addWidget(box)

        inner_layout.addStretch()
        scroll.setWidget(inner)
        layout.addWidget(scroll)

    def _on_changed(self) -> None:
        self.clear_cursor_values()
        self.visibility_changed.emit()

    def select_all(self) -> None:
        for cb in self._checkboxes.values():
            cb.setChecked(True)

    def select_none(self) -> None:
        for cb in self._checkboxes.values():
            cb.setChecked(False)

    def visible_channels(self) -> list[str]:
        return [name for name, cb in self._checkboxes.items() if cb.isChecked()]

    def all_channels(self) -> list[str]:
        return list(self._checkboxes.keys())

    def set_channel_color(self, channel: str, color_hex: str) -> None:
        if channel not in self._color_buttons:
            return
        self._set_button_color(channel, color_hex)

    def channel_color(self, channel: str) -> str | None:
        return self._channel_colors.get(channel)

    def _choose_color(self, channel: str) -> None:
        current = QColor(self._channel_colors.get(channel, "#000000"))
        color = QColorDialog.getColor(current, self, f"Farbe wählen: {channel}")
        if not color.isValid():
            return
        color_hex = color.name()
        self._set_button_color(channel, color_hex)
        self.color_changed.emit(channel, color_hex)

    def _set_button_color(self, channel: str, color_hex: str) -> None:
        self._channel_colors[channel] = color_hex
        btn = self._color_buttons.get(channel)
        if btn is None:
            return
        btn.setStyleSheet(
            "QPushButton {"
            f"background-color: {color_hex};"
            "border: 1px solid #666;"
            "padding: 2px 6px;"
            "}"
        )

    def set_cursor_values(self, values: dict[str, float]) -> None:
        for channel, label in self._value_labels.items():
            cb = self._checkboxes.get(channel)
            if cb is None or not cb.isChecked():
                label.setText("-")
                continue
            if channel not in values:
                label.setText("-")
                continue

            val = float(values[channel])
            if channel in TEMPERATURE_CHANNELS:
                label.setText(f"{val:.1f} °C")
            elif channel in OIL_LEVEL_CHANNELS:
                label.setText(f"{val:.2f}/10")
            elif channel in COUNTER_CHANNELS:
                label.setText(f"{val:.0f}")
            else:
                label.setText(f"{val:.2f}")

    def clear_cursor_values(self) -> None:
        for label in self._value_labels.values():
            label.setText("-")
