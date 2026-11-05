# Explicit, reproducible image for the consumer (replaces Buildpacks' automatic choices).
# Python version is fixed here; production would pin the base image by digest as well.
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY main.py .
# Cloud Run provides PORT. One worker, four threads: at most 4 requests in parallel per instance.
CMD exec gunicorn --bind :$PORT --workers 1 --threads 4 main:app
