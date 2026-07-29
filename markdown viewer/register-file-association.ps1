$ErrorActionPreference = "Stop"

$AppDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$AppScript = Join-Path $AppDir "markdown_viewer.pyw"
$IconPath = Join-Path $AppDir "assets\markdown-viewer.ico"
$ProgId = "CUBE18MarkdownViewer.Document"
$RegisteredAppName = "CUBE18 Markdown Viewer"
$CapabilitiesPath = "Software\CUBE18MarkdownViewer\Capabilities"
$Extensions = @(".md", ".markdown", ".mdown", ".mkd")

function Set-RegistryDefaultValue {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Value
    )

    $RelativePath = $Path -replace "^HKCU:\\", ""
    $Key = [Microsoft.Win32.Registry]::CurrentUser.CreateSubKey($RelativePath)
    if (-not $Key) {
        throw "Cannot open registry key: $Path"
    }
    try {
        $Key.SetValue("", $Value, [Microsoft.Win32.RegistryValueKind]::String)
    }
    finally {
        $Key.Close()
    }
}

function Set-RegistryStringValue {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Value
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        New-Item -Path $Path -Force | Out-Null
    }
    New-ItemProperty -Path $Path -Name $Name -Value $Value -PropertyType String -Force | Out-Null
}

function Set-RegistryBinaryValue {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Name
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        New-Item -Path $Path -Force | Out-Null
    }
    New-ItemProperty -Path $Path -Name $Name -Value ([byte[]]@()) -PropertyType Binary -Force | Out-Null
}

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
    throw "Cannot find application icon: $IconPath"
}

$PythonLauncher = Resolve-PythonWindowedLauncher
$Command = "`"$PythonLauncher`" `"$AppScript`" `"%1`""
$IconValue = "`"$IconPath`",0"

Set-RegistryDefaultValue -Path "HKCU:\Software\Classes\$ProgId" -Value "Markdown Viewer Document"
Set-RegistryStringValue -Path "HKCU:\Software\Classes\$ProgId" -Name "FriendlyTypeName" -Value "Markdown Viewer Document"
Set-RegistryStringValue -Path "HKCU:\Software\Classes\$ProgId" -Name "AppUserModelID" -Value "CUBE18.MarkdownViewer"
Set-RegistryDefaultValue -Path "HKCU:\Software\Classes\$ProgId\DefaultIcon" -Value $IconValue
Set-RegistryDefaultValue -Path "HKCU:\Software\Classes\$ProgId\shell" -Value "open"
Set-RegistryDefaultValue -Path "HKCU:\Software\Classes\$ProgId\shell\open" -Value "用 Markdown Viewer 打开"
Set-RegistryDefaultValue -Path "HKCU:\Software\Classes\$ProgId\shell\open\command" -Value $Command
Set-RegistryStringValue -Path "HKCU:\Software\Classes\$ProgId\Application" -Name "ApplicationName" -Value $RegisteredAppName
Set-RegistryStringValue -Path "HKCU:\Software\Classes\$ProgId\Application" -Name "ApplicationIcon" -Value $IconValue
Set-RegistryStringValue -Path "HKCU:\Software\Classes\$ProgId\Application" -Name "AppUserModelID" -Value "CUBE18.MarkdownViewer"

Set-RegistryStringValue -Path "HKCU:\Software\CUBE18MarkdownViewer\Capabilities" -Name "ApplicationName" -Value $RegisteredAppName
Set-RegistryStringValue -Path "HKCU:\Software\CUBE18MarkdownViewer\Capabilities" -Name "ApplicationDescription" -Value "Open and translate Markdown documents."
Set-RegistryStringValue -Path "HKCU:\Software\CUBE18MarkdownViewer\Capabilities" -Name "ApplicationIcon" -Value $IconValue
foreach ($Extension in $Extensions) {
    Set-RegistryStringValue -Path "HKCU:\Software\CUBE18MarkdownViewer\Capabilities\FileAssociations" -Name $Extension -Value $ProgId
}
Set-RegistryStringValue -Path "HKCU:\Software\RegisteredApplications" -Name $RegisteredAppName -Value $CapabilitiesPath

foreach ($Extension in $Extensions) {
    Set-RegistryDefaultValue -Path "HKCU:\Software\Classes\$Extension" -Value $ProgId
    Set-RegistryStringValue -Path "HKCU:\Software\Classes\$Extension" -Name "Content Type" -Value "text/markdown"
    Set-RegistryStringValue -Path "HKCU:\Software\Classes\$Extension" -Name "PerceivedType" -Value "text"
    Set-RegistryBinaryValue -Path "HKCU:\Software\Classes\$Extension\OpenWithProgids" -Name $ProgId
    Set-RegistryBinaryValue -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts\$Extension\OpenWithProgids" -Name $ProgId

    $ContextMenuPath = "HKCU:\Software\Classes\SystemFileAssociations\$Extension\shell\CUBE18MarkdownViewer"
    Set-RegistryDefaultValue -Path $ContextMenuPath -Value "用 Markdown Viewer 打开"
    Set-RegistryStringValue -Path $ContextMenuPath -Name "Icon" -Value $IconValue
    Set-RegistryDefaultValue -Path "$ContextMenuPath\command" -Value $Command
}

Add-Type -Namespace Win32 -Name ShellNotify -MemberDefinition @"
[System.Runtime.InteropServices.DllImport("shell32.dll")]
public static extern void SHChangeNotify(int wEventId, uint uFlags, System.IntPtr dwItem1, System.IntPtr dwItem2);
"@
[Win32.ShellNotify]::SHChangeNotify(0x08000000, 0, [IntPtr]::Zero, [IntPtr]::Zero)

Write-Host "Registered $RegisteredAppName for .md, .markdown, .mdown and .mkd files."
Write-Host "Open command: $Command"
Write-Host "Icon: $IconPath"
Write-Host "If double-click still opens another app, choose this app in Windows Settings > Apps > Default apps, or use the right-click menu: 用 Markdown Viewer 打开."
