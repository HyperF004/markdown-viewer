import argparse
import ctypes
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import winreg
import zipfile
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
import tkinter as tk


APP_NAME = "CUBE18 Markdown Viewer"
APP_EXE = "CUBE18MarkdownViewer.exe"
APP_ID = "CUBE18.MarkdownViewer"
PROG_ID = "CUBE18MarkdownViewer.Document"
PUBLISHER = "CUBE18"
VERSION = "1.0.0"
MARKER_FILE = ".cube18-markdown-viewer-install"
EXTENSIONS = (".md", ".markdown", ".mdown", ".mkd")

COLORS = {
    "app": "#F6F8FA",
    "panel": "#FFFFFF",
    "sidebar": "#EFF6FF",
    "border": "#E2E8F0",
    "brand": "#2563EB",
    "brand_hover": "#0EA5E9",
    "text": "#111827",
    "muted": "#64748B",
    "success": "#16A34A",
    "danger": "#DC2626",
}


def resource_path(name):
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / name


def default_install_dir():
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Programs" / APP_NAME


def start_menu_shortcut_path():
    return Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "CUBE18" / f"{APP_NAME}.lnk"


def desktop_shortcut_path():
    return Path(os.path.join(os.environ["USERPROFILE"], "Desktop")) / f"{APP_NAME}.lnk"


def set_reg_default(path, value):
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, value)


def set_reg_string(path, name, value):
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)


def set_reg_dword(path, name, value):
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, name, 0, winreg.REG_DWORD, int(value))


def set_reg_binary(path, name):
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, name, 0, winreg.REG_BINARY, b"")


def delete_reg_tree(root, subkey):
    try:
        with winreg.OpenKey(root, subkey, 0, winreg.KEY_READ | winreg.KEY_WRITE) as key:
            while True:
                try:
                    child = winreg.EnumKey(key, 0)
                except OSError:
                    break
                delete_reg_tree(root, f"{subkey}\\{child}")
        winreg.DeleteKey(root, subkey)
    except FileNotFoundError:
        pass


def shell_notify():
    try:
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)
    except Exception:
        pass


def run_powershell(script):
    creationflags = 0
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        creationflags = subprocess.CREATE_NO_WINDOW
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        text=True,
        capture_output=True,
        creationflags=creationflags,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "PowerShell command failed").strip())


def ps_quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def create_shortcut(shortcut_path, target_path, working_dir):
    shortcut_path = Path(shortcut_path)
    shortcut_path.parent.mkdir(parents=True, exist_ok=True)
    script = f"""
$Shell = New-Object -ComObject WScript.Shell
$Shortcut = $Shell.CreateShortcut({ps_quote(shortcut_path)})
$Shortcut.TargetPath = {ps_quote(target_path)}
$Shortcut.WorkingDirectory = {ps_quote(working_dir)}
$Shortcut.IconLocation = {ps_quote(str(target_path) + ",0")}
$Shortcut.Description = 'Open and translate Markdown documents.'
$Shortcut.Save()
"""
    run_powershell(script)


def stop_running_app():
    script = "Get-Process -Name 'CUBE18MarkdownViewer' -ErrorAction SilentlyContinue | Stop-Process -Force"
    run_powershell(script)


def safe_clear_install_dir(install_dir):
    install_dir = Path(install_dir)
    if not install_dir.exists():
        install_dir.mkdir(parents=True, exist_ok=True)
        return

    marker = install_dir / MARKER_FILE
    app_exe = install_dir / APP_EXE
    if marker.exists() or app_exe.exists():
        for item in install_dir.iterdir():
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
        return

    # Avoid wiping an arbitrary user-selected folder. Install into a child directory instead.
    child = install_dir / APP_NAME
    child.mkdir(parents=True, exist_ok=True)
    return child


