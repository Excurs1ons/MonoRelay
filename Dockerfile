FROM python:3.11-slim AS base

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY config.yml.example ./config.yml.example

RUN mkdir -p /app/data

EXPOSE 8787

CMD ["python", "-m", "backend.main"]
