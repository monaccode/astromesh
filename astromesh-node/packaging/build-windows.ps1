# Builds dist\astromesh-node-<version>-windows.zip: a standalone CPython and a venv built on
# it, both AT THEIR FINAL PATH (C:\Program Files\Astromesh), plus install.ps1 and the service
# wrapper. A venv is not relocatable: until node 0.1.8 it was built in staging\ with the
# runner's toolcache Python, and every launcher .exe pointed at D:\a\...\staging.
#
# Needs a writable "$env:ProgramFiles\Astromesh" (the GitHub runner is elevated).
$ErrorActionPreference = "Stop"

$version = (Select-String -Path pyproject.toml -Pattern '^version = "(.*)"').Matches[0].Groups[1].Value
$prefix = if ($env:ASTROMESH_PREFIX) { $env:ASTROMESH_PREFIX } else { Join-Path $env:ProgramFiles "Astromesh" }
Write-Host "==> Building astromesh-node $version for Windows into $prefix"

$pbsRelease = "20260924"
$pyVersion = "3.12.14"
$pyAsset = "cpython-$pyVersion+$pbsRelease-x86_64-pc-windows-msvc-install_only_stripped.tar.gz"
$pySha256 = "c5bf8edfe858c1df9891be498b5bbc8761d383df5b9790658b088fea4870433a"

foreach ($part in "python", "venv") {
    $p = Join-Path $prefix $part
    if (Test-Path $p) { Remove-Item -Recurse -Force $p }
}
New-Item -ItemType Directory -Path $prefix -Force | Out-Null
New-Item -ItemType Directory -Path dist -Force | Out-Null

$tarball = Join-Path $env:TEMP "astromesh-python.tar.gz"
Invoke-WebRequest -Uri "https://github.com/astral-sh/python-build-standalone/releases/download/$pbsRelease/$pyAsset" -OutFile $tarball
$actual = (Get-FileHash -Algorithm SHA256 $tarball).Hash.ToLower()
if ($actual -ne $pySha256) { throw "sha256 mismatch for ${pyAsset}: $actual" }
tar -xzf $tarball -C $prefix    # unpacks to python\
if ($LASTEXITCODE -ne 0) { throw "tar failed" }

$py = Join-Path $prefix "python\python.exe"
$venv = Join-Path $prefix "venv"
& $py -m venv $venv
if ($LASTEXITCODE -ne 0) { throw "venv failed" }
$vpy = Join-Path $venv "Scripts\python.exe"
& $vpy -m pip install --upgrade pip --quiet
& $vpy -m pip install "..\[observability]" ".\[windows]" --quiet
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }

Get-ChildItem -Path $prefix -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force
foreach ($d in "Lib\tkinter", "Lib\idlelib", "Lib\turtledemo", "Lib\test", "tcl") {
    $p = Join-Path $prefix "python\$d"
    if (Test-Path $p) { Remove-Item -Recurse -Force $p }
}

& $vpy -c "import astromesh.api.main, astromesh_node; print('==> venv OK', astromesh_node.__version__)"
if ($LASTEXITCODE -ne 0) { throw "runtime import failed" }

$zip = "dist\astromesh-node-$version-windows.zip"
if (Test-Path $zip) { Remove-Item $zip }
# bsdtar writes a real zip with forward-slash paths (Compress-Archive used backslashes).
tar -a -c -f $zip -C $prefix python venv -C "$PWD\packaging\scripts" install.ps1 -C "$PWD\packaging\windows" astromeshd-service.py
if ($LASTEXITCODE -ne 0) { throw "zip failed" }
Write-Host "==> Built $zip"