def write_uninstall_script(install_dir):
    script = r'''
$ErrorActionPreference = "SilentlyContinue"
$AppName = "CUBE18 Markdown Viewer"
$ProgId = "CUBE18MarkdownViewer.Document"
$Extensions = @(".md", ".markdown", ".mdown", ".mkd")
$InstallDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$StartMenuShortcut = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\CUBE18\CUBE18 Markdown Viewer.lnk"
$DesktopShortcut = Join-Path ([Environment]::GetFolderPath("DesktopDirectory")) "CUBE18 Markdown Viewer.lnk"

Remove-Item -Path $StartMenuShortcut -Force
Remove-Item -Path $DesktopShortcut -Force
Remove-Item -Path "HKCU:\Software\Classes\$ProgId" -Recurse -Force
Remove-Item -Path "HKCU:\Software\CUBE18MarkdownViewer" -Recurse -Force
Remove-ItemProperty -Path "HKCU:\Software\RegisteredApplications" -Name $AppName -Force

foreach ($Extension in $Extensions) {
    $ExtPath = "HKCU:\Software\Classes\$Extension"
    $DefaultValue = (Get-Item -Path $ExtPath).GetValue("")
    if ($DefaultValue -eq $ProgId) {
        Remove-ItemProperty -Path $ExtPath -Name "" -Force
    }
    Remove-ItemProperty -Path "$ExtPath\OpenWithProgids" -Name $ProgId -Force
    Remove-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts\$Extension\OpenWithProgids" -Name $ProgId -Force
    Remove-Item -Path "HKCU:\Software\Classes\SystemFileAssociations\$Extension\shell\CUBE18MarkdownViewer" -Recurse -Force
}

Remove-Item -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\CUBE18MarkdownViewer" -Recurse -Force

Add-Type -Namespace Win32 -Name ShellNotify -MemberDefinition @"
[System.Runtime.InteropServices.DllImport("shell32.dll")]
public static extern void SHChangeNotify(int wEventId, uint uFlags, System.IntPtr dwItem1, System.IntPtr dwItem2);
"@
[Win32.ShellNotify]::SHChangeNotify(0x08000000, 0, [IntPtr]::Zero, [IntPtr]::Zero)

Start-Process -WindowStyle Hidden -FilePath "cmd.exe" -ArgumentList "/c timeout /t 2 /nobreak >nul & rmdir /s /q `"$InstallDir`""
'''
    (Path(install_dir) / "uninstall.ps1").write_text(script, encoding="utf-8")


def register_file_associations(install_dir):
    exe_path = Path(install_dir) / APP_EXE
    icon_value = f'"{exe_path}",0'
    open_command = f'"{exe_path}" "%1"'
    capabilities_path = r"Software\CUBE18MarkdownViewer\Capabilities"

    set_reg_default(rf"Software\Classes\{PROG_ID}", "Markdown Viewer Document")
    set_reg_string(rf"Software\Classes\{PROG_ID}", "FriendlyTypeName", "Markdown Viewer Document")
    set_reg_string(rf"Software\Classes\{PROG_ID}", "AppUserModelID", APP_ID)
    set_reg_default(rf"Software\Classes\{PROG_ID}\DefaultIcon", icon_value)
    set_reg_default(rf"Software\Classes\{PROG_ID}\shell", "open")
    set_reg_default(rf"Software\Classes\{PROG_ID}\shell\open", "用 Markdown Viewer 打开")
    set_reg_default(rf"Software\Classes\{PROG_ID}\shell\open\command", open_command)
    set_reg_string(rf"Software\Classes\{PROG_ID}\Application", "ApplicationName", APP_NAME)
    set_reg_string(rf"Software\Classes\{PROG_ID}\Application", "ApplicationIcon", icon_value)
    set_reg_string(rf"Software\Classes\{PROG_ID}\Application", "AppUserModelID", APP_ID)

    set_reg_string(r"Software\CUBE18MarkdownViewer\Capabilities", "ApplicationName", APP_NAME)
    set_reg_string(r"Software\CUBE18MarkdownViewer\Capabilities", "ApplicationDescription", "Open and translate Markdown documents.")
    set_reg_string(r"Software\CUBE18MarkdownViewer\Capabilities", "ApplicationIcon", icon_value)
    for ext in EXTENSIONS:
        set_reg_string(r"Software\CUBE18MarkdownViewer\Capabilities\FileAssociations", ext, PROG_ID)
    set_reg_string(r"Software\RegisteredApplications", APP_NAME, capabilities_path)

    for ext in EXTENSIONS:
        set_reg_default(rf"Software\Classes\{ext}", PROG_ID)
        set_reg_string(rf"Software\Classes\{ext}", "Content Type", "text/markdown")
        set_reg_string(rf"Software\Classes\{ext}", "PerceivedType", "text")
        set_reg_binary(rf"Software\Classes\{ext}\OpenWithProgids", PROG_ID)
        set_reg_binary(rf"Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts\{ext}\OpenWithProgids", PROG_ID)

        menu_path = rf"Software\Classes\SystemFileAssociations\{ext}\shell\CUBE18MarkdownViewer"
        set_reg_default(menu_path, "用 Markdown Viewer 打开")
        set_reg_string(menu_path, "Icon", icon_value)
        set_reg_default(rf"{menu_path}\command", open_command)

    shell_notify()


