param(
  [Parameter(Mandatory=$true)]
  [ValidateSet("prep","download_pbp","list_slate","pull_halftime","report_halftime","log_prediction","halftime_run","postgame_missing","postgame_single")]
  [string]$Action,

  [string]$Date = "",
  [string]$GameId = ""
)

$ErrorActionPreference = "Stop"

# Workspace root = parent of Scripts\
$WS = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

# Default Date = today if blank
if ([string]::IsNullOrWhiteSpace($Date)) {
  $Date = (Get-Date).ToString("yyyy-MM-dd")
}

$Py = Join-Path $WS ".venv\Scripts\python.exe"

function RunPy([string]$ScriptRelPath, [string[]]$PyArgs) {
  $scriptPath = Join-Path $WS $ScriptRelPath
  Write-Host ""
  Write-Host "RUN:" $scriptPath ($PyArgs -join " ")
  & $Py $scriptPath @PyArgs
  $code = $LASTEXITCODE
  if ($code -ne 0) {
    Write-Host ""
    Write-Host ("FAIL (exit={0}): {1}" -f $code, $scriptPath) -ForegroundColor Red
    exit $code
  }
}

function PullHalftimeWithRetry([string]$gid, [int]$tries = 3) {
  $scriptPath = Join-Path $WS "Scripts\step4_pull_halftime_pbp_v2.py"

  for ($i=1; $i -le $tries; $i++) {
    Write-Host ""
    Write-Host ("RUN (try {0}/{1}): {2} {3}" -f $i, $tries, $scriptPath, $gid)
    & $Py $scriptPath $gid
    $code = $LASTEXITCODE
    if ($code -eq 0) { return }
    Start-Sleep -Seconds (2 * $i)
  }

  # Show newest error log if present (script writes pbp_live_error_* on failure) [1](https://htsag-my.sharepoint.com/personal/jrobinson_htsag_com/Documents/Microsoft%20Copilot%20Chat%20Files/update_all_results_v1.py)
  $logDir = Join-Path $WS "data\logs"
  $pattern = "pbp_live_error_{0}_*.json" -f $gid
  $latest = Get-ChildItem $logDir -Filter $pattern -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1

  Write-Host ""
  if ($latest) {
    Write-Host ("Latest error log: {0}" -f $latest.FullName) -ForegroundColor Yellow
  }

  Write-Host ("FAIL: {0}" -f $scriptPath) -ForegroundColor Red
  exit 2
}

switch ($Action) {

  "prep" {
    RunPy "Scripts\prepare_full_slate_v1.py" @("--date", $Date)
  }

  "download_pbp" {
    $baseline = Join-Path $WS ("data\processed\baselines\last4_{0}.json" -f $Date)
    RunPy "Scripts\step3_download_pbp_baselines.py" @("--baseline", $baseline, "--workers", "8", "--max-rps", "4")
  }

  "list_slate" {
    $csv = Join-Path $WS ("data\processed\slates\slate_d1_{0}.csv" -f $Date)
    Import-Csv $csv |
      Select-Object gameID, away_short, home_short |
      ForEach-Object { "{0}  |  {1} @ {2}" -f $_.gameID, $_.away_short, $_.home_short }
  }

  "pull_halftime" {
    if ([string]::IsNullOrWhiteSpace($GameId)) { Write-Host "GameId is required." -ForegroundColor Red; exit 2 }
    PullHalftimeWithRetry $GameId 3
  }

  "report_halftime" {
    if ([string]::IsNullOrWhiteSpace($GameId)) { Write-Host "GameId is required." -ForegroundColor Red; exit 2 }
    $baseline = Join-Path $WS ("data\processed\baselines\last4_{0}.json" -f $Date)
    $selected = Join-Path $WS ("data\processed\selected_games\selected_games_{0}.json" -f $Date)
    RunPy "Scripts\step4b_feature_report_from_file_v5_test.py" @($GameId, "--baseline-manifest", $baseline, "--selected-games", $selected)  # [2](https://htsag-my.sharepoint.com/personal/jrobinson_htsag_com/Documents/Microsoft%20Copilot%20Chat%20Files/update_new_results_only_v1.py)
  }

  "log_prediction" {
    if ([string]::IsNullOrWhiteSpace($GameId)) { Write-Host "GameId is required." -ForegroundColor Red; exit 2 }
    RunPy "Scripts\log_prediction_to_results_v1.py" @($GameId)  # [2](https://htsag-my.sharepoint.com/personal/jrobinson_htsag_com/Documents/Microsoft%20Copilot%20Chat%20Files/update_new_results_only_v1.py)
  }

  "halftime_run" {
    if ([string]::IsNullOrWhiteSpace($GameId)) { Write-Host "GameId is required." -ForegroundColor Red; exit 2 }

    # 1) Pull halftime (stop hard if it fails)
    & $PSCommandPath -Action pull_halftime -Date $Date -GameId $GameId
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    # 2) Report (stop hard if it fails)
    & $PSCommandPath -Action report_halftime -Date $Date -GameId $GameId
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    # 3) Log (stop hard if it fails)
    & $PSCommandPath -Action log_prediction -Date $Date -GameId $GameId
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
  }

  "postgame_missing" {
    RunPy "Scripts\update_new_results_only_v1.py" @()
  }

  "postgame_single" {
    if ([string]::IsNullOrWhiteSpace($GameId)) { Write-Host "GameId is required." -ForegroundColor Red; exit 2 }
    RunPy "Scripts\update_results_postgame_v1.py" @($GameId)
  }
}