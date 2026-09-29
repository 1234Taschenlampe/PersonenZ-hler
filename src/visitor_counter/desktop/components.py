from __future__ import annotations

from typing import Any, ClassVar

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from .theme import DARK, LIGHT


class Card(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("card", True)


class MetricCard(Card):
    def __init__(self, title: str, value: str = "—", detail: str = "") -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(5)
        self.title_label = QLabel(title)
        self.title_label.setProperty("muted", True)
        self.value_label = QLabel(value)
        self.value_label.setProperty("metric", True)
        self.detail_label = QLabel(detail)
        self.detail_label.setProperty("muted", True)
        self.detail_label.setWordWrap(True)
        layout.addWidget(self.title_label)
        layout.addWidget(self.value_label)
        layout.addWidget(self.detail_label)

    def set_value(self, value: Any, detail: str | None = None) -> None:
        self.value_label.setText("—" if value is None else str(value))
        if detail is not None:
            self.detail_label.setText(detail)


class StatusBadge(QLabel):
    _COLORS: ClassVar[dict[str, tuple[str, str]]] = {
        "ok": ("#dff6dd", "#0f6f0f"),
        "warning": ("#fff4ce", "#7a4f00"),
        "error": ("#fde7e9", "#a4262c"),
        "neutral": ("#e8eaed", "#4a4f55"),
    }

    def __init__(self, text: str = "Unbekannt", state: str = "neutral") -> None:
        super().__init__(text)
        self.setAlignment(Qt.AlignCenter)
        self.set_state(state, text)

    def set_state(self, state: str, text: str | None = None) -> None:
        background, foreground = self._COLORS.get(state, self._COLORS["neutral"])
        self.setStyleSheet(
            f"background:{background};color:{foreground};padding:3px 7px;border-radius:4px;font-weight:600;"
        )
        if text is not None:
            self.setText(text)


class PageHeader(QWidget):
    def __init__(self, title: str, subtitle: str = "") -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 8)
        title_label = QLabel(title)
        title_label.setProperty("title", True)
        subtitle_label = QLabel(subtitle)
        subtitle_label.setProperty("muted", True)
        subtitle_label.setWordWrap(True)
        layout.addWidget(title_label)
        if subtitle:
            layout.addWidget(subtitle_label)


class HistoryChart(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setMinimumHeight(220)
        self._values: list[dict[str, Any]] = []
        self.dark = False

    def set_values(self, values: list[dict[str, Any]], *, dark: bool = False) -> None:
        self._values = values
        self.dark = dark
        self.update()

    def paintEvent(self, event: Any) -> None:  # noqa: N802
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        colors = DARK if self.dark else LIGHT
        rect = self.rect().adjusted(24, 20, -18, -28)
        painter.setPen(QPen(QColor(colors["border"]), 1))
        painter.drawLine(rect.bottomLeft(), rect.bottomRight())
        if not self._values:
            painter.setPen(QColor(colors["muted"]))
            painter.drawText(rect, Qt.AlignCenter, "Noch keine Verlaufsdaten")
            return
        maximum = max(
            1,
            max(
                int(item.get("entries", 0)) + int(item.get("exits", 0))
                for item in self._values
            ),
        )
        slot = rect.width() / max(1, len(self._values))
        width = max(2.0, slot * 0.58)
        for index, item in enumerate(self._values):
            entries = int(item.get("entries", 0))
            exits = int(item.get("exits", 0))
            total = entries + exits
            height = rect.height() * total / maximum
            x = rect.left() + index * slot + (slot - width) / 2
            y = rect.bottom() - height
            path = QPainterPath()
            path.addRoundedRect(x, y, width, height, 3, 3)
            painter.fillPath(path, QColor(colors["accent"]))


def labeled_row(label: str, value: QWidget) -> QWidget:
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    text = QLabel(label)
    text.setProperty("muted", True)
    layout.addWidget(text)
    layout.addStretch()
    layout.addWidget(value)
    return row
