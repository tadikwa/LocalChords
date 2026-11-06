# Start the built program as a user would, with a file on the command line, at zero volume, in a
# data folder of its own. Real window, real keyboard input, real screen capture.
param([string]$Audio, [string]$Out)
$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force $Out | Out-Null
$data = Join-Path (Resolve-Path $Out) "data"
New-Item -ItemType Directory -Force $data | Out-Null
'{"volume": 0.0}' | Set-Content -Encoding utf8 (Join-Path $data "settings.json")
$env:LOCALCHORDS_DATA = $data

Add-Type -AssemblyName System.Windows.Forms, System.Drawing
Add-Type @"
using System; using System.Runtime.InteropServices;
public class W {
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c);
  public struct RECT { public int L, T, R, B; }
}
"@

function Shot($process, $name) {
    $process.Refresh()
    $r = New-Object W+RECT
    [W]::GetWindowRect($process.MainWindowHandle, [ref]$r) | Out-Null
    $bmp = New-Object Drawing.Bitmap ($r.R - $r.L), ($r.B - $r.T)
    $g = [Drawing.Graphics]::FromImage($bmp)
    $g.CopyFromScreen($r.L, $r.T, 0, 0, $bmp.Size)
    $bmp.Save((Join-Path $Out $name))
    $g.Dispose(); $bmp.Dispose()
}

$watch = [Diagnostics.Stopwatch]::StartNew()
$exe = Resolve-Path "dist\LocalChords\LocalChords.exe"
$p = Start-Process -FilePath $exe -ArgumentList "`"$Audio`"" -PassThru
while ($p.MainWindowHandle -eq 0 -and $watch.Elapsed.TotalSeconds -lt 60) {
    Start-Sleep -Milliseconds 50; $p.Refresh()
}
"window after {0:N2} s" -f $watch.Elapsed.TotalSeconds
Start-Sleep -Seconds 1
Shot $p "real_1_analyzing.png"

# The analysis is done when its project file exists.
$projects = Join-Path $data "projects"
while (-not (Test-Path "$projects\*.lchords") -and $watch.Elapsed.TotalSeconds -lt 300) {
    Start-Sleep -Milliseconds 200
}
"analysis saved after {0:N1} s" -f $watch.Elapsed.TotalSeconds
Start-Sleep -Seconds 1
[W]::SetForegroundWindow($p.MainWindowHandle) | Out-Null
Start-Sleep -Milliseconds 300
[Windows.Forms.SendKeys]::SendWait(" ")   # play
Start-Sleep -Seconds 4
Shot $p "real_2_playing.png"
[Windows.Forms.SendKeys]::SendWait("^{UP}")  # transpose
Start-Sleep -Milliseconds 300
[Windows.Forms.SendKeys]::SendWait(" ")   # pause
Start-Sleep -Milliseconds 300
Shot $p "real_3_paused_transposed.png"
$p.Refresh()
"alive: {0}, memory of the interface: {1:N0} MB" -f (-not $p.HasExited), ($p.WorkingSet64 / 1MB)
$p.CloseMainWindow() | Out-Null
if (-not $p.WaitForExit(10000)) { "did not close by itself"; $p.Kill() } else { "closed, exit code {0}" -f $p.ExitCode }
Get-ChildItem $projects | Select-Object Name, Length | Format-Table -AutoSize
$view = (Get-Content (Get-ChildItem "$projects\*.lchords")[0].FullName -Raw -Encoding utf8 | ConvertFrom-Json).view
"saved transpose: {0}" -f $view.transpose
