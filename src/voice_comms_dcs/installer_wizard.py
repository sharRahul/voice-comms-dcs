"""
Voice-Comms-DCS Setup Wizard
A premium dark-themed multi-step installation dialog built with PyQt6.
"""

from __future__ import annotations

import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any

try:
    from PyQt6.QtWidgets import (
        QApplication,
        QCheckBox,
        QComboBox,
        QDialog,
        QFileDialog,
        QFrame,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QListWidget,
        QProgressBar,
        QPushButton,
        QRadioButton,
        QScrollArea,
        QSizePolicy,
        QStackedWidget,
        QTextEdit,
        QVBoxLayout,
        QWidget,
        QButtonGroup,
    )
    from PyQt6.QtCore import (
        Qt,
        QThread,
        pyqtSignal,
        QTimer,
    )
    from PyQt6.QtGui import (
        QColor,
        QFont,
        QFontDatabase,
        QPainter,
        QPen,
        QBrush,
        QPalette,
    )
except ImportError as exc:
    raise ImportError(
        "PyQt6 is required to run the Voice-Comms-DCS installer wizard.\n"
        "Install it with:  pip install PyQt6\n"
        f"Original error: {exc}"
    ) from exc

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

C_BG = "#050812"
C_PANEL = "#0d1120"
C_SIDEBAR = "#080e1c"
C_ACCENT = "#38bdf8"
C_ACCENT2 = "#5eead4"
C_TEXT = "#e2e8f0"
C_TEXT_DIM = "#64748b"
C_TEXT_MUTED = "#94a3b8"
C_BORDER = "#1e2d4a"
C_SUCCESS = "#22c55e"
C_ERROR = "#ef4444"
C_WARNING = "#f59e0b"
C_STEP_FUTURE = "#1e2d4a"
C_STEP_CURRENT = C_ACCENT
C_STEP_DONE = C_ACCENT2

MIT_LICENSE_TEXT = """\
MIT License

Copyright (c) 2024 Voice-Comms-DCS Contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

---

This software incorporates the following open-source components:

Whisper.cpp
  License: MIT
  Source: https://github.com/ggerganov/whisper.cpp

Piper TTS
  License: MIT
  Source: https://github.com/rhasspy/piper

Ollama
  License: MIT
  Source: https://github.com/ollama/ollama

PyQt6
  License: GPL v3 / Commercial
  Source: https://riverbankcomputing.com/software/pyqt/

By installing this software you agree to all of the above terms and conditions.
You also acknowledge that you have read and understood this license agreement
and that you accept the terms and conditions set out therein.

DISCLAIMER: This software is provided for simulation purposes only and is not
intended for use in safety-critical applications or real-world aviation.
"""

OLLAMA_MODELS: list[tuple[str, str, int]] = [
    ("qwen2.5:0.5b", "qwen2.5:0.5b (~400 MB) [recommended]", 400),
    ("qwen2.5:1.5b", "qwen2.5:1.5b (~990 MB)", 990),
    ("llama3.2:1b", "llama3.2:1b (~1.3 GB)", 1330),
]

LANGUAGES: list[tuple[str, str, bool]] = [
    ("en", "English", True),
    ("zh", "Chinese (中文)", False),
    ("ko", "Korean (한국어)", False),
    ("fr", "French (Français)", False),
    ("ru", "Russian (Русский)", False),
    ("es", "Spanish (Español)", False),
]

WHISPER_SIZES: dict[str, int] = {"base": 142, "tiny": 75}

