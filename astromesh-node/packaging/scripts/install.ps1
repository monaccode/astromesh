#Requires -RunAsAdministrator
$ErrorActionPreference = "Stop"

Write-Host "Installing Astromesh Node for Windows..."

$programFiles = $env:ProgramFiles
$programData = $env:ProgramData

$dirs = @(
    "$programData\Astromesh\config",
    "$programData\Astromesh\data\models",
    "$programData\Astromesh\data\memory",
    "$programData\Astromesh\data\data",
    "$programData\Astromesh\logs"
)
foreach ($d in $dirs) {
    New-Item -ItemType Directory -Path $d -Force | Out-Null
}

$destVenv = "$programFiles\Astromesh\venv"
if (Test-Path "venv") {
    Copy-Item -Recurse -Force "venv" $destVenv
}

$binPath = "$destVenv\Scripts"
$currentPath = [Environment]::GetEnvironmentVariable("Path", "Machine")
if ($currentPath -notlike "*$binPath*") {
    [Environment]::SetEnvironmentVariable("Path", "$currentPath;$binPath", "Machine")
    Write-Host "Added $binPath to system PATH"
}

Write-Host "Installation complete. Run 'astromeshctl init' to configure."
