from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .emulator import SCENARIOS, ScenarioResult, run_scenarios


class CameraSchematic(QWidget):
    def __init__(self, title: str, reverse: bool = False) -> None:
        super().__init__()
        self.title = title
        self.reverse = reverse
        self.setMinimumSize(420, 260)

    def paintEvent(self, event) -> None:  # noqa: N802
        _ = event
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(24, 24, 27))
        painter.setPen(QColor(235, 235, 235))
        painter.drawText(18, 28, self.title)
        y = self.height() // 2
        painter.setPen(QPen(QColor(255, 190, 0), 3))
        painter.drawLine(30, y, self.width() - 30, y)
        painter.setPen(QColor(180, 180, 180))
        painter.drawText(35, y - 40, "Zone A")
        painter.drawText(35, y + 55, "Zone B")
        arrow = "B -> A (OUT)" if self.reverse else "A -> B (IN)"
        painter.drawText(self.width() - 150, 28, arrow)
        painter.setPen(QPen(QColor(70, 200, 120), 2))
        cx = self.width() // 2
        cy = y + (60 if self.reverse else -60)
        painter.drawRect(cx - 35, cy - 55, 70, 110)
        painter.drawText(cx - 30, cy + 4, "Person")


class EmulatorWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Personenzaehler Digital Twin Emulator")
        self.resize(1250, 820)
        root = QWidget()
        layout = QVBoxLayout(root)

        header = QHBoxLayout()
        title = QLabel("Hardware-freier Digital Twin")
        title.setStyleSheet("font-size:24px;font-weight:bold;")
        header.addWidget(title, 1)
        self.scenario = QComboBox()
        self.scenario.addItems(sorted(SCENARIOS))
        header.addWidget(self.scenario)
        run_one = QPushButton("Szenario testen")
        run_one.clicked.connect(self.run_selected)
        header.addWidget(run_one)
        run_all = QPushButton("Alle Tests")
        run_all.clicked.connect(self.run_all)
        header.addWidget(run_all)
        layout.addLayout(header)

        camera_row = QHBoxLayout()
        camera_row.addWidget(CameraSchematic("Kamera 1 / Eingang", reverse=False))
        camera_row.addWidget(CameraSchematic("Kamera 2 / Ausgang", reverse=True))
        layout.addLayout(camera_row)

        status_group = QGroupBox("Emulierte Komponenten")
        status_grid = QGridLayout(status_group)
        components = [
            ("WLAN/IP-Kameras", "RTSP-/Netzwerkausfall wird als Frame-Ausfall emuliert"),
            ("YOLO26m/Hailo", "Detektionen, Konfidenz und Totalausfall werden synthetisch erzeugt"),
            ("Tracker", "echter Tracker-Code aus dem Repository"),
            ("OSNet ReID", "deterministische Embeddings + Ausfall/Look-alike-Faelle"),
            ("Zonenlogik", "echte A/neutral/B-Logik aus dem Repository"),
            ("Dual-Camera Consensus", "echter Consensus-Code aus dem Repository"),
        ]
        for row, (name, value) in enumerate(components):
            status_grid.addWidget(QLabel(name), row, 0)
            status_grid.addWidget(QLabel(value), row, 1)
        layout.addWidget(status_group)

        self.results = QTableWidget(0, 4)
        self.results.setHorizontalHeaderLabels(["Szenario", "Status", "Erwartet", "Ist"])
        self.results.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.results, 1)

        self.details = QTextEdit()
        self.details.setReadOnly(True)
        self.details.setMaximumHeight(150)
        layout.addWidget(self.details)
        self.setCentralWidget(root)

    def run_selected(self) -> None:
        self._show_results(run_scenarios([self.scenario.currentText()]))

    def run_all(self) -> None:
        self._show_results(run_scenarios(list(SCENARIOS)))

    def _show_results(self, results: list[ScenarioResult]) -> None:
        self.results.setRowCount(len(results))
        details: list[str] = []
        for row, result in enumerate(results):
            values = [
                result.name,
                "PASS" if result.passed else "FAIL",
                str(result.expected),
                str(result.actual),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 1:
                    item.setTextAlignment(Qt.AlignCenter)
                    item.setBackground(QColor(80, 170, 100) if result.passed else QColor(190, 80, 80))
                self.results.setItem(row, column, item)
            if result.diagnostics:
                details.append(result.name + ": " + " | ".join(result.diagnostics))
        passed = sum(result.passed for result in results)
        details.insert(0, f"Ergebnis: {passed}/{len(results)} Szenarien bestanden")
        self.details.setPlainText("\n".join(details))


def main() -> int:
    app = QApplication.instance() or QApplication([])
    window = EmulatorWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
