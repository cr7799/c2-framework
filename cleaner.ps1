# ==============================================
# COMPLETE CLEANUP – Remove Backdoor & Persistence
# ==============================================

Write-Host "Starting full cleanup..." -ForegroundColor Cyan

# 1. Kill any running backdoor processes (using WMI to get command line)
Write-Host "[1] Stopping backdoor PowerShell processes..."
$backdoorProcs = Get-CimInstance -ClassName Win32_Process -Filter "Name = 'powershell.exe'" | Where-Object {
    $_.CommandLine -like "*backdoor.ps1*"
}
foreach ($proc in $backdoorProcs) {
    Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
    Write-Host "  Killed PID $($proc.ProcessId)"
}

# 2. Delete installed files
Write-Host "[2] Deleting installed files..."
Remove-Item -Path "C:\Users\Public\backdoor.ps1" -Force -ErrorAction SilentlyContinue
Remove-Item -Path "C:\Users\Public\installer.ps1" -Force -ErrorAction SilentlyContinue
Remove-Item -Path "$env:TEMP\cam.exe" -Force -ErrorAction SilentlyContinue

# 3. Remove registry Run keys (both HKCU and HKLM)
Write-Host "[3] Removing registry persistence..."
$regPaths = @(
    "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run",
    "HKLM:\Software\Microsoft\Windows\CurrentVersion\Run"
)
foreach ($path in $regPaths) {
    Remove-ItemProperty -Path $path -Name "WindowsUpdate" -ErrorAction SilentlyContinue
    Write-Host "  Removed from $path"
}

# 4. Remove scheduled task (if created)
Write-Host "[4] Removing scheduled task..."
Unregister-ScheduledTask -TaskName "WindowsUpdateService" -Confirm:$false -ErrorAction SilentlyContinue
Write-Host "  Removed 'WindowsUpdateService' (if existed)"

# 5. Remove Windows Defender exclusions
Write-Host "[5] Removing Windows Defender exclusions..."
Remove-MpPreference -ExclusionPath "C:\Users\Public" -ErrorAction SilentlyContinue
Remove-MpPreference -ExclusionPath "$env:TEMP" -ErrorAction SilentlyContinue
Write-Host "  Removed Defender exclusions"

Write-Host "`nCleanup complete! The backdoor should no longer be active." -ForegroundColor Green
Write-Host "You may restart the computer to ensure all processes are fully terminated." -ForegroundColor Yellow