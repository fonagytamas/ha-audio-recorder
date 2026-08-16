import os
import time
import subprocess
import threading
from datetime import datetime
from flask import Flask, render_template_string, jsonify, request

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

HTML_CODE = """
<!DOCTYPE html>
<html lang="hu">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Szerver Hangrögzítő</title>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #111b21; color: #fff; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
        .card { background: #202c33; padding: 25px; border-radius: 12px; text-align: center; width: 340px; box-shadow: 0 4px 15px rgba(0,0,0,0.5); }
        h3 { margin-top: 0; color: #e9edef; }
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
        #status { margin-top: 15px; font-size: 13px; color: #aebac1; word-break: break-word; min-height: 36px; }
        #timer { font-size: 14px; font-weight: bold; color: #ea4335; margin-top: 5px; display: none; }
    </style>
</head>
<body>
<div class="card">
    <h3>Szerver Hangrögzítő</h3>
    
    <div class="control-group">
        <div class="row">
            <span style="font-size: 14px;">Zajszűrés aktiválása</span>
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
            <option value="mp3">MP3 (Tömörített - kis méret)</option>
            <option value="wav">WAV (Eredeti - nagy méret)</option>
        </select>
    </div>

    <button id="recBtn" onclick="startRec()">Indítás</button>
    <button id="stopBtn" onclick="stopRec()" disabled>Leállítás</button>
    
    <div id="timer">🔴 Rögzítés: <span id="timeVal">00:00</span></div>
    <div id="status">Készenlétben</div>
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
            const res = await fetch('status');
            const data = await res.json();
            
            if (data.is_recording) {
                document.getElementById('recBtn').disabled = true;
                document.getElementById('stopBtn').disabled = false;
                document.getElementById('status').innerText = "🔴 Folyamatban lévő rögzítés...";
                document.getElementById('timer').style.display = "block";
                
                if (timerInterval) clearInterval(timerInterval);
                updateTimer(data.start_time);
                timerInterval = setInterval(() => updateTimer(data.start_time), 1000);
            } else {
                if (timerInterval) clearInterval(timerInterval);
                document.getElementById('timer').style.display = "none";
                document.getElementById('recBtn').disabled = false;
                document.getElementById('stopBtn').disabled = true;
                if (!document.getElementById('status').innerText.includes("💾")) {
                    document.getElementById('status').innerText = "Készenlétben";
                }
            }
        } catch (err) {
            console.error("Státusz ellenőrzési hiba", err);
        }
    }

    async function startRec() {
        document.getElementById('status').innerText = "⏳ Indítás...";
        try {
            const res = await fetch('start', { method: 'POST' });
            const data = await res.json();
            if (data.status === 'ok') {
                checkStatus();
            } else {
                document.getElementById('status').innerText = "❌ Hiba: " + data.message;
            }
        } catch (err) {
            document.getElementById('status').innerText = "❌ Hálózati hiba!";
        }
    }

    async function stopRec() {
        document.getElementById('status').innerText = "⏳ Feldolgozás és mentés...";
        document.getElementById('recBtn').disabled = true;
        document.getElementById('stopBtn').disabled = true;

        const payload = {
            filter: document.getElementById('filterEnable').checked,
            strength: parseInt(document.getElementById('filterStrength').value),
            format: document.getElementById('formatSelect').value
        };

        try {
            const res = await fetch('stop', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const data = await res.json();
            if (data.status === 'stopped') {
                document.getElementById('status').innerText = "💾 Mentve! (" + payload.format.toUpperCase() + ")";
            } else {
                document.getElementById('status').innerText = "⚠️ Leállítva.";
            }
        } catch (err) {
            document.getElementById('status').innerText = "❌ Hiba a feldolgozás során!";
        } finally {
            checkStatus();
        }
    }

    // Oldal betöltésekor és visszatéréskor ellenőrizzük az állapotot
    checkStatus();
    setInterval(checkStatus, 3000); // 3 másodpercenként szinkronizál a szerverrel
</script>
</body>
</html>
"""

