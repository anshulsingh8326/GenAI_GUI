# Download the portable uv executable into tools\uv.exe.
# Called by Setup.bat only after the user says yes.
$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$repoRoot = Split-Path -Parent $PSScriptRoot
$toolsDir = Join-Path $repoRoot 'tools'
$destination = Join-Path $toolsDir 'uv.exe'
$work = Join-Path ([IO.Path]::GetTempPath()) ("genai-uv-" + [Guid]::NewGuid().ToString('N'))
$zip = Join-Path $work 'uv.zip'
$extract = Join-Path $work 'extract'

try {
    New-Item -ItemType Directory -Force -Path $toolsDir, $work | Out-Null

    $url = 'https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-pc-windows-msvc.zip'
    $digest = $null
    try {
        $release = Invoke-RestMethod `
            -Uri 'https://api.github.com/repos/astral-sh/uv/releases/latest' `
            -Headers @{ 'User-Agent' = 'GenAI-GUI-Setup' } `
            -TimeoutSec 30
        $asset = $release.assets |
            Where-Object { $_.name -like '*x86_64-pc-windows-msvc*.zip' } |
            Select-Object -First 1
        if ($asset) {
            $url = $asset.browser_download_url
            $digest = $asset.digest
        }
    } catch {
        Write-Host '[setup] GitHub release lookup failed - using the direct latest URL.'
    }

    Write-Host "[setup] Downloading $url"
    Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $zip -TimeoutSec 300

    if ($digest -match '^sha256:([0-9a-fA-F]{64})$') {
        $expected = $Matches[1].ToLowerInvariant()
        $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $zip).Hash.ToLowerInvariant()
        if ($actual -ne $expected) {
            throw "uv archive checksum mismatch (expected $expected, got $actual)."
        }
    }

    Expand-Archive -LiteralPath $zip -DestinationPath $extract -Force
    $exe = Get-ChildItem -LiteralPath $extract -Recurse -Filter 'uv.exe' -File |
        Select-Object -First 1
    if (-not $exe) {
        throw 'The uv archive did not contain uv.exe.'
    }

    Copy-Item -LiteralPath $exe.FullName -Destination $destination -Force
    $version = & $destination --version
    Write-Host "[setup] Installed $version at tools\uv.exe"
    exit 0
} catch {
    Write-Host "[setup] Error: $($_.Exception.Message)"
    exit 1
} finally {
    Remove-Item -LiteralPath $work -Recurse -Force -ErrorAction SilentlyContinue
}
