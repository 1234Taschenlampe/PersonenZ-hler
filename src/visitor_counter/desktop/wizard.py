from __future__ import annotations

import platform
import shutil
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QSpinBox,
    QVBoxLayout,
    QWizard,
    QWizardPage,
)

from ..application_service import ApplicationService
from ..camera_manager import discover_camera_devices
from ..settings_service import SettingsError, SettingsService


class FirstRunWizard(QWizard):
    def __init__(
        self, service: ApplicationService, settings: SettingsService, parent=None
    ) -> None:  # noqa: ANN001
        super().__init__(parent)
        self.service = service
        self.settings = settings
        self.config = settings.load()
        self.setWindowTitle("PersonenZähler einrichten")
        self.setWizardStyle(QWizard.ModernStyle)
        self.setMinimumSize(760, 560)
        self.setOption(QWizard.NoBackButtonOnStartPage)
        self._build_pages()

    def _build_pages(self) -> None:
        welcome = QWizardPage()
        welcome.setTitle("Willkommen bei PersonenZähler")
        welcome.setSubTitle(
            "In wenigen Schritten: System, Kameras, KI-Hardware und lokale Verbindung."
        )
        layout = QVBoxLayout(welcome)
        text = QLabel(
            "Nach der Einrichtung steuern Sie Kameras, Dienst, Diagnose und Einstellungen vollständig über die Desktop-Anwendung. "
            "Produktive Inferenz bleibt gesperrt, solange ein sicherheitskritischer Punkt offen ist."
        )
        text.setWordWrap(True)
        layout.addWidget(text)
        layout.addStretch()
        self.addPage(welcome)

        system_page = QWizardPage()
        system_page.setTitle("Systemprüfung")
        system_page.setSubTitle(
            "Betriebssystem, Architektur, Python und freier Speicher"
        )
        system_layout = QFormLayout(system_page)
        usage = shutil.disk_usage(self.service.paths.project_root)
        system_layout.addRow("Betriebssystem", QLabel(platform.platform()))
        system_layout.addRow("Architektur", QLabel(platform.machine()))
        system_layout.addRow("Python", QLabel(platform.python_version()))
        system_layout.addRow(
            "Freier Speicher", QLabel(f"{usage.free / (1024**3):.1f} GiB")
        )
        self.addPage(system_page)

        hardware_page = QWizardPage()
        hardware_page.setTitle("Hailo & Modelle")
        hardware_page.setSubTitle(
            "Der Produktionsbetrieb verwendet keinen versteckten CPU-Fallback."
        )
        hardware_layout = QFormLayout(hardware_page)
        hailo_cli = shutil.which("hailortcli")
        detector = self._resolve_model(self.config.model.hef_path)
        reid = self._resolve_model(self.config.model.reid_hef_path)
        self.hailo_ready = bool(hailo_cli)
        self.detector_ready = detector.is_file() and detector.stat().st_size > 0
        self.reid_ready = reid.is_file() and reid.stat().st_size > 0
        hardware_layout.addRow(
            "HailoRT",
            QLabel("gefunden" if self.hailo_ready else "nicht installiert/auffindbar"),
        )
        hardware_layout.addRow(
            "YOLO26m HEF", QLabel("vorhanden" if self.detector_ready else "fehlt")
        )
        hardware_layout.addRow(
            "OSNet HEF", QLabel("vorhanden" if self.reid_ready else "fehlt")
        )
        note = QLabel(
            "Fehlende Komponenten werden als ‚KI-Beschleuniger nicht bereit‘ angezeigt. Es wird kein anderes Modell gestartet."
        )
        note.setWordWrap(True)
        hardware_layout.addRow(note)
        self.addPage(hardware_page)

        camera_page = QWizardPage()
        camera_page.setTitle("Kameras")
        camera_page.setSubTitle(
            "Diese Liste zeigt nur USB-Webcams. Bereits gespeicherte Reolink-RTSP-"
            "Kameras funktionieren unabhängig davon. IP-Kameras anschließend "
            "unter Kameras über RTSP + ONVIF suchen."
        )
        camera_layout = QFormLayout(camera_page)
        discovered = discover_camera_devices()
        sources = [item.stable_path or item.video_node for item in discovered]
        self.camera_1 = QComboBox()
        self.camera_2 = QComboBox()
        self.camera_1_role = QComboBox()
        self.camera_2_role = QComboBox()
        for role in (self.camera_1_role, self.camera_2_role):
            role.addItem("Eingang", "entrance")
            role.addItem("Ausgang", "exit")
        for combo, camera_id in (
            (self.camera_1, "camera_1"),
            (self.camera_2, "camera_2"),
        ):
            combo.setEditable(True)
            combo.addItems(sources)
            current = self.config.cameras[camera_id].device or ""
            if current and combo.findText(current) < 0:
                combo.addItem(current)
            combo.setCurrentText(current)
        self.camera_1_role.setCurrentIndex(
            max(
                0,
                self.camera_1_role.findData(self.config.cameras["camera_1"].role),
            )
        )
        self.camera_2_role.setCurrentIndex(
            max(
                0,
                self.camera_2_role.findData(self.config.cameras["camera_2"].role),
            )
        )
        camera_layout.addRow("Kamera 1", self.camera_1)
        camera_layout.addRow("Rolle Kamera 1", self.camera_1_role)
        camera_layout.addRow("Kamera 2", self.camera_2)
        camera_layout.addRow("Rolle Kamera 2", self.camera_2_role)
        camera_layout.addRow(
            QLabel(
                f"USB-Webcams: {len(sources)} (keine Aussage über RTSP-Kameras). "
                "Netzwerkkameras unter Kameras suchen und Videoframe testen."
            )
        )
        self.addPage(camera_page)

        privacy_page = QWizardPage()
        privacy_page.setTitle("Datenschutz")
        privacy_page.setSubTitle(
            "Angaben sind optional und können später im Bereich Datenschutz ergänzt werden."
        )
        privacy_layout = QFormLayout(privacy_page)
        self.controller = QLineEdit(self.config.privacy.controller_name)
        self.contact = QLineEdit(self.config.privacy.controller_contact)
        self.purpose = QLineEdit(self.config.privacy.purpose)
        self.legal_basis = QLineEdit(self.config.privacy.legal_basis)
        self.notice = QCheckBox("Datenschutzhinweis ist sichtbar angebracht")
        self.notice.setChecked(self.config.privacy.privacy_notice_acknowledged)
        # Keine Pflichtfelder: Die Dokumentation kann später ergänzt werden.
        privacy_layout.addRow("Verantwortlicher", self.controller)
        privacy_layout.addRow("Kontakt", self.contact)
        privacy_layout.addRow("Zweck", self.purpose)
        privacy_layout.addRow("Geprüfte Rechtsgrundlage", self.legal_basis)
        privacy_layout.addRow("", self.notice)
        self.addPage(privacy_page)

        security_page = QWizardPage()
        security_page.setTitle("Sicherheit, API & Lizenz")
        security_page.setSubTitle(
            "Remotezugriff bleibt standardmäßig deaktiviert und erfordert TLS plus Rollen-Tokens."
        )
        security_layout = QFormLayout(security_page)
        self.api_enabled = QCheckBox("Lokale API für Desktop/Android aktivieren")
        self.api_enabled.setChecked(self.config.api.enabled)
        self.api_port = QSpinBox()
        self.api_port.setRange(1, 65535)
        self.api_port.setValue(self.config.api.port)
        license_status = self.service.license_service.inspect()
        self.license_ready = license_status.valid
        security_layout.addRow("", self.api_enabled)
        security_layout.addRow("Lokaler API-Port", self.api_port)
        security_layout.addRow("Bindung", QLabel("127.0.0.1 (sicherer Standard)"))
        security_layout.addRow("Lizenz", QLabel(license_status.label))
        fingerprint = QLabel(license_status.fingerprint)
        fingerprint.setTextInteractionFlags(
            fingerprint.textInteractionFlags() | Qt.TextSelectableByMouse
        )
        fingerprint.setWordWrap(True)
        security_layout.addRow("Gerätefingerabdruck", fingerprint)
        self.addPage(security_page)

        self.summary_page = QWizardPage()
        self.summary_page.setTitle("Einrichtungsstatus")
        self.summary_page.setSubTitle(
            "Die Anwendung zeigt offene Punkte präzise an und startet keinen Ersatz-Inferenzpfad."
        )
        summary_layout = QVBoxLayout(self.summary_page)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        summary_layout.addWidget(self.summary)
        summary_layout.addStretch()
        self.summary_page.initializePage = self._refresh_summary  # type: ignore[method-assign]
        self.addPage(self.summary_page)

    def _refresh_summary(self) -> None:
        issues = self._issues()
        if issues:
            body = (
                "<b>Einrichtung noch nicht vollständig:</b><ul>"
                + "".join(f"<li>{item}</li>" for item in issues)
                + "</ul>"
            )
            body += "Die Einstellungen können gespeichert werden. Der produktive Dienst bleibt bis zur Behebung gesperrt."
        else:
            body = "<b>System bereit.</b><br>Alle für den Produktivstart geprüften Punkte sind erfüllt."
        self.summary.setText(body)

    def accept(self) -> None:
        self.config.cameras["camera_1"].device = (
            self.camera_1.currentText().strip() or None
        )
        self.config.cameras["camera_1"].role = str(self.camera_1_role.currentData())
        self.config.cameras["camera_2"].device = (
            self.camera_2.currentText().strip() or None
        )
        self.config.cameras["camera_2"].role = str(self.camera_2_role.currentData())
        self.config.privacy.controller_name = self.controller.text().strip()
        self.config.privacy.controller_contact = self.contact.text().strip()
        self.config.privacy.purpose = self.purpose.text().strip()
        self.config.privacy.legal_basis = self.legal_basis.text().strip()
        self.config.privacy.privacy_notice_acknowledged = self.notice.isChecked()
        self.config.privacy.privacy_notice_acknowledged_at = (
            datetime.now().astimezone().isoformat() if self.notice.isChecked() else ""
        )
        self.config.api.enabled = self.api_enabled.isChecked()
        self.config.api.bind_host = "127.0.0.1"
        self.config.api.port = self.api_port.value()
        try:
            self.settings.save(self.config)
        except SettingsError as exc:
            QMessageBox.critical(
                self, "Konfiguration konnte nicht gespeichert werden", str(exc)
            )
            return
        # Setup ist gespeichert, auch wenn Kamera/HEF noch fehlen; offene
        # Hardwarepunkte bleiben in der Diagnose sichtbar.
        self.service.mark_first_run_complete()
        super().accept()

    def _issues(self) -> list[str]:
        issues: list[str] = []
        if not self.hailo_ready:
            issues.append("HailoRT/hailortcli wurde nicht gefunden.")
        if not self.detector_ready:
            issues.append("Das YOLO26m-Hailo-10H-Modell fehlt.")
        if self.config.model.reid_required and not self.reid_ready:
            issues.append("Das OSNet-Hailo-10H-Modell für Tageszählung/Re-ID fehlt.")
        if (
            not self.camera_1.currentText().strip()
            or not self.camera_2.currentText().strip()
        ):
            issues.append("Beide Kameraquellen müssen ausgewählt werden.")
        if not self.license_ready:
            issues.append("Eine gültige signierte Produktlizenz fehlt.")
        return issues

    def _resolve_model(self, value: str) -> Path:
        path = Path(value).expanduser()
        return path if path.is_absolute() else self.service.paths.project_root / path
