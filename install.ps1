# One command: irm https://raw.githubusercontent.com/hiworld1231/roblox-codebase-helper/main/install.ps1 | iex
$ErrorActionPreference = 'Stop'
$asset = 'codebase-helper-windows-x86_64.exe'
$base = 'https://github.com/hiworld1231/roblox-codebase-helper/releases/latest/download'
$taskDir = Join-Path ([System.IO.Path]::GetTempPath()) ('codebase-helper-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $taskDir | Out-Null
try {
    $binary = Join-Path $taskDir $asset
    Invoke-WebRequest "$base/$asset" -OutFile $binary
    $checksumFile = Join-Path $taskDir ($asset + '.sha256')
    Invoke-WebRequest "$base/$asset.sha256" -OutFile $checksumFile
    $checksum = (Get-Content -Raw $checksumFile).Trim().Split(' ')[0]
    if ((Get-FileHash $binary -Algorithm SHA256).Hash -ine $checksum) { throw 'Download checksum mismatch. Retry installation.' }
    & $binary --cli
    if ($LASTEXITCODE -ne 0) { throw "Setup failed (exit $LASTEXITCODE). Read the message above and retry." }
} finally {
    Remove-Item -Recurse -Force $taskDir -ErrorAction SilentlyContinue
}
