# ─────────────────────────────────────────────────────────────
#  Stage 1 — Builder
#  Instala dependências Python em venv isolado
# ─────────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

# Evita prompts interativos no apt
ENV DEBIAN_FRONTEND=noninteractive

# Dependências de build (compilar alguns pacotes ARM)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Cria virtualenv isolado
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copia e instala dependências Python primeiro (cache layer)
COPY requirements.txt .
RUN pip install --upgrade pip "setuptools<72" wheel setuptools-rust && \
    pip install --no-cache-dir --no-build-isolation -r requirements.txt

# ─────────────────────────────────────────────────────────────
#  Stage 2 — Runtime
#  Imagem final enxuta com FFmpeg e yt-dlp
# ─────────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

ENV DEBIAN_FRONTEND=noninteractive
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# ── Dependências de sistema ───────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Processamento de vídeo
    ffmpeg \
    # Download YouTube
    curl \
    # tini: gerencia sinais corretamente (importante para Celery)
    tini \
    # Utilitários
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# ── yt-dlp (atualizado separado do pip para facilitar update) ─
RUN curl -L https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp \
    -o /usr/local/bin/yt-dlp && \
    chmod a+rx /usr/local/bin/yt-dlp

# ── Copia venv do builder ─────────────────────────────────────
COPY --from=builder /opt/venv /opt/venv

# ── Usuário não-root (segurança) ──────────────────────────────
RUN useradd --create-home --shell /bin/bash appuser

WORKDIR /app

# ── Copia código da aplicação ─────────────────────────────────
COPY --chown=appuser:appuser . .

# ── Diretórios de trabalho com permissão correta ──────────────
RUN mkdir -p /tmp/videos /app/outputs && \
    chown -R appuser:appuser /tmp/videos /app/outputs

# ── Pré-download do modelo Whisper base no build ──────────────
#    Evita cold start de ~150 MB no primeiro job
#    Remove após uso para não inflar a imagem desnecessariamente
#    (o modelo fica cacheado em ~/.cache/whisper no volume)
USER appuser
RUN python -c "import whisper; whisper.load_model('base')" || true

# ── Healthcheck da API ────────────────────────────────────────
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# tini como entrypoint: encaminha sinais corretamente para Celery
ENTRYPOINT ["/usr/bin/tini", "--"]

# Comando padrão (sobrescrito no docker-compose por serviço)
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
