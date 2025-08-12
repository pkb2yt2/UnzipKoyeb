# Dockerfile for Koyeb Web Service (Free tier)
FROM python:3.12-slim

# System deps for your bot:
# - archive tools (7z/rar/zstd/tar), aria2 for downloads, ffmpeg for media
RUN apt-get update && apt-get install -y --no-install-recommends \
    aria2 p7zip-full p7zip-rar unrar-free zstd tar ffmpeg ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first for better caching
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Bring the source
COPY . /app

# Make sure the entrypoint script is executable
RUN chmod +x /app/start.sh

# Koyeb Web Service expects something to listen here
EXPOSE 8080

# Unbuffered logs
ENV PYTHONUNBUFFERED=1

CMD ["bash", "start.sh"]
