@echo off
setlocal
set "APP_DIR=%~dp0"
pyw.exe "%APP_DIR%markdown_viewer_qt.pyw" %*
