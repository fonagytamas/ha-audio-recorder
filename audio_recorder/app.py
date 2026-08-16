import os
import time
import subprocess
from datetime import datetime
from flask import Flask, render_template_string, jsonify, request, send_from_directory

app = Flask(__name__)

SAVE_DIR = "/config/www/recordings"

def ensure_dir_exists():
    try:
        os.makedirs(SAVE_DIR, exist_ok=True)
        os.chmod("/config/www", 0o777)
        os.chmod(SAVE_DIR, 0o777)
    except Exception as e:
        print(f"Mappa hiba: {e}")

recording_process = None
current_wav_file = None
recording_start_time = None
last_processed_file = None
last_error_log = ""

HTML_CODE = """
<!DOCTYPE html>
<html lang="hu">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>JARVIS Education</title>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #111b21; color: #fff; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; padding: 20px 0; }
        .card { background: #202c33; padding: 25px; border-radius: 12px; text-align: center; width: 360px; box-shadow: 0 4px 15px rgba(0,0,0,0.5); }
        h3 { margin-top: 0; color: #00a884; letter-spacing: 1px; }
        .control-group { margin: 12px 0; text-align: left; background: #111b21; padding: 12px; border-radius: 8px; }
        label { font-size: 13px; color: #8696a0; display: block; margin-bottom: 5px; }
        .row { display: flex; justify-content: space-between; align-items: center; }
        select, input[type=range] { width: 100%; margin-top: 5px; }
        input[type=checkbox] { transform: scale(1.3); cursor: pointer; }
        .slider-val { font-size: 12px; color: #00a884; font-weight: bold; float: right; }
        button { padding: 12px 20px; font-size: 15px; border: none; border-radius: 6px; cursor: pointer; margin: 8px 4px 0 4px; font-weight: bold; width: 45%; }
        #recBtn { background: #00a884; color: white; }
        #stopBtn { background: #ea4335; color: white; }
        button:disabled { opacity: 0.3; cursor: not-allowed; }
        #status { margin-top: 12px; font-size: 13px; color: #aebac1; word-break: break-word; min-height: 24px; }
        #timer { font-size: 14px; font-weight: bold; color: #ea4335; margin-top: 5px; display: none; }
        .player-box { margin-top: 15px; background: #111b21; padding: 12px; border-radius: 8px; text-align: left; display: none; }
        audio { width: 100%; margin-top: 8px; height: 35px; }
        #logBox { font-size: 11px; color: #ff6b6b; margin-top: 10px; text-align: left; white-space: pre-wrap; word-break: break-all; }
    </style>
</head>
<body>
<div class="card">
    <h3>JARVIS Education</h3>
    
    <div class="control-group">
        <label>Hangerő kiemelés (Gain) <span class="slider-val" id="gainVal">+15 dB</span></label>
        <input type="range" id="gainBoost" min="0" max="30" value="15" oninput="document.getElementById('gainVal').innerText = '+' + this.value + ' dB'">
    </div>

    <div class="control-group">
        <div class="row">
            <span style="font-size: 14px;">Intelligens Zajszűrés</span>
            <input type="checkbox" id="filterEnable" checked onchange="toggleFilter()">
        </div>
    </div>

    <div class="control-group" id="noiseGroup">
        <label>Szűrés erőssége <span class="slider-val" id="filterVal">50%</span></label>
        <input type="range" id="filterStrength" min="10" max="100" value="50" oninput="document.getElementById('filterVal').innerText = this.value + '%'">
    </div>

    <div class="control-group">
        <label>Kimeneti formátum</label>
        <select id="formatSelect">
            <option value="mp3">MP3 (Tömörített)</option>
            <option value="wav">WAV (Eredeti)</option>
        </select>
    </div>

    <button id="recBtn" onclick="startRec()">Indítás</button>
    <button id="stopBtn" onclick="stopRec()" disabled>Leállítás</button>
    
    <div id="timer">🔴 Rögzítés: <span id="timeVal">00:00</span></div>
    <div id="status">Készenlétben</div>

    <div class="player-box" id="playerBox">
        <label style="color:#00a884; font-weight:bold;">Azonnali Teszt Lejátszás:</label>
        <audio id="audioPlayer" controls></audio>
    </div>

    <div id="logBox"></div>
</div>

<script>
    let timerInterval = null;

    function toggleFilter() {
        const enabled = document.getElementById('filterEnable').checked;
        document.getElementById('noiseGroup').style.opacity = enabled ? "1" : "0.4";
        document.getElementById('filterStrength').disabled = !enabled;
    }

    function updateTimer(startTimeSeconds) {
        const now = Math.floor(Date.now() / 1000);
        const elapsed = now - startTimeSeconds;
        const mins = String(Math.floor(elapsed / 60)).padStart(2, '0');
        const secs = String(elapsed % 60).padStart(2, '0');
        document.getElementById('timeVal').innerText = `${mins}:${secs}`;
    }

    async function checkStatus() {
        try {
            const res = await fetch('./status');
            const data = await res.json();
            
            if (data.is_recording) {
                document.getElementById('recBtn').disabled = true;
                document.getElementById('stopBtn').disabled = false;
                document.getElementById('status').innerText = "🔴 Rögzítés folyamatban...";
                document.getElementById('timer').style.display = "block";
                
                if (timerInterval) clearInterval(timerInterval);
                updateTimer(data.start_time);
                timerInterval = setInterval(() => updateTimer(data.start_time), 1000);
            } else {
                if (timerInterval) clearInterval(timerInterval);
                document.getElementById('timer').style.display = "none";
                document.getElementById('recBtn').disabled = false;
                document.getElementById('stopBtn').disabled = true;
                
                if (!document.getElementById('status').innerText.includes("💾") && 
                    !document.getElementById('status').innerText.includes("⏳")) {
                    document.getElementById('status').innerText = "Készenlétben";
                }
            }

            if (data.last_error) {
                document.getElementById('logBox').innerText = "Hiba:\n" + data.last_error;
            }
        } catch (err) {
            console.error("Státusz hiba", err);
        }
    }

    async function startRec() {
        document.getElementById('recBtn').disabled = true;
        document.getElementById('status').innerText = "⏳ Indítás...";
        document.getElementById('playerBox').style.display = "none";
        document.getElementById('logBox').innerText = "";
        
        try {
            const res = await fetch('./start', { method: 'POST' });
            const data = await res.json();
            if (data.status === 'ok') {
                checkStatus();
            } else {
                document.getElementById('status').innerText = "❌ Hiba történt!";
                document.getElementById('logBox').innerText = data.message || "Ismeretlen hiba";
                document.getElementById('recBtn').disabled = false;
            }
        } catch (err) {
            document.getElementById('status').innerText = "❌ Hálózati hiba!";
            document.getElementById('logBox').innerText = err.toString();
            document.getElementById('recBtn').disabled = false;
        }
    }

    async function stopRec() {
        document.getElementById('status').innerText = "⏳ Tisztítás és feldolgozás...";
        document.getElementById('recBtn').disabled = true;
        document.getElementById('stopBtn').disabled = true;

        const payload = {
            gain: parseInt(document.getElementById('gainBoost').value),
            filter: document.getElementById('filterEnable').checked,
            strength: parseInt(document.getElementById('filterStrength').value),
            format: document.getElementById('formatSelect').value
        };

        try {
            const res = await fetch('./stop', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const data = await res.json();
            if (data.status === 'stopped') {
                document.getElementById('status').innerText = "💾 Feldolgozás befejezve!";
                loadPlayer();
            } else {
                document.getElementById('status').innerText = "⚠️ Leállítva.";
            }
        } catch (err) {
            document.getElementById('status').innerText = "❌ Hiba a feldolgozás során!";
        } finally {
            checkStatus();
        }
    }

    async function loadPlayer() {
        try {
            const res = await fetch('./latest');
            const data = await res.json();
            if (data.file) {
                const player = document.getElementById('audioPlayer');
                player.src = "./recordings_file/" + data.file + "?t=" + new Date().getTime();
                document.getElementById('playerBox').style.display = "block";
                document.getElementById('status').innerText = "💾 Mentve! Hallgasd meg alább:";
            }
        } catch (e) {
            console.error("Lejátszó hiba", e);
        }
    }

    checkStatus();
    setInterval(checkStatus, 3000);
</script>
</body>
</html>
"""

