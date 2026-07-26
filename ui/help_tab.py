"""Hilfe-Tab: lädt Funktionsbeschreibung aus Markdown-Datei."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QHBoxLayout,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)


class HelpTab(QWidget):
    def __init__(self, markdown_path: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._markdown_path = markdown_path

        layout = QVBoxLayout(self)
        top_row = QHBoxLayout()
        self.reload_btn = QPushButton("Text neu laden")
        self.reload_btn.clicked.connect(self.reload_content)
        top_row.addWidget(self.reload_btn)
        top_row.addStretch()
        layout.addLayout(top_row)

        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(True)
        layout.addWidget(self.browser, stretch=1)

        self.reload_content()

    def reload_content(self) -> None:
        if not self._markdown_path.exists():
            self.browser.setMarkdown(
                "# Funktionsbeschreibung\n\n"
                "Die Datei für die Beschreibung wurde nicht gefunden:\n\n"
                f"`{self._markdown_path}`"
            )
            return

        content = self._markdown_path.read_text(encoding="utf-8")
        self.browser.setMarkdown(content)