def register_uninstall(install_dir):
    install_dir = Path(install_dir)
    exe_path = install_dir / APP_EXE
    size_kb = sum(p.stat().st_size for p in install_dir.rglob("*") if p.is_file()) // 1024
    key = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\CUBE18MarkdownViewer"
    set_reg_string(key, "DisplayName", APP_NAME)
    set_reg_string(key, "DisplayVersion", VERSION)
    set_reg_string(key, "Publisher", PUBLISHER)
    set_reg_string(key, "InstallLocation", str(install_dir))
    set_reg_string(key, "DisplayIcon", f'"{exe_path}",0')
    set_reg_string(key, "UninstallString", f'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "{install_dir / "uninstall.ps1"}"')
    set_reg_dword(key, "NoModify", 1)
    set_reg_dword(key, "NoRepair", 1)
    set_reg_dword(key, "EstimatedSize", int(size_kb))


def install_app(install_dir, desktop_shortcut=True, start_menu_shortcut=True, file_association=True, progress=None):
    def report(percent, text):
        if progress:
            progress(percent, text)

    install_dir = Path(install_dir)
    payload = resource_path("app-payload.zip")
    if not payload.exists():
        raise FileNotFoundError(f"Cannot find installer payload: {payload}")

    report(5, "正在关闭已运行的程序...")
    stop_running_app()

    report(12, "正在准备安装目录...")
    actual_dir = safe_clear_install_dir(install_dir)
    if actual_dir:
        install_dir = Path(actual_dir)
    install_dir.mkdir(parents=True, exist_ok=True)

    report(25, "正在解压程序文件...")
    with tempfile.TemporaryDirectory(prefix="CUBE18MarkdownViewerInstall-") as temp:
        with zipfile.ZipFile(payload, "r") as archive:
            names = archive.namelist()
            total = max(1, len(names))
            for index, name in enumerate(names, start=1):
                archive.extract(name, temp)
                if index % 30 == 0:
                    report(25 + int(index / total * 35), f"正在解压程序文件... {index}/{total}")
        for item in Path(temp).iterdir():
            target = install_dir / item.name
            if item.is_dir():
                if target.exists():
                    shutil.rmtree(target)
                shutil.copytree(item, target)
            else:
                shutil.copy2(item, target)

    exe_path = install_dir / APP_EXE
    if not exe_path.exists():
        raise FileNotFoundError(f"安装失败，未找到主程序：{exe_path}")
    (install_dir / MARKER_FILE).write_text(time.strftime("%Y-%m-%d %H:%M:%S"), encoding="utf-8")

    report(66, "正在写入卸载信息...")
    write_uninstall_script(install_dir)
    register_uninstall(install_dir)

    if file_association:
        report(76, "正在注册 Markdown 文件关联...")
        register_file_associations(install_dir)

    if start_menu_shortcut:
        report(86, "正在创建开始菜单快捷方式...")
        create_shortcut(start_menu_shortcut_path(), exe_path, install_dir)

    if desktop_shortcut:
        report(92, "正在创建桌面快捷方式...")
        create_shortcut(desktop_shortcut_path(), exe_path, install_dir)

    report(100, "安装完成")
    return install_dir


