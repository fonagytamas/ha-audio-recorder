FROM python:3.11-slim
RUN apt-get update && apt-get install -y alsa-utils && rm -rf /var/lib/apt-get/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8099
CMD ["python", "app.py"]
