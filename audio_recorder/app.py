import os
import subprocess
import signal
import time
from flask import Flask, render_template_string, Response, jsonify, request

app = Flask(__name__)

# Mappák beállítása
RECORDINGS_DIR = "/config/www/recordings"
os.makedirs(RECORDINGS_DIR, exist_ok=True)

# Folyamatok nyilvántartása
recording_process = None
current_filename = None
start_time = None

# ----------------------------------------------------
# 1. ÉLŐ STREAM (FFmpeg-el, ALSA / PulseAudio bemenetről)
# ----------------------------------------------------
def generate_audio_stream():
    """Élő MP3 stream előállítása az alapértelmezett mikrofonról"""
    # Az FFmpeg a default ALSA eszközről vagy PulseAudio-ról veszi a hangot
    cmd = [
        "ffmpeg",
        "-f", "alsa",
        "-i", "default",
        "-ac", "1",               # Mono csatorna
        "-ar", "44100",           # 44.1 kHz
        "-b:a", "128k",           # 128 kbps MP3
        "-f", "mp3",
        "pipe:1"
    ]
    
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=1024)
    try:
        while True:
            data = process.stdout.read(1024)
            if not data:
                break
            yield data
    finally:
        process.kill()

@app.route('/stream')
def stream():
    """Élő adás végpont - No-cache fejlécekkel a tekerés elkerülésére"""
    response = Response(generate_audio_stream(), mimetype='audio/mpeg')
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

# ----------------------------------------------------
# 2. RÖGZÍTÉS KEZELÉSE (FFmpeg-el, hogy ne legyen ALSA ütközés)
# ----------------------------------------------------
@app.route('/start', methods=['POST'])
def start_recording():
    global recording_process, current_filename, start_time

    if recording_process is not None:
        return jsonify({"status": "error", "message": "A rögzítés már fut!"}), 400

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    current_filename = os.path.join(RECORDINGS_DIR, f"rec_{timestamp}.mp3")
    start_time = time.time()

    # ffmpeg-et használunk arecord helyett, hogy ne ütközzön az élő adással
    cmd = [
        "ffmpeg",
        "-f", "alsa",
        "-i", "default",
        "-ac", "1",
        "-ar", "44100",
        "-b:a", "128k",
        "-y",
        current_filename
    ]

    try:
        recording_process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return jsonify({"status": "success", "message": "Rögzítés elindítva", "file": current_filename})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/stop', methods=['POST'])
def stop_recording():
    global recording_process, current_filename, start_time

    if recording_process is None:
        return jsonify({"status": "error", "message": "Nincs futó rögzítés!"}), 400

    # SIGINT (Ctrl+C) küldése az FFmpeg-nek, hogy rendben lezárja az MP3 fájlt
    recording_process.send_signal(signal.SIGINT)
    recording_process.wait()

    saved_file = current_filename
    recording_process = None
    current_filename = None
    start_time = None

    return jsonify({"status": "success", "message": "Rögzítés leállítva", "file": saved_file})

@app.route('/status', methods=['GET'])
def get_status():
    is_recording = recording_process is not None
    elapsed = int(time.time() - start_time) if is_recording and start_time else 0
    return jsonify({
        "recording": is_recording,
        "elapsed_seconds": elapsed,
        "filename": os.path.basename(current_filename) if current_filename else None
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8099)
