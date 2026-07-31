$ErrorActionPreference = "Stop"

$ProgId = "MarkdownViewer.Document"
$RegisteredAppName = "Markdown Viewer"
$Extensions = @(".md", ".markdown", ".mdown", ".mkd")

foreach ($Extension in $Extensions) {
    $ExtensionPath = "HKCU:\Software\Classes\$Extension"
    $OpenWithPath = "$ExtensionPath\OpenWithProgids"
    $ExplorerOpenWithPath = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts\$Extension\OpenWithProgids"

    if (Test-Path -LiteralPath $ExtensionPath) {
        $RelativePath = $ExtensionPath -replace "^HKCU:\\", ""
        $Key = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey($RelativePath, $true)
        $CurrentDefault = if ($Key) { $Key.GetValue("") } else { $null }
        if ($CurrentDefault -eq $ProgId) {
            $Key.DeleteValue("", $false)
        }
        if ($Key) {
            $Key.Close()
        }
    }

    if (Test-Path -LiteralPath $OpenWithPath) {
        Remove-ItemProperty -LiteralPath $OpenWithPath -Name $ProgId -ErrorAction SilentlyContinue
    }

    if (Test-Path -LiteralPath $ExplorerOpenWithPath) {
        Remove-ItemProperty -LiteralPath $ExplorerOpenWithPath -Name $ProgId -ErrorAction SilentlyContinue
    }

    Remove-Item -LiteralPath "HKCU:\Software\Classes\SystemFileAssociations\$Extension\shell\MarkdownViewer" -Recurse -Force -ErrorAction SilentlyContinue
}

Remove-ItemProperty -LiteralPath "HKCU:\Software\RegisteredApplications" -Name $RegisteredAppName -ErrorAction SilentlyContinue
Remove-Item -LiteralPath "HKCU:\Software\MarkdownViewer" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath "HKCU:\Software\Classes\$ProgId" -Recurse -Force -ErrorAction SilentlyContinue

Add-Type -Namespace Win32 -Name ShellNotify -MemberDefinition @"
[System.Runtime.InteropServices.DllImport("shell32.dll")]
public static extern void SHChangeNotify(int wEventId, uint uFlags, System.IntPtr dwItem1, System.IntPtr dwItem2);
"@
[Win32.ShellNotify]::SHChangeNotify(0x08000000, 0, [IntPtr]::Zero, [IntPtr]::Zero)

Write-Host "Unregistered Markdown Viewer file association."
