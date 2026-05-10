# syntax=docker/dockerfile:1.7

# ─── Stage 1: builder ──────────────────────────────────────────────
FROM python:3.12-slim AS builder

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
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/usr/local/bin:${PATH}"

WORKDIR /app

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash --uid 1000 botuser \
    && mkdir -p /app/data /app/plugins \
    && chown -R botuser:botuser /app

COPY --from=builder /install /usr/local

USER botuser

# Healthcheck: process alive + DB reachable
HEALTHCHECK --interval=5m --timeout=15s --start-period=30s --retries=3 \
    CMD python -c "import sqlite3, os; sqlite3.connect(os.getenv('DATABASE_PATH','/app/data/bot.db')).execute('SELECT 1')" || exit 1

CMD ["parcel-tracker"]