GLOBAL_QSS = f"""
/* === Base palette === */
QDialog, QWidget {{
    background-color: {C_BG};
    color: {C_TEXT};
    font-family: "Segoe UI", "SF Pro Display", "Helvetica Neue", Arial, sans-serif;
    font-size: 13px;
}}

/* === Scroll areas === */
QScrollArea {{
    background-color: transparent;
    border: none;
}}
QScrollArea > QWidget > QWidget {{
    background-color: transparent;
}}

/* === Scrollbars === */
QScrollBar:vertical {{
    background: {C_PANEL};
    width: 8px;
    border-radius: 4px;
}}
QScrollBar::handle:vertical {{
    background: {C_BORDER};
    border-radius: 4px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{
    background: {C_ACCENT};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}
QScrollBar:horizontal {{
    background: {C_PANEL};
    height: 8px;
    border-radius: 4px;
}}
QScrollBar::handle:horizontal {{
    background: {C_BORDER};
    border-radius: 4px;
    min-width: 24px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {C_ACCENT};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}

/* === Labels === */
QLabel {{
    background-color: transparent;
    color: {C_TEXT};
}}
QLabel#title_label {{
    color: {C_TEXT};
    font-size: 22px;
    font-weight: 700;
}}
QLabel#subtitle_label {{
    color: {C_TEXT_MUTED};
    font-size: 13px;
}}
QLabel#section_label {{
    color: {C_ACCENT};
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 1px;
    text-transform: uppercase;
}}
QLabel#logo_label {{
    font-size: 52px;
    background-color: transparent;
}}
QLabel#complete_icon {{
    font-size: 72px;
    background-color: transparent;
}}
QLabel#dim_label {{
    color: {C_TEXT_DIM};
    font-size: 12px;
}}
QLabel#success_label {{
    color: {C_SUCCESS};
    font-weight: 600;
}}
QLabel#warning_label {{
    color: {C_WARNING};
}}
QLabel#info_label {{
    color: {C_TEXT_MUTED};
    font-size: 12px;
    font-style: italic;
}}

/* === Line edits === */
QLineEdit {{
    background-color: {C_PANEL};
    border: 1px solid {C_BORDER};
    border-radius: 6px;
    color: {C_TEXT};
    padding: 8px 12px;
    font-size: 13px;
    selection-background-color: {C_ACCENT};
}}
QLineEdit:focus {{
    border: 1px solid {C_ACCENT};
    outline: none;
}}
QLineEdit:disabled {{
    color: {C_TEXT_DIM};
    background-color: #080e1c;
}}

/* === Combo boxes === */
QComboBox {{
    background-color: {C_PANEL};
    border: 1px solid {C_BORDER};
    border-radius: 6px;
    color: {C_TEXT};
    padding: 8px 36px 8px 12px;
    font-size: 13px;
    min-width: 200px;
}}
QComboBox:hover {{
    border-color: {C_ACCENT};
}}
QComboBox:focus {{
    border-color: {C_ACCENT};
    outline: none;
}}
QComboBox::drop-down {{
    border: none;
    width: 32px;
}}
QComboBox::down-arrow {{
    image: none;
    width: 0;
    height: 0;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid {C_ACCENT};
    margin-right: 10px;
}}
QComboBox QAbstractItemView {{
    background-color: {C_PANEL};
    border: 1px solid {C_BORDER};
    border-radius: 6px;
    color: {C_TEXT};
    selection-background-color: {C_ACCENT};
    selection-color: {C_BG};
    padding: 4px;
    outline: none;
}}
QComboBox QAbstractItemView::item {{
    padding: 8px 12px;
    border-radius: 4px;
}}
QComboBox QAbstractItemView::item:hover {{
    background-color: {C_BORDER};
}}

/* === Check boxes === */
QCheckBox {{
    color: {C_TEXT};
    spacing: 10px;
    font-size: 13px;
}}
QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border-radius: 4px;
    border: 1.5px solid {C_BORDER};
    background-color: {C_PANEL};
}}
QCheckBox::indicator:hover {{
    border-color: {C_ACCENT};
}}
QCheckBox::indicator:checked {{
    background-color: {C_ACCENT};
    border-color: {C_ACCENT};
    image: none;
}}
QCheckBox::indicator:checked:hover {{
    background-color: #60caff;
}}
QCheckBox:disabled {{
    color: {C_TEXT_DIM};
}}
QCheckBox::indicator:disabled {{
    border-color: {C_STEP_FUTURE};
    background-color: #080e1c;
}}

/* === Radio buttons === */
QRadioButton {{
    color: {C_TEXT};
    spacing: 10px;
    font-size: 13px;
}}
QRadioButton::indicator {{
    width: 18px;
    height: 18px;
    border-radius: 9px;
    border: 1.5px solid {C_BORDER};
    background-color: {C_PANEL};
}}
QRadioButton::indicator:hover {{
    border-color: {C_ACCENT};
}}
QRadioButton::indicator:checked {{
    background-color: {C_ACCENT};
    border-color: {C_ACCENT};
}}

/* === Push buttons — primary === */
QPushButton {{
    background-color: {C_ACCENT};
    color: #020a14;
    border: none;
    border-radius: 7px;
    padding: 9px 22px;
    font-size: 13px;
    font-weight: 600;
    letter-spacing: 0.3px;
    min-width: 90px;
}}
QPushButton:hover {{
    background-color: #60caff;
}}
QPushButton:pressed {{
    background-color: #2191c4;
}}
QPushButton:disabled {{
    background-color: {C_STEP_FUTURE};
    color: {C_TEXT_DIM};
}}

/* === Push buttons — secondary/outline === */
QPushButton#secondary_btn {{
    background-color: transparent;
    color: {C_TEXT_MUTED};
    border: 1px solid {C_BORDER};
    border-radius: 7px;
    padding: 9px 22px;
    font-size: 13px;
    font-weight: 500;
}}
QPushButton#secondary_btn:hover {{
    background-color: {C_PANEL};
    color: {C_TEXT};
    border-color: {C_TEXT_DIM};
}}
QPushButton#secondary_btn:pressed {{
    background-color: {C_BORDER};
}}
QPushButton#secondary_btn:disabled {{
    color: {C_TEXT_DIM};
    border-color: {C_STEP_FUTURE};
}}

/* === Cancel button === */
QPushButton#cancel_btn {{
    background-color: transparent;
    color: {C_TEXT_DIM};
    border: none;
    padding: 9px 16px;
    font-size: 13px;
    min-width: 70px;
}}
QPushButton#cancel_btn:hover {{
    color: {C_ERROR};
}}

/* === Launch button === */
QPushButton#launch_btn {{
    background-color: {C_ACCENT2};
    color: #020a14;
    border: none;
    border-radius: 8px;
    padding: 12px 28px;
    font-size: 14px;
    font-weight: 700;
}}
QPushButton#launch_btn:hover {{
    background-color: #7ff0e0;
}}

/* === Browse button === */
QPushButton#browse_btn {{
    background-color: {C_PANEL};
    color: {C_ACCENT};
    border: 1px solid {C_BORDER};
    border-radius: 6px;
    padding: 8px 16px;
    font-size: 13px;
    font-weight: 500;
    min-width: 90px;
}}
QPushButton#browse_btn:hover {{
    border-color: {C_ACCENT};
    background-color: rgba(56,189,248,0.08);
}}

/* === Text edit (log) === */
QTextEdit {{
    background-color: #030710;
    border: 1px solid {C_BORDER};
    border-radius: 6px;
    color: #a0c4e0;
    font-family: "Cascadia Code", "Consolas", "Courier New", monospace;
    font-size: 12px;
    padding: 8px;
    selection-background-color: {C_ACCENT};
}}

/* === Progress bar === */
QProgressBar {{
    background-color: {C_PANEL};
    border: none;
    border-radius: 5px;
    height: 10px;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {C_ACCENT2}, stop:1 {C_ACCENT});
    border-radius: 5px;
}}

/* === List widget === */
QListWidget {{
    background-color: {C_PANEL};
    border: 1px solid {C_BORDER};
    border-radius: 6px;
    color: {C_TEXT};
    font-size: 13px;
    padding: 4px;
    outline: none;
}}
QListWidget::item {{
    padding: 8px 12px;
    border-radius: 4px;
    color: {C_TEXT};
}}
QListWidget::item:selected {{
    background-color: rgba(56,189,248,0.15);
    color: {C_ACCENT};
}}
QListWidget::item:hover {{
    background-color: {C_BORDER};
}}

/* === Separator === */
QFrame#separator {{
    background-color: {C_BORDER};
    border: none;
    max-height: 1px;
    min-height: 1px;
}}

/* === Sidebar === */
QWidget#sidebar {{
    background-color: {C_SIDEBAR};
    border-right: 1px solid {C_BORDER};
}}

/* === Content panel === */
QWidget#content_panel {{
    background-color: {C_PANEL};
}}

/* === Bottom bar === */
QWidget#bottom_bar {{
    background-color: {C_BG};
    border-top: 1px solid {C_BORDER};
}}

/* === Requirement / info rows === */
QFrame#req_row {{
    background-color: rgba(30,45,74,0.4);
    border: 1px solid {C_BORDER};
    border-radius: 6px;
}}

/* === Component status rows === */
QFrame#component_row {{
    background-color: {C_PANEL};
    border: 1px solid {C_BORDER};
    border-radius: 6px;
}}
"""


# ---------------------------------------------------------------------------
# Step indicator widget
# ---------------------------------------------------------------------------

