# Exit 0 when frontend\dist is missing or older than the Vue sources/config.
# Exit 1 when the existing build is current enough. Launch.bat and Setup.bat
# use the exit code so the app does not rebuild on every start.
$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$frontend = Join-Path $repoRoot 'frontend'
$distIndex = Join-Path $frontend 'dist\index.html'

if (-not (Test-Path -LiteralPath $distIndex)) {
    exit 0
}

$distTime = (Get-Item -LiteralPath $distIndex).LastWriteTimeUtc
$sources = [System.Collections.Generic.List[System.IO.FileInfo]]::new()

$src = Join-Path $frontend 'src'
if (Test-Path -LiteralPath $src) {
    Get-ChildItem -LiteralPath $src -Recurse -File -ErrorAction SilentlyContinue |
        ForEach-Object { $sources.Add($_) }
}

$public = Join-Path $frontend 'public'
if (Test-Path -LiteralPath $public) {
    Get-ChildItem -LiteralPath $public -Recurse -File -ErrorAction SilentlyContinue |
        ForEach-Object { $sources.Add($_) }
}

$rootFiles = @(
    'index.html',
    'package.json',
    'package-lock.json',
    'vite.config.js',
    'vite.config.mjs',
    'vite.config.ts',
    'tsconfig.json',
    'tsconfig.app.json',
    'tsconfig.node.json',
    'tailwind.config.js',
    'tailwind.config.ts',
    'postcss.config.js',
    'postcss.config.mjs'
)
foreach ($name in $rootFiles) {
    $path = Join-Path $frontend $name
    if (Test-Path -LiteralPath $path) {
        $sources.Add((Get-Item -LiteralPath $path))
    }
}

$latest = $sources | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
if ($latest -and $latest.LastWriteTimeUtc -gt $distTime) {
    exit 0
}
exit 1
