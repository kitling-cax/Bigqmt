param(
  [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = [IO.Path]::GetFullPath($ProjectRoot)
$csc = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
if (-not (Test-Path -LiteralPath $csc)) { throw "C# compiler unavailable: $csc" }
$source = Join-Path $ProjectRoot 'tray\BigQMTAccountTray.cs'
$normalizer = Join-Path $ProjectRoot 'scripts\normalize_native_pe.py'
if (-not (Test-Path -LiteralPath $normalizer)) { throw "PE normalizer unavailable: $normalizer" }
& py -3.12 (Join-Path $ProjectRoot 'scripts\generate_native_tray_icons.py')
if ($LASTEXITCODE -ne 0) { throw 'native tray icon generation failed' }
foreach ($item in @(
  @{ Define='SIMULATION'; Name='BigQMT_Simulation.exe'; Icon='BigQMT_Simulation.ico' },
  @{ Define='PRODUCTION'; Name='BigQMT_Production_ReadOnly.exe'; Icon='BigQMT_Production_ReadOnly.ico' }
)) {
  $output = Join-Path $ProjectRoot ('tray\' + $item.Name)
  $icon = Join-Path $ProjectRoot ('tray\' + $item.Icon)
    & $csc /nologo /target:winexe /optimize+ /define:$($item.Define) /win32icon:$icon /reference:System.dll /reference:System.Drawing.dll /reference:System.Windows.Forms.dll /reference:System.Web.Extensions.dll /out:$output $source
    if ($LASTEXITCODE -ne 0) { throw "compile failed: $($item.Name)" }
    & py -3.12 $normalizer $output
    if ($LASTEXITCODE -ne 0) { throw "PE normalization failed: $($item.Name)" }
}

$manifest = foreach ($name in 'BigQMT_Simulation.exe', 'BigQMT_Production_ReadOnly.exe') {
  $path = Join-Path $ProjectRoot ('tray\' + $name)
  $hash = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash
  "$hash  $name"
}
[IO.File]::WriteAllLines((Join-Path $ProjectRoot 'tray\BigQMT_native_tray_checksums.sha256'), $manifest, (New-Object System.Text.UTF8Encoding($false)))
