# Does a keystroke reach the built program, and does its effect reach the saved file? Reports whether
# the program really had the foreground when each key went out, so a stolen focus can't pass for a bug.
param([string]$Audio, [string]$Out, [int]$Tries = 3)
$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force $Out | Out-Null
$data = Join-Path (Resolve-Path $Out) "data"
New-Item -ItemType Directory -Force $data | Out-Null
'{"volume": 0.0}' | Set-Content -Encoding utf8 (Join-Path $data "settings.json")
$env:LOCALCHORDS_DATA = $data
Add-Type -AssemblyName System.Windows.Forms
Add-Type @"
using System; using System.Runtime.InteropServices;
public class K {
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern void keybd_event(byte k, byte s, uint f, UIntPtr e);
}
"@
$p = Start-Process -FilePath (Resolve-Path "dist\LocalChords\LocalChords.exe") -ArgumentList "`"$Audio`"" -PassThru
$projects = Join-Path $data "projects"
$watch = [Diagnostics.Stopwatch]::StartNew()
while (-not (Test-Path "$projects\*.lchords") -and $watch.Elapsed.TotalSeconds -lt 300) { Start-Sleep -Milliseconds 200 }
Start-Sleep -Seconds 2
$p.Refresh()
$sent = 0
for ($i = 0; $i -lt $Tries; $i++) {
    # An ALT tap lets a background process take the foreground, which Windows otherwise refuses.
    [K]::keybd_event(0x12, 0, 0, [UIntPtr]::Zero); [K]::keybd_event(0x12, 0, 2, [UIntPtr]::Zero)
    [K]::SetForegroundWindow($p.MainWindowHandle) | Out-Null
    Start-Sleep -Milliseconds 400
    $front = [K]::GetForegroundWindow() -eq $p.MainWindowHandle
    "try {0}: program in front = {1}" -f ($i + 1), $front
    if ($front) { [Windows.Forms.SendKeys]::SendWait("^{UP}"); $sent++ }
    Start-Sleep -Milliseconds 800
}
"keys sent while in front: $sent"
Start-Sleep -Milliseconds 800
$p.CloseMainWindow() | Out-Null
if (-not $p.WaitForExit(10000)) { "did not close"; $p.Kill() } else { "closed, exit code $($p.ExitCode)" }
$view = (Get-Content (Get-ChildItem "$projects\*.lchords")[0].FullName -Raw -Encoding utf8 | ConvertFrom-Json).view
"saved transpose: $($view.transpose)"