def process_audio_file(wav_path, gain_db, filter_enabled, strength, output_format):
    global last_processed_file, last_error_log
    if not os.path.exists(wav_path):
        return

    output_filename = os.path.basename(wav_path).replace(".wav", f".{output_format}")
    output_path = os.path.join(SAVE_DIR, output_filename)

    filters = []

    if gain_db > 0:
        filters.append(f"volume={gain_db}dB")

    if filter_enabled:
        hp = int(40 + (strength / 100.0) * 200)
        lp = int(12000 - (strength / 100.0) * 8000)
        filters.append(f"highpass=f={hp}")
        filters.append(f"lowpass=f={lp}")
        nr = int(12 + (strength / 100.0) * 28)
        filters.append(f"afftdn=nr={nr}:nf=-40")

    filters.append("compand=attacks=0.02:decays=0.2:points=-80/-80|-45/-20|-10/-6|0/0")
    filters.append("loudnorm=I=-14:TP=-1.0:LRA=11")

    filter_str = ",".join(filters)
    temp_output = os.path.join(SAVE_DIR, f"proc_{int(time.time())}.{output_format}")

    cmd = ["ffmpeg", "-y", "-i", wav_path, "-af", filter_str]

    if output_format == "mp3":
        cmd.extend(["-b:a", "128k", temp_output])
    else:
        cmd.append(temp_output)

    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        last_error_log = ""

        if os.path.exists(temp_output):
            os.replace(temp_output, output_path)
            if output_path != wav_path and os.path.exists(wav_path):
                os.remove(wav_path)

        last_processed_file = output_filename
    except subprocess.CalledProcessError as e:
        last_error_log = e.stderr if e.stderr else str(e)
        last_processed_file = os.path.basename(wav_path)

