# One image: Node builds the frontend, Python serves the API and the built SPA.

FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build


FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt
RUN pip install -r backend/requirements.txt

COPY backend/app backend/app
COPY fixtures fixtures
COPY --from=web /web/dist frontend/dist

RUN useradd --create-home --uid 1000 tellwind && mkdir -p backend/data && chown tellwind backend/data
USER tellwind

EXPOSE 8000
# Render passes $PORT; behind its proxy, trust X-Forwarded-* for the client scheme.
CMD ["sh", "-c", "exec uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
