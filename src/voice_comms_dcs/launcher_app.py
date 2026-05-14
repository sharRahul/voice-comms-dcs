"""
launcher_app.py — PyQt6 main launcher window for Voice-Comms-DCS.

Replaces the legacy Tkinter ui.py as the primary user-facing entry point.
Provides a modern dark-themed control panel for starting/stopping the
Nimbus WebRTC bridge, monitoring connection status, and quick settings.
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
import threading
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import (
    QSettings,
    Qt,
    QTimer,
    pyqtSignal,
    QObject,
)
from PyQt6.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QIcon,
    QPainter,
    QPixmap,
)
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
    QMenu,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

APP_NAME = "Voice-Comms-DCS"
APP_VERSION = "v0.4.0"
WINDOW_TITLE = f"{APP_NAME} — Nimbus Launcher"
WINDOW_W = 820
WINDOW_H = 560

# Colour palette (matches web dashboard)
C_BG = "#050812"
C_PANEL = "#0d1120"
C_PANEL_ALT = "#111827"
C_BORDER = "#1e2d47"
C_ACCENT = "#38bdf8"
C_ACCENT2 = "#5eead4"
C_TEXT = "#e5f6ff"
C_TEXT_DIM = "#7a9bbf"
C_GREEN = "#22c55e"
C_RED = "#ef4444"
C_YELLOW = "#eab308"
C_CARD_HOVER = "#131e34"

MAX_LOG_ENTRIES = 20

# Path roots — resolved relative to this file so they work from any CWD
_SRC_ROOT = Path(__file__).resolve().parent
_PROJECT_ROOT = _SRC_ROOT.parent.parent  # src/voice_comms_dcs -> root
_CONFIG_PATH = _PROJECT_ROOT / "config" / "commands.json"
_PROFILES_DIR = _PROJECT_ROOT / "config" / "aircraft_profiles"


# ---------------------------------------------------------------------------
# Global stylesheet
# ---------------------------------------------------------------------------

STYLESHEET = f"""
/* ── Root ────────────────────────────────────────────── */
QMainWindow, QWidget {{
    background-color: {C_BG};
    color: {C_TEXT};
    font-family: "Segoe UI", "Inter", "SF Pro Display", sans-serif;
    font-size: 13px;
}}

/* ── Panels / Cards ──────────────────────────────────── */
QFrame#card {{
    background-color: {C_PANEL};
    border: 1px solid {C_BORDER};
    border-radius: 8px;
}}
QFrame#header_bar {{
    background-color: {C_PANEL};
    border-bottom: 1px solid {C_BORDER};
    border-radius: 0px;
}}
QFrame#bottom_panel {{
    background-color: {C_PANEL_ALT};
    border: 1px solid {C_BORDER};
    border-radius: 8px;
}}

/* ── Labels ──────────────────────────────────────────── */
QLabel#app_title {{
    color: {C_TEXT};
    font-size: 17px;
    font-weight: 700;
    letter-spacing: 0.5px;
}}
QLabel#app_version {{
    color: {C_ACCENT};
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 1px;
}}
QLabel#nimbus_label {{
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1.5px;
}}
QLabel#card_title {{
    color: {C_TEXT_DIM};
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1.5px;
    text-transform: uppercase;
}}
QLabel#card_status {{
    color: {C_TEXT};
    font-size: 14px;
    font-weight: 600;
}}
QLabel#card_detail {{
    color: {C_TEXT_DIM};
    font-size: 11px;
}}
QLabel#section_title {{
    color: {C_TEXT_DIM};
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1.5px;
}}
QLabel#settings_label {{
    color: {C_TEXT_DIM};
    font-size: 11px;
}}
QLabel#settings_value {{
    color: {C_TEXT};
    font-size: 11px;
}}

