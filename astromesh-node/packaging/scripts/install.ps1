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

# The bundled CPython and the venv built on it were built at exactly these paths, so they
# must land there. Replace old copies: Copy-Item into an existing dir nests the new one.
$installDir = "$programFiles\Astromesh"
New-Item -ItemType Directory -Path $installDir -Force | Out-Null
foreach ($part in "python", "venv") {
    if (-not (Test-Path $part)) { throw "Missing $part\ - run install.ps1 from the extracted zip" }
    $dest = Join-Path $installDir $part
    if (Test-Path $dest) { Remove-Item -Recurse -Force $dest }
    Copy-Item -Recurse -Force $part $dest
}
$destVenv = Join-Path $installDir "venv"

$binPath = "$destVenv\Scripts"
$currentPath = [Environment]::GetEnvironmentVariable("Path", "Machine")
if ($currentPath -notlike "*$binPath*") {
    [Environment]::SetEnvironmentVariable("Path", "$currentPath;$binPath", "Machine")
    Write-Host "Added $binPath to system PATH"
}

Write-Host "Installation complete. Run 'astromeshctl init' to configure."