class Installer(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} 安装向导")
        self.geometry("760x500")
        self.minsize(720, 460)
        self.configure(bg=COLORS["app"])
        self.resizable(False, False)
        self.option_add("*Font", "{Microsoft YaHei UI} 9")
        self.center()

        icon_path = resource_path("markdown-viewer.ico")
        if icon_path.exists():
            try:
                self.iconbitmap(default=str(icon_path))
            except tk.TclError:
                pass

        self.install_dir_var = tk.StringVar(value=str(default_install_dir()))
        self.desktop_var = tk.BooleanVar(value=True)
        self.start_menu_var = tk.BooleanVar(value=True)
        self.association_var = tk.BooleanVar(value=True)
        self.launch_var = tk.BooleanVar(value=True)
        self.page_index = 0
        self.install_result = None
        self.install_error = None

        self.configure_style()
        self.build_shell()
        self.show_page(0)

    def center(self):
        self.update_idletasks()
        width, height = 760, 500
        x = (self.winfo_screenwidth() - width) // 2
        y = (self.winfo_screenheight() - height) // 2
        self.geometry(f"{width}x{height}+{x}+{y}")

    def configure_style(self):
        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("App.TFrame", background=COLORS["app"])
        style.configure("Panel.TFrame", background=COLORS["panel"])
        style.configure("Side.TFrame", background=COLORS["sidebar"])
        style.configure("Title.TLabel", background=COLORS["panel"], foreground=COLORS["text"], font=("Microsoft YaHei UI", 18, "bold"))
        style.configure("Body.TLabel", background=COLORS["panel"], foreground=COLORS["text"], font=("Microsoft YaHei UI", 10))
        style.configure("Muted.TLabel", background=COLORS["panel"], foreground=COLORS["muted"], font=("Microsoft YaHei UI", 9))
        style.configure("SideTitle.TLabel", background=COLORS["sidebar"], foreground=COLORS["brand"], font=("Microsoft YaHei UI", 16, "bold"))
        style.configure("SideMuted.TLabel", background=COLORS["sidebar"], foreground=COLORS["muted"], font=("Microsoft YaHei UI", 9))
        style.configure("Primary.TButton", padding=(18, 8), background=COLORS["brand"], foreground="#FFFFFF", font=("Microsoft YaHei UI", 10, "bold"))
        style.map("Primary.TButton", background=[("active", COLORS["brand_hover"])])
        style.configure("Modern.TButton", padding=(14, 7), font=("Microsoft YaHei UI", 9))
        style.configure("Modern.TCheckbutton", background=COLORS["panel"], foreground=COLORS["text"], font=("Microsoft YaHei UI", 10))
        style.configure("Modern.Horizontal.TProgressbar", troughcolor="#DBEAFE", background=COLORS["brand"], bordercolor=COLORS["border"])

    def build_shell(self):
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        side = ttk.Frame(self, style="Side.TFrame", padding=(26, 30))
        side.grid(row=0, column=0, sticky="nsew")
        side.configure(width=230)
        side.grid_propagate(False)
        ttk.Label(side, text="CUBE18", style="SideTitle.TLabel").pack(anchor="w")
        ttk.Label(side, text="Markdown Viewer", style="SideTitle.TLabel").pack(anchor="w", pady=(0, 22))
        ttk.Label(side, text="本地 Markdown 查看\nDeepSeek 翻译\n右侧译文栏\n文件关联", style="SideMuted.TLabel", justify=tk.LEFT).pack(anchor="w")

        right = ttk.Frame(self, style="Panel.TFrame")
        right.grid(row=0, column=1, sticky="nsew")
        right.rowconfigure(0, weight=1)
        right.columnconfigure(0, weight=1)

        self.page_container = ttk.Frame(right, style="Panel.TFrame", padding=(34, 30, 34, 12))
        self.page_container.grid(row=0, column=0, sticky="nsew")
        self.page_container.columnconfigure(0, weight=1)
        self.page_container.rowconfigure(0, weight=1)

        footer = ttk.Frame(right, style="Panel.TFrame", padding=(24, 12, 24, 22))
        footer.grid(row=1, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)
        self.back_btn = ttk.Button(footer, text="上一步", style="Modern.TButton", command=self.back)
        self.back_btn.grid(row=0, column=1, padx=(0, 8))
        self.next_btn = ttk.Button(footer, text="下一步", style="Primary.TButton", command=self.next)
        self.next_btn.grid(row=0, column=2, padx=(0, 8))
        self.cancel_btn = ttk.Button(footer, text="取消", style="Modern.TButton", command=self.cancel)
        self.cancel_btn.grid(row=0, column=3)

    def clear_page(self):
        for child in self.page_container.winfo_children():
            child.destroy()

    def show_page(self, index):
        self.page_index = index
        self.clear_page()
        if index == 0:
            self.page_welcome()
        elif index == 1:
            self.page_options()
        elif index == 2:
            self.page_install()
        else:
            self.page_finish()
        self.update_buttons()

    def page_welcome(self):
        frame = self.page_container
        ttk.Label(frame, text="欢迎使用安装向导", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            frame,
            text="该向导将安装 CUBE18 Markdown Viewer，并配置快捷方式和 Markdown 文件打开方式。",
            style="Body.TLabel",
            wraplength=430,
        ).pack(anchor="w", pady=(18, 0))
        ttk.Label(
            frame,
            text="安装版包含独立运行时，不需要额外安装 Python。",
            style="Muted.TLabel",
            wraplength=430,
        ).pack(anchor="w", pady=(12, 0))

    def page_options(self):
        frame = self.page_container
        ttk.Label(frame, text="选择安装位置", style="Title.TLabel").pack(anchor="w")
        ttk.Label(frame, text="你可以更改程序安装目录，并选择需要创建的系统入口。", style="Muted.TLabel").pack(anchor="w", pady=(10, 20))

        path_row = ttk.Frame(frame, style="Panel.TFrame")
        path_row.pack(fill=tk.X)
        self.path_entry = ttk.Entry(path_row, textvariable=self.install_dir_var)
        self.path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(path_row, text="浏览...", style="Modern.TButton", command=self.browse_dir).pack(side=tk.LEFT, padx=(8, 0))

        opts = ttk.Frame(frame, style="Panel.TFrame")
        opts.pack(fill=tk.X, pady=(26, 0))
        ttk.Checkbutton(opts, text="创建桌面快捷方式", variable=self.desktop_var, style="Modern.TCheckbutton").pack(anchor="w", pady=4)
        ttk.Checkbutton(opts, text="创建开始菜单快捷方式", variable=self.start_menu_var, style="Modern.TCheckbutton").pack(anchor="w", pady=4)
        ttk.Checkbutton(opts, text="注册 Markdown 文件关联和右键菜单", variable=self.association_var, style="Modern.TCheckbutton").pack(anchor="w", pady=4)
        ttk.Checkbutton(opts, text="安装完成后启动程序", variable=self.launch_var, style="Modern.TCheckbutton").pack(anchor="w", pady=4)

    def page_install(self):
        frame = self.page_container
        ttk.Label(frame, text="正在安装", style="Title.TLabel").pack(anchor="w")
        self.progress_label = ttk.Label(frame, text="准备开始...", style="Body.TLabel")
        self.progress_label.pack(anchor="w", pady=(22, 8))
        self.progress_bar = ttk.Progressbar(frame, orient=tk.HORIZONTAL, maximum=100, mode="determinate", style="Modern.Horizontal.TProgressbar")
        self.progress_bar.pack(fill=tk.X)
        self.detail_label = ttk.Label(frame, text="", style="Muted.TLabel", wraplength=430)
        self.detail_label.pack(anchor="w", pady=(16, 0))
        self.after(120, self.start_install_thread)

    def page_finish(self):
        frame = self.page_container
        if self.install_error:
            ttk.Label(frame, text="安装未完成", style="Title.TLabel").pack(anchor="w")
            ttk.Label(frame, text=str(self.install_error), style="Body.TLabel", wraplength=440).pack(anchor="w", pady=(18, 0))
            return
        ttk.Label(frame, text="安装完成", style="Title.TLabel").pack(anchor="w")
        ttk.Label(frame, text=f"{APP_NAME} 已安装到：", style="Body.TLabel").pack(anchor="w", pady=(18, 0))
        ttk.Label(frame, text=str(self.install_result), style="Muted.TLabel", wraplength=440).pack(anchor="w", pady=(8, 0))
        ttk.Label(frame, text="现在可以通过桌面、开始菜单或 Markdown 文件右键菜单启动。", style="Muted.TLabel", wraplength=440).pack(anchor="w", pady=(18, 0))

    def update_buttons(self):
        self.back_btn.configure(state=tk.NORMAL if self.page_index == 1 else tk.DISABLED)
        if self.page_index == 0:
            self.next_btn.configure(text="下一步", state=tk.NORMAL)
            self.cancel_btn.configure(text="取消", state=tk.NORMAL)
        elif self.page_index == 1:
            self.next_btn.configure(text="安装", state=tk.NORMAL)
            self.cancel_btn.configure(text="取消", state=tk.NORMAL)
        elif self.page_index == 2:
            self.back_btn.configure(state=tk.DISABLED)
            self.next_btn.configure(text="安装中", state=tk.DISABLED)
            self.cancel_btn.configure(state=tk.DISABLED)
        else:
            self.back_btn.configure(state=tk.DISABLED)
            self.next_btn.configure(text="完成", state=tk.NORMAL)
            self.cancel_btn.configure(state=tk.DISABLED)

    def browse_dir(self):
        selected = filedialog.askdirectory(initialdir=self.install_dir_var.get() or str(default_install_dir()))
        if selected:
            self.install_dir_var.set(selected)

    def back(self):
        if self.page_index > 0:
            self.show_page(self.page_index - 1)

    def next(self):
        if self.page_index == 0:
            self.show_page(1)
        elif self.page_index == 1:
            path = self.install_dir_var.get().strip()
            if not path:
                messagebox.showerror("安装路径无效", "请选择安装路径。")
                return
            self.show_page(2)
        elif self.page_index == 3:
            if self.install_result and self.launch_var.get() and not self.install_error:
                try:
                    subprocess.Popen([str(Path(self.install_result) / APP_EXE)], close_fds=True)
                except Exception:
                    pass
            self.destroy()

    def cancel(self):
        if messagebox.askyesno("取消安装", "确定要退出安装向导吗？"):
            self.destroy()

    def start_install_thread(self):
        thread = threading.Thread(target=self.run_install, daemon=True)
        thread.start()

    def update_progress(self, percent, text):
        self.after(0, lambda: self.apply_progress(percent, text))

    def apply_progress(self, percent, text):
        self.progress_bar.configure(value=percent)
        self.progress_label.configure(text=text)
        self.detail_label.configure(text=f"{percent}%")

    def run_install(self):
        try:
            result = install_app(
                self.install_dir_var.get().strip(),
                desktop_shortcut=self.desktop_var.get(),
                start_menu_shortcut=self.start_menu_var.get(),
                file_association=self.association_var.get(),
                progress=self.update_progress,
            )
            self.install_result = result
        except Exception as exc:
            self.install_error = exc
        self.after(350, lambda: self.show_page(3))


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--silent", action="store_true")
    parser.add_argument("--install-dir", default=str(default_install_dir()))
    parser.add_argument("--no-desktop", action="store_true")
    parser.add_argument("--no-start-menu", action="store_true")
    parser.add_argument("--no-association", action="store_true")
    parser.add_argument("--no-launch", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    if args.silent:
        install_dir = install_app(
            args.install_dir,
            desktop_shortcut=not args.no_desktop,
            start_menu_shortcut=not args.no_start_menu,
            file_association=not args.no_association,
            progress=lambda percent, text: print(f"{percent}% {text}", flush=True),
        )
        if not args.no_launch:
            subprocess.Popen([str(Path(install_dir) / APP_EXE)], close_fds=True)
        return

    app = Installer()
    app.mainloop()


if __name__ == "__main__":
    main()
