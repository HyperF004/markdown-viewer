@echo off
setlocal
set "APP_DIR=%~dp0"

where pyw.exe >nul 2>nul
if %ERRORLEVEL%==0 (
  start "" pyw.exe "%APP_DIR%markdown_viewer.pyw" %*
  exit /b 0
)

where pythonw.exe >nul 2>nul
if %ERRORLEVEL%==0 (
  start "" pythonw.exe "%APP_DIR%markdown_viewer.pyw" %*
  exit /b 0
)

where python.exe >nul 2>nul
if %ERRORLEVEL%==0 (
  start "" python.exe "%APP_DIR%markdown_viewer.pyw" %*
  exit /b 0
)

echo Python was not found. Please install Python 3.10 or newer.
pause
exit /b 1
