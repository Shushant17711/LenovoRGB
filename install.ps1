# Lenovo RGB - Windows installer / uninstaller
# Usage:
#   powershell -ExecutionPolicy Bypass -File install.ps1
#   powershell -ExecutionPolicy Bypass -File install.ps1 -Elevated
#
[CmdletBinding()]
param(
    [switch]$NoAutostart,
    [switch]$NoShortcut,
    [switch]$Elevated,
    [switch]$Dev,
    [switch]$BuildExe,
    [switch]$Uninstall,
    [switch]$Purge
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $Root

$Venv = Join-Path $Root ".venv"
$PythonExe = Join-Path $Venv "Scripts\python.exe"
$PythonwExe = Join-Path $Venv "Scripts\pythonw.exe"
$GuiExe = Join-Path $Venv "Scripts\lenovorgb-gui.exe"
$StartMenu = [Environment]::GetFolderPath("Programs")
$ShortcutPath = Join-Path $StartMenu "Lenovo RGB.lnk"
$RunKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
$TaskName = "LenovoRGB"

function Write-Step($Message) { Write-Host "`n$Message" -ForegroundColor Cyan }
function Write-Ok($Message) { Write-Host "  [ok] $Message" -ForegroundColor Green }
function Write-Warn($Message) { Write-Host "  [!]  $Message" -ForegroundColor Yellow }
function Write-Die($Message) {
    Write-Host "`n[error] $Message" -ForegroundColor Red
    exit 1
}

function Remove-Shortcuts {
    foreach ($path in @($ShortcutPath, (Join-Path ([Environment]::GetFolderPath("Desktop")) "Lenovo RGB.lnk"))) {
        if (Test-Path $path) {
            Remove-Item $path -Force
            Write-Ok "Removed shortcut: $path"
        }
    }
}

# ----------------------------------------------------------------- uninstall
if ($Uninstall) {
    Write-Step "Uninstalling Lenovo RGB"
    try {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue | Out-Null
        Write-Ok "Removed scheduled task (if it existed)."
    } catch { }
    try {
        Remove-ItemProperty -Path $RunKey -Name "LenovoRGB" -ErrorAction SilentlyContinue
        Write-Ok "Removed login entry (if it existed)."
    } catch { }
    Remove-Shortcuts
    if ($Purge) {
        foreach ($path in @((Join-Path $env:APPDATA "LenovoRGB"), (Join-Path $env:LOCALAPPDATA "LenovoRGB"))) {
            if (Test-Path $path) {
                Remove-Item $path -Recurse -Force
                Write-Ok "Removed $path"
            }
        }
    }
    if (Test-Path $Venv) {
        Remove-Item $Venv -Recurse -Force
        Write-Ok "Removed .venv"
    }
    Write-Host "`nLenovo RGB was uninstalled.`n" -ForegroundColor Green
    exit 0
}

# ------------------------------------------------------------------- python
Write-Step "Looking for Python 3.9+"
$BasePython = $null
foreach ($name in @("py", "python", "python3")) {
    $command = Get-Command $name -ErrorAction SilentlyContinue
    if (-not $command) { continue }
    try {
        if ($name -eq "py") {
            $candidate = (& py -3 -c "import sys; print(sys.executable)" 2>$null)
        } else {
            $candidate = (& $command.Source -c "import sys; print(sys.executable)" 2>$null)
        }
        if ($candidate -and (Test-Path $candidate)) {
            $supported = (& $candidate -c "import sys; print(sys.version_info >= (3, 9))" 2>$null)
            if ($supported -eq "True") {
                $BasePython = $candidate
                break
            }
        }
    } catch { }
}
if (-not $BasePython) {
    Write-Die "Python 3.9+ was not found. Install it from https://www.python.org/downloads/windows/ and tick 'Add python.exe to PATH'."
}
Write-Ok "Using $BasePython"

# --------------------------------------------------------------------- venv
Write-Step "Installing Python packages"
if (-not (Test-Path $PythonExe)) {
    & $BasePython -m venv $Venv
    if ($LASTEXITCODE -ne 0) { Write-Die "Could not create the virtual environment." }
}
& $PythonExe -m pip install --upgrade pip wheel | Out-Null
$extras = if ($Dev) { "all,dev" } else { "all" }
& $PythonExe -m pip install -e ".[$extras]"
if ($LASTEXITCODE -ne 0) { Write-Die "pip install failed. Check your internet connection and try again." }
Write-Ok "Packages installed."

# ----------------------------------------------------------------- shortcut
if (-not $NoShortcut -and (Test-Path $GuiExe)) {
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($ShortcutPath)
    $shortcut.TargetPath = $GuiExe
    $shortcut.WorkingDirectory = $Root
    $shortcut.IconLocation = (Join-Path $Root "packaging\icon.ico")
    $shortcut.Description = "Lenovo RGB keyboard control"
    $shortcut.Save()
    Write-Ok "Start Menu shortcut created."
}

# ---------------------------------------------------------------- autostart
if (-not $NoAutostart) {
    if ($Elevated) {
        if (Test-Path $GuiExe) {
            try {
                $action = New-ScheduledTaskAction -Execute $GuiExe -WorkingDirectory $Root
                $trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
                $principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" `
                    -LogonType Interactive -RunLevel Highest
                $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
                Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
                    -Principal $principal -Settings $settings -Force | Out-Null
                Remove-ItemProperty -Path $RunKey -Name "LenovoRGB" -ErrorAction SilentlyContinue
                Write-Ok "Scheduled task installed (runs elevated at login)."
            } catch {
                Write-Warn "Could not create the elevated scheduled task (start PowerShell as Administrator)."
                Write-Warn "Falling back to the current-user login entry."
                & $PythonExe -m lenovorgb autostart enable | Out-Null
            }
        }
    } else {
        & $PythonExe -m lenovorgb autostart enable | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Write-Ok "Launch at login enabled (HKCU Run)."
        } else {
            Write-Warn "Could not enable launch at login. Run: .venv\Scripts\python -m lenovorgb autostart enable"
        }
    }
}

# ------------------------------------------------------------------ build exe
if ($BuildExe) {
    Write-Step "Building LenovoRGB.exe"
    & $PythonExe -m pip install "pyinstaller>=6.6" | Out-Null
    & $PythonExe -m PyInstaller --noconfirm "packaging\LenovoRGB.spec"
    if ($LASTEXITCODE -ne 0) { Write-Die "PyInstaller failed." }
    Write-Ok "Executable: $Root\dist\LenovoRGB.exe"
}

# --------------------------------------------------------------------- done
Write-Step "Done"
$Summary = @"
  Open the app     .venv\Scripts\lenovorgb-gui.exe
  Command line     .venv\Scripts\lenovorgb.exe list
  Run a mode       .venv\Scripts\lenovorgb.exe run aurora
  Turn lights off  .venv\Scripts\lenovorgb.exe off
  Troubleshoot     .venv\Scripts\lenovorgb.exe doctor
"@
Write-Host $Summary -ForegroundColor Gray
Write-Host "If the keyboard is not detected, open Lenovo Vantage once and set lighting to Static," -ForegroundColor Yellow
Write-Host "then unplug and re-plug the keyboard. Use -Elevated if Windows blocks HID access." -ForegroundColor Yellow
Write-Host ""
