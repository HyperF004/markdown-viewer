# Markdown Viewer Qt Preview

一个基于 Qt（PySide6）的 Windows Markdown 桌面查看器，内置 DeepSeek 双语翻译（预览版）。

## 当前状态

这是 Tkinter 版向 Qt 迁移的 **Preview 版本**：原生 Qt `QSplitter` 布局，解决了旧 Tk 版 `ttk.PanedWindow` 在 Windows 上实时拖拽侧栏时的控件撕裂问题。

**已实现：**

- Markdown 文件打开与 HTML 预览
- DeepSeek API 配置（API Key 存于 `%APPDATA%\MarkdownViewer\settings.json`，Windows DPAPI 加密保护）
- 选中 / 全文翻译，翻译进度反馈
- 译文按 Markdown 样式渲染
- 原文 / 译文滚动联动
- 可持久化的浅色 / 深色模式（覆盖全部界面元素，Windows 原生标题栏同步切换）
- 右侧译文栏显示 / 隐藏，源码栏显示 / 隐藏（隐藏后预览区自动扩展，恢复时还原宽度）
- 苹果风格自绘跟随滚动开关（绿色 / 灰色 + 180ms 缓动动画）
- 圆角卡片式界面：22px / 28px 圆角、统一留白与配色、分段式模式按钮、细半透明滚动条

**Preview 阶段尚未迁移（计划中）：**

- 目标语言选择
- 搜索与文档目录
- 源码 / 预览 / 分屏切换
- 完整的图片与链接渲染
- 翻译分段并发与更精细的滚动对齐
- 右键菜单、文件关联与卸载逻辑

## 运行

双击 `launch-qt.cmd`，或直接用 Python 运行 `markdown_viewer_qt.pyw`。

依赖：PySide6 6.11.1、Markdown 3.10.3。

## 安装包（Preview）

```text
release-qt\MarkdownViewerQtPreviewSetup.exe
```

SHA-256：`A4F92394B4C246D68FAAC9F2A62004D63F7058D8E373CDE408277C0ECB50AE9E`

Qt Preview 安装器使用独立的 App ID / ProgID，可与旧 Tk 版并存安装，互不覆盖。

## 项目结构

- `markdown_viewer_qt.pyw` — Qt 应用主程序
- `installer\installer_ui_qt.py` — Qt Preview 安装向导
- `dist-qt` — 打包后的 Qt 应用目录
- `release-qt` — 最终安装程序输出目录
- `Qt版本交接说明.txt` — 迁移交接说明

旧 Tkinter 实现已移至同级目录 `E:\CUBE18\markdown viewer-tk-legacy`（含 Tk 源码、旧安装器、注册表关联脚本、构建产物），已归档不再维护。

## 路线图

Qt Preview 功能补齐后，将替换 Tk 版成为正式的 Markdown Viewer，并重建主安装包。

---

# Markdown Viewer Qt Preview

A Qt (PySide6) based Windows Markdown viewer with built-in DeepSeek bilingual translation (preview release).

## Status

This is the **preview release** of the Qt migration from the former Tkinter edition. It uses the native Qt `QSplitter` layout, fixing the widget tearing issue of the old Tk `ttk.PanedWindow` when resizing the sidebar live on Windows.

**Implemented:**

- Markdown file opening with HTML preview
- DeepSeek API configuration (API Key stored in `%APPDATA%\MarkdownViewer\settings.json`, protected with Windows DPAPI)
- Selection / full-document translation with progress feedback
- Translation result rendered as Markdown
- Bidirectional scroll sync between original and translation
- Persistent light / dark mode (applied across the whole UI, syncing the Windows native title bar)
- Show / hide the right-side translation panel, and show / hide the source pane (the preview expands when hidden and restores its width on return)
- Apple-style self-drawn follow-scroll switch (green / gray with 180 ms easing animation)
- Rounded card UI: 22px / 28px corner radii, unified spacing and colors, segmented mode buttons, slim translucent scrollbars

**Not yet migrated (planned):**

- Target language selection
- Search and document TOC
- Source / preview / split view switching
- Full image and link rendering
- Chunked concurrent translation with finer scroll alignment
- Context menus, file association, and uninstall logic

## Run

Double-click `launch-qt.cmd`, or run `markdown_viewer_qt.pyw` with Python.

Dependencies: PySide6 6.11.1, Markdown 3.10.3.

## Installer (Preview)

```text
release-qt\MarkdownViewerQtPreviewSetup.exe
```

SHA-256: `A4F92394B4C246D68FAAC9F2A62004D63F7058D8E373CDE408277C0ECB50AE9E`

The Qt Preview installer uses an independent App ID / ProgID, so it can be installed alongside the archived Tk edition without overwriting it.

## Project Layout

- `markdown_viewer_qt.pyw` — Qt application source
- `installer\installer_ui_qt.py` — Qt Preview installer wizard
- `dist-qt` — packaged Qt application directory
- `release-qt` — final setup executable output
- `Qt版本交接说明.txt` — implementation handoff notes

The former Tkinter implementation has been moved to the sibling folder `E:\CUBE18\markdown viewer-tk-legacy` (Tk source, old installer, file-association scripts, build artifacts) and is archived, no longer maintained.

## Roadmap

Once the Qt Preview feature set is complete, it will replace the Tk edition as the official Markdown Viewer, with the main installer rebuilt.
