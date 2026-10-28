# Download a portable Node.js (win-x64) into tools\node.
# Called by Setup.bat only after the user says yes. No installer, no PATH changes.
$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$repoRoot = Split-Path -Parent $PSScriptRoot
$toolsDir = Join-Path $repoRoot 'tools'
$destination = Join-Path $toolsDir 'node'
$work = Join-Path ([IO.Path]::GetTempPath()) ("genai-node-" + [Guid]::NewGuid().ToString('N'))
$zip = Join-Path $work 'node.zip'
$extract = Join-Path $work 'extract'

try {
    New-Item -ItemType Directory -Force -Path $toolsDir, $work | Out-Null

    $index = Invoke-RestMethod `
        -Uri 'https://nodejs.org/dist/index.json' `
        -Headers @{ 'User-Agent' = 'GenAI-GUI-Setup' } `
        -TimeoutSec 30
    $release = $index |
        Where-Object { $_.lts -ne $false -and $_.files -contains 'win-x64-zip' } |
        Select-Object -First 1
    if (-not $release) {
        throw 'Could not find a Node.js LTS win-x64 zip release.'
    }

    $version = [string]$release.version
    $name = "node-$version-win-x64.zip"
    $url = "https://nodejs.org/dist/$version/$name"
    $shasumsUrl = "https://nodejs.org/dist/$version/SHASUMS256.txt"

    Write-Host "[setup] Downloading Node.js $version (portable, win-x64)"
    Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $zip -TimeoutSec 300

    $shasums = (Invoke-WebRequest -UseBasicParsing -Uri $shasumsUrl -TimeoutSec 60).Content
    $expected = $shasums -split "`n" |
        Where-Object { $_.Trim().EndsWith($name) } |
        ForEach-Object { ($_ -split '\s+')[0].ToLowerInvariant() } |
        Select-Object -First 1
    if (-not $expected) {
        throw "No SHA-256 entry for $name in SHASUMS256.txt."
    }
    $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $zip).Hash.ToLowerInvariant()
    if ($actual -ne $expected) {
        throw "Node.js archive checksum mismatch (expected $expected, got $actual)."
    }

    Expand-Archive -LiteralPath $zip -DestinationPath $extract -Force
    $inner = Get-ChildItem -LiteralPath $extract -Directory | Select-Object -First 1
    if (-not $inner) {
        throw 'The Node.js archive did not contain a folder.'
    }
    if (Test-Path -LiteralPath $destination) {
        Remove-Item -LiteralPath $destination -Recurse -Force
    }
    Move-Item -LiteralPath $inner.FullName -Destination $destination

    $npm = Join-Path $destination 'npm.cmd'
    $node = Join-Path $destination 'node.exe'
    if (-not (Test-Path -LiteralPath $npm) -or -not (Test-Path -LiteralPath $node)) {
        throw 'The extracted Node.js folder is missing node.exe or npm.cmd.'
    }
    $nodeVersion = & $node --version
    Write-Host "[setup] Installed $nodeVersion at tools\node"
    exit 0
} catch {
    Write-Host "[setup] Error: $($_.Exception.Message)"
    exit 1
} finally {
    Remove-Item -LiteralPath $work -Recurse -Force -ErrorAction SilentlyContinue
}
