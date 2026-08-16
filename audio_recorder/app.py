import os
import subprocess
import time
import re
from flask import Flask, render_template, request, jsonify, send_from_directory

app = Flask(__name__)

# Mappák beállítása
SAVE_DIR = "/media/jarvis_recordings"
os.makedirs(SAVE_DIR, exist_ok=True)

# Globális állapotváltozók
recording_process = None
current_wav_file = None
last_processed_file = None


def process_audio_file(wav_path, gain_db, filter_enabled, strength, output_format):
    """
    Feldolgozza a nyers WAV fájlt: zajszűrés, hangerő-kiemelés, normálás és MP3/WAV mentés.
    """
    global last_processed_file
    if not os.path.exists(wav_path):
        print(f"[HIBA] Nem található a WAV fájl: {wav_path}")
        return

    base_name = os.path.splitext(os.path.basename(wav_path))[0]
    ext = "mp3" if output_format == "mp3" else "wav"
    output_filename = f"{base_name}.{ext}"
    output_path = os.path.join(SAVE_DIR, output_filename)

    filters = []

    # =========================================================
    # 1. ZAJSZŰRÉS (A HANGERŐ-KIEMELÉS ELŐTT)
    # =========================================================
    if filter_enabled:
        # FFT alapú intelligens zajcsökkentés (afftdn)
        nr_db = int(12 + (strength / 100.0) * 28)
        filters.append(f"afftdn=nr={nr_db}:nf=-50")

        # Beszédtartomány megtartása (Mély zúgás és magas sípolás vágása)
        hp = int(80 + (strength / 100.0) * 120)      # 80Hz - 200Hz alatti mély zúgás vágása
        lp = int(8000 - (strength / 100.0) * 3500)   # 8000Hz - 4500Hz feletti sípolás vágása
        filters.append(f"highpass=f={hp}")
        filters.append(f"lowpass=f={lp}")

    # =========================================================
    # 2. HANGERŐ-KIEMELÉS ÉS DINAMIKUS NORMÁLÁS (SZŰRÉS UTÁN)
    # =========================================================
    if gain_db > 0:
        filters.append(f"volume={gain_db}dB")

    # Dinamikus normálás (már csak a tiszta beszédet erősíti fel)
    filters.append("dynaudnorm=f=150:g=15")

    # Biztonsági határoló (a recsegés/torzítás ellen)
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
    return render_template("index.html")


# =========================================================
# MIKROFON HANGERŐ KEZELÉS (AMIXER)
# =========================================================
@app.route("/get_mic_volume", methods=["GET"])
def get_mic_volume():
    """Lekéri a mikrofon jelenlegi hangerő-százalékát."""
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
    """Beállítja a rendszerszintű mikrofon hangerőt (0-100%)."""
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


# =========================================================
# FELVÉTEL KEZELÉS
# =========================================================
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
