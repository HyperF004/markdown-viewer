import argparse
import base64
import concurrent.futures
import ctypes
import ctypes.wintypes
import json
import os
import re
import sys
import threading
import tkinter as tk
import urllib.error
import urllib.request
from pathlib import Path
from tkinter import filedialog, messagebox, ttk


APP_NAME = "Markdown Viewer"
APP_ID = "MarkdownViewer"
APP_DIR = Path(__file__).resolve().parent
ICON_PATH = APP_DIR / "assets" / "markdown-viewer.ico"
CONFIG_DIR = Path(os.environ.get("APPDATA", str(APP_DIR))) / "MarkdownViewer"
CONFIG_PATH = CONFIG_DIR / "settings.json"
# 旧版配置目录（曾带 CUBE18 前缀），仅首次启动时用于迁移
LEGACY_CONFIG_PATH = Path(os.environ.get("APPDATA", str(APP_DIR))) / "CUBE18MarkdownViewer" / "settings.json"
COLORS = {
    "app_bg": "#F6F8FA",
    "sidebar_bg": "#F0F2F5",
    "panel_bg": "#FFFFFF",
    "border": "#E2E8F0",
    "brand": "#2563EB",
    "brand_hover": "#0EA5E9",
    "text": "#111827",
    "muted": "#64748B",
    "success": "#16A34A",
    "danger": "#DC2626",
    "input_bg": "#FFFFFF",
    "soft_blue": "#EFF6FF",
}
FONT_FAMILY = "Microsoft YaHei UI"
FALLBACK_FONT = "Segoe UI"
SUPPORTED_TYPES = (
    ("Markdown 文件", "*.md *.markdown *.mdown *.mkd"),
    ("文本文件", "*.txt"),
    ("所有文件", "*.*"),
)

TRANSLATION_LANGUAGES = {
    "中文（简体）": "zh-CN",
    "英语": "en",
    "日语": "ja",
    "韩语": "ko",
    "法语": "fr",
    "德语": "de",
    "西班牙语": "es",
    "俄语": "ru",
}

DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODELS = (
    "deepseek-v4-flash",
    "deepseek-v4-pro",
)
MODEL_DISPLAY = {
    "deepseek-v4-flash": "deepseek-v4-flash ⚡",
    "deepseek-v4-pro": "deepseek-v4-pro 🧠",
}
MODEL_FROM_DISPLAY = {value: key for key, value in MODEL_DISPLAY.items()}
TRANSLATION_QUALITY_MODES = {
    "快速翻译": {
        "thinking": "disabled",
        "temperature": 0.1,
        "system": "You are a fast translation engine. Translate directly and accurately. Preserve Markdown structure. Do not explain.",
    },
    "精翻": {
        "thinking": "enabled",
        "temperature": None,
        "system": "You are a professional translation engine. Translate with high fidelity, preserve terminology, tone, formatting, and Markdown structure. Return only the translated text.",
    },
}

# 整行图片 ![](path)
IMAGE_LINE_PATTERN = re.compile(r"^!\[([^\]]*)\]\(([^)\n]+)\)\s*$")
# 行内标记：代码/加粗/斜体/链接
INLINE_LINK_PATTERN = re.compile(r"(`[^`]+`|\*\*[^*]+\*\*|__[^_]+__|\*[^*]+\*|_[^_]+_|\[[^\]\n]+]\([^)\n]+\))")
# 裸 URL 自动识别
BARE_URL_PATTERN = re.compile(r"https?://[^\s<>()\[\]\"']+")


class DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", ctypes.wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
    ]


def protect_secret(value):
    if not value:
        return ""
    raw = value.encode("utf-8")
    if sys.platform != "win32":
        return base64.b64encode(raw).decode("ascii")
    in_buffer = ctypes.create_string_buffer(raw)
    in_blob = DATA_BLOB(len(raw), ctypes.cast(in_buffer, ctypes.POINTER(ctypes.c_ubyte)))
    out_blob = DATA_BLOB()
    ok = ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)
    )
    if not ok:
        return ""
    try:
        data = ctypes.string_at(out_blob.pbData, out_blob.cbData)
        return base64.b64encode(data).decode("ascii")
    finally:
        ctypes.windll.kernel32.LocalFree(out_blob.pbData)


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
    in_buffer = ctypes.create_string_buffer(raw)
    in_blob = DATA_BLOB(len(raw), ctypes.cast(in_buffer, ctypes.POINTER(ctypes.c_ubyte)))
    out_blob = DATA_BLOB()
    ok = ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)
    )
    if not ok:
        return ""
    try:
        data = ctypes.string_at(out_blob.pbData, out_blob.cbData)
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return ""
    finally:
        ctypes.windll.kernel32.LocalFree(out_blob.pbData)


