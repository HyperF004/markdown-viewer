import argparse
import base64
import ctypes
import ctypes.wintypes
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

import markdown
from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, QThread, Qt, Signal
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QAbstractButton,
    QButtonGroup,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSplitter,
    QSizePolicy,
    QStyle,
    QStyleFactory,
    QTextBrowser,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


APP_NAME = "Markdown Viewer"
APP_DIR = Path(__file__).resolve().parent
ICON_PATH = APP_DIR / "assets" / "markdown-viewer.ico"
CONFIG_DIR = Path(os.environ.get("APPDATA", str(APP_DIR))) / "MarkdownViewer"
CONFIG_PATH = CONFIG_DIR / "settings.json"
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
MODELS = ("deepseek-v4-flash", "deepseek-v4-pro")
LANGUAGES = ("中文（简体）", "英语", "日语", "韩语", "法语", "德语", "西班牙语", "俄语")

COLORS = {
    "app": "#F6F8FA",
    "sidebar": "#F0F2F5",
    "panel": "#FFFFFF",
    "border": "#E2E8F0",
    "brand": "#2563EB",
    "hover": "#0EA5E9",
    "text": "#111827",
    "muted": "#64748B",
    "success": "#16A34A",
}


def markdown_html(value):
    return markdown.markdown(value, extensions=("fenced_code", "tables", "sane_lists", "nl2br"))


