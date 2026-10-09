from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable

import cv2
from PySide6.QtCore import QSettings, Qt, QThreadPool, QTimer
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .. import __version__
from ..application_service import ApplicationService, DashboardSnapshot
from ..camera_manager import discover_camera_devices
from ..diagnostics import (
    collect_diagnostics,
    create_diagnostic_bundle,
    redact_sensitive,
)
from ..license_guard import LicenseError
from ..model_installation import ModelInstallationService
from ..network_camera_discovery import discover_network_cameras
from ..runtime_paths import RuntimePaths
from ..security_assets import SecurityAssetService
from ..settings_service import SettingsError, SettingsService
from .pages import (
    AboutPage,
    CamerasPage,
    EventsPage,
    HardwarePage,
    HistoryPage,
    OverviewPage,
    PrivacyPage,
    SettingsPage,
    SystemPage,
)
from .theme import apply_theme
from .wizard import FirstRunWizard
from .workers import FunctionWorker


class MainWindow(QMainWindow):
    def __init__(self, paths: RuntimePaths, *, show_wizard: bool = True) -> None:
        super().__init__()
        self.paths = paths
        self.paths.ensure_user_directories()
        self.settings_service = SettingsService(
            paths.config_file, allow_privileged=paths.system_layout
        )
        self.application_service = ApplicationService(paths)
        self.model_installation = ModelInstallationService(paths)
        self.security_assets = SecurityAssetService(paths)
        self.thread_pool = QThreadPool.globalInstance()
        self._workers: set[FunctionWorker] = set()
        self._refreshing = False
        self._dark = QSettings("PersonenZaehler", "Desktop").value(
            "darkMode", False, bool
        )
        self.setWindowTitle("PersonenZähler")
        self.setMinimumSize(1100, 720)
        self.resize(1420, 900)
        self._build_ui()
        self._load_config_into_pages()
        self._connect_pages()
        self.refresh()
        self.timer = QTimer(self)
        self.timer.setInterval(3000)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        if (
            show_wizard
            and not paths.first_run_marker.exists()
            and os.environ.get("PERSONENZAEHLER_SKIP_WIZARD") != "1"
        ):
            QTimer.singleShot(250, self.show_first_run_wizard)

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("AppRoot")
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        sidebar = QWidget()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(238)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(14, 18, 14, 16)
        brand = QLabel("PersonenZähler")
        brand.setStyleSheet("font-size:20px;font-weight:650;padding:8px 10px;")
        side.addWidget(brand)
        self.stack = QStackedWidget()
        self.pages = {
            "Übersicht": OverviewPage(),
            "Kameras": CamerasPage(),
            "Ereignisse": EventsPage(),
            "Verlauf": HistoryPage(),
            "KI & Hardware": HardwarePage(),
            "System": SystemPage(),
            "Datenschutz": PrivacyPage(),
            "Einstellungen": SettingsPage(),
            "Über": AboutPage(__version__, self.paths.project_root),
        }
        self.nav_buttons: list[QPushButton] = []
        for index, (title, page) in enumerate(self.pages.items()):
            button = QPushButton(title.replace("&", "&&"))
            button.setCheckable(True)
            button.setProperty("nav", True)
            button.clicked.connect(
                lambda _checked=False, value=index: self._select_page(value)
            )
            self.nav_buttons.append(button)
            side.addWidget(button)
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            scroll.setWidget(page)
            self.stack.addWidget(scroll)
        self.nav_buttons[0].setChecked(True)
        side.addStretch()
        setup = QPushButton("Einrichtungsassistent")
        setup.clicked.connect(self.show_first_run_wizard)
        side.addWidget(setup)
        theme = QPushButton("Dunkel/Hell wechseln")
        theme.clicked.connect(self.toggle_theme)
        side.addWidget(theme)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        top = QWidget()
        top.setObjectName("TopBar")
        top_layout = QHBoxLayout(top)
        top_layout.setContentsMargins(28, 12, 28, 4)
        self.global_status = QLabel("Status wird geladen …")
        self.global_status.setProperty("muted", True)
        refresh = QPushButton("Aktualisieren")
        refresh.clicked.connect(self.refresh)
        top_layout.addWidget(self.global_status)
        top_layout.addStretch()
        top_layout.addWidget(refresh)
        content_layout.addWidget(top)
        content_layout.addWidget(self.stack, 1)
        outer.addWidget(sidebar)
        outer.addWidget(content, 1)
        self.setCentralWidget(root)

    def _connect_pages(self) -> None:
        cameras: CamerasPage = self.pages["Kameras"]  # type: ignore[assignment]
        cameras.discover_requested.connect(self._discover_cameras)
        cameras.network_scan_requested.connect(self._scan_network_cameras)
        cameras.save_requested.connect(self._save_cameras)
        cameras.test_requested.connect(self._test_camera)
        hardware: HardwarePage = self.pages["KI & Hardware"]  # type: ignore[assignment]
        hardware.diagnose_requested.connect(self._run_diagnostics)
        hardware.model_import_requested.connect(self._import_model)
        hardware.model_download_requested.connect(self._download_official_models)
        system: SystemPage = self.pages["System"]  # type: ignore[assignment]
        system.service_action_requested.connect(self._service_action)
        system.logs_requested.connect(self._load_logs)
        system.diagnostic_export_requested.connect(self._export_diagnostics)
        system.pairing_export_requested.connect(self._export_pairing)
        privacy: PrivacyPage = self.pages["Datenschutz"]  # type: ignore[assignment]
        privacy.save_requested.connect(self._save_values)
        privacy.delete_requested.connect(self._delete_personal_data)
        privacy.license_import_requested.connect(self._import_license)
        settings: SettingsPage = self.pages["Einstellungen"]  # type: ignore[assignment]
        settings.save_requested.connect(self._save_values)
        settings.security_asset_import_requested.connect(self._import_security_asset)

    def _select_page(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        for button_index, button in enumerate(self.nav_buttons):
            button.setChecked(button_index == index)

    def refresh(self) -> None:
        if self._refreshing:
            return
        self._refreshing = True
        self.global_status.setText("Status wird aktualisiert …")
        self._run_worker(
            self.application_service.snapshot,
            self._apply_snapshot,
            done=lambda: setattr(self, "_refreshing", False),
        )

    def _apply_snapshot(self, snapshot: DashboardSnapshot) -> None:
        overview: OverviewPage = self.pages["Übersicht"]  # type: ignore[assignment]
        cameras: CamerasPage = self.pages["Kameras"]  # type: ignore[assignment]
        system: SystemPage = self.pages["System"]  # type: ignore[assignment]
        privacy: PrivacyPage = self.pages["Datenschutz"]  # type: ignore[assignment]
        overview.update_snapshot(snapshot)
        cameras.update_snapshot(snapshot)
        system.update_snapshot(snapshot)
        if snapshot.license:
            privacy.set_license(snapshot.license)
        open_items = len(snapshot.privacy_errors) + (
            0 if snapshot.license and snapshot.license.valid else 1
        )
        self.global_status.setText(
            "System bereit"
            if open_items == 0
            else f"{open_items} Punkt(e) erfordern Aufmerksamkeit"
        )
        self._run_worker(self.application_service.recent_events, self._set_events)
        self._run_worker(self.application_service.hourly_history, self._set_history)

    def _set_events(self, events: list[dict[str, Any]]) -> None:
        page: EventsPage = self.pages["Ereignisse"]  # type: ignore[assignment]
        page.set_events(events)

    def _set_history(self, values: list[dict[str, Any]]) -> None:
        page: HistoryPage = self.pages["Verlauf"]  # type: ignore[assignment]
        page.chart.set_values(values, dark=self._dark)

    def _load_config_into_pages(self) -> None:
        try:
            config = self.settings_service.load()
        except SettingsError as exc:
            QMessageBox.critical(self, "Konfigurationsfehler", str(exc))
            return
        self.pages["Kameras"].set_config(config)  # type: ignore[attr-defined]
        self.pages["Datenschutz"].set_config(config)  # type: ignore[attr-defined]
        self.pages["Einstellungen"].set_config(config)  # type: ignore[attr-defined]

    def _save_values(self, values: dict[str, Any]) -> None:
        try:
            self.settings_service.update(values)
        except SettingsError as exc:
            QMessageBox.warning(self, "Einstellungen nicht gespeichert", str(exc))
            return
        self._load_config_into_pages()
        self.global_status.setText(
            "Einstellungen gespeichert · Dienst gegebenenfalls neu starten"
        )
        self.refresh()

    def _save_cameras(self, values: dict[str, dict[str, str]]) -> None:
        try:
            config = self.settings_service.load()
            for camera_id, camera_values in values.items():
                camera = config.cameras[camera_id]
                camera.display_name = camera_values["display_name"] or camera_id
                camera.device = camera_values["device"] or None
                camera.role = camera_values["role"]
                camera.entry_direction = camera_values["entry_direction"]
                camera.exit_direction = camera_values["exit_direction"]
                camera.counting_mode = camera_values["counting_mode"]
            self.settings_service.save(config)
        except SettingsError as exc:
            QMessageBox.warning(self, "Kameras nicht gespeichert", str(exc))
            return
        self.global_status.setText("Kamerakonfiguration gespeichert")
        self.refresh()

    def _discover_cameras(self) -> None:
        def discover() -> list[str]:
            return [
                item.stable_path or item.video_node
                for item in discover_camera_devices()
            ]

        page: CamerasPage = self.pages["Kameras"]  # type: ignore[assignment]
        page.discovery_status.setText("USB-Gerätesuche läuft … (IP-Kameras sind davon unabhängig)")
        self._run_worker(discover, page.set_discovered)

    def _scan_network_cameras(self, subnet: str) -> None:
        page: CamerasPage = self.pages["Kameras"]  # type: ignore[assignment]
        page.discovery_status.setText("Suche: RTSP-TCP und ONVIF-Netzwerkerkennung …")
        self._run_worker(
            lambda: discover_network_cameras(subnet),
            page.set_discovered_network,
        )

    def _test_camera(self, source: str) -> None:
        if not source:
            QMessageBox.information(
                self, "Kamera testen", "Bitte zuerst eine Kameraquelle auswählen."
            )
            return

        def probe() -> tuple[str, bool, str]:
            from ..camera_manager import open_camera_source

            capture = open_camera_source(source, timeout_ms=5000)
            try:
                if not capture.isOpened():
                    return (
                        source, False,
                        "RTSP-Zugriff fehlgeschlagen: IP, Port 554/8554, Kamera-RTSP "
                        "und Benutzer/Passwort prüfen"
                    )
                ok, frame = capture.read()
                if not ok or frame is None or frame.size == 0:
                    return (
                        source, False,
                        "RTSP-Port erreichbar, aber kein Videobild. "
                        "Reolink Substream/Hauptstream, Login oder H.264 prüfen"
                    )
                height, width = frame.shape[:2]
                return source, True, f"Videoframe empfangen · {width}×{height}"
            finally:
                capture.release()

        page: CamerasPage = self.pages["Kameras"]  # type: ignore[assignment]
        self._run_worker(probe, lambda result: page.set_test_result(*result))

    def _run_diagnostics(self) -> None:
        page: HardwarePage = self.pages["KI & Hardware"]  # type: ignore[assignment]
        page.details.setPlainText("Hardwareprüfung läuft …")
        self._run_worker(
            lambda: collect_diagnostics(
                self.paths.project_root,
                config_file=self.paths.config_file,
                output_dir=self.paths.log_dir,
            ),
            page.set_report,
        )

    def _download_official_models(self) -> None:
        self.global_status.setText("Offizielle Hailo-Modelle werden geprüft und geladen …")
        page: HardwarePage = self.pages["KI & Hardware"]  # type: ignore[assignment]
        page.details.setPlainText(
            "Download über Hailo Model Zoo: YOLO26m (5.4.0) / OSNet (5.3.0). "
            "Die vorhandenen SHA-256-Manifeste werden strikt geprüft. "
            "Bitte währenddessen keine Modelle manuell ersetzen."
        )

        def download_all() -> list[str]:
            messages: list[str] = []
            for kind in ("detector", "reid"):
                model = self.model_installation.download_official(kind)
                messages.append(
                    f"{kind}: {model.path.name} ({model.size_bytes} Bytes), SHA-256 korrekt"
                )
            return messages

        def finished(messages: list[str]) -> None:
            QMessageBox.information(
                self, "Offizielle Modelle installiert",
                "\n".join(messages)
                + "\n\nDie echte Hailo-Inferenz muss noch am Pi geprüft werden.",
            )
            self._run_diagnostics()

        self._run_worker(download_all, finished)

    def _import_model(self, kind: str, source: Path) -> None:
        self.global_status.setText("Modell wird sicher importiert …")

        def completed(model: Any) -> None:
            QMessageBox.information(
                self,
                "Modell importiert",
                f"{model.path.name} wurde installiert. Führen Sie jetzt die Hardwareprüfung aus.",
            )
            self._run_diagnostics()

        self._run_worker(
            lambda: self.model_installation.install(kind, source), completed
        )

    def _import_security_asset(self, kind: str, source: Path) -> None:
        def completed(target: Path) -> None:
            field = (
                "api.tls_certificate"
                if kind == "certificate"
                else "api.tls_private_key"
            )
            self._save_values({field: str(target)})
            QMessageBox.information(
                self,
                "TLS-Datei importiert",
                "Die geschützte TLS-Datei wurde installiert. Starten Sie den API-Dienst über die Systemseite neu.",
            )

        self._run_worker(
            lambda: self.security_assets.install_tls_asset(kind, source),
            completed,
        )

    def _service_action(self, action: str) -> None:
        self.global_status.setText(f"Dienstaktion ‚{action}‘ läuft …")
        self._run_worker(
            lambda: self.application_service.service_manager.action(action),
            lambda _result: self.refresh(),
        )

    def _load_logs(self) -> None:
        page: SystemPage = self.pages["System"]  # type: ignore[assignment]
        self._run_worker(
            self.application_service.service_manager.recent_logs, page.logs.setPlainText
        )

    def _export_diagnostics(self) -> None:
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Diagnosepaket speichern",
            str(Path.home() / "personenzaehler-diagnose.zip"),
            "ZIP (*.zip)",
        )
        if not filename:
            return
        destination = Path(filename)
        self._run_worker(
            lambda: create_diagnostic_bundle(
                self.paths.project_root,
                destination,
                config_file=self.paths.config_file,
                log_dir=self.paths.log_dir,
            ),
            lambda path: QMessageBox.information(
                self, "Diagnosepaket erstellt", f"Gespeichert unter:\n{path}"
            ),
        )

    def _export_pairing(self) -> None:
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Android-Pairing speichern",
            str(Path.home() / "personenzaehler-pairing.json"),
            "Pairing-Datei (*.json)",
        )
        if not filename:
            return
        config = self.settings_service.load()
        self._run_worker(
            lambda: self.security_assets.export_pairing(config, Path(filename)),
            lambda path: QMessageBox.information(
                self,
                "Pairing-Datei erstellt",
                f"Die Datei enthält einen geheimen Viewer-Token. Übertragen Sie sie geschützt und löschen Sie sie danach.\n\n{path}",
            ),
        )

    def _delete_personal_data(self, reset_aggregates: bool) -> None:
        choice = QMessageBox.warning(
            self,
            "Daten endgültig löschen",
            "Granulare Ereignisse und pseudonyme Sitzungsdaten werden endgültig gelöscht. Aggregierte Zähler bleiben erhalten.",
            QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        if choice != QMessageBox.Yes:
            return
        self._run_worker(
            lambda: self.application_service.delete_personal_data(reset_aggregates),
            lambda result: QMessageBox.information(
                self, "Daten gelöscht", f"Gelöschte Datensätze: {sum(result.values())}"
            ),
        )

    def _import_license(self, source: Path) -> None:
        try:
            status = self.application_service.license_service.import_file(source)
        except (OSError, LicenseError) as exc:
            QMessageBox.warning(self, "Lizenz ungültig", str(exc))
            return
        self.pages["Datenschutz"].set_license(status)  # type: ignore[attr-defined]
        self.refresh()

    def toggle_theme(self) -> None:
        self._dark = not self._dark
        QSettings("PersonenZaehler", "Desktop").setValue("darkMode", self._dark)
        app = QApplication.instance()
        if isinstance(app, QApplication):
            apply_theme(app, self._dark)
        self._run_worker(self.application_service.hourly_history, self._set_history)

    def show_first_run_wizard(self) -> None:
        try:
            wizard = FirstRunWizard(
                self.application_service, self.settings_service, self
            )
        except SettingsError as exc:
            QMessageBox.critical(
                self, "Assistent konnte nicht gestartet werden", str(exc)
            )
            return
        if wizard.exec():
            self._load_config_into_pages()
            self.refresh()

    def _run_worker(
        self,
        function: Callable[[], Any],
        on_result: Callable[[Any], None],
        *,
        done: Callable[[], None] | None = None,
    ) -> None:
        worker = FunctionWorker(function)
        self._workers.add(worker)
        worker.signals.result.connect(on_result)
        worker.signals.error.connect(self._show_background_error)

        def finished() -> None:
            self._workers.discard(worker)
            if done:
                done()

        worker.signals.finished.connect(finished)
        self.thread_pool.start(worker)

    def _show_background_error(self, message: str) -> None:
        self.global_status.setText("Aktion fehlgeschlagen")
        QMessageBox.warning(
            self, "Aktion fehlgeschlagen", str(redact_sensitive(message))
        )

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        self.timer.stop()
        self.thread_pool.waitForDone(5000)
        event.accept()


def run_desktop(paths: RuntimePaths, *, show_wizard: bool = True) -> int:
    app = QApplication.instance()
    owns_app = app is None
    if app is None:
        app = QApplication([])
    assert isinstance(app, QApplication)
    app.setApplicationName("PersonenZähler")
    app.setOrganizationName("PersonenZaehler")
    app.setApplicationVersion(__version__)
    dark = QSettings("PersonenZaehler", "Desktop").value("darkMode", False, bool)
    apply_theme(app, dark)
    window = MainWindow(paths, show_wizard=show_wizard)
    window.show()
    return app.exec() if owns_app else 0
