FROM python:3.11-slim

WORKDIR /app

# Install dependencies first (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . .

# Chroma writes a small file-based index. Render mounts a persistent disk
# at /data; on platforms without a disk this still works (it's wiped on
# restart, only affecting semantic-recall results).
RUN mkdir -p /app/data

# Render injects the listening port via $PORT — fall back to 8000 locally.
ENV PORT=8000
EXPOSE 8000

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