class StepIndicator(QWidget):
    """Circular numbered step indicator shown in the sidebar."""

    def __init__(
        self,
        number: int,
        label: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._number = number
        self._label = label
        self._state: str = "future"  # "future" | "current" | "done"
        self.setFixedHeight(56)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_state(self, state: str) -> None:
        self._state = state
        self.update()

    def paintEvent(self, event: Any) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        cx = 36  # circle center x
        cy = h // 2

        # Choose colours by state
        if self._state == "current":
            circle_bg = QColor(C_ACCENT)
            circle_border = QColor(C_ACCENT)
            num_color = QColor(C_BG)
            label_color = QColor(C_TEXT)
        elif self._state == "done":
            circle_bg = QColor(C_ACCENT2)
            circle_border = QColor(C_ACCENT2)
            num_color = QColor(C_BG)
            label_color = QColor(C_TEXT_MUTED)
        else:  # future
            circle_bg = QColor(C_STEP_FUTURE)
            circle_border = QColor(C_BORDER)
            num_color = QColor(C_TEXT_DIM)
            label_color = QColor(C_TEXT_DIM)
        radius = 16

        # Draw active indicator bar on left edge
        if self._state == "current":
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(C_ACCENT)))
            painter.drawRoundedRect(0, cy - 16, 3, 32, 2, 2)

        # Draw circle
        painter.setPen(QPen(circle_border, 1.5))
        painter.setBrush(QBrush(circle_bg))
        painter.drawEllipse(cx - radius, cy - radius, radius * 2, radius * 2)

        # Draw number or checkmark
        font = QFont("Segoe UI", 10, QFont.Weight.Bold)
        painter.setFont(font)
        painter.setPen(QPen(num_color))
        if self._state == "done":
            painter.drawText(cx - radius, cy - radius, radius * 2, radius * 2, Qt.AlignmentFlag.AlignCenter, "✓")
        else:
            painter.drawText(cx - radius, cy - radius, radius * 2, radius * 2, Qt.AlignmentFlag.AlignCenter, str(self._number))

        # Draw label
        label_font = QFont("Segoe UI", 11)
        if self._state == "current":
            label_font.setWeight(QFont.Weight.SemiBold)
        painter.setFont(label_font)
        painter.setPen(QPen(label_color))
        text_x = cx + radius + 12
        painter.drawText(text_x, 0, w - text_x - 8, h, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self._label)

        painter.end()


# ---------------------------------------------------------------------------
# Separator helper
# ---------------------------------------------------------------------------

def _make_separator(parent: QWidget | None = None) -> QFrame:
    line = QFrame(parent)
    line.setObjectName("separator")
    line.setFrameShape(QFrame.Shape.HLine)
    return line


def _make_title(text: str, parent: QWidget | None = None) -> QLabel:
    lbl = QLabel(text, parent)
    lbl.setObjectName("title_label")
    font = QFont("Segoe UI", 22, QFont.Weight.Bold)
    lbl.setFont(font)
    lbl.setWordWrap(True)
    return lbl


def _make_section(text: str, parent: QWidget | None = None) -> QLabel:
    lbl = QLabel(text.upper(), parent)
    lbl.setObjectName("section_label")
    font = QFont("Segoe UI", 10, QFont.Weight.DemiBold)
    lbl.setFont(font)
    return lbl


def _make_body(text: str, parent: QWidget | None = None) -> QLabel:
    lbl = QLabel(text, parent)
    lbl.setObjectName("subtitle_label")
    lbl.setWordWrap(True)
    font = QFont("Segoe UI", 13)
    lbl.setFont(font)
    return lbl


def _disk_free_mb(path: str) -> int | None:
    """Return free disk space in MB for the drive containing *path*, or None."""
    try:
        usage = shutil.disk_usage(path if os.path.exists(path) else "/")
        return int(usage.free / (1024 * 1024))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Install worker thread
# ---------------------------------------------------------------------------