/* ── Buttons ─────────────────────────────────────────── */
QPushButton {{
    border-radius: 6px;
    padding: 6px 14px;
    font-size: 12px;
    font-weight: 600;
    border: 1px solid {C_BORDER};
    background-color: {C_PANEL};
    color: {C_TEXT};
}}
QPushButton:hover {{
    background-color: {C_CARD_HOVER};
    border-color: {C_ACCENT};
    color: {C_ACCENT};
}}
QPushButton:pressed {{
    background-color: {C_BG};
}}
QPushButton#btn_dashboard {{
    background-color: {C_ACCENT};
    color: #050812;
    border: none;
    font-size: 14px;
    font-weight: 700;
    padding: 12px 24px;
    border-radius: 8px;
    min-height: 48px;
}}
QPushButton#btn_dashboard:hover {{
    background-color: #7dd3f8;
    color: #050812;
}}
QPushButton#btn_dashboard:pressed {{
    background-color: #0ea5e9;
}}
QPushButton#btn_bridge_start {{
    background-color: {C_PANEL};
    color: {C_ACCENT2};
    border: 1px solid {C_ACCENT2};
    font-size: 14px;
    font-weight: 700;
    padding: 12px 24px;
    border-radius: 8px;
    min-height: 48px;
}}
QPushButton#btn_bridge_start:hover {{
    background-color: #0f2a2a;
    border-color: {C_ACCENT2};
}}
QPushButton#btn_bridge_stop {{
    background-color: {C_PANEL};
    color: {C_RED};
    border: 1px solid {C_RED};
    font-size: 14px;
    font-weight: 700;
    padding: 12px 24px;
    border-radius: 8px;
    min-height: 48px;
}}
QPushButton#btn_bridge_stop:hover {{
    background-color: #2a0f0f;
    border-color: {C_RED};
}}
QPushButton#btn_small {{
    padding: 4px 10px;
    font-size: 11px;
    border-radius: 4px;
    min-height: 0;
}}
QPushButton#btn_card_action {{
    padding: 4px 12px;
    font-size: 11px;
    border-radius: 4px;
    min-height: 0;
    background-color: {C_PANEL_ALT};
    border-color: {C_BORDER};
}}
QPushButton#btn_card_action:hover {{
    border-color: {C_ACCENT};
    color: {C_ACCENT};
    background-color: {C_CARD_HOVER};
}}

/* ── Log list ────────────────────────────────────────── */
QListWidget#activity_log {{
    background-color: #07090f;
    border: 1px solid {C_BORDER};
    border-radius: 6px;
    color: {C_TEXT_DIM};
    font-family: "Consolas", "Courier New", monospace;
    font-size: 11px;
    padding: 4px;
    outline: none;
}}
QListWidget#activity_log::item {{
    padding: 2px 4px;
    border: none;
}}
QListWidget#activity_log::item:selected {{
    background-color: {C_PANEL};
    color: {C_TEXT};
}}

/* ── ComboBox ────────────────────────────────────────── */
QComboBox {{
    background-color: {C_PANEL_ALT};
    border: 1px solid {C_BORDER};
    border-radius: 5px;
    padding: 4px 8px;
    color: {C_TEXT};
    font-size: 11px;
    min-width: 120px;
}}
QComboBox:hover {{
    border-color: {C_ACCENT};
}}
QComboBox::drop-down {{
    border: none;
    width: 20px;
}}
QComboBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {C_TEXT_DIM};
    margin-right: 6px;
}}
QComboBox QAbstractItemView {{
    background-color: {C_PANEL};
    border: 1px solid {C_BORDER};
    selection-background-color: {C_ACCENT};
    selection-color: #050812;
    color: {C_TEXT};
}}

/* ── Scrollbars ──────────────────────────────────────── */
QScrollBar:vertical {{
    background: {C_BG};
    width: 6px;
    border-radius: 3px;
}}
QScrollBar::handle:vertical {{
    background: {C_BORDER};
    border-radius: 3px;
    min-height: 20px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}

/* ── Separator lines ─────────────────────────────────── */
QFrame[frameShape="4"], QFrame[frameShape="5"] {{
    color: {C_BORDER};
}}

/* ── Dialog ──────────────────────────────────────────── */
QDialog {{
    background-color: {C_PANEL};
}}
QDialogButtonBox QPushButton {{
    min-width: 80px;
}}
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_dot_pixmap(color: str, size: int = 10) -> QPixmap:
    """Return a circular pixmap used as a status dot."""
    px = QPixmap(size, size)
    px.fill(Qt.GlobalColor.transparent)
    painter = QPainter(px)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(color))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(0, 0, size, size)
    painter.end()
    return px


