from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PERSONENZAEHLER_SKIP_WIZARD", "1")

from PySide6.QtWidgets import QApplication

from visitor_counter.desktop.main_window import MainWindow
from visitor_counter.desktop.pages import OverviewPage
from visitor_counter.desktop.theme import apply_theme
from visitor_counter.runtime_paths import RuntimePaths


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="personenzaehler-shot-") as directory:
        temporary = Path(directory)
        paths = RuntimePaths.discover(
            root,
            environ={
                "PERSONENZAEHLER_CONFIG_FILE": str(root / "config" / "config.yaml"),
                "PERSONENZAEHLER_DATA_DIR": str(temporary / "data"),
                "PERSONENZAEHLER_LOG_DIR": str(temporary / "logs"),
                "PERSONENZAEHLER_CACHE_DIR": str(temporary / "cache"),
                "PERSONENZAEHLER_STATE_DIR": str(temporary / "state"),
                "PERSONENZAEHLER_LICENSE_FILE": str(temporary / "license.json"),
                "PERSONENZAEHLER_LICENSE_PUBLIC_KEY": str(
                    root / "config" / "license_public_key.pem"
                ),
            },
            home=temporary,
        )
        app = QApplication.instance() or QApplication([])
        apply_theme(app, False)
        window = MainWindow(paths, show_wizard=False)
        page: OverviewPage = window.pages["Übersicht"]  # type: ignore[assignment]
        values = {
            "inside": 27,
            "daily_unique": 146,
            "entered": 182,
            "exited": 155,
            "throughput": 337,
            "suppressed": 12,
            "uncertain": 3,
            "wrong_way": 1,
        }
        for key, value in values.items():
            page.metrics[key].set_value(value)
        for title, label in (
            ("KI-Beschleuniger", "Bereit"),
            ("Kameras", "2/2 online"),
            ("Datenbank", "Bereit"),
            ("Hintergrunddienst", "Läuft"),
            ("Lizenz", "Gültig"),
            ("Datenschutz", "Bereit"),
        ):
            page.health[title].set_state("ok", label)
        page.updated.setText("Live-Demonstration · lokale Verarbeitung")
        window.show()
        app.processEvents()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        if not window.grab().save(str(args.output)):
            return 1
        window.close()
        app.processEvents()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