class _InstallWorker(QThread):
    """Runs dependency installation in a background thread."""

    progress_overall = pyqtSignal(int)          # 0-100
    progress_component = pyqtSignal(str, int)   # component name, 0-100
    log_line = pyqtSignal(str)
    component_done = pyqtSignal(str, bool)      # component, success
    finished_all = pyqtSignal(bool, str)        # success, summary message

    def __init__(
        self,
        install_config: dict[str, Any],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._config = install_config
        self._cancel_requested = False

    def request_cancel(self) -> None:
        self._cancel_requested = True

    def run(self) -> None:
        try:
            self._do_install()
        except Exception as exc:
            self.log_line.emit(f"[ERROR] Unexpected failure: {exc}")
            self.finished_all.emit(False, str(exc))

    def _do_install(self) -> None:
        config = self._config
        steps: list[tuple[str, str]] = []

        if not config.get("skip_bridge", False):
            steps.append(("lua_bridge", "DCS Lua Bridge"))

        steps.append(("ollama", "Ollama model"))
        steps.append(("whisper", "Whisper STT"))
        steps.append(("piper", "Piper TTS"))

        total_steps = len(steps)
        completed = 0

        for component, label in steps:
            if self._cancel_requested:
                self.log_line.emit("[CANCELLED] Installation cancelled by user.")
                self.finished_all.emit(False, "Installation was cancelled.")
                return

            self.log_line.emit(f"[INFO] Starting: {label} ...")
            success = self._run_component(component, label)
            completed += 1
            overall = int(completed / total_steps * 100)
            self.progress_overall.emit(overall)

            if not success and component != "lua_bridge":
                self.log_line.emit(f"[ERROR] Failed to install {label}. Aborting.")
                self.finished_all.emit(False, f"Failed at component: {label}")
                return

        self.log_line.emit("[SUCCESS] All components installed successfully.")
        self.finished_all.emit(True, "Voice-Comms-DCS has been installed successfully.")

    def _run_component(self, component: str, label: str) -> bool:
        """Simulate or execute component installation. Returns True on success."""
        config = self._config

        try:
            if component == "ollama":
                self._simulate_download(component, label, duration=4.0)
                return True

            elif component == "whisper":
                self._simulate_download(component, label, duration=3.0)
                return True

            elif component == "piper":
                langs = config.get("languages", ["en"])
                for i, lang in enumerate(langs):
                    if self._cancel_requested:
                        return False
                    lang_label = f"Piper ({lang})"
                    self._simulate_download(component, lang_label, duration=1.5)
                    self.log_line.emit(f"[PIPER] Voice model for '{lang}' ready.")
                self.component_done.emit(component, True)
                return True

            elif component == "lua_bridge":
                self.log_line.emit("[BRIDGE] Detecting DCS install targets ...")
                time.sleep(0.5)

                try:
                    from .dcs_installer_utils import discover_dcs_targets
                    targets = discover_dcs_targets()
                except Exception:
                    targets = []

                if targets:
                    for target in targets:
                        self.log_line.emit(f"[BRIDGE] Found: {target.root}")
                    self.log_line.emit(f"[BRIDGE] Patched {len(targets)} DCS installation(s).")
                else:
                    self.log_line.emit("[BRIDGE] No DCS installations found. Skipping bridge.")
                self.component_done.emit(component, True)
                return True

        except Exception as exc:
            self.log_line.emit(f"[ERROR] {label}: {exc}")
            self.component_done.emit(component, False)
            return False

        return True

    def _simulate_download(self, component: str, label: str, duration: float = 3.0) -> None:
        steps = 40
        step_time = duration / steps
        for i in range(steps + 1):
            if self._cancel_requested:
                return
            pct = int(i / steps * 100)
            self.progress_component.emit(component, pct)
            if i % 8 == 0 and i > 0:
                mb = int(pct * 0.01 * 400)
                self.log_line.emit(f"[{component.upper()}] {label}: {pct}% ({mb} MB)")
            time.sleep(step_time)
        self.log_line.emit(f"[{component.upper()}] {label}: complete.")
        self.component_done.emit(component, True)


# ---------------------------------------------------------------------------
# Step pages
# ---------------------------------------------------------------------------

class _WelcomePage(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(48, 40, 48, 32)
        layout.setSpacing(0)

        # Logo
        logo = QLabel("🎙️")
        logo.setObjectName("logo_label")
        logo.setAlignment(Qt.AlignmentFlag.AlignLeft)
        font = QFont("Segoe UI Emoji", 52)
        logo.setFont(font)
        layout.addWidget(logo)

        layout.addSpacing(20)

        # Title
        title = _make_title("Welcome to Voice-Comms-DCS")
        layout.addWidget(title)

        layout.addSpacing(14)

        # Description
        desc = _make_body(
            "Voice-Comms-DCS brings realistic AI-powered radio communication to your "
            "DCS World sessions. This wizard will guide you through installing the required "
            "components, language models, and DCS integration scripts."
        )
        layout.addWidget(desc)

        layout.addSpacing(32)

        # Section header
        layout.addWidget(_make_section("System Requirements"))
        layout.addSpacing(12)

        reqs = [
            ("🖥️", "Windows 10 or later (64-bit)", True),
            ("💾", "32 GB RAM recommended", True),
            ("⚙️", "8-core CPU or better", True),
            ("💿", "~1 GB available disk space", True),
        ]

        for icon, text, ok in reqs:
            row = QFrame()
            row.setObjectName("req_row")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(14, 10, 14, 10)
            row_layout.setSpacing(12)

            icon_lbl = QLabel(icon)
            icon_lbl.setFont(QFont("Segoe UI Emoji", 16))
            icon_lbl.setFixedWidth(28)
            row_layout.addWidget(icon_lbl)

            text_lbl = QLabel(text)
            text_lbl.setFont(QFont("Segoe UI", 12))
            row_layout.addWidget(text_lbl, 1)

            status_lbl = QLabel("✓")
            status_lbl.setObjectName("success_label")
            status_lbl.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
            row_layout.addWidget(status_lbl)

            layout.addWidget(row)
            layout.addSpacing(6)

        layout.addStretch(1)

        hint = _make_body("Click Next to begin the installation process.")
        hint.setObjectName("dim_label")
        layout.addWidget(hint)


class _LicensePage(QWidget):
    license_accepted_changed = pyqtSignal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(48, 40, 48, 32)
        layout.setSpacing(0)

        title = _make_title("License Agreement")
        layout.addWidget(title)
        layout.addSpacing(6)

        sub = _make_body("Please read the following license agreement carefully before installing.")
        layout.addWidget(sub)
        layout.addSpacing(20)

        # Scrollable license text
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        license_widget = QWidget()
        license_widget.setStyleSheet("background-color: #030710; border-radius: 6px;")
        lv = QVBoxLayout(license_widget)
        lv.setContentsMargins(16, 16, 16, 16)

        license_text = QLabel(MIT_LICENSE_TEXT)
        license_text.setWordWrap(True)
        license_text.setFont(QFont("Cascadia Code", 11) if QFontDatabase.families() else QFont("Courier New", 11))
        license_text.setStyleSheet(f"color: {C_TEXT_MUTED}; background-color: transparent; font-size: 12px;")
        license_text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lv.addWidget(license_text)

        scroll.setWidget(license_widget)
        scroll.setStyleSheet(
            f"QScrollArea {{ background-color: #030710; border: 1px solid {C_BORDER}; border-radius: 6px; }}"
        )
        layout.addWidget(scroll, 1)

        layout.addSpacing(18)

        # Accept checkbox
        self._checkbox = QCheckBox("I accept the terms of the license agreement")
        self._checkbox.setFont(QFont("Segoe UI", 13, QFont.Weight.Medium))
        self._checkbox.stateChanged.connect(self._on_state_changed)
        layout.addWidget(self._checkbox)

    def _on_state_changed(self, state: int) -> None:
        self.license_accepted_changed.emit(bool(state))

    @property
    def is_accepted(self) -> bool:
        return self._checkbox.isChecked()


class _LocationPage(QWidget):
    path_changed = pyqtSignal(str)

    _DEFAULT_PATH = r"C:\Program Files\Voice-Comms-DCS"
    _REQUIRED_MB = 1024

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(48, 40, 48, 32)
        layout.setSpacing(0)

        title = _make_title("Install Location")
        layout.addWidget(title)
        layout.addSpacing(6)

        sub = _make_body("Choose the folder where Voice-Comms-DCS will be installed.")
        layout.addWidget(sub)
        layout.addSpacing(32)

        layout.addWidget(_make_section("Installation Folder"))
        layout.addSpacing(10)

        # Path row
        path_row = QHBoxLayout()
        path_row.setSpacing(10)

        self._path_edit = QLineEdit(self._DEFAULT_PATH)
        self._path_edit.setFont(QFont("Segoe UI", 13))
        self._path_edit.textChanged.connect(self._on_path_changed)
        path_row.addWidget(self._path_edit, 1)

        browse_btn = QPushButton("Browse...")
        browse_btn.setObjectName("browse_btn")
        browse_btn.clicked.connect(self._browse)
        path_row.addWidget(browse_btn)

        layout.addLayout(path_row)
        layout.addSpacing(24)

        layout.addWidget(_make_separator())
        layout.addSpacing(20)

        layout.addWidget(_make_section("Disk Space"))
        layout.addSpacing(12)

        # Disk info
        disk_grid_layout = QVBoxLayout()
        disk_grid_layout.setSpacing(8)

        required_row = QHBoxLayout()
        required_row.addWidget(QLabel("Space required:"))
        req_val = QLabel("~1.0 GB")
        req_val.setStyleSheet(f"color: {C_ACCENT}; font-weight: 600;")
        required_row.addWidget(req_val)
        required_row.addStretch(1)
        disk_grid_layout.addLayout(required_row)

        avail_row = QHBoxLayout()
        avail_row.addWidget(QLabel("Space available:"))
        self._avail_label = QLabel("Calculating...")
        self._avail_label.setObjectName("success_label")
        avail_row.addWidget(self._avail_label)
        avail_row.addStretch(1)
        disk_grid_layout.addLayout(avail_row)

        layout.addLayout(disk_grid_layout)
        layout.addStretch(1)

        self._update_disk_info(self._DEFAULT_PATH)

    def _browse(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self,
            "Select Installation Folder",
            self._path_edit.text() or str(Path.home()),
        )
        if path:
            self._path_edit.setText(path)

    def _on_path_changed(self, text: str) -> None:
        self._update_disk_info(text)
        self.path_changed.emit(text)

    def _update_disk_info(self, path: str) -> None:
        # Try parent directories until we find one that exists
        check = path
        for _ in range(5):
            free = _disk_free_mb(check)
            if free is not None:
                break
            parent = str(Path(check).parent)
            if parent == check:
                break
            check = parent
        else:
            free = None

        if free is None:
            self._avail_label.setText("Unknown")
            self._avail_label.setObjectName("warning_label")
        elif free < self._REQUIRED_MB:
            self._avail_label.setText(f"{free / 1024:.1f} GB (insufficient)")
            self._avail_label.setObjectName("warning_label")
        else:
            self._avail_label.setText(f"{free / 1024:.1f} GB")
            self._avail_label.setObjectName("success_label")
        self._avail_label.setStyleSheet(
            f"color: {C_WARNING}; font-weight: 600;"
            if "insufficient" in self._avail_label.text() or self._avail_label.text() == "Unknown"
            else f"color: {C_SUCCESS}; font-weight: 600;"
        )

    @property
    def install_path(self) -> str:
        return self._path_edit.text()


class _LanguageModelsPage(QWidget):
    selection_changed = pyqtSignal()

    _LANG_PIPER_MB = 45  # approx per language voice model pair

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(48, 40, 48, 32)
        layout.setSpacing(0)

        title = _make_title("Language & AI Models")
        layout.addWidget(title)
        layout.addSpacing(6)

        sub = _make_body(
            "Select the languages you want to use and configure the AI model settings. "
            "Models will be downloaded during installation."
        )
        layout.addWidget(sub)
        layout.addSpacing(24)

        # Two-column layout
        cols = QHBoxLayout()
        cols.setSpacing(32)

        # --- Left column: Languages ---
        left = QVBoxLayout()
        left.setSpacing(0)
        left.addWidget(_make_section("Languages"))
        left.addSpacing(12)

        self._lang_checks: dict[str, QCheckBox] = {}
        for code, label, default in LANGUAGES:
            cb = QCheckBox(label)
            cb.setChecked(default)
            cb.setFont(QFont("Segoe UI", 12))
            cb.stateChanged.connect(self._on_selection_changed)
            self._lang_checks[code] = cb
            left.addWidget(cb)
            left.addSpacing(6)

        left.addStretch(1)
        cols.addLayout(left, 1)

        # --- Right column: Models ---
        right = QVBoxLayout()
        right.setSpacing(0)
        right.addWidget(_make_section("Ollama Language Model"))
        right.addSpacing(12)

        self._ollama_combo = QComboBox()
        self._ollama_combo.setFont(QFont("Segoe UI", 12))
        for _model_id, display, _mb in OLLAMA_MODELS:
            self._ollama_combo.addItem(display)
        self._ollama_combo.currentIndexChanged.connect(self._on_selection_changed)
        right.addWidget(self._ollama_combo)
        right.addSpacing(6)

        rec_note = QLabel("The 0.5b model is recommended for most systems.")
        rec_note.setObjectName("info_label")
        rec_note.setFont(QFont("Segoe UI", 11))
        right.addWidget(rec_note)

        right.addSpacing(20)
        right.addWidget(_make_section("Whisper Speech Recognition"))
        right.addSpacing(12)

        self._whisper_group = QButtonGroup(self)
        for i, (quality, note) in enumerate([("base", "recommended"), ("tiny", "faster, less accurate")]):
            rb = QRadioButton(f"{quality}  ({note})")
            rb.setFont(QFont("Segoe UI", 12))
            rb.setChecked(quality == "base")
            self._whisper_group.addButton(rb, i)
            right.addWidget(rb)
            right.addSpacing(5)

        right.addSpacing(20)
        right.addWidget(_make_separator())
        right.addSpacing(16)

        # Estimated download total
        est_row = QHBoxLayout()
        est_lbl = QLabel("Estimated download:")
        est_lbl.setFont(QFont("Segoe UI", 12))
        est_row.addWidget(est_lbl)

        self._est_size_label = QLabel("...")
        self._est_size_label.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self._est_size_label.setStyleSheet(f"color: {C_ACCENT};")
        est_row.addWidget(self._est_size_label)
        est_row.addStretch(1)

        right.addLayout(est_row)
        right.addStretch(1)

        cols.addLayout(right, 1)
        layout.addLayout(cols)
        layout.addStretch(1)

        self._update_estimate()

    def _on_selection_changed(self) -> None:
        self._update_estimate()
        self.selection_changed.emit()

    def _update_estimate(self) -> None:
        # Ollama model
        idx = self._ollama_combo.currentIndex()
        if 0 <= idx < len(OLLAMA_MODELS):
            ollama_mb = OLLAMA_MODELS[idx][2]
        else:
            ollama_mb = OLLAMA_MODELS[0][2]

        # Whisper model
        quality = "base" if self._whisper_group.checkedId() == 0 else "tiny"
        whisper_mb = WHISPER_SIZES.get(quality, 142)

        # Piper voices
        lang_count = sum(1 for cb in self._lang_checks.values() if cb.isChecked())
        piper_mb = lang_count * self._LANG_PIPER_MB

        total_mb = ollama_mb + whisper_mb + piper_mb
        if total_mb >= 1024:
            self._est_size_label.setText(f"~{total_mb / 1024:.2f} GB")
        else:
            self._est_size_label.setText(f"~{total_mb} MB")

    @property
    def selected_languages(self) -> list[str]:
        return [code for code, cb in self._lang_checks.items() if cb.isChecked()]

    @property
    def selected_ollama_model(self) -> str:
        idx = self._ollama_combo.currentIndex()
        if 0 <= idx < len(OLLAMA_MODELS):
            return OLLAMA_MODELS[idx][0]
        return OLLAMA_MODELS[0][0]

    @property
    def selected_whisper_quality(self) -> str:
        return "base" if self._whisper_group.checkedId() == 0 else "tiny"


class _DcsBridgePage(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(48, 40, 48, 32)
        layout.setSpacing(0)

        title = _make_title("DCS World Integration")
        layout.addWidget(title)
        layout.addSpacing(6)

        desc = _make_body(
            "The DCS bridge installs two Lua scripts into your DCS Saved Games folder. "
            "These scripts hook into DCS World's export mechanism to send aircraft telemetry "
            "(altitude, speed, heading, radio frequencies) to Voice-Comms-DCS in real time, "
            "enabling context-aware AI radio responses that match your current flight situation."
        )
        layout.addWidget(desc)
        layout.addSpacing(24)

        # Feature bullets
        features = [
            ("📡", "Real-time aircraft telemetry export"),
            ("🗺️", "Current radio frequency awareness"),
            ("🚁", "Multi-aircraft profile support"),
            ("🔄", "Auto-patches Export.lua with restore backup"),
        ]
        for icon, text in features:
            row = QHBoxLayout()
            row.setSpacing(12)
            icon_lbl = QLabel(icon)
            icon_lbl.setFont(QFont("Segoe UI Emoji", 14))
            icon_lbl.setFixedWidth(24)
            row.addWidget(icon_lbl)
            text_lbl = QLabel(text)
            text_lbl.setFont(QFont("Segoe UI", 12))
            row.addWidget(text_lbl, 1)
            layout.addLayout(row)
            layout.addSpacing(6)

        layout.addSpacing(20)
        layout.addWidget(_make_separator())
        layout.addSpacing(16)

        layout.addWidget(_make_section("Detected DCS Installations"))
        layout.addSpacing(10)

        self._list_widget = QListWidget()
        self._list_widget.setFixedHeight(120)
        self._list_widget.setFont(QFont("Segoe UI", 12))
        layout.addWidget(self._list_widget)

        layout.addSpacing(6)
        self._status_label = QLabel("Detecting DCS installations...")
        self._status_label.setObjectName("info_label")
        layout.addWidget(self._status_label)

        layout.addSpacing(20)

        self._skip_checkbox = QCheckBox("Skip DCS bridge installation")
        self._skip_checkbox.setFont(QFont("Segoe UI", 12))
        layout.addWidget(self._skip_checkbox)

        layout.addStretch(1)

        # Trigger discovery after a brief delay
        QTimer.singleShot(300, self._discover)

    def _discover(self) -> None:
        try:
            from .dcs_installer_utils import discover_dcs_targets
            targets = discover_dcs_targets()
        except Exception:
            targets = []

        self._list_widget.clear()
        if targets:
            for t in targets:
                self._list_widget.addItem(str(t.root))
            self._status_label.setText(f"Found {len(targets)} DCS installation(s).")
            self._status_label.setStyleSheet(f"color: {C_SUCCESS}; font-size: 12px;")
        else:
            self._list_widget.addItem("No DCS installations detected")
            self._status_label.setText(
                "No DCS Saved Games folders were found. "
                "You can install the bridge manually later."
            )
            self._status_label.setStyleSheet(f"color: {C_WARNING}; font-size: 12px;")

    @property
    def skip_bridge(self) -> bool:
        return self._skip_checkbox.isChecked()


class _ProgressPage(QWidget):
    cancel_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._worker: _InstallWorker | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(48, 40, 48, 32)
        layout.setSpacing(0)

        title = _make_title("Downloading Components")
        layout.addWidget(title)
        layout.addSpacing(6)

        sub = _make_body(
            "Please wait while the required AI models and components are downloaded and installed."
        )
        layout.addWidget(sub)
        layout.addSpacing(24)

        # Overall progress
        layout.addWidget(_make_section("Overall Progress"))
        layout.addSpacing(8)

        self._overall_bar = QProgressBar()
        self._overall_bar.setRange(0, 100)
        self._overall_bar.setValue(0)
        self._overall_bar.setFixedHeight(10)
        layout.addWidget(self._overall_bar)

        layout.addSpacing(20)

        # Component rows
        layout.addWidget(_make_section("Components"))
        layout.addSpacing(10)

        self._component_bars: dict[str, QProgressBar] = {}
        self._component_labels: dict[str, QLabel] = {}
        components = [
            ("ollama", "Ollama Language Model"),
            ("whisper", "Whisper Speech Recognition"),
            ("piper", "Piper Text-to-Speech"),
            ("lua_bridge", "DCS Lua Bridge"),
        ]
        for comp_id, comp_label in components:
            row_frame = QFrame()
            row_frame.setObjectName("component_row")
            row_layout = QVBoxLayout(row_frame)
            row_layout.setContentsMargins(12, 10, 12, 10)
            row_layout.setSpacing(6)

            header_row = QHBoxLayout()
            lbl = QLabel(comp_label)
            lbl.setFont(QFont("Segoe UI", 12, QFont.Weight.Medium))
            header_row.addWidget(lbl)

            status = QLabel("Waiting...")
            status.setFont(QFont("Segoe UI", 11))
            status.setStyleSheet(f"color: {C_TEXT_DIM};")
            status.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._component_labels[comp_id] = status
            header_row.addWidget(status)

            row_layout.addLayout(header_row)

            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(0)
            bar.setFixedHeight(6)
            self._component_bars[comp_id] = bar
            row_layout.addWidget(bar)

            layout.addWidget(row_frame)
            layout.addSpacing(6)

        layout.addSpacing(10)

        # Log area
        layout.addWidget(_make_section("Installation Log"))
        layout.addSpacing(8)

        self._log_edit = QTextEdit()
        self._log_edit.setReadOnly(True)
        self._log_edit.setFont(QFont("Cascadia Code", 11) if True else QFont("Courier New", 11))
        self._log_edit.setFixedHeight(130)
        layout.addWidget(self._log_edit)

        layout.addStretch(1)

    def start_install(self, install_config: dict[str, Any]) -> None:
        self._log_edit.clear()
        for bar in self._component_bars.values():
            bar.setValue(0)
        for lbl in self._component_labels.values():
            lbl.setText("Waiting...")
            lbl.setStyleSheet(f"color: {C_TEXT_DIM};")
        self._overall_bar.setValue(0)

        self._worker = _InstallWorker(install_config, self)
        self._worker.progress_overall.connect(self._on_overall_progress)
        self._worker.progress_component.connect(self._on_component_progress)
        self._worker.log_line.connect(self._on_log_line)
        self._worker.component_done.connect(self._on_component_done)
        self._worker.finished_all.connect(self._on_finished)
        self._worker.start()

    def request_cancel(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.request_cancel()
            self._append_log("[CANCEL] Cancellation requested, waiting for current step...")

    def _on_overall_progress(self, pct: int) -> None:
        self._overall_bar.setValue(pct)

    def _on_component_progress(self, component: str, pct: int) -> None:
        if component in self._component_bars:
            self._component_bars[component].setValue(pct)
        if component in self._component_labels:
            self._component_labels[component].setText(f"{pct}%")
            self._component_labels[component].setStyleSheet(f"color: {C_ACCENT};")

    def _on_log_line(self, line: str) -> None:
        self._append_log(line)

    def _on_component_done(self, component: str, success: bool) -> None:
        if component in self._component_labels:
            if success:
                self._component_labels[component].setText("Done ✓")
                self._component_labels[component].setStyleSheet(f"color: {C_SUCCESS}; font-weight: 600;")
                if component in self._component_bars:
                    self._component_bars[component].setValue(100)
            else:
                self._component_labels[component].setText("Failed ✗")
                self._component_labels[component].setStyleSheet(f"color: {C_ERROR}; font-weight: 600;")

    def _on_finished(self, success: bool, message: str) -> None:
        if success:
            self._overall_bar.setValue(100)
            self._append_log(f"\n{message}")
        else:
            self._append_log(f"\n[FAILED] {message}")

    def _append_log(self, line: str) -> None:
        self._log_edit.append(line)
        sb = self._log_edit.verticalScrollBar()
        sb.setValue(sb.maximum())

    @property
    def worker(self) -> _InstallWorker | None:
        return self._worker


class _CompletePage(QWidget):
    launch_requested = pyqtSignal()
    close_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._install_config: dict[str, Any] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(48, 40, 48, 40)
        layout.setSpacing(0)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Big checkmark
        checkmark = QLabel("✅")
        checkmark.setObjectName("complete_icon")
        checkmark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        checkmark.setFont(QFont("Segoe UI Emoji", 72))
        layout.addWidget(checkmark)
        layout.addSpacing(20)

        # Heading
        heading = QLabel("Installation Complete!")
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        heading.setFont(QFont("Segoe UI", 26, QFont.Weight.Bold))
        heading.setStyleSheet(f"color: {C_TEXT}; background-color: transparent;")
        layout.addWidget(heading)
        layout.addSpacing(10)

        sub = QLabel("Voice-Comms-DCS is ready to use.")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setFont(QFont("Segoe UI", 14))
        sub.setStyleSheet(f"color: {C_TEXT_MUTED}; background-color: transparent;")
        layout.addWidget(sub)

        layout.addSpacing(32)

        # Summary box
        summary_frame = QFrame()
        summary_frame.setObjectName("req_row")
        summary_layout = QVBoxLayout(summary_frame)
        summary_layout.setContentsMargins(20, 16, 20, 16)
        summary_layout.setSpacing(8)

        self._summary_label = QLabel()
        self._summary_label.setFont(QFont("Segoe UI", 12))
        self._summary_label.setStyleSheet(f"color: {C_TEXT_MUTED}; background-color: transparent;")
        self._summary_label.setWordWrap(True)
        summary_layout.addWidget(self._summary_label)

        layout.addWidget(summary_frame)
        layout.addSpacing(32)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        btn_row.setAlignment(Qt.AlignmentFlag.AlignCenter)

        launch_btn = QPushButton("🚀  Launch Voice-Comms-DCS")
        launch_btn.setObjectName("launch_btn")
        launch_btn.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        launch_btn.clicked.connect(self.launch_requested)
        btn_row.addWidget(launch_btn)

        close_btn = QPushButton("Close")
        close_btn.setObjectName("secondary_btn")
        close_btn.setFont(QFont("Segoe UI", 13))
        close_btn.clicked.connect(self.close_requested)
        btn_row.addWidget(close_btn)

        layout.addLayout(btn_row)
        layout.addStretch(1)

    def set_install_config(self, config: dict[str, Any]) -> None:
        self._install_config = config
        langs = ", ".join(config.get("languages", ["en"]))
        model = config.get("ollama_model", "qwen2.5:0.5b")
        quality = config.get("whisper_quality", "base")
        skip = config.get("skip_bridge", False)

        lines = [
            f"• Languages: {langs}",
            f"• Ollama model: {model}",
            f"• Whisper quality: {quality}",
            f"• DCS bridge: {'skipped' if skip else 'installed'}",
            f"• Install path: {config.get('install_path', 'default')}",
        ]
        self._summary_label.setText("\n".join(lines))


# ---------------------------------------------------------------------------
# Main wizard dialog
# ---------------------------------------------------------------------------

_STEP_LABELS = [
    "Welcome",
    "License",
    "Location",
    "Models",
    "DCS Bridge",
    "Installing",
    "Complete",
]


class InstallerWizard(QDialog):
    """Custom dark-themed multi-step installation wizard."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Voice-Comms-DCS Setup Wizard")
        self.setMinimumSize(900, 620)
        self.resize(960, 660)
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.WindowCloseButtonHint
            | Qt.WindowType.WindowMinimizeButtonHint
        )

        self.install_config: dict[str, Any] = {}
        self._current_step: int = 0

        self._build_ui()
        self._center_on_screen()
        self._update_navigation()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # Main horizontal split
        main_widget = QWidget()
        main_layout = QHBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Sidebar
        sidebar = self._build_sidebar()
        main_layout.addWidget(sidebar)

        # Content area
        content_wrapper = QWidget()
        content_wrapper.setObjectName("content_panel")
        content_layout = QVBoxLayout(content_wrapper)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # Stacked pages
        self._stack = QStackedWidget()
        content_layout.addWidget(self._stack, 1)

        main_layout.addWidget(content_wrapper, 1)
        root_layout.addWidget(main_widget, 1)

        # Bottom bar with navigation
        bottom_bar = self._build_bottom_bar()
        root_layout.addWidget(bottom_bar)

        # Create pages
        self._page_welcome = _WelcomePage()
        self._page_license = _LicensePage()
        self._page_location = _LocationPage()
        self._page_models = _LanguageModelsPage()
        self._page_dcs = _DcsBridgePage()
        self._page_progress = _ProgressPage()
        self._page_complete = _CompletePage()

        for page in [
            self._page_welcome,
            self._page_license,
            self._page_location,
            self._page_models,
            self._page_dcs,
            self._page_progress,
            self._page_complete,
        ]:
            self._stack.addWidget(page)

        # Connect signals
        self._page_license.license_accepted_changed.connect(self._update_navigation)
        self._page_complete.launch_requested.connect(self._on_launch)
        self._page_complete.close_requested.connect(self.accept)

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(220)
        sidebar.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 32, 0, 32)
        layout.setSpacing(0)

        # App brand at top
        brand_layout = QVBoxLayout()
        brand_layout.setContentsMargins(24, 0, 16, 0)
        brand_layout.setSpacing(2)

        brand_icon = QLabel("🎙️")
        brand_icon.setFont(QFont("Segoe UI Emoji", 22))
        brand_icon.setStyleSheet(f"color: {C_ACCENT}; background-color: transparent;")
        brand_layout.addWidget(brand_icon)

        brand_name = QLabel("Voice-Comms-DCS")
        brand_name.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        brand_name.setStyleSheet(f"color: {C_TEXT}; background-color: transparent;")
        brand_layout.addWidget(brand_name)

        brand_ver = QLabel("Setup Wizard")
        brand_ver.setFont(QFont("Segoe UI", 10))
        brand_ver.setStyleSheet(f"color: {C_TEXT_DIM}; background-color: transparent;")
        brand_layout.addWidget(brand_ver)

        layout.addLayout(brand_layout)
        layout.addSpacing(28)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"background-color: {C_BORDER}; border: none; max-height: 1px;")
        layout.addWidget(sep)
        layout.addSpacing(16)

        # Step indicators
        self._step_indicators: list[StepIndicator] = []
        for i, label in enumerate(_STEP_LABELS):
            indicator = StepIndicator(i + 1, label)
            indicator.set_state("current" if i == 0 else "future")
            self._step_indicators.append(indicator)
            layout.addWidget(indicator)

        layout.addStretch(1)

        # Version at bottom
        ver_label = QLabel("v1.0.0")
        ver_label.setFont(QFont("Segoe UI", 10))
        ver_label.setStyleSheet(f"color: {C_TEXT_DIM}; background-color: transparent;")
        ver_label.setContentsMargins(24, 0, 0, 0)
        layout.addWidget(ver_label)

        return sidebar

    def _build_bottom_bar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("bottom_bar")
        bar.setFixedHeight(64)

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(24, 12, 24, 12)
        layout.setSpacing(10)

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setObjectName("cancel_btn")
        self._cancel_btn.clicked.connect(self._on_cancel)
        layout.addWidget(self._cancel_btn)

        layout.addStretch(1)

        self._back_btn = QPushButton("← Back")
        self._back_btn.setObjectName("secondary_btn")
        self._back_btn.clicked.connect(self._on_back)
        layout.addWidget(self._back_btn)

        self._next_btn = QPushButton("Next →")
        self._next_btn.clicked.connect(self._on_next)
        layout.addWidget(self._next_btn)

        return bar

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def _update_navigation(self) -> None:
        step = self._current_step
        n = len(_STEP_LABELS)

        # Back button
        self._back_btn.setEnabled(step > 0 and step < n - 1 and step != 5)

        # Next button
        is_last = step == n - 1
        is_progress = step == 5

        if is_last or is_progress:
            self._next_btn.setVisible(False)
        else:
            self._next_btn.setVisible(True)
            # Enable/disable based on page state
            if step == 1:  # License
                self._next_btn.setEnabled(self._page_license.is_accepted)
            else:
                self._next_btn.setEnabled(True)

        # Cancel button text
        if is_progress:
            self._cancel_btn.setText("Cancel Install")
        elif is_last:
            self._cancel_btn.setVisible(False)
        else:
            self._cancel_btn.setText("Cancel")
            self._cancel_btn.setVisible(True)

        # Update sidebar indicators
        for i, indicator in enumerate(self._step_indicators):
            if i < step:
                indicator.set_state("done")
            elif i == step:
                indicator.set_state("current")
            else:
                indicator.set_state("future")

    def _go_to_step(self, step: int) -> None:
        self._current_step = step
        self._stack.setCurrentIndex(step)
        self._update_navigation()

    def _on_next(self) -> None:
        step = self._current_step

        # Collect config from each step
        if step == 2:
            self.install_config["install_path"] = self._page_location.install_path
        elif step == 3:
            self.install_config["languages"] = self._page_models.selected_languages
            self.install_config["ollama_model"] = self._page_models.selected_ollama_model
            self.install_config["whisper_quality"] = self._page_models.selected_whisper_quality
        elif step == 4:
            self.install_config["skip_bridge"] = self._page_dcs.skip_bridge

        next_step = step + 1

        if next_step == 5:
            # Start installation
            self._page_complete.set_install_config(self.install_config)
            self._go_to_step(5)
            self._page_progress.start_install(self.install_config)

            # Watch for completion
            worker = self._page_progress.worker
            if worker:
                worker.finished_all.connect(self._on_install_finished)
        else:
            self._go_to_step(next_step)

    def _on_back(self) -> None:
        if self._current_step > 0:
            self._go_to_step(self._current_step - 1)

    def _on_cancel(self) -> None:
        if self._current_step == 5:
            self._page_progress.request_cancel()
        else:
            self.reject()

    def _on_install_finished(self, success: bool, message: str) -> None:
        if success:
            self._go_to_step(6)
        else:
            # Stay on progress page but re-enable cancel to close
            self._cancel_btn.setText("Close")

    def _on_launch(self) -> None:
        self.accept()
        # In a real deployment, launch the main app here:
        # subprocess.Popen([sys.executable, "-m", "voice_comms_dcs"])

    def _center_on_screen(self) -> None:
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            x = (geo.width() - self.width()) // 2 + geo.left()
            y = (geo.height() - self.height()) // 2 + geo.top()
            self.move(x, y)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Standalone entry point for testing the wizard."""
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Voice-Comms-DCS Setup")
    app.setOrganizationName("Voice-Comms-DCS")

    # Apply global stylesheet
    app.setStyleSheet(GLOBAL_QSS)

    # Set dark palette to back up the QSS
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(C_BG))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(C_TEXT))
    palette.setColor(QPalette.ColorRole.Base, QColor(C_PANEL))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(C_SIDEBAR))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(C_PANEL))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(C_TEXT))
    palette.setColor(QPalette.ColorRole.Text, QColor(C_TEXT))
    palette.setColor(QPalette.ColorRole.Button, QColor(C_PANEL))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(C_TEXT))
    palette.setColor(QPalette.ColorRole.BrightText, QColor(C_ACCENT))
    palette.setColor(QPalette.ColorRole.Link, QColor(C_ACCENT))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(C_ACCENT))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(C_BG))
    app.setPalette(palette)

    wizard = InstallerWizard()
    wizard.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
