# Analyze every participant folder under a dataset directory and generate
# one PDF report each.
#
# Usage (from the repository root):
#   powershell -ExecutionPolicy Bypass -File scripts\analyze_all_subjects.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\analyze_all_subjects.ps1 -DataDir "D:\OtherData" -Baseline "baseline.csv"
#
param(
    [string]$DataDir = "SubjectsData",
    [string]$Baseline = "",
    [string]$OutDir = "output\reports",
    [switch]$SaveDb
)

$repo = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repo ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { $python = "python" }

$folders = Get-ChildItem -Path (Join-Path $repo $DataDir) -Directory |
    Where-Object { $_.Name -ne "baseline" }

$ok = 0; $failed = 0
foreach ($folder in $folders) {
    Write-Host "=== $($folder.Name) ===" -ForegroundColor Cyan
    $cliArgs = @("-m", "biomech_analyzer.cli", "report", $folder.FullName, "--out", $OutDir)
    if ($Baseline) { $cliArgs += @("--baseline", $Baseline) }
    if ($SaveDb)   { $cliArgs += "--save-db" }
    $env:PYTHONPATH = Join-Path $repo "src"
    & $python @cliArgs
    if ($LASTEXITCODE -eq 0) { $ok++ } else { $failed++ }
}
Write-Host ""
Write-Host "Done: $ok report(s) generated, $failed folder(s) failed." -ForegroundColor Green
Write-Host "Reports: $(Join-Path $repo $OutDir)"
