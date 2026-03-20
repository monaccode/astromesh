$ErrorActionPreference = "Stop"

$version = python -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])"
Write-Host "Building astromesh-node $version for Windows..."

$staging = "staging\windows"
if (Test-Path $staging) { Remove-Item -Recurse -Force $staging }
New-Item -ItemType Directory -Path $staging | Out-Null

python -m venv "$staging\venv"
& "$staging\venv\Scripts\pip" install --quiet ..\  .\[windows]

Copy-Item "packaging\windows\astromeshd-service.py" "$staging\" -ErrorAction SilentlyContinue
Copy-Item "packaging\scripts\install.ps1" "$staging\" -ErrorAction SilentlyContinue

New-Item -ItemType Directory -Path dist -Force | Out-Null
Compress-Archive -Path "$staging\*" -DestinationPath "dist\astromesh-node-$version-windows.zip" -Force
Write-Host "Built dist\astromesh-node-$version-windows.zip"