class DataBlob(ctypes.Structure):
    _fields_ = [("cbData", ctypes.wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


def protect_secret(value):
    if not value:
        return ""
    raw = value.encode("utf-8")
    if sys.platform != "win32":
        return base64.b64encode(raw).decode("ascii")
    input_buffer = ctypes.create_string_buffer(raw)
    input_blob = DataBlob(len(raw), ctypes.cast(input_buffer, ctypes.POINTER(ctypes.c_ubyte)))
    output_blob = DataBlob()
    if not ctypes.windll.crypt32.CryptProtectData(ctypes.byref(input_blob), None, None, None, None, 0, ctypes.byref(output_blob)):
        return ""
    try:
        return base64.b64encode(ctypes.string_at(output_blob.pbData, output_blob.cbData)).decode("ascii")
    finally:
        ctypes.windll.kernel32.LocalFree(output_blob.pbData)


def unprotect_secret(value):
    if not value:
        return ""
    try:
        raw = base64.b64decode(value)
    except Exception:
        return ""
    if sys.platform != "win32":
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            return ""
    input_buffer = ctypes.create_string_buffer(raw)
    input_blob = DataBlob(len(raw), ctypes.cast(input_buffer, ctypes.POINTER(ctypes.c_ubyte)))
    output_blob = DataBlob()
    if not ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(input_blob), None, None, None, None, 0, ctypes.byref(output_blob)):
        return ""
    try:
        return ctypes.string_at(output_blob.pbData, output_blob.cbData).decode("utf-8")
    except UnicodeDecodeError:
        return ""
    finally:
        ctypes.windll.kernel32.LocalFree(output_blob.pbData)


def text_chunks(value, limit=3600):
    parts = [part.strip() for part in value.split("\n\n") if part.strip()]
    chunks, current = [], ""
    for part in parts or [value]:
        candidate = f"{current}\n\n{part}".strip()
        if current and len(candidate) > limit:
            chunks.append(current)
            current = part
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


class MacSwitch(QAbstractButton):
    """A compact macOS-style switch with a green/grey animated track."""

    def __init__(self, checked=True, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setFixedSize(44, 26)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("跟随滚动")
        self._offset = 1.0 if checked else 0.0
        self._dark_mode = False
        self._animation = QPropertyAnimation(self, b"offset", self)
        self._animation.setDuration(180)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.toggled.connect(self.animate)

    def get_offset(self):
        return self._offset

    def set_offset(self, value):
        self._offset = float(value)
        self.update()

    offset = Property(float, get_offset, set_offset)

    def animate(self, checked):
        self._animation.stop()
        self._animation.setStartValue(self._offset)
        self._animation.setEndValue(1.0 if checked else 0.0)
        self._animation.start()

    def set_dark_mode(self, enabled):
        self._dark_mode = enabled
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        track = self.rect().adjusted(1, 2, -1, -2)
        off = QColor("#3A3A3C" if self._dark_mode else "#D1D1D6")
        on = QColor("#34C759")
        color = QColor(
            round(off.red() + (on.red() - off.red()) * self._offset),
            round(off.green() + (on.green() - off.green()) * self._offset),
            round(off.blue() + (on.blue() - off.blue()) * self._offset),
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawRoundedRect(track, track.height() / 2, track.height() / 2)
        knob_size = track.height() - 4
        left = track.left() + 2
        right = track.right() - knob_size - 1
        knob_x = left + (right - left) * self._offset
        # A restrained shadow separates the white thumb from the off-state track.
        painter.setBrush(QColor(0, 0, 0, 22))
        painter.drawEllipse(int(knob_x), track.top() + 3, knob_size, knob_size)
        painter.setBrush(QColor("#FFFFFF"))
        painter.drawEllipse(int(knob_x), track.top() + 2, knob_size, knob_size)
        painter.end()


class TranslationWorker(QThread):
    progress = Signal(int, int)
    completed = Signal(str)
    failed = Signal(str)

    def __init__(self, chunks, language, api_key, model, quality):
        super().__init__()
        self.chunks = chunks
        self.language = language
        self.api_key = api_key
        self.model = model
        self.quality = quality

    def run(self):
        try:
            translated = []
            for index, chunk in enumerate(self.chunks, start=1):
                translated.append(self.translate_chunk(chunk))
                self.progress.emit(index, len(self.chunks))
            self.completed.emit("\n\n".join(translated))
        except Exception as exc:
            self.failed.emit(str(exc))

    def translate_chunk(self, value):
        fast = self.quality == "快速翻译"
        system = (
            "You are a fast translation engine. Translate directly and accurately. "
            "Preserve Markdown structure. Return only the translation."
            if fast
            else "You are a professional translator. Preserve Markdown structure, terminology, tone, and formatting. Return only the translation."
        )
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": f"Translate the following Markdown into {self.language}:\n\n{value}"},
            ],
            "temperature": 0.1 if fast else 0.3,
            "thinking": {"type": "disabled" if fast else "enabled"},
        }
        request = urllib.request.Request(
            DEEPSEEK_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=50) as response:
                result = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(detail or f"HTTP Error {exc.code}") from exc
        return result["choices"][0]["message"]["content"].strip()


class SettingsDialog(QDialog):
    def __init__(self, parent, values):
        super().__init__(parent)
        self.setWindowTitle("DeepSeek API 配置")
        self.setModal(True)
        self.setMinimumWidth(460)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)
        title = QLabel("DeepSeek API 配置")
        title.setObjectName("dialogTitle")
        layout.addWidget(title)
        layout.addWidget(QLabel("API Key"))
        self.key = QLineEdit(values.get("api_key", ""))
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.key.setPlaceholderText("请输入您的 DeepSeek API Key (sk-...)")
        layout.addWidget(self.key)
        layout.addWidget(QLabel("默认模型"))
        self.model = QComboBox()
        self.model.addItem("deepseek-v4-flash  ⚡", MODELS[0])
        self.model.addItem("deepseek-v4-pro  🧠", MODELS[1])
        self.model.setCurrentIndex(max(0, self.model.findData(values.get("model", MODELS[0]))))
        layout.addWidget(self.model)
        layout.addWidget(QLabel("Base URL"))
        base = QLineEdit("https://api.deepseek.com")
        base.setReadOnly(True)
        layout.addWidget(base)
        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton("关闭")
        cancel.clicked.connect(self.reject)
        save = QPushButton("保存")
        save.setObjectName("primary")
        save.clicked.connect(self.accept)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        layout.addLayout(buttons)

    def values(self):
        return {"api_key": self.key.text().strip(), "model": self.model.currentData()}