def _make_tray_icon_pixmap(size: int = 64) -> QPixmap:
    """Generate a simple tray icon pixmap with the app initials."""
    px = QPixmap(size, size)
    px.fill(Qt.GlobalColor.transparent)
    painter = QPainter(px)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(C_PANEL))
    painter.setPen(QColor(C_ACCENT))
    painter.drawRoundedRect(2, 2, size - 4, size - 4, 10, 10)
    font = QFont("Segoe UI", size // 4, QFont.Weight.Bold)
    painter.setFont(font)
    painter.setPen(QColor(C_ACCENT))
    painter.drawText(px.rect(), Qt.AlignmentFlag.AlignCenter, "VC")
    painter.end()
    return px


def _ts() -> str:
    """Return a short HH:MM:SS timestamp."""
    return datetime.now().strftime("%H:%M:%S")


def _open_file_in_editor(path: str) -> None:
    """Open a file in the platform default text editor."""
    system = platform.system()
    if system == "Windows":
        os.startfile(path)  # type: ignore[attr-defined]
    elif system == "Darwin":
        subprocess.Popen(["open", path])
    else:
        for editor in ("xdg-open", "gedit", "nano"):
            if _which(editor):
                subprocess.Popen([editor, path])
                return


def _which(cmd: str) -> bool:
    """Return True if *cmd* is available on PATH."""
    import shutil
    return shutil.which(cmd) is not None


# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------

class LauncherConfig:
    """Reads the subset of commands.json fields the launcher needs."""

    def __init__(self) -> None:
        self.config_path: str = str(_CONFIG_PATH)
        self.webrtc_host: str = "127.0.0.1"
        self.webrtc_port: int = 8765
        self.ollama_base_url: str = "http://127.0.0.1:11434"
        self.ollama_model: str = "qwen2.5:0.5b"
        self.language_selected: str = "en"
        self.language_installed: list[str] = ["en"]
        self.ptt_hotkey: str = "right_ctrl"
        self.aircraft_profiles: list[str] = []
        self._load()

    def _load(self) -> None:
        try:
            with open(_CONFIG_PATH, encoding="utf-8") as fh:
                data: dict = json.load(fh)
        except (FileNotFoundError, json.JSONDecodeError):
            data = {}

        webrtc = data.get("webrtc", {})
        self.webrtc_host = webrtc.get("host", self.webrtc_host)
        self.webrtc_port = int(webrtc.get("port", self.webrtc_port))

        llm = data.get("llm", {})
        self.ollama_base_url = llm.get("base_url", self.ollama_base_url)
        self.ollama_model = llm.get("model", self.ollama_model)

        lang = data.get("language", {})
        self.language_selected = lang.get("selected", self.language_selected)
        installed = lang.get("installed", self.language_installed)
        self.language_installed = installed if isinstance(installed, list) else [installed]

        ptt = data.get("push_to_talk", {})
        self.ptt_hotkey = ptt.get("hotkey", self.ptt_hotkey)

        # Aircraft profiles from filesystem
        if _PROFILES_DIR.is_dir():
            self.aircraft_profiles = sorted(
                p.stem for p in _PROFILES_DIR.glob("*.json")
            )
        if not self.aircraft_profiles:
            self.aircraft_profiles = ["default"]

    @property
    def dashboard_url(self) -> str:
        return f"http://{self.webrtc_host}:{self.webrtc_port}/dashboard"


# ---------------------------------------------------------------------------
# Status-dot label helper widget
# ---------------------------------------------------------------------------

class StatusDot(QLabel):
    """A small coloured circle indicator."""

    def __init__(self, color: str = C_RED, size: int = 10, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._size = size
        self.set_color(color)
        self.setFixedSize(size, size)

    def set_color(self, color: str) -> None:
        self.setPixmap(_make_dot_pixmap(color, self._size))


# ---------------------------------------------------------------------------
# Status card widget
# ---------------------------------------------------------------------------

class StatusCard(QFrame):
    """One of the three status cards in the top row."""

    def __init__(
        self,
        title: str,
        status_text: str = "—",
        detail_text: str = "",
        show_action: bool = False,
        action_label: str = "Start",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        self.setMinimumWidth(210)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(4)

        # Title row
        title_row = QHBoxLayout()
        title_row.setSpacing(6)
        self._dot = StatusDot(C_RED, size=8)
        lbl_title = QLabel(title.upper())
        lbl_title.setObjectName("card_title")
        title_row.addWidget(self._dot)
        title_row.addWidget(lbl_title)
        title_row.addStretch()
        root.addLayout(title_row)

        # Status
        self._lbl_status = QLabel(status_text)
        self._lbl_status.setObjectName("card_status")
        root.addWidget(self._lbl_status)

        # Detail
        self._lbl_detail = QLabel(detail_text)
        self._lbl_detail.setObjectName("card_detail")
        root.addWidget(self._lbl_detail)

        # Optional action button
        self._btn_action: Optional[QPushButton] = None
        if show_action:
            self._btn_action = QPushButton(action_label)
            self._btn_action.setObjectName("btn_card_action")
            self._btn_action.setCursor(Qt.CursorShape.PointingHandCursor)
            root.addSpacing(4)
            root.addWidget(self._btn_action, alignment=Qt.AlignmentFlag.AlignLeft)

    def set_status(self, text: str, color: str) -> None:
        self._lbl_status.setText(text)
        self._dot.set_color(color)

    def set_detail(self, text: str) -> None:
        self._lbl_detail.setText(text)

    @property
    def action_button(self) -> Optional[QPushButton]:
        return self._btn_action


# ---------------------------------------------------------------------------
# "Minimize to tray" preference dialog
# ---------------------------------------------------------------------------

class TrayPreferenceDialog(QDialog):
    """Ask the user once whether to minimise to tray on close."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Close behaviour")
        self.setModal(True)
        self.setFixedSize(360, 160)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(12)

        lbl = QLabel(
            "What should happen when you close the window?\n\n"
            "• Minimise to system tray — the bridge keeps running.\n"
            "• Quit the application entirely."
        )
        lbl.setWordWrap(True)
        layout.addWidget(lbl)

        btns = QDialogButtonBox()
        self._btn_tray = btns.addButton("Minimise to Tray", QDialogButtonBox.ButtonRole.AcceptRole)
        self._btn_quit = btns.addButton("Quit", QDialogButtonBox.ButtonRole.RejectRole)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

        self.minimize_to_tray: bool = True

    def accept(self) -> None:
        self.minimize_to_tray = True
        super().accept()

    def reject(self) -> None:
        self.minimize_to_tray = False
        super().reject()


# ---------------------------------------------------------------------------
# Signals bridge (for cross-thread UI updates)
# ---------------------------------------------------------------------------

class _Signals(QObject):
    log_message = pyqtSignal(str)
    bridge_died = pyqtSignal()


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class LauncherWindow(QMainWindow):
    """Primary launcher window for Voice-Comms-DCS."""

    def __init__(self) -> None:
        super().__init__()
        self._cfg = LauncherConfig()
        self._bridge_proc: Optional[subprocess.Popen] = None  # type: ignore[type-arg]
        self._signals = _Signals()
        self._minimize_to_tray: Optional[bool] = None  # None = not yet decided

        self._settings = QSettings("VoiceCommsDCS", "Launcher")
        stored = self._settings.value("minimize_to_tray")
        if stored is not None:
            self._minimize_to_tray = stored == "true" or stored is True

        self._build_ui()
        self._build_tray()
        self._connect_signals()
        self._start_poll_timer()
        self._log(f"Launcher started — {APP_NAME} {APP_VERSION}")

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self.setWindowTitle(WINDOW_TITLE)
        self.setFixedSize(WINDOW_W, WINDOW_H)
        self.setWindowIcon(QIcon(_make_tray_icon_pixmap()))

        # Centre on screen
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            self.move(
                geo.center().x() - WINDOW_W // 2,
                geo.center().y() - WINDOW_H // 2,
            )

        central = QWidget()
        self.setCentralWidget(central)
        vbox = QVBoxLayout(central)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)

        vbox.addWidget(self._build_header())
        inner = QWidget()
        inner_layout = QVBoxLayout(inner)
        inner_layout.setContentsMargins(16, 14, 16, 14)
        inner_layout.setSpacing(12)
        inner_layout.addLayout(self._build_status_cards())
        inner_layout.addLayout(self._build_main_actions())
        inner_layout.addLayout(self._build_bottom_section())
        vbox.addWidget(inner)

    def _build_header(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("header_bar")
        bar.setFixedHeight(52)

        h = QHBoxLayout(bar)
        h.setContentsMargins(18, 0, 18, 0)
        h.setSpacing(10)

        # App name
        lbl_name = QLabel(APP_NAME)
        lbl_name.setObjectName("app_title")
        h.addWidget(lbl_name)

        lbl_ver = QLabel(APP_VERSION)
        lbl_ver.setObjectName("app_version")
        h.addWidget(lbl_ver)

        h.addStretch()

        # Status dot + NIMBUS label on right
        self._header_dot = StatusDot(C_RED, size=10)
        h.addWidget(self._header_dot)

        self._lbl_nimbus = QLabel("NIMBUS OFFLINE")
        self._lbl_nimbus.setObjectName("nimbus_label")
        self._lbl_nimbus.setStyleSheet(f"color: {C_RED};")
        h.addWidget(self._lbl_nimbus)

        return bar

    def _build_status_cards(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(10)

        # Card 1 – WebRTC Bridge
        self._card_bridge = StatusCard(
            "WebRTC Bridge",
            status_text="Stopped",
            detail_text=f"Port {self._cfg.webrtc_port}",
            show_action=True,
            action_label="Start",
        )
        row.addWidget(self._card_bridge)

        # Card 2 – Ollama LLM
        self._card_llm = StatusCard(
            "Ollama LLM",
            status_text="Offline",
            detail_text=self._cfg.ollama_model,
        )
        row.addWidget(self._card_llm)

        # Card 3 – DCS Connection
        self._card_dcs = StatusCard(
            "DCS Connection",
            status_text="Waiting",
            detail_text="No telemetry received",
        )
        row.addWidget(self._card_dcs)

        return row

    def _build_main_actions(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(12)

        self._btn_dashboard = QPushButton("  Open Dashboard")
        self._btn_dashboard.setObjectName("btn_dashboard")
        self._btn_dashboard.setCursor(Qt.CursorShape.PointingHandCursor)
        # Add a small unicode icon for visual appeal
        self._btn_dashboard.setText("⬡  Open Dashboard")
        row.addWidget(self._btn_dashboard)

        self._btn_bridge = QPushButton("▶  Start Nimbus Bridge")
        self._btn_bridge.setObjectName("btn_bridge_start")
        self._btn_bridge.setCursor(Qt.CursorShape.PointingHandCursor)
        row.addWidget(self._btn_bridge)

        return row

    def _build_bottom_section(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(12)

        # ── Left: activity log ─────────────────────────────────────
        log_frame = QFrame()
        log_frame.setObjectName("bottom_panel")
        log_layout = QVBoxLayout(log_frame)
        log_layout.setContentsMargins(10, 10, 10, 10)
        log_layout.setSpacing(6)

        lbl_log = QLabel("RECENT ACTIVITY")
        lbl_log.setObjectName("section_title")
        log_layout.addWidget(lbl_log)

        self._log_list = QListWidget()
        self._log_list.setObjectName("activity_log")
        self._log_list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self._log_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._log_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        log_layout.addWidget(self._log_list)

        row.addWidget(log_frame, stretch=3)

        # ── Right: quick settings ──────────────────────────────────
        settings_frame = QFrame()
        settings_frame.setObjectName("bottom_panel")
        settings_frame.setMinimumWidth(220)
        settings_frame.setMaximumWidth(260)
        sl = QVBoxLayout(settings_frame)
        sl.setContentsMargins(12, 10, 12, 10)
        sl.setSpacing(8)

        lbl_settings = QLabel("QUICK SETTINGS")
        lbl_settings.setObjectName("section_title")
        sl.addWidget(lbl_settings)

        sl.addWidget(self._make_sep())

        # Config path row
        cfg_row = QHBoxLayout()
        cfg_row.setSpacing(6)
        lbl_cfg = QLabel("Config:")
        lbl_cfg.setObjectName("settings_label")
        lbl_cfg.setFixedWidth(46)
        cfg_row.addWidget(lbl_cfg)
        self._lbl_config_path = QLabel(self._short_path(self._cfg.config_path))
        self._lbl_config_path.setObjectName("settings_value")
        self._lbl_config_path.setToolTip(self._cfg.config_path)
        cfg_row.addWidget(self._lbl_config_path, stretch=1)
        btn_edit = QPushButton("Edit…")
        btn_edit.setObjectName("btn_small")
        btn_edit.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_edit.setFixedWidth(46)
        btn_edit.clicked.connect(self._on_edit_config)
        cfg_row.addWidget(btn_edit)
        sl.addLayout(cfg_row)

        sl.addWidget(self._make_sep())

        # Language selector
        lang_row = QHBoxLayout()
        lang_row.setSpacing(6)
        lbl_lang = QLabel("Language:")
        lbl_lang.setObjectName("settings_label")
        lbl_lang.setFixedWidth(62)
        lang_row.addWidget(lbl_lang)
        self._combo_lang = QComboBox()
        for lang in self._cfg.language_installed:
            self._combo_lang.addItem(lang.upper(), lang)
        idx = self._combo_lang.findData(self._cfg.language_selected)
        if idx >= 0:
            self._combo_lang.setCurrentIndex(idx)
        lang_row.addWidget(self._combo_lang, stretch=1)
        sl.addLayout(lang_row)

        # Aircraft profile selector
        profile_row = QHBoxLayout()
        profile_row.setSpacing(6)
        lbl_profile = QLabel("Profile:")
        lbl_profile.setObjectName("settings_label")
        lbl_profile.setFixedWidth(62)
        profile_row.addWidget(lbl_profile)
        self._combo_profile = QComboBox()
        for p in self._cfg.aircraft_profiles:
            self._combo_profile.addItem(p)
        profile_row.addWidget(self._combo_profile, stretch=1)
        sl.addLayout(profile_row)

        sl.addWidget(self._make_sep())

        # PTT key display
        ptt_row = QHBoxLayout()
        ptt_row.setSpacing(6)
        lbl_ptt = QLabel("PTT Key:")
        lbl_ptt.setObjectName("settings_label")
        lbl_ptt.setFixedWidth(62)
        ptt_row.addWidget(lbl_ptt)
        self._lbl_ptt = QLabel(self._cfg.ptt_hotkey.replace("_", " ").title())
        self._lbl_ptt.setObjectName("settings_value")
        self._lbl_ptt.setStyleSheet(
            f"color: {C_ACCENT2}; font-family: 'Consolas','Courier New',monospace; font-size:11px;"
        )
        ptt_row.addWidget(self._lbl_ptt, stretch=1)
        sl.addLayout(ptt_row)

        sl.addStretch()
        row.addWidget(settings_frame, stretch=2)

        return row

    @staticmethod
    def _make_sep() -> QFrame:
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        return sep

    @staticmethod
    def _short_path(path: str, max_len: int = 28) -> str:
        p = Path(path)
        s = p.name
        return s if len(s) <= max_len else "…" + s[-(max_len - 1):]

    # ------------------------------------------------------------------
    # System tray
    # ------------------------------------------------------------------

    def _build_tray(self) -> None:
        tray_icon = QIcon(_make_tray_icon_pixmap(64))
        self._tray = QSystemTrayIcon(tray_icon, self)
        self._tray.setToolTip(f"{APP_NAME} {APP_VERSION}")

        menu = QMenu()
        menu.setStyleSheet(
            f"QMenu {{ background: {C_PANEL}; color: {C_TEXT}; border: 1px solid {C_BORDER}; }}"
            f"QMenu::item:selected {{ background: {C_ACCENT}; color: #050812; }}"
        )
        act_open = menu.addAction("Open")
        assert act_open is not None
        act_open.triggered.connect(self._tray_open)
        act_toggle = menu.addAction("Show / Hide")
        assert act_toggle is not None
        act_toggle.triggered.connect(self._tray_toggle)
        menu.addSeparator()
        act_quit = menu.addAction("Quit")
        assert act_quit is not None
        act_quit.triggered.connect(self._quit_app)

        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_tray_activated)
        self._tray.show()

    def _tray_open(self) -> None:
        self.showNormal()
        self.activateWindow()

    def _tray_toggle(self) -> None:
        if self.isVisible():
            self.hide()
        else:
            self.showNormal()
            self.activateWindow()

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._tray_open()

    # ------------------------------------------------------------------
    # Signal / slot wiring
    # ------------------------------------------------------------------

    def _connect_signals(self) -> None:
        self._btn_dashboard.clicked.connect(self._on_open_dashboard)
        self._btn_bridge.clicked.connect(self._on_toggle_bridge)
        self._signals.log_message.connect(self._append_log_item)
        self._signals.bridge_died.connect(self._on_bridge_died)

        # Card "Start" action button
        if self._card_bridge.action_button:
            self._card_bridge.action_button.clicked.connect(self._on_toggle_bridge)

    # ------------------------------------------------------------------
    # Poll timer — checks bridge process + Ollama reachability
    # ------------------------------------------------------------------

    def _start_poll_timer(self) -> None:
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll_status)
        self._poll_timer.start(2000)

    def _poll_status(self) -> None:
        bridge_running = self._bridge_proc is not None and self._bridge_proc.poll() is None
        self._update_bridge_card(bridge_running)
        self._update_header(bridge_running)

        # Non-blocking Ollama check in background thread
        threading.Thread(target=self._check_ollama, daemon=True).start()

    def _update_bridge_card(self, running: bool) -> None:
        if running:
            self._card_bridge.set_status("Running", C_GREEN)
            self._card_bridge.set_detail(f"Port {self._cfg.webrtc_port}")
            if self._card_bridge.action_button:
                self._card_bridge.action_button.setText("Stop")
        else:
            self._card_bridge.set_status("Stopped", C_RED)
            self._card_bridge.set_detail(f"Port {self._cfg.webrtc_port}")
            if self._card_bridge.action_button:
                self._card_bridge.action_button.setText("Start")

    def _update_header(self, bridge_running: bool) -> None:
        if bridge_running:
            self._header_dot.set_color(C_GREEN)
            self._lbl_nimbus.setText("NIMBUS ONLINE")
            self._lbl_nimbus.setStyleSheet(f"color: {C_GREEN};")
        else:
            self._header_dot.set_color(C_RED)
            self._lbl_nimbus.setText("NIMBUS OFFLINE")
            self._lbl_nimbus.setStyleSheet(f"color: {C_RED};")

    def _check_ollama(self) -> None:
        """Ping Ollama in a daemon thread; update card via signal-safe method."""
        import urllib.request
        url = f"{self._cfg.ollama_base_url}/api/tags"
        try:
            with urllib.request.urlopen(url, timeout=1.5) as resp:
                connected = resp.status == 200
        except Exception:
            connected = False

        # Must update UI on main thread
        QTimer.singleShot(0, lambda: self._update_llm_card(connected))

    def _update_llm_card(self, connected: bool) -> None:
        if connected:
            self._card_llm.set_status("Connected", C_GREEN)
        else:
            self._card_llm.set_status("Offline", C_RED)
        self._card_llm.set_detail(self._cfg.ollama_model)

    # DCS telemetry card — placeholder: would hook into a live socket in
    # a fuller implementation; here we show a static "Waiting" state.
    def _update_dcs_card_waiting(self) -> None:
        self._card_dcs.set_status("Waiting", C_YELLOW)
        self._card_dcs.set_detail("No telemetry received")

    # ------------------------------------------------------------------
    # Activity log
    # ------------------------------------------------------------------

    def _log(self, message: str) -> None:
        """Append a timestamped entry. Safe to call from any thread."""
        formatted = f"[{_ts()}] {message}"
        self._signals.log_message.emit(formatted)

    def _append_log_item(self, text: str) -> None:
        item = QListWidgetItem(text)
        item.setForeground(QColor(C_TEXT_DIM))
        self._log_list.addItem(item)
        # Trim to max entries
        while self._log_list.count() > MAX_LOG_ENTRIES:
            self._log_list.takeItem(0)
        self._log_list.scrollToBottom()

    # ------------------------------------------------------------------
    # Bridge start / stop
    # ------------------------------------------------------------------

    def _on_toggle_bridge(self) -> None:
        if self._bridge_proc is not None and self._bridge_proc.poll() is None:
            self._stop_bridge()
        else:
            self._start_bridge()

    def _start_bridge(self) -> None:
        self._log("Starting Nimbus bridge…")
        self._card_bridge.set_status("Starting…", C_YELLOW)
        self._btn_bridge.setText("◼  Stop Nimbus Bridge")
        self._btn_bridge.setObjectName("btn_bridge_stop")
        self._btn_bridge.setStyle(self._btn_bridge.style())  # force stylesheet re-apply

        cmd = self._bridge_command()
        try:
            self._bridge_proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError as exc:
            self._log(f"ERROR: Could not start bridge — {exc}")
            self._card_bridge.set_status("Error", C_RED)
            self._btn_bridge.setText("▶  Start Nimbus Bridge")
            self._btn_bridge.setObjectName("btn_bridge_start")
            self._btn_bridge.setStyle(self._btn_bridge.style())
            return

        self._log(f"Bridge started (PID {self._bridge_proc.pid})")

        # Open dashboard after a short delay
        QTimer.singleShot(1500, self._on_open_dashboard)

        # Monitor subprocess in background thread
        threading.Thread(target=self._watch_bridge, daemon=True).start()

    def _stop_bridge(self) -> None:
        if self._bridge_proc is None:
            return
        self._log("Stopping Nimbus bridge…")
        try:
            self._bridge_proc.terminate()
            self._bridge_proc.wait(timeout=5)
        except Exception:
            try:
                self._bridge_proc.kill()
            except Exception:
                pass
        self._bridge_proc = None
        self._log("Bridge stopped.")
        self._card_bridge.set_status("Stopped", C_RED)
        self._btn_bridge.setText("▶  Start Nimbus Bridge")
        self._btn_bridge.setObjectName("btn_bridge_start")
        self._btn_bridge.setStyle(self._btn_bridge.style())

    def _bridge_command(self) -> list[str]:
        """Build the subprocess command to launch the WebRTC bridge."""
        # Try the installed script first, fall back to module invocation
        if _which("voice-comms-dcs-webrtc"):
            return ["voice-comms-dcs-webrtc"]
        return [sys.executable, "-m", "voice_comms_dcs.webrtc_bridge"]

    def _watch_bridge(self) -> None:
        """Block until the bridge process exits, then signal the main thread."""
        if self._bridge_proc is None:
            return
        self._bridge_proc.wait()
        self._signals.bridge_died.emit()

    def _on_bridge_died(self) -> None:
        if self._bridge_proc is not None:
            rc = self._bridge_proc.returncode
            self._log(f"Bridge exited (return code {rc})")
        self._bridge_proc = None
        self._card_bridge.set_status("Stopped", C_RED)
        self._btn_bridge.setText("▶  Start Nimbus Bridge")
        self._btn_bridge.setObjectName("btn_bridge_start")
        self._btn_bridge.setStyle(self._btn_bridge.style())

    # ------------------------------------------------------------------
    # Dashboard
    # ------------------------------------------------------------------

    def _on_open_dashboard(self) -> None:
        url = self._cfg.dashboard_url
        self._log(f"Opening dashboard: {url}")
        webbrowser.open(url)

    # ------------------------------------------------------------------
    # Settings panel actions
    # ------------------------------------------------------------------

    def _on_edit_config(self) -> None:
        path = self._cfg.config_path
        if not Path(path).exists():
            QMessageBox.warning(
                self,
                "Config Not Found",
                f"Config file not found:\n{path}\n\n"
                "Run the application once to generate a default config.",
            )
            return
        self._log(f"Opening config: {path}")
        _open_file_in_editor(path)

    # ------------------------------------------------------------------
    # Close / quit handling
    # ------------------------------------------------------------------

    def closeEvent(self, event) -> None:  # type: ignore[override]
        if self._minimize_to_tray is None:
            # Ask the user (only once)
            dlg = TrayPreferenceDialog(self)
            dlg.exec()
            self._minimize_to_tray = dlg.minimize_to_tray
            # Persist preference
            self._settings.setValue("minimize_to_tray", str(self._minimize_to_tray).lower())

        if self._minimize_to_tray:
            event.ignore()
            self.hide()
            self._tray.showMessage(
                APP_NAME,
                "Minimised to tray — bridge is still running.",
                QSystemTrayIcon.MessageIcon.Information,
                2500,
            )
        else:
            self._cleanup_and_quit()
            event.accept()

    def _quit_app(self) -> None:
        self._cleanup_and_quit()
        QApplication.quit()

    def _cleanup_and_quit(self) -> None:
        if self._bridge_proc is not None and self._bridge_proc.poll() is None:
            self._log("Stopping bridge on quit…")
            try:
                self._bridge_proc.terminate()
                self._bridge_proc.wait(timeout=4)
            except Exception:
                pass
        self._tray.hide()


# ---------------------------------------------------------------------------
# Application entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Entry point registered in pyproject.toml / setup.cfg."""
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName("VoiceCommsDCS")
    # Keep running when last window is hidden (tray mode)
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet(STYLESHEET)

    # Use a monospace font for the log if available
    QFontDatabase.addApplicationFont(
        str(Path(__file__).parent / "assets" / "fonts" / "JetBrainsMono-Regular.ttf")
    )  # silently ignored if not present

    window = LauncherWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