@app.route('/')
def index():
    ensure_dir_exists()
    return render_template_string(HTML_CODE)

@app.route('/recordings_file/<filename>')
def serve_file(filename):
    return send_from_directory(SAVE_DIR, filename)

@app.route('/latest', methods=['GET'])
def get_latest():
    global last_processed_file
    return jsonify({"file": last_processed_file})

@app.route('/status', methods=['GET'])
def get_status():
    global recording_process, recording_start_time, last_error_log
    is_recording = recording_process is not None and recording_process.poll() is None
    return jsonify({
        "is_recording": is_recording,
        "start_time": recording_start_time if is_recording else None,
        "last_error": last_error_log
    })

@app.route('/start', methods=['POST'])
def start_recording():
    global recording_process, current_wav_file, recording_start_time, last_error_log
    ensure_dir_exists()
    last_error_log = ""

    if recording_process is not None and recording_process.poll() is None:
        try:
            recording_process.kill()
        except Exception:
            pass
        recording_process = None

    now_str = datetime.now().strftime("%Y-%m-%d_%H-%M")
    current_wav_file = os.path.join(SAVE_DIR, f"rec_{now_str}.wav")
    recording_start_time = int(time.time())

    cmd = ["arecord", "-f", "S16_LE", "-r", "44100", "-c", "1", current_wav_file]
    
    try:
        recording_process = subprocess.Popen(cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
        time.sleep(0.3)
        
        if recording_process.poll() is not None:
            _, err = recording_process.communicate()
            err_text = err.decode('utf-8', errors='ignore') if err else "Ismeretlen arecord hiba"
            recording_process = None
            recording_start_time = None
            last_error_log = err_text
            return jsonify({"status": "error", "message": err_text})

        return jsonify({"status": "ok"})
    except Exception as e:
        recording_process = None
        recording_start_time = None
        last_error_log = str(e)
        return jsonify({"status": "error", "message": str(e)})

@app.route('/stop', methods=['POST'])
def stop_recording():
    global recording_process, current_wav_file, recording_start_time
    data = request.get_json() or {}
    
    gain = data.get('gain', 15)
    filter_enabled = data.get('filter', True)
    strength = data.get('strength', 50)
    output_format = data.get('format', 'mp3')

    if recording_process is not None:
        try:
            recording_process.terminate()
            recording_process.wait(timeout=2)
        except Exception:
            recording_process.kill()
        
        recording_process = None
        recording_start_time = None

        if current_wav_file and os.path.exists(current_wav_file):
            process_audio_file(current_wav_file, gain, filter_enabled, strength, output_format)

        return jsonify({"status": "stopped"})

    return jsonify({"status": "not_running"})

if __name__ == '__main__':
    ensure_dir_exists()
    app.run(host='0.0.0.0', port=8099)
