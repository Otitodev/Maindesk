# HealthDesk AI — single-container build (TRD §12.3).
# Voice (Pipecat) runs in-process as FastAPI routes — no separate worker,
# so the gateway is the only process in the container and uvicorn owns
# signal handling directly.

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      build-essential libpq-dev curl \
      # libgl1/libglib2.0-0: opencv-python (pulled in transitively by
      # pipecat-ai[webrtc]'s aiortc dep) needs these at import time even
      # though the voice widget is audio-only — python:3.12-slim doesn't
      # ship them by default.
      libgl1 libglib2.0-0 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY app ./app
COPY landingpage ./landingpage

ENV HEALTHDESK_VOICE=true

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
