import os
import time
import subprocess
from flask import Flask, render_template_string, jsonify

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

HTML_CODE = """
<!DOCTYPE html>
<html lang="hu">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Szerver Hangrögzítő</title>
    <style>
        body { font-family: sans-serif; background-color: #111b21; color: #fff; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
        .card { background: #202c33; padding: 30px; border-radius: 12px; text-align: center; width: 320px; box-shadow: 0 4px 10px rgba(0,0,0,0.3); }
        button { padding: 12px 20px; font-size: 15px; border: none; border-radius: 6px; cursor: pointer; margin: 8px; font-weight: bold; }
        #recBtn { background: #00a884; color: white; }
        #stopBtn { background: #ea4335; color: white; }
        button:disabled { opacity: 0.3; cursor: not-allowed; }
        #status { margin-top: 15px; font-size: 14px; color: #aebac1; word-break: break-word; }
    </style>
</head>
<body>
<div class="card">
    <h3>Szerver Mikrofon Rögzítő</h3>
    <button id="recBtn" onclick="startRec()">Rögzítés Indítása</button>
    <button id="stopBtn" onclick="stopRec()" disabled>Leállítás</button>
    <div id="status">Készenlétben (HA szerver mikrofonja)</div>
</div>
<script>
    async function startRec() {
        document.getElementById('status').innerText = "⏳ Indítás...";
        try {
            const res = await fetch('start', { method: 'POST' });
            const data = await res.json();
            if(data.status === 'ok') {
                document.getElementById('status').innerText = "🔴 Szerver rögzít...";
                document.getElementById('recBtn').disabled = true;
                document.getElementById('stopBtn').disabled = false;
            } else {
                document.getElementById('status').innerText = "❌ Hiba: " + data.message;
            }
        } catch (err) {
            document.getElementById('status').innerText = "❌ Hálózati hiba!";
        }
    }

    async function stopRec() {
        document.getElementById('status').innerText = "⏳ Mentés...";
        try {
            const res = await fetch('stop', { method: 'POST' });
            const data = await res.json();
            if(data.status === 'stopped') {
                document.getElementById('status').innerText = "💾 Mentve a www/recordings mappába!";
            } else {
                document.getElementById('status').innerText = "⚠️ Leállítva";
            }
            document.getElementById('recBtn').disabled = false;
            document.getElementById('stopBtn').disabled = true;
        } catch (err) {
            document.getElementById('status').innerText = "❌ Hálózati hiba leállításkor!";
        }
    }
</script>
</body>
</html>
"""

@app.route('/')
def index():
    ensure_dir_exists()
    return render_template_string(HTML_CODE)

@app.route('/start', methods=['POST'])
def start_recording():
    global recording_process
    ensure_dir_exists()

    if recording_process is None:
        filename = os.path.join(SAVE_DIR, f"rec_{int(time.time())}.wav")
        
        # Először plughw:0,0 eszközről próbálunk rögzíteni (első fizikai hangkártya)
        cmd = ["arecord", "-D", "plughw:0,0", "-f", "S16_LE", "-r", "44100", "-c", "1", filename]
        try:
            recording_process = subprocess.Popen(cmd, stderr=subprocess.PIPE)
            time.sleep(0.5)
            
            if recording_process.poll() is not None:
                _, err = recording_process.communicate()
                err_msg = err.decode('utf-8', errors='ignore') if err else "Ismeretlen hiba"
                
                # Ha a plughw:0,0 nem nyílik meg, megpróbáljuk a sima default eszközt
                cmd_fallback = ["arecord", "-f", "S16_LE", "-r", "44100", "-c", "1", filename]
                recording_process = subprocess.Popen(cmd_fallback, stderr=subprocess.PIPE)
                time.sleep(0.5)
                
                if recording_process.poll() is not None:
                    _, err_fb = recording_process.communicate()
                    err_msg_fb = err_fb.decode('utf-8', errors='ignore') if err_fb else err_msg
                    recording_process = None
                    return jsonify({"status": "error", "message": err_msg_fb})
                
            return jsonify({"status": "ok"})
        except Exception as e:
            recording_process = None
            return jsonify({"status": "error", "message": str(e)})
            
    return jsonify({"status": "already_running"})

@app.route('/stop', methods=['POST'])
def stop_recording():
    global recording_process
    if recording_process is not None:
        try:
            recording_process.terminate()
            recording_process.wait(timeout=2)
        except Exception:
            recording_process.kill()
        recording_process = None
        return jsonify({"status": "stopped"})
    return jsonify({"status": "not_running"})

if __name__ == '__main__':
    ensure_dir_exists()
    app.run(host='0.0.0.0', port=8099)
