from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QGridLayout, QLabel, QMainWindow, QVBoxLayout, QWidget


class _ValueLabel(QLabel):
    def __init__(self, text: str = "-") -> None:
        super().__init__(text)
        font = QFont()
        font.setPointSize(34)
        font.setBold(True)
        self.setFont(font)
        self.setAlignment(Qt.AlignCenter)


class OccupancyWindow(QMainWindow):
    """Display 1: large anonymous occupancy counters only."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Personenzaehler - Belegung")
        root = QWidget()
        layout = QVBoxLayout(root)
        title = QLabel("AKTUELLE BELEGUNG")
        title.setAlignment(Qt.AlignCenter)
        title_font = QFont()
        title_font.setPointSize(28)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)
        self.inside = _ValueLabel("-")
        self.inside.setStyleSheet("font-size:110px;font-weight:800;")
        layout.addWidget(self.inside, 1)
        grid = QGridLayout()
        grid.addWidget(QLabel("Heute / Gesamt Eintritte"), 0, 0)
        grid.addWidget(QLabel("Heute / Gesamt Austritte"), 0, 1)
        self.entered = _ValueLabel("-")
        self.exited = _ValueLabel("-")
        grid.addWidget(self.entered, 1, 0)
        grid.addWidget(self.exited, 1, 1)
        layout.addLayout(grid)
        self.setCentralWidget(root)

    def update_status(self, payload: dict[str, Any]) -> None:
        counts = payload.get("counts", {})
        self.inside.setText(str(counts.get("inside", "-")))
        self.entered.setText(str(counts.get("entered", "-")))
        self.exited.setText(str(counts.get("exited", "-")))


class SystemWindow(QMainWindow):
    """Display 2: camera/AI health without live video or personal data."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Personenzaehler - Systemstatus")
        root = QWidget()
        self.layout = QVBoxLayout(root)
        title = QLabel("SYSTEMSTATUS")
        title.setAlignment(Qt.AlignCenter)
        title_font = QFont()
        title_font.setPointSize(28)
        title_font.setBold(True)
        title.setFont(title_font)
        self.layout.addWidget(title)
        self.summary = QLabel("Warte auf Laufzeitdaten …")
        self.summary.setWordWrap(True)
        self.summary.setFont(QFont("Sans Serif", 18))
        self.layout.addWidget(self.summary, 1)
        self.setCentralWidget(root)

    def update_status(self, payload: dict[str, Any]) -> None:
        runtime = payload.get("runtime", {})
        cameras = payload.get("cameras", [])
        lines: list[str] = []
        for camera in cameras:
            name = camera.get("name") or camera.get("camera_id", "Kamera")
            lines.append(
                f"{name}: {camera.get('status', '-')} | "
                f"{camera.get('actual_fps', '-')} FPS | "
                f"Reconnects {camera.get('reconnect_count', '-')} | "
                f"Decodefehler {camera.get('decode_errors', '-')}"
            )
        lines.extend(
            [
                "",
                f"KI: {runtime.get('hailo_status', '-')}",
                f"Inferenz: {runtime.get('inference_fps', '-')} FPS | {runtime.get('hailo_latency_ms', '-')} ms",
                f"End-to-End: {runtime.get('total_latency_ms', '-')} ms",
                f"OSNet: {runtime.get('reid_status', '-')} | {runtime.get('reid_latency_ms', '-')} ms",
                f"OSNet Aufrufe: {runtime.get('reid_inference_count', '-')}",
                f"Frame-Queue: {runtime.get('queue_length', '-')}",
            ]
        )
        self.summary.setText("\n".join(lines))


class DualDisplayController:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.status_path = project_root / "data" / "live_status.json"
        self.occupancy = OccupancyWindow()
        self.system = SystemWindow()
        self.timer = QTimer()
        self.timer.timeout.connect(self.refresh)
        self.timer.start(500)
        self._position_windows()
        self.refresh()

    def _position_windows(self) -> None:
        screens = QApplication.screens()
        windows = (self.occupancy, self.system)
        for index, window in enumerate(windows):
            screen = screens[min(index, len(screens) - 1)] if screens else None
            if screen is not None:
                window.setGeometry(screen.geometry())
            window.showFullScreen()

    def refresh(self) -> None:
        try:
            payload = json.loads(self.status_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            self.occupancy.inside.setText("-")
            self.system.summary.setText("Keine aktuellen Laufzeitdaten vom Personenzaehler.")
            return
        self.occupancy.update_status(payload)
        self.system.update_status(payload)


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    project_root = Path.cwd().resolve()
    controller = DualDisplayController(project_root)
    app._visitor_counter_display_controller = controller  # type: ignore[attr-defined]
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
