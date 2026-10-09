from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..application_service import DashboardSnapshot
from ..configuration import AppConfig
from ..license_service import LicenseStatus
from ..network_camera_discovery import RtspCandidate, reolink_rtsp_url
from .components import Card, HistoryChart, MetricCard, PageHeader, StatusBadge
from .live_preview import CameraPreviewPanel


class BasePage(QWidget):
    def __init__(self, title: str, subtitle: str = "") -> None:
        super().__init__()
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(28, 20, 28, 28)
        self.layout.setSpacing(16)
        self.layout.addWidget(PageHeader(title, subtitle))


class OverviewPage(BasePage):
    def __init__(self) -> None:
        super().__init__(
            "Übersicht",
            "Live-Status der Zählung und aller produktionskritischen Komponenten",
        )
        grid = QGridLayout()
        grid.setSpacing(12)
        definitions = [
            ("inside", "Aktuell im Gebäude"),
            ("daily_unique", "Besucher heute"),
            ("entered", "Eintritte"),
            ("exited", "Austritte"),
            ("throughput", "Gesamtdurchfluss"),
            ("suppressed", "Doppelzählungen verhindert"),
            ("uncertain", "Unsichere Ereignisse"),
            ("wrong_way", "Fehlrichtungen"),
        ]
        self.metrics: dict[str, MetricCard] = {}
        for index, (key, title) in enumerate(definitions):
            card = MetricCard(title)
            self.metrics[key] = card
            grid.addWidget(card, index // 4, index % 4)
        self.layout.addLayout(grid)

        health = Card()
        health_layout = QGridLayout(health)
        health_layout.setContentsMargins(18, 16, 18, 16)
        health_layout.setSpacing(12)
        self.health: dict[str, StatusBadge] = {}
        for index, title in enumerate(
            (
                "KI-Beschleuniger",
                "Kameras",
                "Datenbank",
                "Hintergrunddienst",
                "Lizenz",
                "Datenschutz",
            )
        ):
            badge = StatusBadge()
            self.health[title] = badge
            health_layout.addWidget(QLabel(title), index // 3 * 2, index % 3)
            health_layout.addWidget(badge, index // 3 * 2 + 1, index % 3)
        self.layout.addWidget(health)
        self.updated = QLabel("Noch nicht aktualisiert")
        self.updated.setProperty("muted", True)
        self.layout.addWidget(self.updated)
        self.inference_info = QLabel("KI-Verarbeitung wird geprüft …")
        self.inference_info.setProperty("muted", True)
        self.inference_info.setWordWrap(True)
        self.layout.addWidget(self.inference_info)
        self.preview_panel = CameraPreviewPanel(self)
        self.layout.addWidget(self.preview_panel)
        self.layout.addStretch()

    def update_snapshot(self, snapshot: DashboardSnapshot) -> None:
        for key, card in self.metrics.items():
            card.set_value(snapshot.counts.get(key, 0))
        runtime_ready = str(snapshot.runtime.get("hailo_status", "")).lower() in {
            "ready",
            "ok",
            "bereit",
        }
        self.health["KI-Beschleuniger"].set_state(
            "ok" if runtime_ready else "error",
            "Bereit" if runtime_ready else "Nicht bereit",
        )
        online = sum(
            str(item.get("status", "")).upper() == "ONLINE" for item in snapshot.cameras
        )
        self.health["Kameras"].set_state(
            "ok" if online else "warning",
            f"{online} von {len(snapshot.cameras)} online",
        )
        try:
            inference_fps = float(snapshot.runtime.get("inference_fps") or 0)
        except (ValueError, TypeError):
            inference_fps = 0.0
        if online and inference_fps <= 0:
            self.inference_info.setText(
                "Kamera überträgt Bilder, aber die KI verarbeitet derzeit keine Frames. "
                "Zähldienst, Hailo und YOLO26m prüfen."
            )
        elif inference_fps > 0:
            self.inference_info.setText(
                f"KI verarbeitet {inference_fps:.1f} Bilder/s. "
                "Eintritte und Austritte werden erst nach einem gültigen "
                "Überqueren der konfigurierten Zähllinie gezählt."
            )
        else:
            self.inference_info.setText("Keine laufende KI-Verarbeitung.")
        self.health["Datenbank"].set_state(
            "ok" if snapshot.database.get("exists") else "warning",
            "Bereit" if snapshot.database.get("exists") else "Noch leer",
        )
        service_running = (
            snapshot.service is not None and snapshot.service.state.value == "läuft"
        )
        self.health["Hintergrunddienst"].set_state(
            "ok" if service_running else "warning",
            snapshot.service.state.value if snapshot.service else "Unbekannt",
        )
        license_valid = bool(snapshot.license and snapshot.license.valid)
        self.health["Lizenz"].set_state(
            "ok" if license_valid else "error",
            snapshot.license.label if snapshot.license else "Unbekannt",
        )
        self.health["Datenschutz"].set_state(
            "ok" if not snapshot.privacy_errors else "warning",
            "Bereit"
            if not snapshot.privacy_errors
            else f"{len(snapshot.privacy_errors)} offen",
        )
        self.updated.setText(
            "Aktualisiert: "
            + datetime.fromtimestamp(snapshot.timestamp)
            .astimezone()
            .strftime("%H:%M:%S")
        )


class CamerasPage(BasePage):
    discover_requested = Signal()
    network_scan_requested = Signal(str)
    save_requested = Signal(dict)
    test_requested = Signal(str)

    def __init__(self) -> None:
        super().__init__(
            "Kameras",
            "Netzwerkkameras erkennen, Bildübertragung testen und Zählbereiche pro Kamera einstellen",
        )
        toolbar = QHBoxLayout()
        discover = QPushButton("USB-Kameras suchen")
        discover.clicked.connect(self.discover_requested.emit)
        network_scan = QPushButton("IP-Kameras suchen (RTSP + ONVIF)")
        network_scan.setProperty("primary", True)
        self.scan_subnet = QLineEdit()
        self.scan_subnet.setPlaceholderText("Automatisch oder 192.168.1.0/24")
        self.scan_subnet.setToolTip("Nur eigene private Netze, maximal /24. Leer = direkt angeschlossene Netze.")
        self.scan_subnet.setMaximumWidth(235)
        network_scan.clicked.connect(
            lambda: self.network_scan_requested.emit(self.scan_subnet.text().strip())
        )
        save = QPushButton("Änderungen speichern")
        save.clicked.connect(self._emit_save)
        self.discovery_status = QLabel(
            "Zwei Kameraplätze · Netzwerkgeräte auch ohne USB-Webcam möglich"
        )
        self.discovery_status.setProperty("muted", True)
        toolbar.addWidget(network_scan)
        toolbar.addWidget(self.scan_subnet)
        toolbar.addWidget(discover)
        toolbar.addWidget(save)
        toolbar.addWidget(self.discovery_status)
        toolbar.addStretch()
        self.layout.addLayout(toolbar)
        hint = QLabel(
            "RTSP-Kameras im eigenen LAN suchen oder die Kamera-IP manuell eingeben. "
            "ONVIF findet zusätzliche Kamerakandidaten, RTSP bestätigt nur einen Port, keine Videobilder. "
            "Bei getrennten Router-Netzen muss der Pi das Kamera-Subnetz erreichen."
        )
        hint.setWordWrap(True)
        hint.setProperty("muted", True)
        self.layout.addWidget(hint)
        self.cameras_summary = QLabel("Kamerastatus wird geladen …")
        self.cameras_summary.setProperty("muted", True)
        self.layout.addWidget(self.cameras_summary)
        self.cards: dict[str, dict[str, QWidget]] = {}
        for camera_id in ("camera_1", "camera_2"):
            card = Card()
            form = QFormLayout(card)
            form.setContentsMargins(18, 16, 18, 16)
            name = QLineEdit()
            source = QComboBox()
            source.setEditable(True)
            source.setToolTip("RTSP-URL eingeben oder über die IP-Hilfe zusammenstellen.")
            ip_address = QLineEdit()
            ip_address.setPlaceholderText("z. B. 192.168.68.101")
            rtsp_port = QSpinBox()
            rtsp_port.setRange(1, 65535)
            rtsp_port.setValue(554)
            camera_user = QLineEdit()
            camera_user.setPlaceholderText("Kamera-Benutzername")
            camera_password = QLineEdit()
            camera_password.setEchoMode(QLineEdit.Password)
            camera_password.setPlaceholderText("Passwort; bei vorhandener URL nur für Änderung nötig")
            stream = QComboBox()
            stream.addItem("Substream (schneller)", "sub")
            stream.addItem("Hauptstream (hohe Auflösung)", "main")
            apply_ip = QPushButton("Reolink-Quelle aus IP übernehmen")
            apply_ip.clicked.connect(
                lambda _checked=False, cid=camera_id: self._apply_reolink(cid)
            )
            source.currentIndexChanged.connect(
                lambda _index, cid=camera_id: self._set_ip_from_selection(cid)
            )
            role = QComboBox()
            role.addItem("Eingangsbereich", "entrance")
            role.addItem("Ausgangsbereich", "exit")
            entry_direction = QComboBox()
            entry_direction.addItem("A → B bedeutet hinein", "A_to_B")
            entry_direction.addItem("B → A bedeutet hinein", "B_to_A")
            exit_direction = QComboBox()
            exit_direction.addItem("B → A bedeutet hinaus", "B_to_A")
            exit_direction.addItem("A → B bedeutet hinaus", "A_to_B")
            exit_direction.setEnabled(False)
            exit_direction.setToolTip("Die Austrittsrichtung ist immer die Gegenrichtung.")
            entry_direction.currentIndexChanged.connect(
                lambda _index, x=entry_direction, y=exit_direction:
                    y.setCurrentIndex(max(0, y.findData(
                        "B_to_A" if x.currentData() == "A_to_B" else "A_to_B"
                    )))
            )
            counting_mode = QComboBox()
            counting_mode.addItem("Linie/Seitenwechsel (empfohlen)", "line")
            counting_mode.addItem("Erst am Bildrand nach Verschwinden", "exit_edge")
            status = StatusBadge()
            test = QPushButton("Verbindung testen")
            test.clicked.connect(lambda _checked=False, cid=camera_id: self._test(cid))
            form.addRow(QLabel(f"{camera_id.replace('_', ' ').title()}"), status)
            form.addRow("Anzeigename", name)
            form.addRow("Kameraquelle", source)
            form.addRow("IP-Adresse (manuell)", ip_address)
            form.addRow("RTSP-Port", rtsp_port)
            form.addRow("Benutzername", camera_user)
            form.addRow("Passwort", camera_password)
            form.addRow("Videoqualität", stream)
            form.addRow("", apply_ip)
            form.addRow("Kamera-Standort", role)
            form.addRow("Welche Richtung führt ins Gebäude?", entry_direction)
            form.addRow("Automatisch gegenläufiger Ausgang", exit_direction)
            form.addRow("Wann wird gezählt?", counting_mode)
            count_hint = QLabel(
                "Beide Türen zählen in beide Richtungen: Rein = +1, raus = −1. "
                "Im Bildrandmodus wird erst bei bestätigtem Seitenwechsel und "
                "anschließendem Verschwinden am Bildrand gezählt. "
                "Nur unsichtbar werden ist keine sichere Passage."
            )
            count_hint.setWordWrap(True)
            count_hint.setProperty("muted", True)
            form.addRow("", count_hint)
            form.addRow("", test)
            self.cards[camera_id] = {
                "name": name,
                "source": source,
                "ip_address": ip_address,
                "rtsp_port": rtsp_port,
                "camera_user": camera_user,
                "camera_password": camera_password,
                "stream": stream,
                "role": role,
                "entry_direction": entry_direction,
                "exit_direction": exit_direction,
                "counting_mode": counting_mode,
                "status": status,
            }
            self.layout.addWidget(card)
        self.layout.addStretch()

    def set_config(self, config: AppConfig) -> None:
        for camera_id, controls in self.cards.items():
            camera = config.cameras[camera_id]
            controls["name"].setText(camera.display_name)  # type: ignore[attr-defined]
            source: QComboBox = controls["source"]  # type: ignore[assignment]
            self._select_source(source, camera.device or "")
            # Populate IP and RTSP port from a saved stream without exposing
            # previously entered passwords in the form.
            from urllib.parse import urlsplit
            parsed = urlsplit(camera.device or "")
            if parsed.scheme.lower() in {"rtsp", "rtsps"} and parsed.hostname:
                controls["ip_address"].setText(parsed.hostname)  # type: ignore[attr-defined]
                controls["rtsp_port"].setValue(parsed.port or 554)  # type: ignore[attr-defined]
            role: QComboBox = controls["role"]  # type: ignore[assignment]
            role.setCurrentIndex(max(0, role.findData(camera.role)))
            entry: QComboBox = controls["entry_direction"]  # type: ignore[assignment]
            entry.setCurrentIndex(max(0, entry.findData(camera.entry_direction)))
            exits: QComboBox = controls["exit_direction"]  # type: ignore[assignment]
            exits.setCurrentIndex(max(0, exits.findData(camera.exit_direction)))
            mode: QComboBox = controls["counting_mode"]  # type: ignore[assignment]
            mode.setCurrentIndex(max(0, mode.findData(camera.counting_mode)))

    @staticmethod
    def _source(combo: QComboBox) -> str:
        index = combo.currentIndex()
        if index >= 0 and combo.currentText() == combo.itemText(index):
            data = combo.itemData(index)
            if isinstance(data, str):
                return data
        return combo.currentText().strip()

    @staticmethod
    def _select_source(combo: QComboBox, value: str) -> None:
        if not value:
            combo.setCurrentText("")
            return
        index = next(
            (i for i in range(combo.count()) if combo.itemData(i) == value), -1
        )
        if index < 0:
            # Preserve the real URI in item data but mask saved credentials.
            from urllib.parse import urlsplit
            parsed = urlsplit(value)
            label = (
                f"{parsed.scheme}://***@{parsed.hostname}{':' + str(parsed.port) if parsed.port else ''}{parsed.path}"
                if parsed.scheme.lower() in {"rtsp", "rtsps"} and parsed.password
                else value
            )
            combo.addItem(label, value)
            index = combo.count() - 1
        combo.setCurrentIndex(index)

    def set_discovered(self, sources: list[str]) -> None:
        for controls in self.cards.values():
            combo: QComboBox = controls["source"]  # type: ignore[assignment]
            current = self._source(combo)
            for source in sources:
                if source and not any(combo.itemData(i) == source for i in range(combo.count())):
                    combo.addItem(source, source)
            self._select_source(combo, current)
        self.discovery_status.setText(
            f"USB-Suche: {len(sources)} lokale USB-Webcam(s). "
            "Bereits konfigurierte RTSP-Kameras sind davon unabhängig."
        )

    def set_discovered_network(self, sources: list[RtspCandidate]) -> None:
        for controls in self.cards.values():
            combo: QComboBox = controls["source"]  # type: ignore[assignment]
            existing = self._source(combo)
            for camera in sources:
                source = camera.url_template
                if not any(combo.itemData(i) == source for i in range(combo.count())):
                    combo.addItem(camera.label, source)
            self._select_source(combo, existing)
        self.discovery_status.setText(
            f"{len(sources)} Netzwerkkandidat(en): "
            f"{sum(item.rtsp_ready for item in sources)} mit RTSP-Port erreichbar, "
            f"{sum(not item.rtsp_ready for item in sources)} nur ONVIF. "
            "Bitte IP übernehmen, Zugangsdaten eingeben und Videoframe testen."
            if sources else "Keine neuen IP-Kameras gefunden. Gespeicherte Kameras bleiben erhalten. "
            "IP manuell eingeben oder anderes /24-Subnetz wählen."
        )

    def _set_ip_from_selection(self, camera_id: str) -> None:
        # Selecting an ONVIF/RTSP candidate prepares the editable IP fields,
        # not a fake authenticated camera connection.
        from urllib.parse import urlsplit
        controls = self.cards.get(camera_id)
        if not controls:
            return
        source = self._source(controls["source"])  # type: ignore[arg-type]
        parsed = urlsplit(source)
        if parsed.scheme.lower() in {"rtsp", "rtsps"} and parsed.hostname:
            controls["ip_address"].setText(parsed.hostname)  # type: ignore[attr-defined]
            controls["rtsp_port"].setValue(parsed.port or 554)  # type: ignore[attr-defined]

    def _apply_reolink(self, camera_id: str) -> None:
        from PySide6.QtWidgets import QMessageBox
        from urllib.parse import unquote, urlsplit

        controls = self.cards[camera_id]
        combo: QComboBox = controls["source"]  # type: ignore[assignment]
        ip = controls["ip_address"].text().strip()  # type: ignore[attr-defined]
        username = controls["camera_user"].text().strip()  # type: ignore[attr-defined]
        password = controls["camera_password"].text()  # type: ignore[attr-defined]
        # Changing only sub/main quality must not remove existing credentials.
        # We never insert recovered passwords into any visible text field.
        existing = urlsplit(self._source(combo))
        if existing.hostname == ip and existing.username and existing.password:
            old_username = unquote(existing.username)
            if not username:
                username = old_username
            if not password and username == old_username:
                password = unquote(existing.password)
        try:
            url = reolink_rtsp_url(
                ip, username, password,
                port=controls["rtsp_port"].value(),  # type: ignore[attr-defined]
                stream=str(controls["stream"].currentData()),  # type: ignore[attr-defined]
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Kamera-IP prüfen", str(exc))
            return
        combo: QComboBox = controls["source"]  # type: ignore[assignment]
        self._select_source(combo, url)
        controls["camera_password"].clear()  # type: ignore[attr-defined]
        self.discovery_status.setText(
            "RTSP-Quelle vorbereitet. Verbindung testen und Einstellungen speichern."
        )

    def update_snapshot(self, snapshot: DashboardSnapshot) -> None:
        online_count = sum(
            str(c.get("status", "")).upper() == "ONLINE"
            and c.get("seconds_since_last_frame", 0) is not None
            and float(c.get("seconds_since_last_frame", 0)) < 10
            for c in snapshot.cameras
        )
        configured_count = sum(
            bool(self._source(c["source"])) for c in self.cards.values()  # type: ignore[arg-type]
        )
        self.cameras_summary.setText(
            f"{configured_count} konfigurierte Kameraquellen · "
            f"{online_count} von {len(snapshot.cameras)} liefern aktuell Bilder. "
            "USB-Suche und IP-Kamerasuche sind unabhängig."
        )
        for camera in snapshot.cameras:
            camera_id = str(camera.get("camera_id", ""))
            if camera_id not in self.cards:
                continue
            age = camera.get("seconds_since_last_frame")
            online = str(camera.get("status", "")).upper() == "ONLINE"
            if age is not None and float(age) > 10:
                online = False
            detail = f"{camera.get('status', 'unbekannt')}"
            if not online and age is not None and float(age) > 10:
                detail = "Kein aktuelles Bild"
            if online and camera.get("actual_fps") is not None:
                detail += f" · {camera['actual_fps']} FPS"
            if not online and camera.get("last_error"):
                detail += " · " + str(camera["last_error"])[:95]
            badge: StatusBadge = self.cards[camera_id]["status"]  # type: ignore[assignment]
            badge.set_state("ok" if online else "warning", detail)

    def set_test_result(self, source: str, ok: bool, message: str) -> None:
        for controls in self.cards.values():
            combo: QComboBox = controls["source"]  # type: ignore[assignment]
            if self._source(combo) == source:
                badge: StatusBadge = controls["status"]  # type: ignore[assignment]
                badge.set_state("ok" if ok else "error", message)

    def _test(self, camera_id: str) -> None:
        combo: QComboBox = self.cards[camera_id]["source"]  # type: ignore[assignment]
        self.test_requested.emit(self._source(combo))

    def _emit_save(self) -> None:
        values: dict[str, dict[str, str]] = {}
        for camera_id, controls in self.cards.items():
            values[camera_id] = {
                "display_name": controls["name"].text().strip(),  # type: ignore[attr-defined]
                "device": self._source(controls["source"]),  # type: ignore[arg-type]
                "role": str(controls["role"].currentData()),  # type: ignore[attr-defined]
                "entry_direction": str(controls["entry_direction"].currentData()),  # type: ignore[attr-defined]
                "exit_direction": str(controls["exit_direction"].currentData()),  # type: ignore[attr-defined]
                "counting_mode": str(controls["counting_mode"].currentData()),  # type: ignore[attr-defined]
            }
        self.save_requested.emit(values)


class EventsPage(BasePage):
    def __init__(self) -> None:
        super().__init__(
            "Ereignisse", "Eintritte, Austritte, unsichere Entscheidungen und Warnungen"
        )
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["Zeit", "Kamera", "Richtung", "Typ", "Sicher", "Grund"]
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.layout.addWidget(self.table, 1)

    def set_events(self, events: list[dict[str, Any]]) -> None:
        self.table.setRowCount(len(events))
        for row, event in enumerate(events):
            timestamp = event.get("timestamp")
            when = (
                datetime.fromtimestamp(float(timestamp))
                .astimezone()
                .strftime("%d.%m. %H:%M:%S")
                if timestamp
                else "—"
            )
            values = [
                when,
                event.get("camera_id") or "—",
                event.get("direction") or "—",
                event.get("event_type") or "Passage",
                "Nein" if event.get("uncertain") else "Ja",
                event.get("reason") or "—",
            ]
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(str(value)))


class HistoryPage(BasePage):
    def __init__(self) -> None:
        super().__init__(
            "Verlauf & Statistiken",
            "Aggregierte Passagewerte ohne Video- oder Bildspeicherung",
        )
        chart_card = Card()
        layout = QVBoxLayout(chart_card)
        title = QLabel("Passagen der letzten 24 Stunden")
        title.setStyleSheet("font-size:17px;font-weight:600;")
        self.chart = HistoryChart()
        layout.addWidget(title)
        layout.addWidget(self.chart)
        self.layout.addWidget(chart_card)
        self.layout.addStretch()


class HardwarePage(BasePage):
    diagnose_requested = Signal()
    model_import_requested = Signal(str, Path)
    model_download_requested = Signal()

    def __init__(self) -> None:
        super().__init__(
            "KI & Hardware", "Hailo-10H, YOLO26m, OSNet, Kameras und Systemressourcen"
        )
        row = QHBoxLayout()
        self.hailo = StatusBadge("Noch nicht geprüft")
        self.model = StatusBadge("Noch nicht geprüft")
        run = QPushButton("Hardwareprüfung starten")
        run.setProperty("primary", True)
        run.clicked.connect(self.diagnose_requested.emit)
        row.addWidget(QLabel("Hailo-10H"))
        row.addWidget(self.hailo)
        row.addSpacing(24)
        row.addWidget(QLabel("YOLO26m-Modell"))
        row.addWidget(self.model)
        row.addStretch()
        row.addWidget(run)
        self.layout.addLayout(row)
        imports = QHBoxLayout()
        download = QPushButton("Beide Originalmodelle herunterladen")
        download.setProperty("primary", True)
        download.setToolTip(
            "Hailo Model Zoo: YOLO26m und OSNet; streng über die hinterlegten SHA-256-Prüfsummen verifiziert."
        )
        download.clicked.connect(self.model_download_requested.emit)
        imports.addWidget(download)
        detector = QPushButton("YOLO26m-HEF importieren")
        detector.clicked.connect(lambda: self._choose_model("detector"))
        reid = QPushButton("OSNet-HEF importieren")
        reid.clicked.connect(lambda: self._choose_model("reid"))
        imports.addWidget(detector)
        imports.addWidget(reid)
        imports.addStretch()
        self.layout.addLayout(imports)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setPlaceholderText(
            "Starten Sie eine Prüfung. Die Oberfläche bleibt währenddessen bedienbar."
        )
        self.layout.addWidget(self.details, 1)

    def set_report(self, report: dict[str, Any]) -> None:
        hailo = report.get("hailortcli", {})
        ready = hailo.get("returncode") == 0 and bool(hailo.get("stdout"))
        self.hailo.set_state(
            "ok" if ready else "error", "Bereit" if ready else "Nicht erkannt"
        )
        detector = report.get("detector", {})
        model_ready = bool(detector.get("exists"))
        self.model.set_state(
            "ok" if model_ready else "error",
            "Installiert" if model_ready else "Fehlt",
        )
        self.details.setPlainText(json.dumps(report, indent=2, ensure_ascii=False))

    def _choose_model(self, kind: str) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self, "Hailo-Modell importieren", "", "Hailo Executable Format (*.hef)"
        )
        if filename:
            self.model_import_requested.emit(kind, Path(filename))


class SystemPage(BasePage):
    service_action_requested = Signal(str)
    logs_requested = Signal()
    diagnostic_export_requested = Signal()
    pairing_export_requested = Signal()

    def __init__(self) -> None:
        super().__init__(
            "System",
            "Hintergrunddienst, Datenbank, API, Android-Verbindung, Logs und Supportdiagnose",
        )
        card = Card()
        layout = QVBoxLayout(card)
        row = QHBoxLayout()
        self.service_badge = StatusBadge()
        row.addWidget(QLabel("Hintergrunddienst"))
        row.addWidget(self.service_badge)
        row.addStretch()
        for label, action in (
            ("Starten", "start"),
            ("Stoppen", "stop"),
            ("Neu starten", "restart"),
        ):
            button = QPushButton(label)
            button.clicked.connect(
                lambda _checked=False, value=action: self.service_action_requested.emit(
                    value
                )
            )
            row.addWidget(button)
        layout.addLayout(row)
        self.database_label = QLabel("Datenbank: unbekannt")
        self.database_label.setProperty("muted", True)
        layout.addWidget(self.database_label)
        self.api_label = QLabel("API/Android: unbekannt")
        self.api_label.setProperty("muted", True)
        layout.addWidget(self.api_label)
        self.layout.addWidget(card)
        toolbar = QHBoxLayout()
        logs = QPushButton("Logs aktualisieren")
        logs.clicked.connect(self.logs_requested.emit)
        export = QPushButton("Diagnosepaket exportieren")
        export.setProperty("primary", True)
        export.clicked.connect(self.diagnostic_export_requested.emit)
        pairing = QPushButton("Android-Pairing exportieren")
        pairing.clicked.connect(self.pairing_export_requested.emit)
        toolbar.addWidget(logs)
        toolbar.addWidget(export)
        toolbar.addWidget(pairing)
        toolbar.addStretch()
        self.layout.addLayout(toolbar)
        self.logs = QPlainTextEdit()
        self.logs.setReadOnly(True)
        self.logs.setPlaceholderText(
            "Technische Logs werden hier angezeigt; bekannte Secrets werden im Export redigiert."
        )
        self.layout.addWidget(self.logs, 1)

    def update_snapshot(self, snapshot: DashboardSnapshot) -> None:
        if snapshot.service:
            state = snapshot.service.state.value
            color = (
                "ok"
                if state == "läuft"
                else "error"
                if state == "Fehler"
                else "warning"
            )
            self.service_badge.set_state(color, state)
        exists = snapshot.database.get("exists")
        size = int(snapshot.database.get("size_bytes", 0))
        self.database_label.setText(
            f"Datenbank: {'bereit' if exists else 'noch nicht angelegt'} · {size / 1024:.1f} KiB"
        )
        api = snapshot.api
        endpoint = f"{api.get('bind_host', '—')}:{api.get('port', '—')}"
        protection = "TLS" if api.get("tls") else "nur lokal/kein TLS"
        self.api_label.setText(
            f"API/Android: {'aktiv' if api.get('enabled') else 'deaktiviert'} · {endpoint} · {protection}"
        )


class PrivacyPage(BasePage):
    save_requested = Signal(dict)
    delete_requested = Signal(bool)
    license_import_requested = Signal(Path)

    def __init__(self) -> None:
        super().__init__(
            "Datenschutz & Sicherheit",
            "Aktive Schutzmaßnahmen verständlich prüfen und verwalten",
        )
        form_card = Card()
        form = QFormLayout(form_card)
        form.setContentsMargins(18, 16, 18, 16)
        self.controller = QLineEdit()
        self.contact = QLineEdit()
        self.purpose = QLineEdit()
        self.legal_basis = QLineEdit()
        self.notice = QCheckBox("Datenschutzhinweis ist sichtbar angebracht")
        self.preview = QCheckBox("Lokale anonymisierte Vorschau aktivieren")
        self.remote_video = QCheckBox("Remote-Livebild explizit aktivieren")
        self.store_events = QCheckBox("Granulare Ereignisse verschlüsselt speichern")
        self.retention = QSpinBox()
        self.retention.setRange(1, 168)
        self.retention.setSuffix(" Stunden")
        form.addRow("Verantwortlicher", self.controller)
        form.addRow("Datenschutzkontakt", self.contact)
        form.addRow("Zweck", self.purpose)
        form.addRow("Geprüfte Rechtsgrundlage", self.legal_basis)
        form.addRow("", self.notice)
        form.addRow("", self.preview)
        form.addRow("", self.remote_video)
        form.addRow("", self.store_events)
        form.addRow("Aufbewahrung", self.retention)
        save = QPushButton("Schutzeinstellungen speichern")
        save.setProperty("primary", True)
        save.clicked.connect(self._emit_save)
        form.addRow("", save)
        self.layout.addWidget(form_card)

        license_card = Card()
        license_layout = QVBoxLayout(license_card)
        license_layout.addWidget(QLabel("Produktlizenz"))
        self.license_badge = StatusBadge()
        self.license_detail = QLabel()
        self.license_detail.setProperty("muted", True)
        self.license_detail.setWordWrap(True)
        import_button = QPushButton("Lizenzdatei importieren")
        import_button.clicked.connect(self._choose_license)
        license_layout.addWidget(self.license_badge)
        license_layout.addWidget(self.license_detail)
        license_layout.addWidget(import_button, 0, Qt.AlignLeft)
        self.layout.addWidget(license_card)

        danger = Card()
        danger_layout = QHBoxLayout(danger)
        danger_layout.setContentsMargins(18, 16, 18, 16)
        danger_layout.addWidget(QLabel("Gespeicherte granulare Daten löschen"))
        danger_layout.addStretch()
        delete = QPushButton("Personenbezogene Daten löschen")
        delete.clicked.connect(lambda: self.delete_requested.emit(False))
        danger_layout.addWidget(delete)
        self.layout.addWidget(danger)
        self.layout.addStretch()

    def set_config(self, config: AppConfig) -> None:
        self.controller.setText(config.privacy.controller_name)
        self.contact.setText(config.privacy.controller_contact)
        self.purpose.setText(config.privacy.purpose)
        self.legal_basis.setText(config.privacy.legal_basis)
        self.notice.setChecked(config.privacy.privacy_notice_acknowledged)
        self.preview.setChecked(config.display.show_camera_preview)
        self.remote_video.setChecked(config.privacy.video_stream_enabled)
        self.store_events.setChecked(config.database.store_events)
        self.retention.setValue(config.database.retention_hours)

    def set_license(self, status: LicenseStatus) -> None:
        self.license_badge.set_state("ok" if status.valid else "error", status.label)
        detail = status.detail
        if status.license_id:
            detail += f" · ID {status.license_id}"
        self.license_detail.setText(detail)

    def _emit_save(self) -> None:
        self.save_requested.emit(
            {
                "privacy.controller_name": self.controller.text().strip(),
                "privacy.controller_contact": self.contact.text().strip(),
                "privacy.purpose": self.purpose.text().strip(),
                "privacy.legal_basis": self.legal_basis.text().strip(),
                "privacy.privacy_notice_acknowledged": self.notice.isChecked(),
                "privacy.privacy_notice_acknowledged_at": datetime.now()
                .astimezone()
                .isoformat()
                if self.notice.isChecked()
                else "",
                "display.show_camera_preview": self.preview.isChecked(),
                "display.anonymization_mode": "full_frame",
                "privacy.video_stream_enabled": self.remote_video.isChecked(),
                "database.store_events": self.store_events.isChecked(),
                "database.retention_hours": self.retention.value(),
            }
        )

    def _choose_license(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Signierte Lizenz importieren",
            "",
            "Lizenz (*.json);;Alle Dateien (*)",
        )
        if filename:
            self.license_import_requested.emit(Path(filename))


class SettingsPage(BasePage):
    save_requested = Signal(dict)
    security_asset_import_requested = Signal(str, Path)

    def __init__(self) -> None:
        super().__init__(
            "Einstellungen",
            "Normale Betriebsparameter grafisch ändern; sichere Produktionsregeln bleiben erzwungen",
        )
        card = Card()
        form = QFormLayout(card)
        form.setContentsMargins(18, 16, 18, 16)
        self.confidence = QDoubleSpinBox()
        self.confidence.setRange(0.05, 0.95)
        self.confidence.setSingleStep(0.05)
        self.reid = QDoubleSpinBox()
        self.reid.setRange(0.50, 0.99)
        self.reid.setSingleStep(0.01)
        self.timeout = QSpinBox()
        self.timeout.setRange(1, 1440)
        self.timeout.setSuffix(" Minuten")
        self.api_enabled = QCheckBox("Lokale API aktivieren")
        self.api_host = QLineEdit()
        self.api_port = QSpinBox()
        self.api_port.setRange(1, 65535)
        self.tls_certificate = QLineEdit()
        self.tls_certificate.setReadOnly(True)
        self.tls_private_key = QLineEdit()
        self.tls_private_key.setReadOnly(True)
        certificate_button = QPushButton("TLS-Zertifikat importieren")
        certificate_button.clicked.connect(lambda: self._choose_tls("certificate"))
        key_button = QPushButton("TLS-Schlüssel importieren")
        key_button.clicked.connect(lambda: self._choose_tls("private_key"))
        form.addRow("Detektionsschwelle", self.confidence)
        form.addRow("Re-ID-Schwelle", self.reid)
        form.addRow("Anwesenheits-Timeout", self.timeout)
        form.addRow("", self.api_enabled)
        form.addRow("API-Bindung", self.api_host)
        form.addRow("API-Port", self.api_port)
        form.addRow("TLS-Zertifikat", self.tls_certificate)
        form.addRow("", certificate_button)
        form.addRow("TLS-Privatschlüssel", self.tls_private_key)
        form.addRow("", key_button)
        warning = QLabel(
            "Remote-Bindung wird nur mit Authentifizierung und TLS akzeptiert. CPU-/Dummy-Fallbacks können hier nicht aktiviert werden."
        )
        warning.setWordWrap(True)
        warning.setProperty("muted", True)
        form.addRow("Sichere Grenzen", warning)
        save = QPushButton("Einstellungen speichern")
        save.setProperty("primary", True)
        save.clicked.connect(self._emit_save)
        form.addRow("", save)
        self.layout.addWidget(card)
        self.layout.addStretch()

    def set_config(self, config: AppConfig) -> None:
        self.confidence.setValue(config.model.confidence_threshold)
        self.reid.setValue(config.identity.reid_threshold)
        self.timeout.setValue(config.timeout.presence_timeout_minutes)
        self.api_enabled.setChecked(config.api.enabled)
        self.api_host.setText(config.api.bind_host)
        self.api_port.setValue(config.api.port)
        self.tls_certificate.setText(config.api.tls_certificate)
        self.tls_private_key.setText(config.api.tls_private_key)

    def _emit_save(self) -> None:
        self.save_requested.emit(
            {
                "model.confidence_threshold": self.confidence.value(),
                "identity.reid_threshold": self.reid.value(),
                "timeout.presence_timeout_minutes": self.timeout.value(),
                "api.enabled": self.api_enabled.isChecked(),
                "api.bind_host": self.api_host.text().strip(),
                "api.port": self.api_port.value(),
            }
        )

    def _choose_tls(self, kind: str) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "TLS-Datei importieren",
            "",
            "TLS/PEM (*.crt *.key *.pem);;Alle Dateien (*)",
        )
        if filename:
            self.security_asset_import_requested.emit(kind, Path(filename))


class AboutPage(BasePage):
    def __init__(self, version: str, project_root: Path) -> None:
        super().__init__("Über", "Version, Lizenzinformationen und Projektkomponenten")
        card = Card()
        layout = QVBoxLayout(card)
        name = QLabel("PersonenZähler Desktop Suite")
        name.setStyleSheet("font-size:20px;font-weight:650;")
        layout.addWidget(name)
        layout.addWidget(QLabel(f"Version {version}"))
        root = QLabel(f"Laufzeitbasis: {project_root}")
        root.setProperty("muted", True)
        root.setWordWrap(True)
        layout.addWidget(root)
        text = QLabel(
            "Native Linux-Anwendung für Raspberry Pi 5, Hailo-10H und YOLO26m. "
            "Sie stellt technische Privacy-by-Design-Maßnahmen bereit; die Rechtmäßigkeit eines konkreten Einsatzes muss der Betreiber prüfen."
        )
        text.setWordWrap(True)
        layout.addWidget(text)
        self.layout.addWidget(card)
        self.layout.addStretch()