class PillButton(tk.Canvas):
    def __init__(self, parent, text, variable, value, command=None, width=78, height=24):
        super().__init__(
            parent,
            width=width,
            height=height,
            highlightthickness=0,
            bg=COLORS["sidebar_bg"],
            cursor="hand2",
        )
        self.text = text
        self.variable = variable
        self.value = value
        self.command = command
        self.width = width
        self.height = height
        self.hover = False
        self.bind("<Button-1>", self.on_click)
        self.bind("<Enter>", lambda _event: self.set_hover(True))
        self.bind("<Leave>", lambda _event: self.set_hover(False))
        self.variable.trace_add("write", lambda *_args: self.draw())
        self.draw()

    def set_hover(self, value):
        self.hover = value
        self.draw()

    def on_click(self, _event):
        self.variable.set(self.value)
        if self.command:
            self.command()
        self.draw()

    def draw(self):
        self.delete("all")
        selected = self.variable.get() == self.value
        fill = COLORS["brand"] if selected else (COLORS["soft_blue"] if self.hover else COLORS["panel_bg"])
        outline = COLORS["brand"] if selected or self.hover else COLORS["border"]
        text_fill = "#FFFFFF" if selected else COLORS["text"]
        radius = self.height // 2
        self.create_oval(1, 1, self.height - 1, self.height - 1, fill=fill, outline=outline)
        self.create_oval(self.width - self.height + 1, 1, self.width - 1, self.height - 1, fill=fill, outline=outline)
        self.create_rectangle(radius, 1, self.width - radius, self.height - 1, fill=fill, outline=fill)
        self.create_line(radius, 1, self.width - radius, 1, fill=outline)
        self.create_line(radius, self.height - 1, self.width - radius, self.height - 1, fill=outline)
        self.create_text(self.width // 2, self.height // 2, text=self.text, fill=text_fill, font=(FONT_FAMILY, 9, "bold" if selected else "normal"))


class IOSSwitch(tk.Canvas):
    def __init__(self, parent, variable, command=None):
        super().__init__(parent, width=38, height=22, highlightthickness=0, bg=COLORS["sidebar_bg"], cursor="hand2")
        self.variable = variable
        self.command = command
        self.bind("<Button-1>", self.toggle)
        self.variable.trace_add("write", lambda *_args: self.draw())
        self.draw()

    def toggle(self, _event=None):
        self.variable.set(not self.variable.get())
        if self.command:
            self.command()
        self.draw()

    def draw(self):
        self.delete("all")
        on = self.variable.get()
        track = COLORS["brand"] if on else "#CBD5E1"
        knob_x = 27 if on else 11
        self.create_oval(0, 0, 22, 22, fill=track, outline=track)
        self.create_oval(16, 0, 38, 22, fill=track, outline=track)
        self.create_rectangle(11, 0, 27, 22, fill=track, outline=track)
        self.create_oval(knob_x - 8, 3, knob_x + 8, 19, fill="#FFFFFF", outline="#FFFFFF")


class GradientButton(tk.Canvas):
    def __init__(self, parent, text, command, height=40):
        super().__init__(parent, height=height, highlightthickness=0, bg=COLORS["sidebar_bg"], cursor="hand2")
        self.text = text
        self.command = command
        self.height = height
        self.hover = False
        self.pressed = False
        self.enabled = True
        self._draw_after_id = None
        self.bind("<Configure>", self.schedule_draw)
        self.bind("<Enter>", lambda _event: self.set_hover(True))
        self.bind("<Leave>", lambda _event: self.set_hover(False))
        self.bind("<ButtonPress-1>", lambda _event: self.set_pressed(True))
        self.bind("<ButtonRelease-1>", self.release)

    def schedule_draw(self, _event=None):
        if self._draw_after_id:
            return
        self._draw_after_id = self.after_idle(self.draw)

    def set_hover(self, value):
        self.hover = value
        self.draw()

    def set_pressed(self, value):
        self.pressed = value
        self.draw()

    def release(self, event):
        if not self.enabled:
            return
        was_pressed = self.pressed
        self.set_pressed(False)
        if was_pressed and 0 <= event.x <= self.winfo_width() and 0 <= event.y <= self.winfo_height():
            self.command()

    def set_enabled(self, value):
        self.enabled = value
        self.configure(cursor="hand2" if value else "arrow")
        self.draw()

    def draw(self):
        self._draw_after_id = None
        self.delete("all")
        width = max(1, self.winfo_width())
        y_offset = 1 if self.pressed else 0
        left = COLORS["brand_hover"] if self.hover else COLORS["brand"]
        right = "#38BDF8" if self.hover else COLORS["brand_hover"]
        if not self.enabled:
            left = "#94A3B8"
            right = "#CBD5E1"
        step = 3
        for x in range(0, width, step):
            ratio = x / max(1, width - 1)
            color = self.mix(left, right, ratio)
            self.create_rectangle(x, 2 + y_offset, min(width, x + step), self.height - 2 + y_offset, outline=color, fill=color)
        self.create_text(width // 2, self.height // 2 + y_offset, text=self.text, fill="#FFFFFF", font=(FONT_FAMILY, 10, "bold"))

    @staticmethod
    def mix(a, b, ratio):
        av = tuple(int(a[i : i + 2], 16) for i in (1, 3, 5))
        bv = tuple(int(b[i : i + 2], 16) for i in (1, 3, 5))
        cv = tuple(round(av[i] + (bv[i] - av[i]) * ratio) for i in range(3))
        return f"#{cv[0]:02x}{cv[1]:02x}{cv[2]:02x}"


class OverlayScrollbar(tk.Canvas):
    def __init__(self, parent, target, command, bg):
        super().__init__(parent, width=10, highlightthickness=0, bg=bg, cursor="hand2")
        self.target = target
        self.command = command
        self.first = 0.0
        self.last = 1.0
        self.visible = False
        self.hide_job = None
        self.dragging = False
        self.drag_offset = 0
        self.bind("<Enter>", lambda _event: self.show())
        self.bind("<Leave>", lambda _event: self.schedule_hide())
        self.bind("<ButtonPress-1>", self.start_drag)
        self.bind("<B1-Motion>", self.drag)
        self.bind("<ButtonRelease-1>", self.stop_drag)
        self.bind("<Configure>", lambda _event: self.draw() if self.visible else None)

    def set(self, first, last):
        self.first = float(first)
        self.last = float(last)
        if self.visible or self.dragging:
            self.draw()

    def show(self):
        self.visible = True
        if self.hide_job:
            self.after_cancel(self.hide_job)
            self.hide_job = None
        self.draw()

    def schedule_hide(self, delay=700):
        if self.dragging:
            return
        if self.hide_job:
            self.after_cancel(self.hide_job)
        self.hide_job = self.after(delay, self.hide)

    def hide(self):
        self.visible = False
        self.draw()

    def draw(self):
        self.delete("all")
        if not self.visible or self.last - self.first >= 0.995:
            return
        height = max(1, self.winfo_height())
        thumb_h = max(36, int((self.last - self.first) * height))
        thumb_y = int(self.first * height)
        thumb_y = min(max(2, thumb_y), max(2, height - thumb_h - 2))
        color = "#64748B" if self.dragging else "#94A3B8"
        x0, x1 = 3, 8
        radius = (x1 - x0) // 2
        self.create_oval(x0, thumb_y, x1, thumb_y + radius * 2, fill=color, outline="")
        self.create_rectangle(x0, thumb_y + radius, x1, thumb_y + thumb_h - radius, fill=color, outline="")
        self.create_oval(x0, thumb_y + thumb_h - radius * 2, x1, thumb_y + thumb_h, fill=color, outline="")

    def start_drag(self, event):
        self.show()
        self.dragging = True
        height = max(1, self.winfo_height())
        thumb_h = max(36, int((self.last - self.first) * height))
        thumb_y = int(self.first * height)
        self.drag_offset = max(0, event.y - thumb_y)

    def drag(self, event):
        height = max(1, self.winfo_height())
        span = max(0.01, self.last - self.first)
        thumb_h = max(36, int(span * height))
        usable = max(1, height - thumb_h)
        fraction = (event.y - self.drag_offset) / usable
        fraction = min(max(0.0, fraction), 1.0)
        self.command("moveto", fraction)

    def stop_drag(self, _event):
        self.dragging = False
        self.schedule_hide()


def enable_high_dpi_awareness():
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def set_windows_app_id():
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except Exception:
        pass


enable_high_dpi_awareness()
set_windows_app_id()


SAMPLE_MARKDOWN = """# 欢迎使用 Markdown Viewer

这是一个本地 Windows Markdown 文本查看器。

## 打开文件

- 点击左上角的“打开文件”
- 或把 `.md`、`.markdown` 文件关联到本程序后直接双击
- 也可以把文件拖到 `launch.cmd` 上打开

## 支持的显示

- 标题目录
- 加粗、斜体、行内代码
- 引用、列表、代码块
- 搜索高亮和结果跳转

```python
print("Hello Markdown")
```

> 除非你主动使用在线翻译，否则文件内容只在本机读取。
"""


class MarkdownViewer(tk.Tk):
    def __init__(self, initial_file=None):
        super().__init__()
        self.apply_dpi_scaling()
        self.title(APP_NAME)
        self.set_window_icon()
        self.geometry("1320x820")
        self.minsize(1040, 660)
        self.configure(bg=COLORS["app_bg"])
        self.option_add("*Font", f"{{{FONT_FAMILY}}} 9")

        self.current_file = None
        self.current_markdown = ""
        self.view_mode = tk.StringVar(value="preview")
        self.search_var = tk.StringVar()
        self.search_count_var = tk.StringVar(value="0/0")
        self.file_info_var = tk.StringVar(value="未打开文件")
        self.api_key_var = tk.StringVar()
        self.model_var = tk.StringVar(value=DEEPSEEK_MODELS[0])
        self.base_url_var = tk.StringVar(value=DEEPSEEK_BASE_URL)
        self.target_language_var = tk.StringVar(value="中文（简体）")
        self.translation_quality_var = tk.StringVar(value="快速翻译")
        self.translation_scope_var = tk.StringVar(value="selection")
        self.translation_scope_display_var = tk.StringVar(value="选中翻译")
        self.follow_scroll_var = tk.BooleanVar(value=True)
        self.translation_notice_accepted = False
        self.match_ranges = []
        self.active_match = -1
        self.toc_targets = []
        self._last_headings = []
        self._embedded_images = {}
        self._link_tag_counter = 0
        self._pane_sizes_set = False
        self._sidebar_visible = True
        self._sidebar_width = 380
        self._sidebar_min_width = 246
        self._syncing_scroll = False
        self._sync_after_id = None
        self._resizing_layout = False
        self._resize_after_id = None
        self.translation_buttons = []
        self.sidebar_toggle_button = None
        self.view_menu = None
        self.translation_panel_menu = None
        self.tools_menu = None
        self.tools_sidebar_index = None
        self.search_window = None
        self.progress_total = 0
        self.progress_done = 0
        self.translation_raw_text = ""
        self.model_display_var = tk.StringVar(value=MODEL_DISPLAY[self.model_var.get()])

        self.load_settings()

        self._configure_style()
        self._build_menu()
        self._build_layout()
        self._bind_shortcuts()

        if initial_file:
            self.open_path(initial_file)
        else:
            self.show_welcome()

    def apply_dpi_scaling(self):
        try:
            dpi = self.winfo_fpixels("1i")
            self.tk.call("tk", "scaling", dpi / 72)
        except tk.TclError:
            pass

    def set_window_icon(self):
        if not ICON_PATH.exists():
            return
        try:
            self.iconbitmap(default=str(ICON_PATH))
        except tk.TclError:
            pass

    def _configure_style(self):
        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")

        style.configure("App.TFrame", background=COLORS["app_bg"])
        style.configure("Panel.TFrame", background=COLORS["panel_bg"])
        style.configure("Sidebar.TFrame", background=COLORS["sidebar_bg"])
        style.configure("Card.TFrame", background=COLORS["panel_bg"], relief=tk.FLAT)
        style.configure("Muted.TLabel", background=COLORS["panel_bg"], foreground=COLORS["muted"], font=(FONT_FAMILY, 9))
        style.configure("Title.TLabel", background=COLORS["panel_bg"], foreground=COLORS["text"], font=(FONT_FAMILY, 14, "bold"))
        style.configure("SidebarTitle.TLabel", background=COLORS["sidebar_bg"], foreground=COLORS["text"], font=(FONT_FAMILY, 12, "bold"))
        style.configure("SidebarMuted.TLabel", background=COLORS["sidebar_bg"], foreground=COLORS["muted"], font=(FONT_FAMILY, 9))
        style.configure("Toolbar.TButton", padding=(12, 7), font=(FONT_FAMILY, 9), background=COLORS["panel_bg"], foreground=COLORS["text"], bordercolor=COLORS["border"], lightcolor=COLORS["panel_bg"], darkcolor=COLORS["border"])
        style.map("Toolbar.TButton", background=[("active", COLORS["soft_blue"])], bordercolor=[("active", COLORS["brand_hover"])])
        style.configure("Primary.TButton", padding=(14, 8), font=(FONT_FAMILY, 10, "bold"), background=COLORS["brand"], foreground="#FFFFFF", bordercolor=COLORS["brand"])
        style.map("Primary.TButton", background=[("active", COLORS["brand_hover"]), ("pressed", COLORS["brand"])], foreground=[("disabled", "#E5E7EB")])
        style.configure("Mode.TRadiobutton", background=COLORS["panel_bg"], padding=(8, 4), font=(FONT_FAMILY, 9))
        style.configure("Modern.Horizontal.TProgressbar", troughcolor="#DBEAFE", bordercolor=COLORS["border"], background=COLORS["brand"], lightcolor=COLORS["brand"], darkcolor=COLORS["brand"])
        style.configure("Success.Horizontal.TProgressbar", troughcolor="#DCFCE7", bordercolor=COLORS["border"], background=COLORS["success"], lightcolor=COLORS["success"], darkcolor=COLORS["success"])

    def load_settings(self):
        path = CONFIG_PATH
        if not path.exists() and LEGACY_CONFIG_PATH.exists():
            path = LEGACY_CONFIG_PATH
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        self.target_language_var.set(data.get("target_language", self.target_language_var.get()))
        self.translation_quality_var.set(data.get("translation_quality", self.translation_quality_var.get()))
        scope = data.get("translation_scope", self.translation_scope_var.get())
        self.translation_scope_var.set(scope)
        self.translation_scope_display_var.set("全文翻译" if scope == "document" else "选中翻译")
        model = data.get("model", self.model_var.get())
        if model in DEEPSEEK_MODELS:
            self.model_var.set(model)
            self.model_display_var.set(MODEL_DISPLAY[model])
        api_key = unprotect_secret(data.get("api_key", ""))
        if api_key:
            self.api_key_var.set(api_key)

    def save_settings(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        data = {
            "model": self.model_var.get(),
            "target_language": self.target_language_var.get(),
            "translation_quality": self.translation_quality_var.get(),
            "translation_scope": self.translation_scope_var.get(),
            "api_key": protect_secret(self.api_key_var.get().strip()),
        }
        CONFIG_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _build_menu(self):
        menu = tk.Menu(self)
        file_menu = tk.Menu(menu, tearoff=False)
        file_menu.add_command(label="打开文件...", accelerator="Ctrl+O", command=self.choose_file)
        file_menu.add_command(label="示例文档", command=lambda: self.load_markdown(SAMPLE_MARKDOWN, None))
        file_menu.add_command(label="重新载入", accelerator="Ctrl+R", command=self.reload_file)
        file_menu.add_separator()
        file_menu.add_command(label="退出", accelerator="Alt+F4", command=self.destroy)

        view_menu = tk.Menu(menu, tearoff=False)
        mode_menu = tk.Menu(view_menu, tearoff=False)
        mode_menu.add_radiobutton(label="预览", variable=self.view_mode, value="preview", command=self.apply_view_mode)
        mode_menu.add_radiobutton(label="源码", variable=self.view_mode, value="source", command=self.apply_view_mode)
        mode_menu.add_radiobutton(label="分屏", variable=self.view_mode, value="split", command=self.apply_view_mode)
        search_menu = tk.Menu(view_menu, tearoff=False)
        search_menu.add_command(label="查找...", accelerator="Ctrl+F", command=self.focus_search)
        search_menu.add_command(label="上一个", command=lambda: self.activate_match(self.active_match - 1))
        search_menu.add_command(label="下一个", command=lambda: self.activate_match(self.active_match + 1))
        search_menu.add_command(label="清除搜索", command=self.clear_search)
        translation_panel_menu = tk.Menu(view_menu, tearoff=False)
        translation_panel_menu.add_command(label="隐藏翻译栏", command=self.toggle_sidebar)
        translation_panel_menu.add_command(label="同步到当前原文", command=self.sync_translation_to_active_content)
        view_menu.add_cascade(label="显示模式", menu=mode_menu)
        view_menu.add_cascade(label="搜索", menu=search_menu)
        view_menu.add_cascade(label="翻译栏", menu=translation_panel_menu)
        self.view_menu = view_menu
        self.translation_panel_menu = translation_panel_menu

        settings_menu = tk.Menu(menu, tearoff=False)
        settings_menu.add_command(label="DeepSeek API 配置...", command=self.open_settings_dialog)

        tools_menu = tk.Menu(menu, tearoff=False)
        tools_menu.add_command(label="开始翻译", accelerator="Ctrl+T", command=self.translate_current_scope)
        tools_menu.add_command(label="翻译选中文本", command=self.translate_selection)
        tools_menu.add_command(label="翻译全文", command=self.translate_document)
        tools_menu.add_separator()
        tools_menu.add_command(label="翻译选项...", command=self.open_translation_options_dialog)
        tools_menu.add_command(label="复制译文", command=self.copy_translation)
        tools_menu.add_separator()
        self.tools_sidebar_index = tools_menu.index(tk.END) + 1
        tools_menu.add_command(label="显示/隐藏翻译栏", command=self.toggle_sidebar)
        self.tools_menu = tools_menu

        help_menu = tk.Menu(menu, tearoff=False)
        help_menu.add_command(label="如何关联 Markdown 文件", command=self.show_registration_help)
        help_menu.add_command(label="关于", command=self.show_about)

        menu.add_cascade(label="文件", menu=file_menu)
        menu.add_cascade(label="视图", menu=view_menu)
        menu.add_cascade(label="设置", menu=settings_menu)
        menu.add_cascade(label="工具", menu=tools_menu)
        menu.add_cascade(label="帮助", menu=help_menu)
        self.config(menu=menu)

    def _build_layout(self):
        root = ttk.Frame(self, style="App.TFrame", padding=12)
        root.pack(fill=tk.BOTH, expand=True)

        self.shell = ttk.PanedWindow(root, orient=tk.HORIZONTAL)
        self.shell.pack(fill=tk.BOTH, expand=True)

        main = ttk.Frame(self.shell, style="Panel.TFrame")
        self.main_panel = main
        self.shell.add(main, weight=1)

        self.sidebar = ttk.Frame(self.shell, style="Sidebar.TFrame", padding=(14, 12, 14, 12), width=self._sidebar_width)
        self.shell.add(self.sidebar, weight=0)
        try:
            self.shell.pane(self.sidebar, minsize=self._sidebar_min_width)
        except tk.TclError:
            pass
        self.sidebar.pack_propagate(False)
        self._build_translation_panel(self.sidebar, in_sidebar=True)

        self.content = ttk.PanedWindow(main, orient=tk.HORIZONTAL)
        self.content.pack(fill=tk.BOTH, expand=True, padx=14, pady=(14, 12))

        self.source_frame = ttk.Frame(self.content, style="Panel.TFrame")
        self.preview_frame = ttk.Frame(self.content, style="Panel.TFrame")
        self.content.add(self.source_frame, weight=1)
        self.content.add(self.preview_frame, weight=2)

        self.source_text = tk.Text(
            self.source_frame,
            wrap=tk.NONE,
            borderwidth=1,
            relief=tk.SOLID,
            padx=14,
            pady=14,
            bg=COLORS["panel_bg"],
            fg=COLORS["text"],
            insertbackground=COLORS["brand"],
            selectbackground="#b8dcd6",
            font=("Cascadia Mono", 10),
        )
        source_x = ttk.Scrollbar(self.source_frame, orient=tk.HORIZONTAL, command=self.source_text.xview)
        self.source_scrollbar = OverlayScrollbar(self.source_frame, self.source_text, self.on_source_scrollbar, COLORS["panel_bg"])
        self.source_text.configure(yscrollcommand=self.on_source_yview, xscrollcommand=source_x.set)
        self.source_text.grid(row=0, column=0, sticky="nsew")
        self.source_scrollbar.grid(row=0, column=0, sticky="nse")
        source_x.grid(row=1, column=0, sticky="ew")
        self.source_frame.columnconfigure(0, weight=1)
        self.source_frame.rowconfigure(0, weight=1)
        self.source_text.bind("<MouseWheel>", lambda event: self.on_text_mousewheel(event, self.source_text, "translation"))
        self.source_text.bind("<Motion>", lambda event: self.on_text_motion(event, self.source_scrollbar))
        self.source_text.bind("<Leave>", lambda event: self.on_text_leave(event, self.source_scrollbar))
        # 纯预览器：源码区只读，程序内部写入时临时切回 NORMAL
        self.source_text.configure(state=tk.DISABLED)

        self.preview_text = tk.Text(
            self.preview_frame,
            wrap=tk.WORD,
            borderwidth=1,
            relief=tk.SOLID,
            padx=28,
            pady=24,
            bg=COLORS["panel_bg"],
            fg=COLORS["text"],
            selectbackground="#b8dcd6",
            font=(FONT_FAMILY, 10),
        )
        self.preview_scrollbar = OverlayScrollbar(self.preview_frame, self.preview_text, self.on_preview_scrollbar, COLORS["panel_bg"])
        self.preview_text.configure(yscrollcommand=self.on_preview_yview)
        self.preview_text.grid(row=0, column=0, sticky="nsew")
        self.preview_scrollbar.grid(row=0, column=0, sticky="nse")
        self.preview_frame.columnconfigure(0, weight=1)
        self.preview_frame.rowconfigure(0, weight=1)
        self.preview_text.configure(state=tk.DISABLED)
        self.preview_text.bind("<MouseWheel>", lambda event: self.on_text_mousewheel(event, self.preview_text, "translation"))
        self.preview_text.bind("<Motion>", lambda event: self.on_text_motion(event, self.preview_scrollbar))
        self.preview_text.bind("<Leave>", lambda event: self.on_text_leave(event, self.preview_scrollbar))

        self.status = ttk.Label(main, text="就绪", style="Muted.TLabel", anchor=tk.W, padding=(14, 6))
        self.status.pack(fill=tk.X)

        self._configure_preview_tags()
        self.apply_view_mode()
        self.shell.bind("<Configure>", self.set_initial_pane_sizes, add="+")
        self.bind("<Configure>", self.on_window_configure, add="+")

    def set_initial_pane_sizes(self, _event=None):
        if self._pane_sizes_set or self.shell.winfo_width() < 700:
            return
        try:
            self.update_idletasks()
            self.shell.sashpos(0, max(320, self.shell.winfo_width() - self._sidebar_width))
            self._pane_sizes_set = True
        except tk.TclError:
            pass

    def on_window_configure(self, event):
        if event.widget is not self:
            return
        self._resizing_layout = True
        if self._resize_after_id:
            self.after_cancel(self._resize_after_id)
        self._resize_after_id = self.after(140, self.finish_window_resize)

    def finish_window_resize(self):
        self._resizing_layout = False
        self._resize_after_id = None
        if self.follow_scroll_var.get():
            self.sync_translation_to_active_content()

    def toggle_sidebar(self):
        if self._sidebar_visible:
            self.hide_sidebar()
            return
        self.show_sidebar()

    def hide_sidebar(self):
        try:
            total = self.shell.winfo_width()
            current = self.shell.sashpos(0)
            current_width = max(0, total - current)
            if current_width >= self._sidebar_min_width:
                self._sidebar_width = current_width
            self.shell.forget(self.sidebar)
        except tk.TclError:
            return
        self._sidebar_visible = False
        self.update_sidebar_toggle_state()
        self.status.configure(text="翻译栏已隐藏")

    def show_sidebar(self):
        try:
            self.shell.add(self.sidebar, weight=0)
        except tk.TclError:
            return
        try:
            self.shell.pane(self.sidebar, minsize=self._sidebar_min_width)
        except tk.TclError:
            pass
        try:
            self.update_idletasks()
            total = self.shell.winfo_width()
            width = max(self._sidebar_min_width, self._sidebar_width)
            self.shell.sashpos(0, max(320, total - width))
        except tk.TclError:
            pass
        self._sidebar_visible = True
        self.update_sidebar_toggle_state()
        self.status.configure(text="翻译栏已显示")

    def update_sidebar_toggle_state(self):
        label = "隐藏翻译栏" if self._sidebar_visible else "显示翻译栏"
        if self.sidebar_toggle_button:
            self.sidebar_toggle_button.configure(text=label)
        if self.translation_panel_menu:
            try:
                self.translation_panel_menu.entryconfigure(0, label=label)
            except tk.TclError:
                pass
        if self.tools_menu is not None and self.tools_sidebar_index is not None:
            try:
                self.tools_menu.entryconfigure(self.tools_sidebar_index, label=label)
            except tk.TclError:
                pass

    def animate_sidebar(self, show):
        try:
            total = self.shell.winfo_width()
            current = self.shell.sashpos(0)
            self.shell.pane(self.sidebar, minsize=0 if not show else self._sidebar_min_width)
        except tk.TclError:
            return
        target_sidebar = self._sidebar_width if show else 0
        start_sidebar = max(0, total - current)
        steps = 10
        delta = (target_sidebar - start_sidebar) / steps

        def step(index=1):
            width = max(0, round(start_sidebar + delta * index))
            try:
                self.shell.sashpos(0, max(0, total - width))
            except tk.TclError:
                return
            if index < steps:
                self.after(22, lambda: step(index + 1))
            else:
                if not show:
                    try:
                        self.shell.forget(self.sidebar)
                    except tk.TclError:
                        pass
                    self._sidebar_visible = False
                    self.sidebar_toggle_button.configure(text="显示翻译栏")
                else:
                    self._sidebar_visible = True
                    self.sidebar_toggle_button.configure(text="隐藏翻译栏")
                    try:
                        self.shell.pane(self.sidebar, minsize=self._sidebar_min_width)
                    except tk.TclError:
                        pass

        step()

    def draw_follow_scroll_switch(self):
        if not hasattr(self, "follow_scroll_switch"):
            return
        self.follow_scroll_switch.draw()

    def toggle_follow_scroll(self):
        if self.follow_scroll_var.get():
            self.sync_translation_to_active_content()

    def sync_translation_scope_from_display(self):
        self.translation_scope_var.set("document" if self.translation_scope_display_var.get() == "全文翻译" else "selection")

    def sync_translation_scope_to_display(self):
        self.translation_scope_display_var.set("全文翻译" if self.translation_scope_var.get() == "document" else "选中翻译")

    def on_source_scrollbar(self, *args):
        self.source_text.yview(*args)
        self.sync_translation_to_widget(self.source_text)

    def on_preview_scrollbar(self, *args):
        self.preview_text.yview(*args)
        self.sync_translation_to_widget(self.preview_text)

    def on_source_yview(self, first, last):
        self.source_scrollbar.set(first, last)
        self.schedule_scroll_sync("translation", self.source_text)

    def on_preview_yview(self, first, last):
        self.preview_scrollbar.set(first, last)
        self.schedule_scroll_sync("translation", self.preview_text)

    def on_translation_scrollbar(self, *args):
        self.translation_text.yview(*args)
        self.sync_active_content_to_widget(self.translation_text)

    def on_translation_yview(self, first, last):
        self.translation_scrollbar.set(first, last)
        self.schedule_scroll_sync("content", self.translation_text)

    def on_text_mousewheel(self, event, widget, sync_target):
        delta = -1 * int(event.delta / 120) if event.delta else 0
        if delta:
            widget.yview_scroll(delta * 3, "units")
        try:
            first, _last = widget.yview()
        except tk.TclError:
            return "break"
        if widget is self.source_text:
            self.source_scrollbar.show()
        elif widget is self.preview_text:
            self.preview_scrollbar.show()
        elif widget is self.translation_text:
            self.translation_scrollbar.show()
        self.schedule_scroll_sync(sync_target, widget)
        return "break"

    def on_text_motion(self, event, scrollbar):
        widget_width = event.widget.winfo_width()
        if event.x >= widget_width - 28:
            scrollbar.show()
        else:
            scrollbar.schedule_hide(260)

    def on_text_leave(self, _event, scrollbar):
        scrollbar.schedule_hide(360)

    def sync_translation_to_active_content(self):
        if self.view_mode.get() == "source":
            self.sync_translation_to_widget(self.source_text)
        else:
            self.sync_translation_to_widget(self.preview_text)

    def sync_translation_to_widget(self, widget):
        self.sync_texts_by_visible_line(widget, self.translation_text)

    def sync_active_content_to_widget(self, widget):
        target = self.source_text if self.view_mode.get() == "source" else self.preview_text
        self.sync_texts_by_visible_line(widget, target)

    def schedule_scroll_sync(self, target, origin_widget):
        if self._syncing_scroll or self._resizing_layout or not self.follow_scroll_var.get():
            return
        if self._sync_after_id:
            self.after_cancel(self._sync_after_id)
        self._sync_after_id = self.after_idle(lambda: self.run_scroll_sync(target, origin_widget))

    def run_scroll_sync(self, target, origin_widget):
        self._sync_after_id = None
        if target == "translation":
            self.sync_translation_to_widget(origin_widget)
        else:
            self.sync_active_content_to_widget(origin_widget)

    def sync_translation_to_fraction(self, first):
        if self._syncing_scroll or not self.follow_scroll_var.get():
            return
        if not hasattr(self, "translation_text"):
            return
        try:
            self._syncing_scroll = True
            self.translation_text.yview_moveto(float(first))
        except tk.TclError:
            pass
        finally:
            self._syncing_scroll = False

    def sync_content_to_fraction(self, first):
        if self._syncing_scroll or not self.follow_scroll_var.get():
            return
        try:
            self._syncing_scroll = True
            target = self.source_text if self.view_mode.get() == "source" else self.preview_text
            target.yview_moveto(float(first))
        except tk.TclError:
            pass
        finally:
            self._syncing_scroll = False

    def sync_texts_by_visible_line(self, source, target):
        if self._syncing_scroll or not self.follow_scroll_var.get():
            return
        if source is target:
            return
        try:
            source_line = int(source.index("@0,0").split(".")[0])
            source_total = max(1, int(source.index("end-1c").split(".")[0]))
            target_total = max(1, int(target.index("end-1c").split(".")[0]))
            if source_total <= 1 or target_total <= 1:
                return
            ratio = (source_line - 1) / max(1, source_total - 1)
            target_line = 1 + round(ratio * (target_total - 1))
            target_line = min(max(1, target_line), target_total)
            self._syncing_scroll = True
            target.yview(f"{target_line}.0")
        except (tk.TclError, ValueError):
            pass
        finally:
            self._syncing_scroll = False

    def open_settings_dialog(self):
        if hasattr(self, "settings_window") and self.settings_window.winfo_exists():
            self.settings_window.lift()
            self.settings_window.focus_force()
            return

        window = tk.Toplevel(self)
        self.settings_window = window
        window.title("设置 - DeepSeek API")
        window.transient(self)
        window.grab_set()
        window.resizable(False, False)
        window.configure(bg=COLORS["app_bg"])
        if ICON_PATH.exists():
            try:
                window.iconbitmap(default=str(ICON_PATH))
            except tk.TclError:
                pass

        frame = ttk.Frame(window, style="Card.TFrame", padding=22)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="DeepSeek API 配置", style="Title.TLabel").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 14))

        ttk.Label(frame, text="API Key", style="Muted.TLabel").grid(row=1, column=0, sticky="w", pady=6)
        self.api_key_entry = tk.Entry(
            frame,
            width=46,
            relief=tk.FLAT,
            bg=COLORS["input_bg"],
            fg=COLORS["text"],
            insertbackground=COLORS["brand"],
            highlightthickness=1,
            highlightbackground=COLORS["border"],
            highlightcolor=COLORS["brand_hover"],
            font=(FONT_FAMILY, 10),
        )
        self.api_key_entry.grid(row=1, column=1, sticky="ew", pady=6)
        self.apply_api_key_placeholder()

        ttk.Label(frame, text="模型", style="Muted.TLabel").grid(row=2, column=0, sticky="w", pady=6)
        self.model_display_var.set(MODEL_DISPLAY.get(self.model_var.get(), MODEL_DISPLAY[DEEPSEEK_MODELS[0]]))
        self.model_combo = ttk.Combobox(
            frame,
            textvariable=self.model_display_var,
            values=list(MODEL_FROM_DISPLAY.keys()),
            width=43,
            state="readonly",
        )
        self.model_combo.grid(row=2, column=1, sticky="ew", pady=6)
        self.model_combo.bind("<<ComboboxSelected>>", lambda _event: self.sync_model_from_display())

        ttk.Label(frame, text="Base URL", style="Muted.TLabel").grid(row=3, column=0, sticky="w", pady=6)
        self.base_url_entry = ttk.Entry(frame, textvariable=self.base_url_var, width=46, state="readonly")
        self.base_url_entry.grid(row=3, column=1, sticky="ew", pady=6)

        note = ttk.Label(
            frame,
            text="保存后会写入本机配置；Windows 下 API Key 使用 DPAPI 加密保护。",
            style="Muted.TLabel",
        )
        note.grid(row=4, column=0, columnspan=2, sticky="w", pady=(10, 0))

        actions = ttk.Frame(frame, style="Panel.TFrame")
        actions.grid(row=5, column=0, columnspan=2, sticky="e", pady=(16, 0))
        self.settings_saved_label = ttk.Label(actions, text="", style="Muted.TLabel", foreground=COLORS["success"])
        self.settings_saved_label.pack(side=tk.LEFT, padx=(0, 14))
        save_button = ttk.Button(actions, text="保存", style="Primary.TButton", command=self.save_settings_from_dialog)
        save_button.pack(side=tk.RIGHT)
        ttk.Button(actions, text="关闭", style="Toolbar.TButton", command=window.destroy).pack(side=tk.RIGHT, padx=(0, 8))

        frame.columnconfigure(1, weight=1)
        window.update_idletasks()
        self.center_window(window)
        if self.api_key_var.get():
            self.api_key_entry.focus_set()

    def center_window(self, window):
        window.update_idletasks()
        width = window.winfo_width()
        height = window.winfo_height()
        x = self.winfo_rootx() + (self.winfo_width() - width) // 2
        y = self.winfo_rooty() + (self.winfo_height() - height) // 2
        window.geometry(f"+{max(0, x)}+{max(0, y)}")

    def apply_api_key_placeholder(self):
        placeholder = "请输入您的 DeepSeek API Key (sk-...)"
        self.api_key_placeholder_active = False
        if self.api_key_var.get():
            self.api_key_entry.insert(0, self.api_key_var.get())
            self.api_key_entry.configure(show="*")
        else:
            self.api_key_placeholder_active = True
            self.api_key_entry.insert(0, placeholder)
            self.api_key_entry.configure(fg=COLORS["muted"], show="", font=(FONT_FAMILY, 10, "italic"))
        self.api_key_entry.bind("<FocusIn>", lambda _event: self.clear_api_key_placeholder(placeholder))
        self.api_key_entry.bind("<FocusOut>", lambda _event: self.restore_api_key_placeholder(placeholder))

    def clear_api_key_placeholder(self, placeholder):
        if self.api_key_placeholder_active:
            self.api_key_entry.delete(0, tk.END)
            self.api_key_placeholder_active = False
            self.api_key_entry.configure(fg=COLORS["text"], show="*", font=(FONT_FAMILY, 10))

    def restore_api_key_placeholder(self, placeholder):
        if not self.api_key_entry.get():
            self.api_key_placeholder_active = True
            self.api_key_entry.insert(0, placeholder)
            self.api_key_entry.configure(fg=COLORS["muted"], show="", font=(FONT_FAMILY, 10, "italic"))

    def sync_model_from_display(self):
        self.model_var.set(MODEL_FROM_DISPLAY.get(self.model_display_var.get(), DEEPSEEK_MODELS[0]))

    def save_settings_from_dialog(self):
        key = "" if getattr(self, "api_key_placeholder_active", False) else self.api_key_entry.get().strip()
        self.api_key_var.set(key)
        self.sync_model_from_display()
        self.save_settings()
        if hasattr(self, "settings_saved_label"):
            self.settings_saved_label.configure(text="✔ 已保存")
            self.after(1500, self.clear_settings_saved_label)

    def clear_settings_saved_label(self):
        if not hasattr(self, "settings_saved_label"):
            return
        try:
            self.settings_saved_label.configure(text="")
        except tk.TclError:
            pass  # 设置窗口已关闭，标签已销毁

    def open_translation_options_dialog(self):
        if hasattr(self, "translation_options_window") and self.translation_options_window.winfo_exists():
            self.translation_options_window.lift()
            self.translation_options_window.focus_force()
            return

        window = tk.Toplevel(self)
        self.translation_options_window = window
        window.title("翻译选项")
        window.transient(self)
        window.resizable(False, False)
        window.configure(bg="#ffffff")
        if ICON_PATH.exists():
            try:
                window.iconbitmap(default=str(ICON_PATH))
            except tk.TclError:
                pass

        frame = ttk.Frame(window, style="Panel.TFrame", padding=18)
        frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frame, text="翻译选项", style="Title.TLabel").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 14))

        ttk.Label(frame, text="目标语言", style="Muted.TLabel").grid(row=1, column=0, sticky="w", pady=6)
        ttk.Combobox(
            frame,
            textvariable=self.target_language_var,
            values=list(TRANSLATION_LANGUAGES.keys()),
            width=24,
            state="readonly",
        ).grid(row=1, column=1, sticky="ew", pady=6)

        ttk.Label(frame, text="翻译范围", style="Muted.TLabel").grid(row=2, column=0, sticky="w", pady=6)
        scope_combo = ttk.Combobox(
            frame,
            textvariable=self.translation_scope_display_var,
            values=("选中翻译", "全文翻译"),
            width=24,
            state="readonly",
        )
        scope_combo.grid(row=2, column=1, sticky="ew", pady=6)
        scope_combo.bind("<<ComboboxSelected>>", lambda _event: self.sync_translation_scope_from_display())

        ttk.Label(frame, text="翻译模式", style="Muted.TLabel").grid(row=3, column=0, sticky="w", pady=6)
        ttk.Combobox(
            frame,
            textvariable=self.translation_quality_var,
            values=("快速翻译", "精翻"),
            width=24,
            state="readonly",
        ).grid(row=3, column=1, sticky="ew", pady=6)

        hint = ttk.Label(frame, text="快速翻译关闭 thinking；精翻开启 thinking。", style="Muted.TLabel")
        hint.grid(row=4, column=0, columnspan=2, sticky="w", pady=(10, 0))

        actions = ttk.Frame(frame, style="Panel.TFrame")
        actions.grid(row=5, column=0, columnspan=2, sticky="e", pady=(16, 0))
        ttk.Button(actions, text="保存并关闭", style="Primary.TButton", command=lambda: (self.save_settings(), window.destroy())).pack(side=tk.RIGHT)

        frame.columnconfigure(1, weight=1)
        window.update_idletasks()
        x = self.winfo_rootx() + 110
        y = self.winfo_rooty() + 110
        window.geometry(f"+{x}+{y}")

    def _build_translation_panel(self, parent, in_sidebar=False):
        style_name = "Sidebar.TFrame" if in_sidebar else "Panel.TFrame"
        panel = ttk.Frame(parent, style=style_name, padding=(0, 0, 0, 0) if in_sidebar else (14, 0, 14, 12))
        panel.pack(fill=tk.BOTH, expand=True)

        header = ttk.Frame(panel, style=style_name)
        header.pack(fill=tk.X)
        title_row = ttk.Frame(header, style=style_name)
        title_row.pack(fill=tk.X)
        title_row.columnconfigure(1, weight=1)

        ttk.Label(title_row, text="📖 译文", style="SidebarTitle.TLabel" if in_sidebar else "Title.TLabel").grid(row=0, column=0, sticky="w")
        self.translation_state = ttk.Label(title_row, text="未翻译", style="SidebarMuted.TLabel")
        self.translation_state.grid(row=0, column=1, sticky="w", padx=(10, 6))
        ttk.Label(title_row, text="🔗 跟随", style="SidebarMuted.TLabel").grid(row=0, column=2, sticky="e", padx=(0, 6))
        self.follow_scroll_switch = IOSSwitch(title_row, self.follow_scroll_var, command=self.toggle_follow_scroll)
        self.follow_scroll_switch.grid(row=0, column=3, sticky="e")

        mode_panel = ttk.Frame(header, style=style_name)
        mode_panel.pack(fill=tk.X, pady=(8, 0))
        scope_row = ttk.Frame(mode_panel, style=style_name)
        scope_row.pack(fill=tk.X)
        PillButton(scope_row, "选中", self.translation_scope_var, "selection", command=self.sync_translation_scope_to_display, width=76).pack(side=tk.LEFT, padx=(0, 6))
        PillButton(scope_row, "全文", self.translation_scope_var, "document", command=self.sync_translation_scope_to_display, width=76).pack(side=tk.LEFT)

        quality_row = ttk.Frame(mode_panel, style=style_name)
        quality_row.pack(fill=tk.X, pady=(5, 0))
        PillButton(quality_row, "⚡ 快速", self.translation_quality_var, "快速翻译", width=76).pack(side=tk.LEFT, padx=(0, 6))
        PillButton(quality_row, "🧠 精翻", self.translation_quality_var, "精翻", width=76).pack(side=tk.LEFT)

        self.translate_button = GradientButton(header, "翻译", self.translate_current_scope, height=40)
        self.translate_button.pack(fill=tk.X, pady=(10, 0))
        self.translation_buttons.append(self.translate_button)

        divider = ttk.Separator(panel, orient=tk.HORIZONTAL)
        divider.pack(fill=tk.X, pady=(10, 8))

        self.progress_frame = ttk.Frame(panel, style=style_name)
        self.progress_label = ttk.Label(self.progress_frame, text="", style="SidebarMuted.TLabel")
        self.progress_label.pack(fill=tk.X)
        self.translation_progress = ttk.Progressbar(self.progress_frame, orient=tk.HORIZONTAL, mode="determinate", style="Modern.Horizontal.TProgressbar")
        self.translation_progress.pack(fill=tk.X, pady=(3, 0))

        result_frame = ttk.Frame(panel, style=style_name)
        result_frame.pack(fill=tk.BOTH, expand=True, pady=(6, 0))
        self.translation_text = tk.Text(
            result_frame,
            height=12,
            wrap=tk.WORD,
            borderwidth=1,
            relief=tk.FLAT,
            padx=12,
            pady=10,
            bg=COLORS["panel_bg"],
            fg=COLORS["text"],
            selectbackground="#b8dcd6",
            font=(FONT_FAMILY, 10),
        )
        self.translation_scrollbar = OverlayScrollbar(result_frame, self.translation_text, self.on_translation_scrollbar, COLORS["panel_bg"])
        self.translation_text.configure(yscrollcommand=self.on_translation_yview)
        self.translation_text.grid(row=0, column=0, sticky="nsew")
        self.translation_scrollbar.grid(row=0, column=0, sticky="nse")
        result_frame.columnconfigure(0, weight=1)
        result_frame.rowconfigure(0, weight=1)
        self.translation_text.insert(tk.END, "选中预览或源码里的文字，然后点击“翻译选中”。")
        self.translation_text.configure(state=tk.DISABLED)
        self._build_translation_context_menu()
        self.translation_text.bind("<Button-3>", self.show_translation_context_menu)
        self.translation_text.bind("<MouseWheel>", lambda event: self.on_text_mousewheel(event, self.translation_text, "content"))
        self.translation_text.bind("<Motion>", lambda event: self.on_text_motion(event, self.translation_scrollbar))
        self.translation_text.bind("<Leave>", lambda event: self.on_text_leave(event, self.translation_scrollbar))
        header.bind("<Button-3>", self.show_translation_context_menu)

    def _build_translation_context_menu(self):
        self.translation_context_menu = tk.Menu(self, tearoff=False)
        self.translation_context_menu.add_command(label="翻译选项...", command=self.open_translation_options_dialog)
        self.translation_context_menu.add_command(label="复制译文", command=self.copy_translation)
        self.translation_context_menu.add_separator()
        self.translation_context_menu.add_command(label="隐藏翻译栏", command=self.toggle_sidebar)

    def show_translation_context_menu(self, event):
        self.translation_context_menu.tk_popup(event.x_root, event.y_root)

    def _configure_preview_tags(self):
        self.configure_markdown_tags(self.preview_text)
        self.configure_markdown_tags(self.translation_text)

    def configure_markdown_tags(self, text):
        text.tag_configure("h1", font=(FONT_FAMILY, 24, "bold"), spacing1=8, spacing3=12, foreground=COLORS["text"])
        text.tag_configure("h2", font=(FONT_FAMILY, 18, "bold"), spacing1=12, spacing3=8, foreground=COLORS["text"])
        text.tag_configure("h3", font=(FONT_FAMILY, 14, "bold"), spacing1=10, spacing3=6, foreground=COLORS["text"])
        text.tag_configure("body", font=(FONT_FAMILY, 10), spacing3=6)
        text.tag_configure("bold", font=(FONT_FAMILY, 10, "bold"))
        text.tag_configure("italic", font=(FONT_FAMILY, 10, "italic"))
        text.tag_configure("code", font=("Cascadia Mono", 10), background="#EDF2F7", foreground="#0F172A")
        text.tag_configure("codeblock", font=("Cascadia Mono", 10), background="#111827", foreground="#F8FAFC", lmargin1=14, lmargin2=14)
        text.tag_configure("quote", foreground=COLORS["muted"], background=COLORS["soft_blue"], lmargin1=16, lmargin2=16)
        text.tag_configure("bullet", lmargin1=20, lmargin2=40)
        text.tag_configure("rule", foreground="#94A3B8")
        text.tag_configure("search", background="#FFE08A")
        text.tag_configure("search_active", background="#F97316", foreground="#FFFFFF")
        text.tag_configure("welcome_title", font=(FONT_FAMILY, 28, "bold"), foreground=COLORS["text"], justify=tk.CENTER, spacing3=12)
        text.tag_configure("welcome_body", font=(FONT_FAMILY, 12), foreground=COLORS["muted"], justify=tk.CENTER, spacing3=8)

    def _bind_shortcuts(self):
        self.bind("<Control-o>", lambda _event: self.choose_file())
        self.bind("<Control-r>", lambda _event: self.reload_file())
        self.bind("<Control-f>", lambda _event: self.focus_search())
        self.bind("<Control-t>", lambda _event: self.translate_current_scope())
        self.search_var.trace_add("write", lambda *_args: self.update_search())

    def focus_search(self):
        if self.search_window and self.search_window.winfo_exists():
            self.search_window.lift()
            self.search_window.focus_force()
            self.search_entry.focus_set()
            self.search_entry.select_range(0, tk.END)
            return

        window = tk.Toplevel(self)
        self.search_window = window
        window.title("搜索")
        window.transient(self)
        window.resizable(False, False)
        window.configure(bg=COLORS["app_bg"])
        if ICON_PATH.exists():
            try:
                window.iconbitmap(default=str(ICON_PATH))
            except tk.TclError:
                pass

        frame = ttk.Frame(window, style="Card.TFrame", padding=16)
        frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frame, text="搜索正文", style="Muted.TLabel").grid(row=0, column=0, sticky="w", columnspan=4)
        self.search_entry = ttk.Entry(frame, textvariable=self.search_var, width=34)
        self.search_entry.grid(row=1, column=0, sticky="ew", pady=(8, 0), columnspan=4)
        ttk.Button(frame, text="上一个", style="Toolbar.TButton", command=lambda: self.activate_match(self.active_match - 1)).grid(
            row=2, column=0, sticky="ew", pady=(10, 0)
        )
        ttk.Button(frame, text="下一个", style="Toolbar.TButton", command=lambda: self.activate_match(self.active_match + 1)).grid(
            row=2, column=1, sticky="ew", padx=(8, 0), pady=(10, 0)
        )
        ttk.Button(frame, text="清除", style="Toolbar.TButton", command=self.clear_search).grid(row=2, column=2, sticky="ew", padx=(8, 0), pady=(10, 0))
        ttk.Label(frame, textvariable=self.search_count_var, style="Muted.TLabel", width=8, anchor=tk.CENTER).grid(
            row=2, column=3, sticky="ew", padx=(8, 0), pady=(10, 0)
        )
        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)
        frame.columnconfigure(2, weight=1)
        self.search_entry.focus_set()
        self.search_entry.select_range(0, tk.END)
        window.bind("<Escape>", lambda _event: window.destroy())
        window.bind("<Return>", lambda _event: self.activate_match(self.active_match + 1))
        window.protocol("WM_DELETE_WINDOW", window.destroy)
        window.update_idletasks()
        x = self.winfo_rootx() + 220
        y = self.winfo_rooty() + 120
        window.geometry(f"+{x}+{y}")

    def clear_search(self):
        self.search_var.set("")
        self.update_search()

    def choose_file(self):
        filename = filedialog.askopenfilename(title="打开 Markdown 文件", filetypes=SUPPORTED_TYPES)
        if filename:
            self.open_path(filename)

    def open_path(self, filename):
        path = Path(filename)
        if not path.exists():
            messagebox.showerror(APP_NAME, f"找不到文件：\n{path}")
            return
        try:
            data = path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            data = path.read_text(encoding="gb18030", errors="replace")
        except OSError as exc:
            messagebox.showerror(APP_NAME, f"无法打开文件：\n{exc}")
            return
        self.load_markdown(data, path)

    def load_markdown(self, markdown, path):
        self.current_file = path
        self.current_markdown = markdown
        self.source_text.configure(state=tk.NORMAL)
        self.source_text.delete("1.0", tk.END)
        self.source_text.insert("1.0", markdown)
        self.source_text.configure(state=tk.DISABLED)
        self.render_preview()
        self.update_header()

    def show_welcome(self):
        self.current_file = None
        self.current_markdown = ""
        self.source_text.configure(state=tk.NORMAL)
        self.source_text.delete("1.0", tk.END)
        self.source_text.configure(state=tk.DISABLED)
        self.toc_targets = []
        self.file_info_var.set("未打开文件")
        self.status.configure(text="提示：点击“打开文件”，或先运行注册脚本后双击 .md 文件。")
        self.preview_text.configure(state=tk.NORMAL)
        self.preview_text.delete("1.0", tk.END)
        self.preview_text.insert(tk.END, "\n\n打开一个 Markdown 文件\n", ("welcome_title",))
        self.preview_text.insert(
            tk.END,
            "通过“文件 > 打开文件”载入 Markdown，或安装/关联后直接双击 Markdown 文件。\n\n"
            "你也可以从“文件 > 示例文档”先看界面效果。",
            ("welcome_body",),
        )
        self.preview_text.configure(state=tk.DISABLED)

    def reload_file(self):
        if not self.current_file:
            self.show_welcome()
            return
        self.open_path(self.current_file)

    def update_header(self):
        if self.current_file:
            size = self.current_file.stat().st_size if self.current_file.exists() else 0
            self.file_info_var.set(f"{self.current_file.name}  {self.current_file.parent}")
            self.status.configure(text=f"已打开：{self.current_file}    {max(1, round(size / 1024))} KB")
            self.title(f"{self.current_file.name} - {APP_NAME}")
        else:
            self.file_info_var.set("示例文档")
            self.status.configure(text="正在查看示例文档")
            self.title(APP_NAME)

    def apply_view_mode(self):
        panes = self.content.panes()
        for pane in panes:
            self.content.forget(pane)

        mode = self.view_mode.get()
        if mode == "source":
            self.content.add(self.source_frame, weight=1)
        elif mode == "split":
            self.content.add(self.source_frame, weight=1)
            self.content.add(self.preview_frame, weight=2)
        else:
            self.content.add(self.preview_frame, weight=1)

    def render_preview(self):
        headings = self.render_markdown_into(self.preview_text, self.current_markdown)
        self.toc_targets = [index for _level, _title, index in headings]
        self._last_headings = headings
        self.update_search()

    def render_markdown_into(self, text_widget, markdown):
        text_widget.configure(state=tk.NORMAL)
        text_widget.delete("1.0", tk.END)
        self._embedded_images.setdefault(text_widget, []).clear()

        lines = markdown.replace("\r\n", "\n").split("\n")
        in_code = False
        code_language = ""
        headings = []

        for raw_line in lines:
            line = raw_line.rstrip()
            stripped = line.strip()

            if stripped.startswith("```"):
                in_code = not in_code
                code_language = stripped[3:].strip() if in_code else ""
                if in_code and code_language:
                    self._insert_plain(text_widget, f"{code_language}\n", ("code",))
                else:
                    self._insert_plain(text_widget, "\n", ("body",))
                continue

            if in_code:
                self._insert_plain(text_widget, line + "\n", ("codeblock",))
                continue

            if not stripped:
                self._insert_plain(text_widget, "\n", ("body",))
                continue

            image_match = IMAGE_LINE_PATTERN.match(stripped)
            if image_match:
                self._insert_image_line(text_widget, image_match.group(1), image_match.group(2))
                continue

            heading = re.match(r"^(#{1,6})\s+(.+?)\s*#*$", stripped)
            if heading:
                level = min(len(heading.group(1)), 3)
                title = heading.group(2).strip()
                index = text_widget.index(tk.INSERT)
                self._insert_inline(text_widget, title + "\n", (f"h{level}",))
                headings.append((level, title, index))
                continue

            if re.match(r"^(-{3,}|\*{3,}|_{3,})$", stripped):
                self._insert_plain(text_widget, "────────────────────────\n", ("rule",))
                continue

            if stripped.startswith(">"):
                self._insert_inline(text_widget, stripped.lstrip("> ").strip() + "\n", ("quote",))
                continue

            list_match = re.match(r"^\s*(([-*+])|(\d+\.))\s+(.+)$", line)
            if list_match:
                marker = list_match.group(1)
                content = list_match.group(4)
                prefix = f"{marker} "
                self._insert_plain(text_widget, prefix, ("bullet",))
                self._insert_inline(text_widget, content + "\n", ("bullet",))
                continue

            if "|" in stripped and stripped.count("|") >= 2:
                self._insert_plain(text_widget, stripped + "\n", ("code",))
                continue

            self._insert_inline(text_widget, stripped + "\n", ("body",))

        text_widget.configure(state=tk.DISABLED)
        return headings

    def _insert_plain(self, text_widget, value, tags=()):
        text_widget.insert(tk.END, value, tags)

    def _insert_inline(self, text_widget, value, base_tags=()):
        position = 0
        for match in INLINE_LINK_PATTERN.finditer(value):
            if match.start() > position:
                self._insert_plain_with_links(text_widget, value[position : match.start()], base_tags)
            token = match.group(0)
            tags = base_tags
            text = token
            if token.startswith("`"):
                text = token[1:-1]
                tags = base_tags + ("code",)
            elif token.startswith(("**", "__")):
                text = token[2:-2]
                tags = base_tags + ("bold",)
            elif token.startswith(("*", "_")):
                text = token[1:-1]
                tags = base_tags + ("italic",)
            elif token.startswith("["):
                text, url = self._parse_inline_link(token)
                tags = base_tags + (self._create_link_tag(text_widget, url),)
            text_widget.insert(tk.END, text, tags)
            position = match.end()
        if position < len(value):
            self._insert_plain_with_links(text_widget, value[position:], base_tags)

    def _insert_plain_with_links(self, text_widget, value, base_tags):
        """插入纯文本片段，并把裸 http(s) 链接变成可点击链接。"""
        position = 0
        for match in BARE_URL_PATTERN.finditer(value):
            if match.start() > position:
                text_widget.insert(tk.END, value[position : match.start()], base_tags)
            url = match.group(0).rstrip(".,;!?，。；！？")
            text_widget.insert(tk.END, url, base_tags + (self._create_link_tag(text_widget, url),))
            position = match.end()
        if position < len(value):
            text_widget.insert(tk.END, value[position:], base_tags)

    def _parse_inline_link(self, token):
        close = token.find("]")
        text = token[1:close]
        url = token[close + 2 : -1].strip()
        if re.search(r"\s", url):
            url = re.split(r"\s+", url, maxsplit=1)[0]
        return text, url

    def _create_link_tag(self, text_widget, url):
        self._link_tag_counter += 1
        tag = f"link_{self._link_tag_counter}"
        text_widget.tag_configure(tag, foreground=COLORS["brand"], underline=True)
        text_widget.tag_bind(tag, "<Button-1>", lambda _event, u=url: self._open_markdown_link(u))
        text_widget.tag_bind(tag, "<Enter>", lambda _event: text_widget.configure(cursor="hand2"))
        text_widget.tag_bind(tag, "<Leave>", lambda _event: text_widget.configure(cursor=""))
        return tag

    def _open_markdown_link(self, url):
        url = url.strip()
        if not url:
            return
        if url.startswith("#"):
            self._jump_to_anchor(url[1:])
            return
        if "://" not in url and not url.lower().startswith(("mailto:", "tel:")):
            path = self._resolve_local_path(url)
            if path is not None:
                self.open_path(path)
                return
        try:
            os.startfile(url)
        except OSError as exc:
            messagebox.showerror(APP_NAME, f"无法打开链接：\n{url}\n\n{exc}")

    def _jump_to_anchor(self, anchor):
        wanted = re.sub(r"[^a-zA-Z0-9一-鿿]+", "", anchor.lower())
        for _level, title, index in self._last_headings:
            candidate = re.sub(r"[^a-zA-Z0-9一-鿿]+", "", title.lower())
            if candidate == wanted:
                self.preview_text.see(index)
                break

    def _resolve_local_path(self, src):
        src = src.strip().strip('<>"')
        if not src or "://" in src or src.lower().startswith(("data:", "mailto:", "tel:")):
            return None
        base = self.current_file.parent if self.current_file else APP_DIR
        path = Path(src)
        if not path.is_absolute():
            path = base / path
        return path if path.exists() else None

    def _load_embedded_image(self, src):
        """加载本地图片为 tk.PhotoImage（PNG/GIF 等 Tk 原生格式），超出最大尺寸按整数倍缩小；失败返回 None。"""
        path = self._resolve_local_path(src)
        if path is None:
            return None
        try:
            photo = tk.PhotoImage(file=str(path))
        except (tk.TclError, OSError):
            return None
        max_width, max_height = 600, 480
        width, height = photo.width(), photo.height()
        factor = max((width + max_width - 1) // max_width, (height + max_height - 1) // max_height)
        if factor > 1:
            photo = photo.subsample(factor, factor)
        return photo

    def _insert_image_line(self, text_widget, alt, src):
        photo = self._load_embedded_image(src)
        if photo is not None:
            self._embedded_images.setdefault(text_widget, []).append(photo)
            text_widget.image_create(tk.END, image=photo)
            self._insert_plain(text_widget, "\n", ("body",))
        else:
            self._insert_inline(text_widget, f"🖼 {alt or '图片'}\n", ("quote",))

    def jump_to_heading(self, _event):
        if not hasattr(self, "toc_list"):
            return
        selection = self.toc_list.curselection()
        if not selection:
            return
        index = selection[0]
        if index >= len(self.toc_targets):
            return
        target = self.toc_targets[index]
        self.preview_text.see(target)

    def update_search(self):
        self.preview_text.configure(state=tk.NORMAL)
        self.preview_text.tag_remove("search", "1.0", tk.END)
        self.preview_text.tag_remove("search_active", "1.0", tk.END)
        self.match_ranges = []
        self.active_match = -1

        query = self.search_var.get()
        if query:
            start = "1.0"
            while True:
                index = self.preview_text.search(query, start, tk.END, nocase=True)
                if not index:
                    break
                end = f"{index}+{len(query)}c"
                self.preview_text.tag_add("search", index, end)
                self.match_ranges.append((index, end))
                start = end

        self.preview_text.configure(state=tk.DISABLED)
        if self.match_ranges:
            self.activate_match(0)
        else:
            self.search_count_var.set("0/0")

    def activate_match(self, index):
        if not self.match_ranges:
            self.search_count_var.set("0/0")
            return
        self.preview_text.configure(state=tk.NORMAL)
        self.preview_text.tag_remove("search_active", "1.0", tk.END)
        self.active_match = index % len(self.match_ranges)
        start, end = self.match_ranges[self.active_match]
        self.preview_text.tag_add("search_active", start, end)
        self.preview_text.see(start)
        self.preview_text.configure(state=tk.DISABLED)
        self.search_count_var.set(f"{self.active_match + 1}/{len(self.match_ranges)}")
        self.status.configure(text=f"搜索：{self.search_var.get()}    {self.search_count_var.get()}")

    def get_selected_text(self):
        for widget in (self.preview_text, self.source_text):
            try:
                ranges = widget.tag_ranges(tk.SEL)
                if ranges:
                    return widget.get(ranges[0], ranges[1]).strip()
            except tk.TclError:
                continue
        return ""

    def translate_selection(self):
        text = self.get_selected_text()
        if not text:
            messagebox.showinfo(APP_NAME, "请先在预览或源码中选中要翻译的文字。")
            return
        self.start_translation(text, "选中文本")

    def translate_document(self):
        text = self.source_text.get("1.0", "end-1c").strip() or self.current_markdown.strip()
        if not text:
            messagebox.showinfo(APP_NAME, "请先打开一个 Markdown 文件。")
            return
        if len(text) > 12000:
            ok = messagebox.askyesno(APP_NAME, "全文较长，翻译会分段发送并可能需要更久。是否继续？")
            if not ok:
                return
        self.start_translation(text, "全文")

    def translate_current_scope(self):
        if self.translation_scope_var.get() == "document":
            self.translate_document()
        else:
            self.translate_selection()

    def start_translation(self, text, source_label):
        api_key = self.api_key_var.get().strip()
        if not api_key:
            messagebox.showinfo(APP_NAME, "请先在“设置 > DeepSeek API 配置”里填写 DeepSeek API Key。")
            self.open_settings_dialog()
            return
        if not api_key.startswith("sk-"):
            ok = messagebox.askyesno(APP_NAME, "API Key 通常以 sk- 开头。当前格式看起来不太像，仍要继续吗？")
            if not ok:
                self.open_settings_dialog()
                return

        if not self.translation_notice_accepted:
            ok = messagebox.askokcancel(
                APP_NAME,
                "翻译会把待翻译文本发送到 DeepSeek API。\n\n"
                "选中翻译不会在侧边栏重复展示原文，只会显示译文。是否继续？",
            )
            if not ok:
                return
            self.translation_notice_accepted = True

        target_label = self.target_language_var.get()
        target_language = TRANSLATION_LANGUAGES.get(target_label, "zh-CN")
        model = self.model_var.get()
        quality = self.translation_quality_var.get()
        chunks = self.split_translation_chunks(text)
        self.set_translation_text(f"正在使用 DeepSeek {quality}...")
        self.translation_state.configure(text=f"{source_label} - {quality} - {model}")
        self.status.configure(text="正在翻译，界面仍可继续浏览文档。")
        self.show_translation_progress(len(chunks))
        self.set_translation_buttons_state(tk.DISABLED)

        worker = threading.Thread(
            target=self.translation_worker,
            args=(chunks, target_language, target_label, api_key, model, quality),
            daemon=True,
        )
        worker.start()

    def translation_worker(self, chunks, target_language, target_label, api_key, model, quality):
        try:
            translated = self.translate_online(chunks, target_language, target_label, api_key, model, quality)
        except Exception as exc:
            error = str(exc)
            self.after(0, lambda error=error: self.finish_translation_error(error))
            return
        self.after(0, lambda: self.finish_translation_success(translated, target_label))

    def translate_online(self, chunks, target_language, target_label, api_key, model, quality):
        if len(chunks) == 1:
            result = self.translate_chunk(chunks[0], target_language, target_label, api_key, model, quality)
            self.after(0, lambda: self.update_translation_progress(1, 1))
            return result

        translated_chunks = [None] * len(chunks)
        model_parallelism = 12 if model == "deepseek-v4-flash" else 4
        max_workers = min(model_parallelism, len(chunks))
        done = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(self.translate_chunk, chunk, target_language, target_label, api_key, model, quality): index
                for index, chunk in enumerate(chunks)
            }
            for future in concurrent.futures.as_completed(futures):
                translated_chunks[futures[future]] = future.result()
                done += 1
                self.after(0, lambda done=done, total=len(chunks): self.update_translation_progress(done, total))
        return "".join(translated_chunks).strip()

    def split_translation_chunks(self, text, limit=5000):
        """按 Markdown 结构边界分块：段落/标题/列表/引用整块切，代码围栏整块保留。

        只有单个块超过上限（如超长代码块）才按行硬拆，避免常见文档的
        段落、表格、代码块被拦腰截断导致译文结构损坏。
        """
        blocks = self._split_markdown_blocks(text)
        chunks = []
        current = ""
        for block in blocks:
            if len(current) + len(block) <= limit:
                current += block
                continue
            if current:
                chunks.append(current)
                current = ""
            if len(block) <= limit:
                current = block
                continue
            # 单块超限：按行拆，行保持完整
            piece = ""
            for line in block.split("\n"):
                if len(piece) + len(line) + 1 > limit and piece:
                    chunks.append(piece)
                    piece = ""
                piece += line + "\n"
            if piece:
                chunks.append(piece)
        if current:
            chunks.append(current)
        return chunks or [text]

    def _split_markdown_blocks(self, text):
        """把 Markdown 切成结构块：代码围栏整块保留，其余按空行分段。"""
        blocks = []
        current = []
        in_fence = False
        for raw_line in text.split("\n"):
            stripped = raw_line.strip()
            if stripped.startswith("```"):
                in_fence = not in_fence
                current.append(raw_line)
                if not in_fence:
                    blocks.append("\n".join(current) + "\n")
                    current = []
                continue
            if in_fence:
                current.append(raw_line)
                continue
            if not stripped:
                if current:
                    blocks.append("\n".join(current) + "\n\n")
                    current = []
                continue
            current.append(raw_line)
        if current:
            blocks.append("\n".join(current) + "\n")
        return blocks

    def translate_chunk(self, text, target_language, target_label, api_key, model, quality):
        mode = TRANSLATION_QUALITY_MODES.get(quality, TRANSLATION_QUALITY_MODES["快速翻译"])
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": mode["system"]},
                {
                    "role": "user",
                    "content": (
                        f"Translate the following Markdown/text into {target_label} ({target_language}). "
                        "Return only the translation. Preserve Markdown syntax, heading levels, list markers, blockquotes, "
                        "tables, code fences, inline code, links, and original line breaks. Translate only human-readable prose; "
                        "do not translate code, URLs, file paths, or Markdown control characters.\n\n"
                        f"{text}"
                    ),
                },
            ],
            "thinking": {"type": mode["thinking"]},
        }
        if mode["temperature"] is not None:
            payload["temperature"] = mode["temperature"]
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            f"{DEEPSEEK_BASE_URL}/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": "MarkdownViewer/1.0",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=18) as response:
                payload = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"DeepSeek API HTTP {exc.code}: {detail}") from exc
        data = json.loads(payload)
        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError("DeepSeek API 没有返回 choices。")
        message = choices[0].get("message") or {}
        content = message.get("content", "")
        if not content:
            raise RuntimeError("DeepSeek API 返回了空译文。")
        return content

    def finish_translation_success(self, translated, target_label):
        self.set_translation_text(translated or "没有返回译文。")
        self.translation_state.configure(text=f"已翻译为{target_label}")
        self.status.configure(text="翻译完成")
        self.complete_translation_progress()
        self.set_translation_buttons_state(tk.NORMAL)

    def finish_translation_error(self, exc):
        self.set_translation_text(f"翻译失败：{exc}")
        self.translation_state.configure(text="翻译失败")
        self.status.configure(text="翻译失败，请检查网络连接后重试。")
        self.hide_translation_progress()
        self.set_translation_buttons_state(tk.NORMAL)

    def set_translation_text(self, value):
        self.translation_raw_text = value
        self.render_markdown_into(self.translation_text, value)
        self.fade_translation_result()

    def show_translation_progress(self, total):
        self.progress_total = total
        self.progress_done = 0
        self.progress_frame.pack(fill=tk.X, before=self.translation_text.master, pady=(0, 6))
        if total <= 1:
            self.progress_label.configure(text="翻译中...")
            self.translation_progress.configure(mode="indeterminate", style="Modern.Horizontal.TProgressbar")
            self.translation_progress.start(12)
        else:
            self.translation_progress.stop()
            self.translation_progress.configure(mode="determinate", maximum=total, value=0, style="Modern.Horizontal.TProgressbar")
            self.progress_label.configure(text=f"正在翻译 第 0/{total} 段")

    def update_translation_progress(self, done, total):
        self.progress_done = done
        self.progress_total = total
        if total <= 1:
            self.progress_label.configure(text="翻译中...")
            return
        self.translation_progress.configure(value=done)
        self.progress_label.configure(text=f"正在翻译 第 {done}/{total} 段")

    def complete_translation_progress(self):
        self.translation_progress.stop()
        self.translation_progress.configure(mode="determinate", style="Success.Horizontal.TProgressbar")
        total = max(1, self.progress_total)
        self.translation_progress.configure(maximum=total, value=total)
        self.progress_label.configure(text="翻译完成")
        self.after(1500, self.hide_translation_progress)

    def hide_translation_progress(self):
        if hasattr(self, "progress_frame"):
            self.translation_progress.stop()
            self.progress_frame.pack_forget()

    def fade_translation_result(self, step=0):
        colors = ("#EFF6FF", "#F8FBFF", COLORS["panel_bg"])
        color = colors[min(step, len(colors) - 1)]
        self.translation_text.configure(bg=color)
        if step < len(colors) - 1:
            self.after(55, lambda: self.fade_translation_result(step + 1))

    def copy_translation(self):
        text = self.translation_raw_text.strip() or self.translation_text.get("1.0", "end-1c").strip()
        if not text:
            return
        self.clipboard_clear()
        self.clipboard_append(text)
        self.status.configure(text="译文已复制到剪贴板")

    def set_translation_buttons_state(self, state):
        for button in self.translation_buttons:
            if hasattr(button, "set_enabled"):
                button.set_enabled(state != tk.DISABLED)
            else:
                button.configure(state=state)

    def show_registration_help(self):
        app_dir = Path(__file__).resolve().parent
        messagebox.showinfo(
            APP_NAME,
            "在 PowerShell 中运行：\n\n"
            f'powershell -ExecutionPolicy Bypass -File "{app_dir / "register-file-association.ps1"}"\n\n'
            "之后双击 .md / .markdown 文件就会用本查看器打开。",
        )

    def show_about(self):
        messagebox.showinfo(APP_NAME, f"{APP_NAME}\n本地 Markdown 文本查看器。")


def parse_args():
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("file", nargs="?", help="要打开的 Markdown 文件")
    return parser.parse_args()


def main():
    args = parse_args()
    app = MarkdownViewer(args.file)
    app.mainloop()


if __name__ == "__main__":
    main()
