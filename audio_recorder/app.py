import os
import re
import signal
import subprocess
import time
from flask import (
    Flask,
    Response,
    jsonify,
    render_template_string,
    request,
    send_from_directory,
)

app = Flask(__name__)

# Mappák beállítása
RECORDINGS_DIR = "/config/www/recordings"
os.makedirs(RECORDINGS_DIR, exist_ok=True)

# Folyamatok nyilvántartása
recording_process = None
current_filename = None
start_time = None

# =========================================================
# 1. HTML FELÜLET
# =========================================================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="hu">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>JARVIS Audio Vezérlő</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background: #121212; color: #fff; }
        .card { background: #1e1e1e; padding: 20px; border-radius: 10px; max-width: 500px; margin: 0 auto 20px auto; box-shadow: 0 4px 10px rgba(0,0,0,0.5); }
        h2 { text-align: center; color: #00adb5; margin-top: 0; }
        .timer { text-align: center; font-size: 32px; font-weight: bold; color: #ff4757; margin: 15px 0; font-family: monospace; }
        .control-group { margin-bottom: 15px; }
        label { display: block; margin-bottom: 5px; font-weight: bold; }
        input[type=range] { width: 100%; box-sizing: border-box; }
        button { width: 48%; padding: 12px; border: none; border-radius: 5px; font-size: 16px; cursor: pointer; font-weight: bold; }
        .btn-start { background: #28a745; color: white; }
        .btn-start:disabled { background: #555; cursor: not-allowed; }
        .btn-stop { background: #dc3545; color: white; }
        .btn-stop:disabled { background: #555; cursor: not-allowed; }
        .btn-group { display: flex; justify-content: space-between; margin-top: 15px; }
        audio { width: 100%; margin-top: 10px; display: block; }
        .status { text-align: center; margin-top: 15px; font-style: italic; color: #aaa; word-break: break-all; }
    </style>
</head>
<body>

<div class="card">
    <h2>Élő Audio Stream</h2>
    <p style="text-align: center; color: #ccc; margin-top: 0;">Valós idejű hallgatás a mikrofonból:</p>
    <!-- Relatív útvonal Ingress kompatibilitáshoz -->
    <audio id="streamPlayer" controls src="stream"></audio>
</div>

<div class="card">
    <h2>JARVIS Felvétel Vezérlő</h2>

    <div class="timer" id="timer">00:00</div>

    <div class="control-group">
        <label for="micVol">Mikrofon Bemeneti Hangerő: <span id="micVolVal">80</span>%</label>
        <input type="range" id="micVol" min="0" max="100" value="80" oninput="updateMicVolume(this.value)">
    </div>

    <div class="btn-group">
        <button class="btn-start" id="startBtn" onclick="startRecording()">Indítás</button>
        <button class="btn-stop" id="stopBtn" onclick="stopRecording()" disabled>Leállítás</button>
    </div>

    <div class="status" id="statusText">Készenlétben...</div>

    <audio id="audioPlayer" controls></audio>
</div>

<script>
    let timerInterval = null;

    window.addEventListener('DOMContentLoaded', () => {
        fetch('get_mic_volume')
            .then(res => res.json())
            .then(data => {
                if (data.status === 'success') {
                    document.getElementById('micVol').value = data.volume;
                    document.getElementById('micVolVal').innerText = data.volume;
                }
            })
            .catch(err => console.error("Hiba:", err));

        checkStatus();
    });

    function checkStatus() {
        fetch('status')
            .then(res => res.json())
            .then(data => {
                if (data.recording) {
                    document.getElementById('statusText').innerText = "Felvétel folyamatban...";
                    document.getElementById('startBtn').disabled = true;
                    document.getElementById('stopBtn').disabled = false;
                    startTimer(data.elapsed_seconds);
                }
            });
    }

    function updateMicVolume(val) {
        document.getElementById('micVolVal').innerText = val;
        fetch('set_mic_volume', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ volume: parseInt(val) })
        });
    }

    function startTimer(offsetSeconds = 0) {
        let seconds = offsetSeconds;
        const updateDisplay = (s) => {
            const mins = String(Math.floor(s / 60)).padStart(2, '0');
            const secs = String(s % 60).padStart(2, '0');
            document.getElementById('timer').innerText = `${mins}:${secs}`;
        };
        updateDisplay(seconds);
        clearInterval(timerInterval);
        timerInterval = setInterval(() => {
            seconds++;
            updateDisplay(seconds);
        }, 1000);
    }

    function stopTimer() {
        clearInterval(timerInterval);
    }

    function startRecording() {
        document.getElementById('statusText').innerText = "Indítás...";
        fetch('start', { method: 'POST' })
            .then(res => res.json())
            .then(data => {
                if (data.status === 'success') {
                    document.getElementById('statusText').innerText = "Felvétel folyamatban...";
                    document.getElementById('startBtn').disabled = true;
                    document.getElementById('stopBtn').disabled = false;
                    startTimer(0);
                } else {
                    document.getElementById('statusText').innerText = "Hiba: " + data.message;
                }
            });
    }

    function stopRecording() {
        stopTimer();
        document.getElementById('statusText').innerText = "Fájl mentése...";
        document.getElementById('startBtn').disabled = false;
        document.getElementById('stopBtn').disabled = true;

        fetch('stop', { method: 'POST' })
            .then(res => res.json())
            .then(data => {
                if (data.status === 'success') {
                    document.getElementById('statusText').innerText = "Kész: " + data.file;
                    const player = document.getElementById('audioPlayer');
                    player.src = 'recordings/' + data.file + '?t=' + new Date().getTime();
                    player.play();
                } else {
                    document.getElementById('statusText').innerText = "Hiba: " + data.message;
                }
            });
    }
</script>

</body>
</html>
"""


@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)


# =========================================================
# 2. ÉLŐ STREAM ENDPOINT
# =========================================================
def generate_audio_stream():
    cmd = [
        "ffmpeg",
        "-f",
        "alsa",
        "-i",
        "default",
        "-ac",
        "1",
        "-ar",
        "44100",
        "-b:a",
        "128k",
        "-f",
        "mp3",
        "pipe:1",
    ]

    process = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=1024
    )
    try:
        while True:
            data = process.stdout.read(1024)
            if not data:
                break
            yield data
    finally:
        process.kill()


@app.route("/stream")
def stream():
    response = Response(generate_audio_stream(), mimetype="audio/mpeg")
    response.headers["Cache-Control"] = (
        "no-cache, no-store, must-revalidate, private"
    )
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


# =========================================================
# 3. FELVÉTEL KEZELÉS (FFmpeg)
# =========================================================
@app.route("/start", methods=["POST"])
def start_recording():
    global recording_process, current_filename, start_time

    if recording_process is not None:
        return (
            jsonify({"status": "error", "message": "A rögzítés már fut!"}),
            400,
        )

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    filename_only = f"rec_{timestamp}.mp3"
    current_filename = os.path.join(RECORDINGS_DIR, filename_only)
    start_time = time.time()

    cmd = [
        "ffmpeg",
        "-f",
        "alsa",
        "-i",
        "default",
        "-ac",
        "1",
        "-ar",
        "44100",
        "-b:a",
        "128k",
        "-y",
        current_filename,
    ]

    try:
        recording_process = subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        return jsonify(
            {
                "status": "success",
                "message": "Rögzítés elindítva",
                "file": filename_only,
            }
        )
    except Exception as e:
        recording_process = None
        start_time = None
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/stop", methods=["POST"])
def stop_recording():
    global recording_process, current_filename, start_time

    if recording_process is None:
        return jsonify({"status": "error", "message": "Nincs futó rögzítés!"}), 400

    recording_process.send_signal(signal.SIGINT)
    try:
        recording_process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        recording_process.kill()

    saved_file = (
        os.path.basename(current_filename) if current_filename else None
    )
    recording_process = None
    current_filename = None
    start_time = None

    return jsonify({"status": "success", "file": saved_file})


@app.route("/status", methods=["GET"])
def get_status():
    is_recording = recording_process is not None
    elapsed = (
        int(time.time() - start_time) if is_recording and start_time else 0
    )
    return jsonify({"recording": is_recording, "elapsed_seconds": elapsed})


# =========================================================
# 4. HANGERŐ ÉS FÁJL KISZOLGÁLÁS
# =========================================================
@app.route("/get_mic_volume", methods=["GET"])
def get_mic_volume():
    try:
        res = subprocess.run(
            ["amixer", "sget", "Capture"], capture_output=True, text=True
        )
        if res.returncode != 0:
            res = subprocess.run(
                ["amixer", "sget", "Mic"], capture_output=True, text=True
            )

        match = re.search(r"\[(\d+)%\]", res.stdout)
        if match:
            return jsonify(
                {"status": "success", "volume": int(match.group(1))}
            )
        return jsonify({"status": "success", "volume": 80})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


@app.route("/set_mic_volume", methods=["POST"])
def set_mic_volume():
    data = request.json or {}
    volume = data.get("volume", 80)
    try:
        res = subprocess.run(
            ["amixer", "sset", "Capture", f"{volume}%"],
            capture_output=True,
            text=True,
        )
        if res.returncode != 0:
            subprocess.run(
                ["amixer", "sset", "Mic", f"{volume}%"],
                capture_output=True,
                text=True,
            )

        return jsonify({"status": "success", "volume": volume})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


@app.route("/recordings/<filename>")
def get_recording(filename):
    return send_from_directory(RECORDINGS_DIR, filename)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8099)
