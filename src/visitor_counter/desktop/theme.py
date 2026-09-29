from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication

LIGHT = {
    "window": "#f5f6f8",
    "surface": "#ffffff",
    "surface_alt": "#eef1f5",
    "text": "#15171a",
    "muted": "#616975",
    "border": "#dfe3e8",
    "accent": "#0f6cbd",
    "accent_hover": "#115ea3",
    "success": "#0f7b0f",
    "warning": "#9d5d00",
    "danger": "#c42b1c",
}

DARK = {
    "window": "#111315",
    "surface": "#1b1d20",
    "surface_alt": "#25282c",
    "text": "#f4f4f4",
    "muted": "#a7adb5",
    "border": "#34383d",
    "accent": "#60a5fa",
    "accent_hover": "#7db4f7",
    "success": "#6ccb5f",
    "warning": "#f6c344",
    "danger": "#ff8273",
}


def stylesheet(dark: bool) -> str:
    c = DARK if dark else LIGHT
    return f"""
    * {{ font-size: 14px; }}
    QMainWindow, QDialog, QWizard, QWidget#AppRoot {{ background: {c["window"]}; color: {c["text"]}; }}
    QWidget {{ color: {c["text"]}; }}
    QWidget#Sidebar {{ background: {c["surface"]}; border-right: 1px solid {c["border"]}; }}
    QWidget#TopBar {{ background: {c["window"]}; }}
    QFrame[card='true'] {{ background: {c["surface"]}; border: 1px solid {c["border"]}; border-radius: 5px; }}
    QLabel[muted='true'] {{ color: {c["muted"]}; }}
    QLabel[title='true'] {{ font-size: 22px; font-weight: 600; }}
    QLabel[metric='true'] {{ font-size: 26px; font-weight: 650; }}
    QLabel[badge='true'] {{ padding: 5px 10px; border-radius: 4px; background: {c["surface_alt"]}; }}
    QPushButton {{ min-height: 34px; padding: 0 14px; border: 1px solid {c["border"]}; border-radius: 5px; background: {c["surface"]}; }}
    QPushButton:hover {{ background: {c["surface_alt"]}; }}
    QPushButton:pressed {{ background: {c["border"]}; }}
    QPushButton[primary='true'] {{ color: white; background: {c["accent"]}; border-color: {c["accent"]}; font-weight: 600; }}
    QPushButton[primary='true']:hover {{ background: {c["accent_hover"]}; }}
    QPushButton[nav='true'] {{ text-align: left; padding-left: 16px; min-height: 40px; border: none; background: transparent; }}
    QPushButton[nav='true']:checked {{ background: {c["surface_alt"]}; color: {c["accent"]}; font-weight: 600; }}
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QTableWidget {{
      min-height: 34px; padding: 2px 8px; border: 1px solid {c["border"]}; border-radius: 5px; background: {c["surface"]}; selection-background-color: {c["accent"]};
    }}
    QTableWidget {{ gridline-color: {c["border"]}; }}
    QHeaderView::section {{ background: {c["surface_alt"]}; border: none; border-bottom: 1px solid {c["border"]}; padding: 8px; font-weight: 600; }}
    QScrollArea {{ border: none; background: transparent; }}
    QScrollBar:vertical {{ width: 10px; background: transparent; }}
    QScrollBar::handle:vertical {{ background: {c["border"]}; min-height: 26px; border-radius: 5px; }}
    QToolTip {{ background: {c["surface"]}; color: {c["text"]}; border: 1px solid {c["border"]}; }}
    """


def apply_theme(app: QApplication, dark: bool) -> None:
    colors = DARK if dark else LIGHT
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(colors["window"]))
    palette.setColor(QPalette.WindowText, QColor(colors["text"]))
    palette.setColor(QPalette.Base, QColor(colors["surface"]))
    palette.setColor(QPalette.Text, QColor(colors["text"]))
    palette.setColor(QPalette.Button, QColor(colors["surface"]))
    palette.setColor(QPalette.ButtonText, QColor(colors["text"]))
    palette.setColor(QPalette.Highlight, QColor(colors["accent"]))
    palette.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    app.setPalette(palette)
    available = set(QFontDatabase.families())
    if not available:
        for font_path in (
            Path("C:/Windows/Fonts/segoeui.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
            Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"),
        ):
            if (
                font_path.is_file()
                and QFontDatabase.addApplicationFont(str(font_path)) >= 0
            ):
                available = set(QFontDatabase.families())
                if available:
                    break
    family = next(
        (
            candidate
            for candidate in (
                "Inter",
                "Segoe UI Variable",
                "Segoe UI",
                "Noto Sans",
                "DejaVu Sans",
            )
            if candidate in available
        ),
        app.font().family(),
    )
    app.setFont(QFont(family, 10))
    app.setStyleSheet(stylesheet(dark))
