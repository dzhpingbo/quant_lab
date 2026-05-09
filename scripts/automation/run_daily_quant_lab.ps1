param(
    [string]$Config = "",
    [switch]$DryRun,
    [switch]$SkipUpdate,
    [switch]$SkipStrategy,
    [string]$Date = "",
    [double]$MaxRuntimeMinutes = 0,
    [switch]$AllowDirty
)

$ErrorActionPreference = "Stop"
$Python = "C:\Users\Administrator\.conda\envs\aimodel\python.exe"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path (Join-Path $ScriptDir "..\..")
if ([string]::IsNullOrWhiteSpace($Config)) {
    $Config = Join-Path $ScriptDir "daily_quant_lab_config.yaml"
}

$OutputRoot = Join-Path $ProjectRoot "outputs\daily_quant_lab_runs"
New-Item -ItemType Directory -Force -Path $OutputRoot | Out-Null

$StdoutLog = Join-Path $OutputRoot "latest_scheduler_stdout.log"
$StderrLog = Join-Path $OutputRoot "latest_scheduler_stderr.log"
$Runner = Join-Path $ScriptDir "daily_quant_lab_runner.py"

"[$(Get-Date -Format o)] Starting daily quant_lab wrapper" | Out-File -FilePath $StdoutLog -Encoding utf8
"ProjectRoot=$ProjectRoot" | Out-File -FilePath $StdoutLog -Encoding utf8 -Append
"Config=$Config" | Out-File -FilePath $StdoutLog -Encoding utf8 -Append
"Python=$Python" | Out-File -FilePath $StdoutLog -Encoding utf8 -Append
"" | Out-File -FilePath $StderrLog -Encoding utf8

Set-Location $ProjectRoot

if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    "Configured Python does not exist: $Python" | Out-File -FilePath $StderrLog -Encoding utf8 -Append
    exit 2
}

$RunnerArgs = @(
    $Runner,
    "--config", $Config
)
if ($DryRun) {
    $RunnerArgs += "--dry-run"
}
if ($SkipUpdate) {
    $RunnerArgs += "--skip-update"
}
if ($SkipStrategy) {
    $RunnerArgs += "--skip-strategy"
}
if (-not [string]::IsNullOrWhiteSpace($Date)) {
    $RunnerArgs += @("--date", $Date)
}
if ($MaxRuntimeMinutes -gt 0) {
    $RunnerArgs += @("--max-runtime-minutes", [string]$MaxRuntimeMinutes)
}
if ($AllowDirty) {
    $RunnerArgs += "--allow-dirty"
}

function ConvertTo-ProcessArgument {
    param([string]$Value)
    if ($Value -match '[\s"]') {
        return '"' + ($Value -replace '"', '\"') + '"'
    }
    return $Value
}

$Psi = New-Object System.Diagnostics.ProcessStartInfo
$Psi.FileName = $Python
$Psi.Arguments = (($RunnerArgs | ForEach-Object { ConvertTo-ProcessArgument $_ }) -join " ")
$Psi.WorkingDirectory = [string]$ProjectRoot
$Psi.UseShellExecute = $false
$Psi.RedirectStandardOutput = $true
$Psi.RedirectStandardError = $true

$Process = New-Object System.Diagnostics.Process
$Process.StartInfo = $Psi
[void]$Process.Start()
$RunnerStdout = $Process.StandardOutput.ReadToEnd()
$RunnerStderr = $Process.StandardError.ReadToEnd()
$Process.WaitForExit()
$ExitCode = $Process.ExitCode

if (-not [string]::IsNullOrEmpty($RunnerStdout)) {
    $RunnerStdout | Out-File -FilePath $StdoutLog -Encoding utf8 -Append
}
if (-not [string]::IsNullOrEmpty($RunnerStderr)) {
    $RunnerStderr | Out-File -FilePath $StderrLog -Encoding utf8 -Append
}

"[$(Get-Date -Format o)] Runner exit code: $ExitCode" | Out-File -FilePath $StdoutLog -Encoding utf8 -Append
exit $ExitCode
