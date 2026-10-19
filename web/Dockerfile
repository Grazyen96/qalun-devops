# One image for both halves of the web layer:
#   API:    the default command (uvicorn on port 8000)
#   worker: `qalun-web-worker` (metrics on port 9100)
#
# Build from the repository root, because the image installs QuranText itself:
#   docker build -f web/Dockerfile -t qalun-web .
#
# The speech model and the Quran store are baked in at build time, so a pod
# starts without downloading anything and every image tag is one fixed artifact.

FROM python:3.12-slim

# ffmpeg/ffprobe: QuranText decodes every recording through them.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    QURANTEXT_CACHE_DIR=/opt/qalun/cache \
    QURANTEXT_DATA_DIR=/opt/qalun/data \
    QURANTEXT_OUTPUT_DIR=/tmp/qalun-output

WORKDIR /src

# QuranText first: it changes less often than the web layer, so this layer stays cached.
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install .

COPY web ./web
RUN pip install ./web

RUN python -c "from qurantext.services.model_store import LOCAL_MODEL, ensure_model; ensure_model(LOCAL_MODEL)" \
    && qurantext build-db

# Run as an unprivileged user. Only the transcript cache under the cache folder is
# written at run time; the model and the store are read-only to it.
# The model store creates its folders for its owner only, which is root here.
RUN useradd --system --uid 10001 --create-home qalun \
    && chmod -R a+rX /opt/qalun \
    && mkdir -p /opt/qalun/cache/transcripts \
    && chown qalun /opt/qalun/cache/transcripts
USER 10001
WORKDIR /home/qalun

EXPOSE 8000 9100
CMD ["uvicorn", "--factory", "qalun_web.app:create_app_from_env", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]
