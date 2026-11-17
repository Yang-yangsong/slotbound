param([string]$Python = 'python')

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$output = New-Item -ItemType Directory -Force (Join-Path $root 'dist')
$temp = New-Item -ItemType Directory -Force (Join-Path $root 'build')
$helper = Join-Path $temp.FullName 'slotbound-launch.exe'
$gcc = Get-Command gcc.exe -ErrorAction Stop
& $gcc.Source -Wall -Wextra -Werror -O2 -static -municode -o $helper (Join-Path $root 'launch_windows.c')
if ($LASTEXITCODE -ne 0) { throw 'Native launcher build failed.' }

$nativePython = & $Python -c 'import sys; print(sys.base_prefix)'
if ($LASTEXITCODE -ne 0) { throw 'Windows Python with Tkinter is needed to build the application.' }
$assets = @('slotbound_odds.lua', 'slotbound_sections.lua', 'costs.txt')
$pack = @(
    '-m', 'PyInstaller', '--clean', '--noconfirm', '--onefile', '--windowed', '--noupx',
    '--name', 'Slotbound-Controls', '--distpath', $output.FullName,
    '--workpath', $temp.FullName, '--specpath', $temp.FullName,
    '--add-binary', "${helper}:."
)
foreach ($asset in $assets) {
    $pack += @('--add-data', ((Join-Path $root $asset) + ':.'))
}
foreach ($name in @('LICENSE.txt', 'tcl/tk8.6/license.terms')) {
    $license = Join-Path $nativePython $name
    if (Test-Path -LiteralPath $license) {
        $pack += @('--add-data', "${license}:runtime-licenses")
    }
}
$pack += (Join-Path $root 'slotbound_controls.pyw')
& $Python @pack
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed.' }
