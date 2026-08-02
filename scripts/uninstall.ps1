$ErrorActionPreference = "Stop"
$InstallDir = Join-Path $env:LOCALAPPDATA "Programs\AbrarStudio"
$DesktopLink = Join-Path ([Environment]::GetFolderPath("Desktop")) "Abrar Studio.lnk"
$StartLink = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Abrar Studio.lnk"
Remove-Item $DesktopLink -Force -ErrorAction SilentlyContinue
Remove-Item $StartLink -Force -ErrorAction SilentlyContinue
Remove-Item $InstallDir -Recurse -Force -ErrorAction SilentlyContinue
Write-Host "Abrar Studio application files were removed. Projects in Documents were kept."
