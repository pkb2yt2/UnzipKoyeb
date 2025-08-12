# Dockerfile for Koyeb Web Service (Free tier)
FROM python:3.12-slim

WORKDIR /app

# Copy reqs first to leverage Docker layer cache
COPY requirements.txt /app/requirements.txt

# Install runtime deps + temporary build toolchain for tgcrypto,
# add 'unrar' for RAR5 and 'git' for GitPython.
RUN set -eux; \
    echo "deb http://deb.debian.org/debian bookworm main non-free" > /etc/apt/sources.list; \
    echo "deb http://security.debian.org/debian-security bookworm-security main non-free" >> /etc/apt/sources.list; \
    echo "deb http://deb.debian.org/debian bookworm-updates main non-free" >> /etc/apt/sources.list; \
    apt-get update && apt-get install -y --no-install-recommends \
      aria2 p7zip-full unrar zstd tar ffmpeg ca-certificates git build-essential \
    && pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r /app/requirements.txt \
    && apt-get purge -y --auto-remove build-essential \
    && rm -rf /var/lib/apt/lists/*

# Bring the app
COPY . /app

# Ensure start script is executable
RUN chmod +x /app/start.sh

# Koyeb Web Service expects something to listen here
EXPOSE 8080

# Unbuffered logs
ENV PYTHONUNBUFFERED=1

CMD ["bash", "start.sh"]
