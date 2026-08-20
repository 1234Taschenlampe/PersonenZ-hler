from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from visitor_counter.desktop.main_window import MainWindow
from visitor_counter.runtime_paths import RuntimePaths


def test_desktop_shell_builds_all_navigation_pages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("PERSONENZAEHLER_SKIP_WIZARD", "1")
    root = Path.cwd()
    paths = RuntimePaths.discover(
        root,
        environ={
            "PERSONENZAEHLER_CONFIG_FILE": str(root / "config" / "config.yaml"),
            "PERSONENZAEHLER_DATA_DIR": str(tmp_path / "data"),
            "PERSONENZAEHLER_LOG_DIR": str(tmp_path / "logs"),
            "PERSONENZAEHLER_CACHE_DIR": str(tmp_path / "cache"),
            "PERSONENZAEHLER_STATE_DIR": str(tmp_path / "state"),
            "PERSONENZAEHLER_LICENSE_FILE": str(tmp_path / "license.json"),
            "PERSONENZAEHLER_LICENSE_PUBLIC_KEY": str(tmp_path / "public.pem"),
        },
        home=tmp_path,
    )
    app = QApplication.instance() or QApplication([])
    window = MainWindow(paths, show_wizard=False)
    try:
        assert window.stack.count() == 9
        assert set(window.pages) == {
            "Übersicht",
            "Kameras",
            "Ereignisse",
            "Verlauf",
            "KI & Hardware",
            "System",
            "Datenschutz",
            "Einstellungen",
            "Über",
        }
    finally:
        window.close()
        app.processEvents()
