# CUBE18 Markdown Viewer

一个不使用 Electron 的 Windows Markdown 桌面查看器。

## 功能

- Markdown 预览、源码、分屏
- 文档目录与搜索
- DeepSeek API 翻译：设置菜单中配置 API Key、模型选择、固定 Base URL
- 右侧现代译文栏：选中/全文、快速/精翻、跟随滚动、翻译进度、译文结果
- 蓝白灰现代主题、自绘胶囊按钮、iOS 风格开关、渐变翻译按钮
- 译文结果按 Markdown 样式渲染，并支持原文/译文双向滚动同步
- 半透明浮动滚动条：靠近或滚动时显示，平时隐藏
- 当前用户注册表文件关联
- 自定义应用图标和 Markdown 文件图标

常用操作已收进菜单栏：文件打开/示例文档在“文件”菜单，预览/源码/分屏和搜索在“视图”菜单，翻译相关操作在“工具”菜单和右侧译文栏。

翻译功能使用 `https://api.deepseek.com/chat/completions`。只有点击翻译按钮后，软件才会发送待翻译文本；选中翻译不会在侧边栏重复展示原文。

模型选项为 `deepseek-v4-flash` 和 `deepseek-v4-pro`。快速翻译使用 `thinking=false`，精翻使用 `thinking=true`，两种翻译模式独立于模型下拉框。

API Key 可在“设置 -> DeepSeek API 配置...”中保存到本机，Windows 下使用 DPAPI 加密保护。

往期回滚备份和临时构建文件已集中归档到 `归档_临时文件和回滚_20260729` 文件夹。

## 启动

双击 `launch.cmd`。

## 安装版

安装程序位于：

```text
release\CUBE18MarkdownViewerSetup.exe
```

双击会打开完整安装向导，包含欢迎页、安装路径选择、安装选项、进度页和完成页。

默认安装到当前用户目录：

```text
%LOCALAPPDATA%\Programs\CUBE18 Markdown Viewer
```

安装向导中可以更改安装路径，也可以选择是否创建开始菜单快捷方式、桌面快捷方式，以及是否注册 `.md`、`.markdown`、`.mdown`、`.mkd` 的打开方式和右键菜单。安装版不依赖用户本机 Python。

## 关联 Markdown 文件

在 PowerShell 中运行：

```powershell
powershell -ExecutionPolicy Bypass -File ".\register-file-association.ps1"
```

之后双击 `.md`、`.markdown`、`.mdown`、`.mkd` 文件即可用本查看器打开。

如果 Windows 已经为 Markdown 设置过其他默认应用，双击可能会被系统的 `UserChoice` 保护挡住；脚本同时会加入右键菜单“用 Markdown Viewer 打开”，并把软件加入 Windows 默认应用列表。此时可以在“设置 > 应用 > 默认应用”里选择 `CUBE18 Markdown Viewer`。

## 取消关联

```powershell
powershell -ExecutionPolicy Bypass -File ".\unregister-file-association.ps1"
```

注册表写入位置为当前用户的 `HKCU:\Software\Classes`，不需要管理员权限。
