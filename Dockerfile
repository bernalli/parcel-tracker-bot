# syntax=docker/dockerfile:1.7

# ─── Stage 1: builder ──────────────────────────────────────────────
FROM python:3.12-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gettext \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src/ ./src/

# Compile gettext catalogs (.po → .mo) so setuptools package-data
# `locale/*/LC_MESSAGES/*.mo` finds them at install time.
RUN set -eu; for po in src/parcel_tracker/i18n/locale/*/LC_MESSAGES/messages.po; do \
        msgfmt "$po" -o "${po%.po}.mo"; \
    done

RUN pip install --prefix=/install --no-warn-script-location .

# ─── Stage 2: runtime ──────────────────────────────────────────────
FROM python:3.12-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/usr/local/bin:${PATH}"

WORKDIR /app

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /usr/sbin/nologin --uid 1000 botuser \
    && mkdir -p /app/data /app/plugins \
    && chown botuser:botuser /app/data

COPY --from=builder /install /usr/local

# Inside the container the web dashboard must listen on all interfaces so the
# published port reaches it; docker-compose.yml binds that port to the host's
# loopback only. It is off unless WEB_ENABLED=true.
ENV WEB_BIND_HOST=0.0.0.0 \
    WEB_PORT=8080
EXPOSE 8080

USER botuser

# Healthcheck: DB exists and is readable. Opened read-only so a missing
# database fails the check instead of being silently created empty.
HEALTHCHECK --interval=5m --timeout=15s --start-period=30s --retries=3 \
    CMD python -c "import os, pathlib, sqlite3; sqlite3.connect(pathlib.Path(os.getenv('DATABASE_PATH','/app/data/bot.db')).absolute().as_uri() + '?mode=ro', uri=True).execute('SELECT 1')" || exit 1

CMD ["parcel-tracker"]
