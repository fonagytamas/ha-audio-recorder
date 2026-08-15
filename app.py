import os
import time
from flask import Flask, render_template_string
from flask_sock import Sock

app = Flask(__name__)
sock = Sock(app)

SAVE_DIR = "/media/recordings"
os.makedirs(SAVE_DIR, exist_ok=True)

HTML_CODE = """
<!DOCTYPE html>
<html lang="hu">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Hangrögzítő</title>
    <style>
        body { font-family: sans-serif; background-color: #111b21; color: #fff; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
        .card { background: #202c33; padding: 30px; border-radius: 12px; text-align: center; width: 280px; box-shadow: 0 4px 10px rgba(0,0,0,0.3); }
        button { padding: 12px 20px; font-size: 15px; border: none; border-radius: 6px; cursor: pointer; margin: 8px; font-weight: bold; }
        #recBtn { background: #00a884; color: white; }
        #stopBtn { background: #ea4335; color: white; }
        button:disabled { opacity: 0.3; cursor: not-allowed; }
        #status { margin-top: 15px; font-size: 13px; color: #aebac1; }
    </style>
</head>
<body>
<div class="card">
    <h3>Hangrögzítő</h3>
    <button id="recBtn">Rögzítés</button>
    <button id="stopBtn" disabled>Leállítás</button>
    <div id="status">Készenlétben</div>
</div>
<script>
    const recBtn = document.getElementById('recBtn');
    const stopBtn = document.getElementById('stopBtn');
    const statusText = document.getElementById('status');
    let mediaRecorder, socket;

    recBtn.addEventListener('click', async () => {
        try {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const currentPath = window.location.pathname.endsWith('/') ? window.location.pathname : window.location.pathname + '/';
            const wsUrl = `${protocol}//${window.location.host}${currentPath}ws`;

            socket = new WebSocket(wsUrl);

            socket.onopen = async () => {
                const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });

                mediaRecorder.ondataavailable = (e) => {
                    if (e.data.size > 0 && socket.readyState === WebSocket.OPEN) socket.send(e.data);
                };

                mediaRecorder.onstop = () => {
                    if (socket.readyState === WebSocket.OPEN) socket.close();
                    stream.getTracks().forEach(t => t.stop());
                };

                mediaRecorder.start(250);
                statusText.innerText = "🔴 Rögzítés...";
                recBtn.disabled = true;
                stopBtn.disabled = false;
            };

            socket.onerror = () => { statusText.innerText = "❌ Hálózati / WebSocket hiba!"; };
        } catch (err) {
            statusText.innerText = "⚠️ Mikrofon megtagadva vagy nem HTTPS!";
        }
    });

    stopBtn.addEventListener('click', () => {
        if (mediaRecorder && mediaRecorder.state !== 'inactive') {
            mediaRecorder.stop();
            statusText.innerText = "💾 Mentve a /media/recordings mappába!";
            recBtn.disabled = false;
            stopBtn.disabled = true;
        }
    });
</script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_CODE)

@app.route('/ws')
@sock.route('/ws')
def audio_stream(ws):
    filename = os.path.join(SAVE_DIR, f"rec_{int(time.time())}.webm")
    with open(filename, "wb") as f:
        while True:
            data = ws.receive()
            if data is None:
                break
            if isinstance(data, bytes):
                f.write(data)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8099)
