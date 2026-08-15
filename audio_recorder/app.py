import os
import time
import subprocess
from flask import Flask, render_template_string, jsonify

app = Flask(__name__)

SAVE_DIR = "/config/www/recordings"
os.makedirs(SAVE_DIR, exist_ok=True)

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
        .card { background: #202c33; padding: 30px; border-radius: 12px; text-align: center; width: 300px; box-shadow: 0 4px 10px rgba(0,0,0,0.3); }
        button { padding: 12px 20px; font-size: 15px; border: none; border-radius: 6px; cursor: pointer; margin: 8px; font-weight: bold; }
        #recBtn { background: #00a884; color: white; }
        #stopBtn { background: #ea4335; color: white; }
        button:disabled { opacity: 0.3; cursor: not-allowed; }
        #status { margin-top: 15px; font-size: 14px; color: #aebac1; }
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
            document.getElementById('status').innerText = "💾 Mentve a www/recordings mappába!";
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
    return render_template_string(HTML_CODE)

@app.route('/start', methods=['POST'])
def start_recording():
    global recording_process
    if recording_process is None:
        filename = os.path.join(SAVE_DIR, f"rec_{int(time.time())}.wav")
        cmd = ["arecord", "-D", "default", "-f", "cd", "-t", "wav", filename]
        try:
            recording_process = subprocess.Popen(cmd)
            return jsonify({"status": "ok"})
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)})
    return jsonify({"status": "already_running"})

@app.route('/stop', methods=['POST'])
def stop_recording():
    global recording_process
    if recording_process is not None:
        recording_process.terminate()
        recording_process.wait()
        recording_process = None
        return jsonify({"status": "stopped"})
    return jsonify({"status": "not_running"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8099)
