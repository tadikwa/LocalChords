# Time from launch to window, and what a one-file build leaves in %TEMP%: run, wait for the window
# (which a one-file build's child process owns, not the process started), measure _MEI folders,
# close it like a user would, then check what remains.
#   scripts\launch_time.ps1 <exe> <runs> [kill]
# With "kill", the last run ends by killing the processes instead, as Task Manager would.
param([string]$Exe, [int]$Runs = 3, [string]$Mode = "close")
$ErrorActionPreference = "Stop"
$temp = [IO.Path]::GetTempPath()
# Its own data folder: the user's settings and songs stay out of it.
$env:LOCALCHORDS_DATA = Join-Path (Get-Location) "work\launch_data"
function MeiFolders { @(Get-ChildItem $temp -Directory -Filter "_MEI*" -ErrorAction SilentlyContinue) }
function SizeMB($dirs) {
    $sum = 0
    foreach ($d in $dirs) {
        $sum += (Get-ChildItem $d.FullName -Recurse -File -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum
    }
    [math]::Round($sum / 1MB, 1)
}
$name = [IO.Path]::GetFileNameWithoutExtension($Exe)
$before = MeiFolders | ForEach-Object FullName
for ($i = 1; $i -le $Runs; $i++) {
    $watch = [Diagnostics.Stopwatch]::StartNew()
    $p = Start-Process -FilePath $Exe -PassThru
    $window = $null
    while (-not $window -and $watch.Elapsed.TotalSeconds -lt 120) {
        Start-Sleep -Milliseconds 25
        $window = Get-Process -Name $name -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
    }
    $seconds = $watch.Elapsed.TotalSeconds
    Start-Sleep -Seconds 2
    $new = MeiFolders | Where-Object { $before -notcontains $_.FullName }
    $procs = @(Get-Process -Name $name -ErrorAction SilentlyContinue).Count
    $last = ($i -eq $Runs -and $Mode -eq "kill")
    if ($last) {
        Get-Process -Name $name -ErrorAction SilentlyContinue | Stop-Process -Force
    } else {
        $window.CloseMainWindow() | Out-Null
    }
    $p.WaitForExit(60000) | Out-Null
    Start-Sleep -Seconds 2
    $left = MeiFolders | Where-Object { $before -notcontains $_.FullName }
    "run {0}: window {1:N2} s, processes {2}, _MEI while running {3} MB, after {4}: {5} folder(s), {6} MB" -f `
        $i, $seconds, $procs, (SizeMB $new), ($(if ($last) { "kill" } else { "close" })), @($left).Count, (SizeMB $left)
}
