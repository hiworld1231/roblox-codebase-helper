# One command: irm https://raw.githubusercontent.com/hiworld1231/roblox-codebase-helper/main/install.ps1 | iex
$ErrorActionPreference = 'Stop'
$previousProgress = $ProgressPreference
$ProgressPreference = 'SilentlyContinue'
$asset = 'codebase-helper-windows-x86_64.exe'
$base = 'https://github.com/hiworld1231/roblox-codebase-helper/releases/latest/download'
$taskDir = Join-Path ([System.IO.Path]::GetTempPath()) ('codebase-helper-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $taskDir | Out-Null
try {
    $binary = Join-Path $taskDir $asset
    Invoke-WebRequest -UseBasicParsing "$base/$asset" -OutFile $binary
    $checksumFile = Join-Path $taskDir ($asset + '.sha256')
    Invoke-WebRequest -UseBasicParsing "$base/$asset.sha256" -OutFile $checksumFile
    $checksum = (Get-Content -Raw $checksumFile).Trim().Split(' ')[0]
    $stream = [System.IO.File]::OpenRead($binary)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try { $actual = [System.BitConverter]::ToString($sha.ComputeHash($stream)).Replace('-', '') }
    finally { $stream.Dispose(); $sha.Dispose() }
    if ($actual -ine $checksum) { throw 'Download checksum mismatch. Retry installation.' }
    & $binary --cli
    if ($LASTEXITCODE -ne 0) { throw "Setup failed (exit $LASTEXITCODE). Read the message above and retry." }
} finally {
    $ProgressPreference = $previousProgress
    Remove-Item -Recurse -Force $taskDir -ErrorAction SilentlyContinue
}
