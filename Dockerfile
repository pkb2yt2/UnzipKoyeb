FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    aria2 p7zip-full unrar-free zstd tar ffmpeg ca-certificates cpulimit \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY . /app
RUN chmod +x /app/start.sh
EXPOSE 8080
ENV PYTHONUNBUFFERED=1
CMD ["bash", "start.sh"]
