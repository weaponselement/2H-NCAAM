$d = Read-Host "Backfill date (YYYY-MM-DD)"

$python = Join-Path $PSScriptRoot "..\.venv\Scripts\python.exe"
$script = Join-Path $PSScriptRoot "backfill_halftime_predictions_for_date_v1.py"

& $python $script --date $d