class MarkdownViewerQt(QMainWindow):
    def __init__(self, initial_path=None):
        super().__init__()
        self.current_path = None
        self.translation_worker = None
        self.syncing = False
        self.source_width = 0
        self.settings = self.load_settings()
        self.dark_mode = self.settings.get("theme", "light") == "dark"
        self.setWindowTitle(f"{APP_NAME} Qt Preview")
        self.setMinimumSize(1040, 660)
        self.resize(1320, 820)
        if ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(ICON_PATH)))
        self.build_ui()
        self.build_menu()
        self.apply_styles()
        self.set_markdown("# 欢迎使用 Markdown Viewer\n\n这是全新 Qt 界面预览版。打开 Markdown 文件即可预览与翻译。")
        if initial_path:
            self.open_path(initial_path)

    def build_ui(self):
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(20, 20, 20, 18)
        outer.setSpacing(0)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(5)
        outer.addWidget(self.splitter, 1)

        self.content_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.content_splitter.setChildrenCollapsible(False)
        self.content_splitter.setHandleWidth(4)
        content = QWidget()
        content.setMinimumWidth(320)
        content.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(14, 14, 14, 0)
        content_layout.addWidget(self.content_splitter, 1)
        self.status = QLabel("就绪")
        self.status.setObjectName("status")
        content_layout.addWidget(self.status)

        self.source = QPlainTextEdit()
        self.source.setObjectName("sourceEditor")
        self.source.setMinimumWidth(0)
        self.source.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        self.source.setReadOnly(True)
        self.source.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.source.setFont(QFont("Cascadia Mono", 10))
        self.preview = QTextBrowser()
        self.preview.setObjectName("previewPane")
        self.preview.setMinimumWidth(0)
        self.preview.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        self.preview.setOpenExternalLinks(True)
        self.preview.setFont(QFont("Microsoft YaHei UI", 10))
        self.content_splitter.addWidget(self.source)
        self.content_splitter.addWidget(self.preview)
        self.content_splitter.setStretchFactor(0, 1)
        self.content_splitter.setStretchFactor(1, 2)

        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setMinimumWidth(240)
        side = QVBoxLayout(self.sidebar)
        side.setContentsMargins(14, 12, 14, 12)
        side.setSpacing(8)
        header = QHBoxLayout()
        side_title = QLabel("译文")
        side_title.setObjectName("sidebarTitle")
        header.addWidget(side_title)
        self.translation_state = QLabel("未翻译")
        self.translation_state.setObjectName("muted")
        header.addWidget(self.translation_state)
        header.addStretch()
        follow_label = QLabel("跟随")
        follow_label.setObjectName("followLabel")
        header.addWidget(follow_label)
        self.follow = MacSwitch(True)
        header.addWidget(self.follow)
        side.addLayout(header)

        self.scope_group = QButtonGroup(self)
        scope = QHBoxLayout()
        self.selection_button = self.mode_button("选中", True)
        self.document_button = self.mode_button("全文")
        self.scope_group.addButton(self.selection_button)
        self.scope_group.addButton(self.document_button)
        scope.addWidget(self.selection_button)
        scope.addWidget(self.document_button)
        scope.addStretch()
        side.addLayout(scope)

        self.quality_group = QButtonGroup(self)
        quality = QHBoxLayout()
        self.fast_button = self.mode_button("快速", True)
        self.pro_button = self.mode_button("精翻")
        self.quality_group.addButton(self.fast_button)
        self.quality_group.addButton(self.pro_button)
        quality.addWidget(self.fast_button)
        quality.addWidget(self.pro_button)
        quality.addStretch()
        side.addLayout(quality)

        self.translate_button = QPushButton("翻译")
        self.translate_button.setObjectName("translate")
        self.translate_button.clicked.connect(self.translate_current)
        side.addWidget(self.translate_button)
        line = QFrame()
        line.setObjectName("divider")
        line.setFrameShape(QFrame.Shape.HLine)
        side.addWidget(line)
        self.progress_label = QLabel("")
        self.progress_label.setObjectName("muted")
        self.progress_label.hide()
        self.progress = QProgressBar()
        self.progress.hide()
        side.addWidget(self.progress_label)
        side.addWidget(self.progress)
        self.translation = QTextBrowser()
        self.translation.setObjectName("translationPane")
        self.translation.setFont(QFont("Microsoft YaHei UI", 10))
        self.translation.setHtml("<p>选中原文后点击“翻译”，或切换到“全文”。</p>")
        side.addWidget(self.translation, 1)
        self.splitter.addWidget(content)
        self.splitter.addWidget(self.sidebar)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)
        self.splitter.setSizes([900, 380])

        self.source.verticalScrollBar().valueChanged.connect(lambda value: self.sync_scroll(self.source, self.translation, value))
        self.preview.verticalScrollBar().valueChanged.connect(lambda value: self.sync_scroll(self.preview, self.translation, value))
        self.translation.verticalScrollBar().valueChanged.connect(lambda value: self.sync_scroll(self.translation, self.active_content(), value))

    def mode_button(self, text, checked=False):
        button = QPushButton(text)
        button.setCheckable(True)
        button.setChecked(checked)
        button.setObjectName("mode")
        button.setMinimumHeight(28)
        button.setMinimumWidth(64)
        return button

    def build_menu(self):
        file_menu = self.menuBar().addMenu("文件")
        open_action = QAction("打开文件...", self, shortcut="Ctrl+O", triggered=self.choose_file)
        reload_action = QAction("重新载入", self, shortcut="Ctrl+R", triggered=self.reload_file)
        file_menu.addActions([open_action, reload_action])
        file_menu.addSeparator()
        file_menu.addAction(QAction("退出", self, shortcut="Alt+F4", triggered=self.close))
        view_menu = self.menuBar().addMenu("视图")
        self.source_action = QAction("隐藏源码栏", self, triggered=self.toggle_source)
        self.sidebar_action = QAction("隐藏翻译栏", self, triggered=self.toggle_sidebar)
        view_menu.addActions([self.source_action, self.sidebar_action])
        view_menu.addSeparator()
        self.theme_action = QAction("深色模式", self, checkable=True)
        self.theme_action.setChecked(self.dark_mode)
        self.theme_action.toggled.connect(self.set_dark_mode)
        view_menu.addAction(self.theme_action)
        settings_menu = self.menuBar().addMenu("设置")
        settings_menu.addAction(QAction("DeepSeek API 配置...", self, triggered=self.open_settings))
        tools = self.menuBar().addMenu("工具")
        tools.addAction(QAction("开始翻译", self, shortcut="Ctrl+T", triggered=self.translate_current))
        tools.addAction(QAction("复制译文", self, triggered=lambda: QApplication.clipboard().setText(self.translation.toPlainText())))

    def apply_styles(self):
        if self.dark_mode:
            colors = {
                "app": "#1C1C1E", "menu": "#2C2C2E", "panel": "#2C2C2E", "sidebar": "#242426",
                "border": "#3A3A3C", "text": "#F5F5F7", "muted": "#AEAEB2", "menu_hover": "#3A3A3C",
                "field_hover": "#3A3A3C", "mode": "#3A3A3C", "mode_hover": "#48484A", "mode_checked": "#344B67",
                "brand": "#0A84FF", "brand_hover": "#409CFF", "brand_pressed": "#006EDB", "progress": "#1D3D62",
                "success": "#30D158", "scroll": "rgba(235,235,245,0.30)", "scroll_hover": "rgba(235,235,245,0.52)",
            }
        else:
            colors = {
                "app": "#F5F5F7", "menu": "rgba(255,255,255,0.82)", "panel": "#FFFFFF", "sidebar": "#ECECF1",
                "border": "#D2D2D7", "text": "#1D1D1F", "muted": "#6E6E73", "menu_hover": "#E8E8ED",
                "field_hover": "#FFFFFF", "mode": "#E2E2E7", "mode_hover": "#D7D7DD", "mode_checked": "#FFFFFF",
                "brand": "#007AFF", "brand_hover": "#0A84FF", "brand_pressed": "#006EDB", "progress": "#DDEBFF",
                "success": "#34C759", "scroll": "rgba(60,60,67,0.28)", "scroll_hover": "rgba(60,60,67,0.46)",
            }
        self.follow.set_dark_mode(self.dark_mode)
        markdown_style = f"""
            body {{ color: {colors['text']}; background: transparent; font-family: 'Microsoft YaHei UI', 'Segoe UI'; line-height: 1.65; }}
            a {{ color: {colors['brand']}; }}
            code {{ background: {colors['mode']}; border-radius: 4px; padding: 2px 4px; }}
            pre {{ background: {colors['mode']}; border: 1px solid {colors['border']}; border-radius: 8px; padding: 10px; }}
            blockquote {{ color: {colors['muted']}; border-left: 3px solid {colors['brand']}; margin-left: 0; padding-left: 10px; }}
            table {{ border-collapse: collapse; }}
            th, td {{ border: 1px solid {colors['border']}; padding: 6px; }}
            th {{ background: {colors['mode']}; }}
        """
        for browser in (self.preview, self.translation):
            browser.document().setDefaultStyleSheet(markdown_style)
        self.setStyleSheet(f"""
            QMainWindow, #root {{ background: {colors['app']}; color: {colors['text']}; font-family: 'Segoe UI Variable', 'Microsoft YaHei UI', 'Segoe UI'; font-size: 10pt; }}
            QMenuBar {{ background: {colors['menu']}; color: {colors['text']}; border: none; border-bottom: 1px solid {colors['border']}; padding: 3px 8px; }}
            QMenuBar::item {{ color: {colors['text']}; padding: 6px 10px; border-radius: 5px; }}
            QMenuBar::item:selected {{ background: {colors['menu_hover']}; }}
            QMenu {{ background: {colors['menu']}; color: {colors['text']}; border: 1px solid {colors['border']}; padding: 5px; }}
            QMenu::item {{ color: {colors['text']}; padding: 7px 26px 7px 12px; border-radius: 5px; }}
            QMenu::item:selected {{ background: {colors['mode_checked']}; color: {colors['brand_hover']}; }}
            #sourceEditor, #previewPane, #translationPane {{ background: {colors['panel']}; color: {colors['text']}; border: 1px solid {colors['border']}; border-radius: 22px; padding: 14px; selection-background-color: #275D9B; }}
            #sidebar {{ background: {colors['sidebar']}; border: 1px solid {colors['border']}; border-radius: 28px; }}
            QSplitter::handle {{ background: transparent; width: 5px; }}
            QSplitter::handle:hover {{ background: {colors['brand_hover']}; }}
            QSplitter::handle:pressed {{ background: {colors['brand']}; }}
            QPushButton {{ border: 1px solid {colors['border']}; background: {colors['panel']}; color: {colors['text']}; padding: 5px 11px; border-radius: 9px; }}
            QPushButton:hover {{ background: {colors['field_hover']}; border-color: {colors['muted']}; }}
            QPushButton:pressed {{ background: {colors['mode']}; }}
            QPushButton#mode {{ background: {colors['mode']}; border: none; border-radius: 9px; color: {colors['text']}; font-weight: 600; }}
            QPushButton#mode:hover {{ background: {colors['mode_hover']}; }}
            QPushButton#mode:checked {{ background: {colors['mode_checked']}; color: {colors['brand_hover']}; border: 1px solid {colors['border']}; }}
            QPushButton#translate {{ min-height: 42px; background: {colors['brand']}; color: white; border: none; border-radius: 12px; font-weight: 700; }}
            QPushButton#translate:hover {{ background: {colors['brand_hover']}; }}
            QPushButton#translate:pressed {{ background: {colors['brand_pressed']}; }}
            #sidebarTitle {{ font-size: 12pt; font-weight: 700; color: {colors['text']}; }}
            #followLabel, #muted, #status {{ color: {colors['muted']}; }}
            #status {{ padding: 8px 3px 1px; font-size: 9pt; }}
            QProgressBar {{ border: none; background: {colors['progress']}; border-radius: 3px; height: 6px; }}
            QProgressBar::chunk {{ background: {colors['success']}; border-radius: 3px; }}
            #divider {{ border: none; background: {colors['border']}; min-height: 1px; max-height: 1px; }}
            QScrollBar:vertical {{ background: transparent; width: 10px; margin: 6px 2px; }}
            QScrollBar::handle:vertical {{ background: {colors['scroll']}; min-height: 36px; border-radius: 4px; }}
            QScrollBar::handle:vertical:hover {{ background: {colors['scroll_hover']}; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
            QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px 6px; }}
            QScrollBar::handle:horizontal {{ background: {colors['scroll']}; min-width: 36px; border-radius: 4px; }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0px; }}
            #dialogTitle {{ font-size: 16pt; font-weight: 700; color: {colors['text']}; }}
            QDialog {{ background: {colors['app']}; color: {colors['text']}; }}
            QLineEdit, QComboBox {{ background: {colors['panel']}; color: {colors['text']}; border: 1px solid {colors['border']}; padding: 8px; border-radius: 7px; }}
            QLineEdit:focus, QComboBox:focus {{ border: 2px solid {colors['brand']}; }}
            QPushButton#primary {{ background: {colors['brand']}; color: white; border: none; border-radius: 7px; padding: 8px 17px; }}
            QToolTip {{ background: {colors['menu']}; color: {colors['text']}; border: 1px solid {colors['border']}; padding: 4px; }}
        """)
        self.apply_window_chrome()

    def apply_window_chrome(self):
        """Keep the native Windows title bar aligned with the selected theme."""
        if sys.platform != "win32":
            return
        value = ctypes.c_int(1 if self.dark_mode else 0)
        hwnd = int(self.winId())
        for attribute in (20, 19):  # 20 is Windows 11; 19 supports early Windows 10 builds.
            try:
                result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, attribute, ctypes.byref(value), ctypes.sizeof(value)
                )
                if result == 0:
                    break
            except (AttributeError, OSError):
                break

    def showEvent(self, event):
        super().showEvent(event)
        self.apply_window_chrome()

    def set_dark_mode(self, enabled):
        self.dark_mode = enabled
        self.settings["theme"] = "dark" if enabled else "light"
        self.save_settings()
        self.apply_styles()

    def active_content(self):
        return self.source if self.source.isVisible() else self.preview

    def sync_scroll(self, source, target, value):
        if self.syncing or not self.follow.isChecked() or not target:
            return
        source_bar = source.verticalScrollBar()
        target_bar = target.verticalScrollBar()
        if source_bar.maximum() <= 0 or target_bar.maximum() <= 0:
            return
        self.syncing = True
        target_bar.setValue(round(value / source_bar.maximum() * target_bar.maximum()))
        self.syncing = False

    def choose_file(self):
        filename, _ = QFileDialog.getOpenFileName(self, "打开 Markdown 文件", "", "Markdown (*.md *.markdown *.mdown *.mkd);;Text (*.txt);;All files (*.*)")
        if filename:
            self.open_path(filename)

    def open_path(self, filename):
        try:
            path = Path(filename)
            self.set_markdown(path.read_text(encoding="utf-8"))
            self.current_path = path
            self.status.setText(f"已打开：{path.name}")
        except (OSError, UnicodeDecodeError) as exc:
            QMessageBox.critical(self, APP_NAME, f"无法打开文件：\n{exc}")

    def reload_file(self):
        if self.current_path:
            self.open_path(self.current_path)

    def set_markdown(self, value):
        self.source.setPlainText(value)
        self.preview.setHtml(markdown_html(value))

    def load_settings(self):
        try:
            settings = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            settings["api_key"] = unprotect_secret(settings.get("api_key", ""))
            return settings
        except (OSError, json.JSONDecodeError):
            return {"model": MODELS[0], "api_key": ""}

    def save_settings(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        stored = dict(self.settings)
        stored["api_key"] = protect_secret(self.settings.get("api_key", ""))
        CONFIG_PATH.write_text(json.dumps(stored, ensure_ascii=False, indent=2), encoding="utf-8")

    def open_settings(self):
        dialog = SettingsDialog(self, self.settings)
        if dialog.exec():
            self.settings.update(dialog.values())
            self.save_settings()
            self.status.setText("DeepSeek API 配置已保存")

    def translate_current(self):
        if self.translation_worker and self.translation_worker.isRunning():
            return
        api_key = self.settings.get("api_key", "")
        if not api_key:
            self.open_settings()
            api_key = self.settings.get("api_key", "")
            if not api_key:
                return
        selected = self.source.textCursor().selectedText().replace("\u2029", "\n").strip()
        full = self.source.toPlainText().strip()
        value = full if self.document_button.isChecked() else selected
        if not value:
            QMessageBox.information(self, APP_NAME, "请先在原文中选中要翻译的文字，或切换到“全文”。")
            return
        self.translate_button.setEnabled(False)
        self.translation_state.setText("翻译中")
        self.progress_label.setText("翻译中...")
        self.progress_label.show()
        self.progress.setRange(0, max(1, len(text_chunks(value))))
        self.progress.setValue(0)
        self.progress.show()
        quality = "快速翻译" if self.fast_button.isChecked() else "精翻"
        self.translation_worker = TranslationWorker(text_chunks(value), "中文（简体）", api_key, self.settings.get("model", MODELS[0]), quality)
        self.translation_worker.progress.connect(self.update_progress)
        self.translation_worker.completed.connect(self.translation_done)
        self.translation_worker.failed.connect(self.translation_failed)
        self.translation_worker.start()

    def update_progress(self, done, total):
        self.progress.setRange(0, total)
        self.progress.setValue(done)
        self.progress_label.setText("翻译中..." if total == 1 else f"正在翻译 第 {done}/{total} 段")

    def translation_done(self, value):
        self.translation.setHtml(markdown_html(value))
        self.translation_state.setText("已翻译为中文（简体）")
        self.status.setText("翻译完成")
        self.progress.setValue(self.progress.maximum())
        self.progress_label.setText("翻译完成")
        self.translate_button.setEnabled(True)

    def translation_failed(self, message):
        self.translation_state.setText("翻译失败")
        self.translation.setPlainText(f"翻译失败：\n{message}")
        self.status.setText("翻译失败")
        self.progress.hide()
        self.progress_label.hide()
        self.translate_button.setEnabled(True)

    def toggle_sidebar(self):
        visible = self.sidebar.isVisible()
        self.sidebar.setVisible(not visible)
        self.sidebar_action.setText("显示翻译栏" if visible else "隐藏翻译栏")

    def toggle_source(self):
        visible = self.source.isVisible()
        if visible:
            self.source_width = self.content_splitter.sizes()[0]
            self.source.hide()
            self.source_action.setText("显示源码栏")
            return
        self.source.show()
        total = sum(self.content_splitter.sizes())
        source_width = self.source_width or max(320, total // 3)
        self.content_splitter.setSizes([source_width, max(1, total - source_width)])
        self.source_action.setText("隐藏源码栏")


def main():
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("file", nargs="?", help="Markdown 文件")
    args = parser.parse_args()
    app = QApplication(sys.argv)
    app.setStyle(QStyleFactory.create("Fusion"))
    window = MarkdownViewerQt(args.file)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