def process_audio_file(wav_path, filter_enabled, strength, output_format):
    """FFmpeg segítségével zajszűrést végez és a kiválasztott formátumba ment."""
    if not os.path.exists(wav_path):
        return

    output_path = wav_path.replace(".wav", f".{output_format}")

    filters = []
    if filter_enabled:
        hp = int(50 + (strength / 100.0) * 250)
        lp = int(8000 - (strength / 100.0) * 5500)
        nr = int(10 + (strength / 100.0) * 30)

        filters.append(f"highpass=f={hp}")
        filters.append(f"lowpass=f={lp}")
        filters.append(f"afftdn=nr={nr}")
    
    filters.append("loudnorm")
    filter_str = ",".join(filters)

    cmd = ["ffmpeg", "-y", "-i", wav_path]
    if filter_str:
        cmd.extend(["-af", filter_str])

    if output_format == "mp3":
        cmd.extend(["-b:a", "96k", output_path])
    else:
        temp_wav = wav_path.replace(".wav", "_clean.wav")
        cmd.append(temp_wav)

    try:
        subprocess.run(cmd, capture_output=True, check=True)
        if output_format == "wav" and os.path.exists(temp_wav):
            os.replace(temp_wav, wav_path)
        elif output_format == "mp3" and os.path.exists(output_path):
            os.remove(wav_path)
    except Exception as e:
        print(f"FFmpeg hiba: {e}")

@app.route('/')
def index():
    ensure_dir_exists()
    return render_template_string(HTML_CODE)

@app.route('/status', methods=['GET'])
def get_status():
    global recording_process, recording_start_time
    is_recording = recording_process is not None and recording_process.poll() is None
    return jsonify({
        "is_recording": is_recording,
        "start_time": recording_start_time if is_recording else None
    })

@app.route('/start', methods=['POST'])
def start_recording():
    global recording_process, current_wav_file, recording_start_time
    ensure_dir_exists()

    if recording_process is None or recording_process.poll() is not None:
        # Év-Hónap-Nap_Óra-Perc formátumú fájlnév (pl. rec_2026-08-16_09-46.wav)
        now_str = datetime.now().strftime("%Y-%m-%d_%H-%M")
        current_wav_file = os.path.join(SAVE_DIR, f"rec_{now_str}.wav")
        recording_start_time = int(time.time())

        cmd = ["arecord", "-D", "plughw:0,0", "-f", "S16_LE", "-r", "44100", "-c", "1", current_wav_file]
        try:
            recording_process = subprocess.Popen(cmd, stderr=subprocess.PIPE)
            time.sleep(0.5)
            
            if recording_process.poll() is not None:
                # Fallback a default eszközre
                cmd_fb = ["arecord", "-f", "S16_LE", "-r", "44100", "-c", "1", current_wav_file]
                recording_process = subprocess.Popen(cmd_fb, stderr=subprocess.PIPE)
                time.sleep(0.5)
                
                if recording_process.poll() is not None:
                    _, err_fb = recording_process.communicate()
                    recording_process = None
                    recording_start_time = None
                    return jsonify({"status": "error", "message": err_fb.decode('utf-8', errors='ignore')})

            return jsonify({"status": "ok"})
        except Exception as e:
            recording_process = None
            recording_start_time = None
            return jsonify({"status": "error", "message": str(e)})

    return jsonify({"status": "already_running"})

@app.route('/stop', methods=['POST'])
def stop_recording():
    global recording_process, current_wav_file, recording_start_time
    data = request.get_json() or {}
    
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
            threading.Thread(
                target=process_audio_file,
                args=(current_wav_file, filter_enabled, strength, output_format)
            ).start()

        return jsonify({"status": "stopped"})

    return jsonify({"status": "not_running"})

if __name__ == '__main__':
    ensure_dir_exists()
    app.run(host='0.0.0.0', port=8099)
