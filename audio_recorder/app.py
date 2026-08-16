import os
import subprocess
import time
import re
from flask import Flask, render_template_string, request, jsonify, send_from_directory

app = Flask(__name__)

# Mappák beállítása
SAVE_DIR = "/media/jarvis_recordings"
os.makedirs(SAVE_DIR, exist_ok=True)

# Globális állapotváltozók
recording_process = None
current_wav_file = None
last_processed_file = None

# =========================================================
# BEÉPÍTETT HTML FELÜLET
# =========================================================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="hu">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>JARVIS Rögzítő & Hangkezelő</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 30px; background: #121212; color: #fff; }
        .card { background: #1e1e1e; padding: 20px; border-radius: 10px; max-width: 500px; margin: 0 auto; box-shadow: 0 4px 10px rgba(0,0,0,0.5); }
        h2 { text-align: center; color: #00adb5; margin-bottom: 10px; }
        .timer { text-align: center; font-size: 32px; font-weight: bold; color: #ff4757; margin: 15px 0; font-family: monospace; }
        .control-group { margin-bottom: 15px; }
        label { display: block; margin-bottom: 5px; font-weight: bold; }
        input[type=range], select { width: 100%; box-sizing: border-box; }
        button { width: 48%; padding: 12px; border: none; border-radius: 5px; font-size: 16px; cursor: pointer; font-weight: bold; }
        .btn-start { background: #28a745; color: white; }
        .btn-start:disabled { background: #555; cursor: not-allowed; }
        .btn-stop { background: #dc3545; color: white; }
        .btn-stop:disabled { background: #555; cursor: not-allowed; }
        .btn-group { display: flex; justify-content: space-between; margin-top: 15px; }
        audio { width: 100%; margin-top: 20px; display: block; }
        .status { text-align: center; margin-top: 15px; font-style: italic; color: #aaa; }
    </style>
</head>
<body>

<div class="card">
    <h2>JARVIS Felvétel Vezérlő</h2>

    <!-- IDŐSZÁMLÁLÓ -->
    <div class="timer" id="timer">00:00</div>

    <!-- MIKROFON BEMENETI HANGERŐ -->
    <div class="control-group">
        <label for="micVol">Mikrofon Bemeneti Hangerő: <span id="micVolVal">80</span>%</label>
        <input type="range" id="micVol" min="0" max="100" value="80" oninput="updateMicVolume(this.value)">
    </div>

    <!-- UTÓFELDOLGOZÁSI GAIN -->
    <div class="control-group">
        <label for="gain">Utólagos Hangerő Kiemelés (Gain): <span id="gainVal">0</span> dB</label>
        <input type="range" id="gain" min="0" max="30" value="0" oninput="document.getElementById('gainVal').innerText=this.value">
    </div>

    <!-- ZAJSZŰRÉS -->
    <div class="control-group">
        <label>
            <input type="checkbox" id="filter" checked> Intelligens Zajszűrés Be
        </label>
    </div>

    <div class="control-group">
        <label for="strength">Zajszűrés Erőssége: <span id="strengthVal">50</span>%</label>
        <input type="range" id="strength" min="10" max="100" value="50" oninput="document.getElementById('strengthVal').innerText=this.value">
    </div>

    <!-- FORMÁTUM -->
    <div class="control-group">
        <label for="format">Kimeneti Formátum:</label>
        <select id="format" style="padding: 8px; border-radius: 5px; background: #333; color: white; border: 1px solid #555;">
            <option value="mp3" selected>MP3</option>
            <option value="wav">WAV</option>
        </select>
    </div>

    <!-- GOMBOK -->
    <div class="btn-group">
        <button class="btn-start" id="startBtn" onclick="startRecording()">Indítás</button>
        <button class="btn-stop" id="stopBtn" onclick="stopRecording()" disabled>Leállítás</button>
    </div>

    <div class="status" id="statusText">Készenlétben...</div>

    <!-- VISSZAJÁTSZÓ LEJÁTSZÓ -->
    <audio id="audioPlayer" controls></audio>
</div>

<script>
    let timerInterval = null;
    let seconds = 0;

    window.addEventListener('DOMContentLoaded', () => {
        fetch('/get_mic_volume')
            .then(res => res.json())
            .then(data => {
                if (data.status === 'success') {
                    document.getElementById('micVol').value = data.volume;
                    document.getElementById('micVolVal').innerText = data.volume;
                }
            })
            .catch(err => console.error("Hiba a mikrofon hangerő lekérésekor:", err));
    });

    function updateMicVolume(val) {
        document.getElementById('micVolVal').innerText = val;
        fetch('/set_mic_volume', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ volume: parseInt(val) })
        });
    }

    function startTimer() {
        seconds = 0;
        document.getElementById('timer').innerText = "00:00";
        clearInterval(timerInterval);
        timerInterval = setInterval(() => {
            seconds++;
            const mins = String(Math.floor(seconds / 60)).padStart(2, '0');
            const secs = String(seconds % 60).padStart(2, '0');
            document.getElementById('timer').innerText = `${mins}:${secs}`;
        }, 1000);
    }

    function stopTimer() {
        clearInterval(timerInterval);
    }

    function startRecording() {
        document.getElementById('statusText').innerText = "Felvétel indítása...";
        fetch('/start', { method: 'POST' })
            .then(res => res.json())
            .then(data => {
                if (data.status === 'success') {
                    document.getElementById('statusText').innerText = "Felvétel folyamatban...";
                    document.getElementById('startBtn').disabled = true;
                    document.getElementById('stopBtn').disabled = false;
                    startTimer();
                } else {
                    document.getElementById('statusText').innerText = "Hiba: " + data.message;
                }
            })
            .catch(err => {
                document.getElementById('statusText').innerText = "Hálózati hiba az indításkor.";
            });
    }

    function stopRecording() {
        stopTimer();
        document.getElementById('statusText').innerText = "Feldolgozás és zajszűrés (FFmpeg)...";
        document.getElementById('startBtn').disabled = false;
        document.getElementById('stopBtn').disabled = true;

        const payload = {
            gain: parseFloat(document.getElementById('gain').value),
            filter: document.getElementById('filter').checked,
            strength: parseFloat(document.getElementById('strength').value),
            format: document.getElementById('format').value
        };

        fetch('/stop', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        })
        .then(res => res.json())
        .then(data => {
            if (data.status === 'success') {
                document.getElementById('statusText').innerText = "Kész: " + data.file;
                const player = document.getElementById('audioPlayer');
                player.src = '/recordings/' + data.file + '?t=' + new Date().getTime();
                player.play();
            } else {
                document.getElementById('statusText').innerText = "Hiba: " + data.message;
            }
        })
        .catch(err => {
            document.getElementById('statusText').innerText = "Hálózati hiba a feldolgozáskor.";
        });
    }
</script>

</body>
</html>
"""

def process_audio_file(wav_path, gain_db, filter_enabled, strength, output_format):
    global last_processed_file
    if not os.path.exists(wav_path):
        print(f"[HIBA] Nem található a WAV fájl: {wav_path}")
        return

    base_name = os.path.splitext(os.path.basename(wav_path))[0]
    ext = "mp3" if output_format == "mp3" else "wav"
    output_filename = f"{base_name}.{ext}"
    output_path = os.path.join(SAVE_DIR, output_filename)

    filters = []

    if filter_enabled:
        nr_db = int(12 + (strength / 100.0) * 28)
        filters.append(f"afftdn=nr={nr_db}:nf=-50")

        hp = int(80 + (strength / 100.0) * 120)
        lp = int(8000 - (strength / 100.0) * 3500)
        filters.append(f"highpass=f={hp}")
        filters.append(f"lowpass=f={lp}")

    if gain_db > 0:
        filters.append(f"volume={gain_db}dB")

    filters.append("dynaudnorm=f=150:g=15")
    filters.append("alimiter=limit=0.95")

    filter_str = ",".join(filters)

    if output_format == "mp3":
        cmd = [
            "ffmpeg", "-y", 
            "-i", wav_path, 
            "-af", filter_str, 
            "-c:a", "libmp3lame", 
            "-b:a", "128k", 
            output_path
        ]
    else:
        temp_wav = os.path.join(SAVE_DIR, f"temp_{os.path.basename(wav_path)}")
        cmd = ["ffmpeg", "-y", "-i", wav_path, "-af", filter_str, temp_wav]

    try:
        print(f"[INFO] FFmpeg parancs futtatása: {' '.join(cmd)}")
        res = subprocess.run(cmd, capture_output=True, text=True)

        if res.returncode != 0 and output_format == "mp3":
            print("[FIGYELMEZTETÉS] Első FFmpeg próbálkozás sikertelen, próbálkozás alter kódolóval...")
            cmd_fallback = [
                "ffmpeg", "-y", "-i", wav_path, 
                "-af", filter_str, "-acodec", "mp3", output_path
            ]
            subprocess.run(cmd_fallback, capture_output=True, text=True)

        if output_format == "mp3" and os.path.exists(output_path):
            if os.path.exists(wav_path):
                os.remove(wav_path)
            last_processed_file = output_filename
            print(f"[SIKER] MP3 fájl sikeresen létrehozva: {output_filename}")
        else:
            if os.path.exists(temp_wav):
                os.replace(temp_wav, wav_path)
            last_processed_file = os.path.basename(wav_path)
            print(f"[INFO] WAV fájl feldolgozva: {last_processed_file}")

    except Exception as e:
        print(f"[KIVÉTEL HIBA] FFmpeg feldolgozási hiba: {e}")
        last_processed_file = os.path.basename(wav_path)


@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route("/get_mic_volume", methods=["GET"])
def get_mic_volume():
    try:
        res = subprocess.run(["amixer", "sget", "Capture"], capture_output=True, text=True)
        if res.returncode != 0:
            res = subprocess.run(["amixer", "sget", "Mic"], capture_output=True, text=True)

        match = re.search(r"\[(\d+)%\]", res.stdout)
        if match:
            return jsonify({"status": "success", "volume": int(match.group(1))})
        return jsonify({"status": "success", "volume": 80})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


@app.route("/set_mic_volume", methods=["POST"])
def set_mic_volume():
    data = request.json or {}
    volume = data.get("volume", 80)
    try:
        res = subprocess.run(["amixer", "sset", "Capture", f"{volume}%"], capture_output=True, text=True)
        if res.returncode != 0:
            subprocess.run(["amixer", "sset", "Mic", f"{volume}%"], capture_output=True, text=True)

        print(f"[INFO] Mikrofon hangerő beállítva: {volume}%")
        return jsonify({"status": "success", "volume": volume})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


@app.route("/start", methods=["POST"])
def start_recording():
    global recording_process, current_wav_file
    if recording_process is not None:
        return jsonify({"status": "error", "message": "A felvétel már folyamatban van!"})

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    current_wav_file = os.path.join(SAVE_DIR, f"rec_{timestamp}.wav")

    cmd = ["arecord", "-D", "default", "-f", "cd", "-t", "wav", current_wav_file]
    
    try:
        recording_process = subprocess.Popen(cmd)
        print(f"[INFO] Felvétel elindítva: {current_wav_file}")
        return jsonify({"status": "success", "file": current_wav_file})
    except Exception as e:
        recording_process = None
        current_wav_file = None
        return jsonify({"status": "error", "message": str(e)})


@app.route("/stop", methods=["POST"])
def stop_recording():
    global recording_process, current_wav_file, last_processed_file
    if recording_process is None:
        return jsonify({"status": "error", "message": "Nincs aktív felvétel!"})

    recording_process.terminate()
    try:
        recording_process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        recording_process.kill()

    recording_process = None

    data = request.json or {}
    gain_db = float(data.get("gain", 0))
    filter_enabled = bool(data.get("filter", False))
    strength = float(data.get("strength", 50))
    output_format = data.get("format", "mp3").lower()

    if current_wav_file and os.path.exists(current_wav_file):
        process_audio_file(current_wav_file, gain_db, filter_enabled, strength, output_format)

    saved_file = last_processed_file
    current_wav_file = None

    return jsonify({"status": "success", "file": saved_file})


@app.route("/recordings/<filename>")
def get_recording(filename):
    return send_from_directory(SAVE_DIR, filename)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8099)
