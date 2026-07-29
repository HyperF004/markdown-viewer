$ErrorActionPreference = "Stop"

$AppDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$AppScript = Join-Path $AppDir "markdown_viewer.pyw"
$IconPath = Join-Path $AppDir "assets\markdown-viewer.ico"
$LocalShortcut = Join-Path $AppDir "Markdown Viewer.lnk"
$StartMenuDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\CUBE18"
$StartMenuShortcut = Join-Path $StartMenuDir "Markdown Viewer.lnk"

function Resolve-PythonWindowedLauncher {
    foreach ($CommandName in "pyw.exe", "pythonw.exe", "python.exe") {
        $Command = Get-Command $CommandName -ErrorAction SilentlyContinue
        if ($Command -and $Command.Source) {
            return $Command.Source
        }
    }
    throw "Cannot find pyw.exe, pythonw.exe or python.exe. Please install Python 3.10 or newer."
}

if (-not (Test-Path -LiteralPath $AppScript)) {
    throw "Cannot find application script: $AppScript"
}

if (-not (Test-Path -LiteralPath $IconPath)) {
    throw "Cannot find icon: $IconPath"
}

$PythonLauncher = Resolve-PythonWindowedLauncher
$Shell = New-Object -ComObject WScript.Shell

foreach ($ShortcutPath in $LocalShortcut, $StartMenuShortcut) {
    $ShortcutDir = Split-Path -Parent $ShortcutPath
    New-Item -ItemType Directory -Path $ShortcutDir -Force | Out-Null

    $Shortcut = $Shell.CreateShortcut($ShortcutPath)
    $Shortcut.TargetPath = $PythonLauncher
    $Shortcut.Arguments = "`"$AppScript`""
    $Shortcut.WorkingDirectory = $AppDir
    $Shortcut.IconLocation = "$IconPath,0"
    $Shortcut.Description = "CUBE18 Markdown Viewer"
    $Shortcut.Save()

    Write-Host "Created shortcut: $ShortcutPath"
}
