FROM python:3.11-slim

# Rendszerfüggőségek telepítése
# - alsa-utils: arecord és amixer használatához
# - ffmpeg és libmp3lame-dev: audio konvertáláshoz és zajszűréshez
RUN apt-get update && apt-get install -y --no-install-recommends \
    alsa-utils \
    libasound2-plugins \
    pulseaudio-utils \
    ffmpeg \
    libmp3lame-dev \
    && rm -rf /var/lib/apt-get/lists/*

WORKDIR /app

# Mappa létrehozása a felvételeknek (ha nem lenne csatolva)
RUN mkdir -p /config/www/recordings

# Python függőségek telepítése
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Alkalmazás kód másolása
COPY . .

# Port megnyitása a Web UI és Stream számára
EXPOSE 8099

CMD ["python", "app.py"]
