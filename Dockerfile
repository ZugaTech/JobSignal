# syntax=docker/dockerfile:1
# JobSignal: Vite/React UI (built) + FastAPI backend served by uvicorn.

FROM node:20-bookworm-slim AS frontend
WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci
COPY index.html vite.config.ts tsconfig.json tsconfig.node.json tailwind.config.js postcss.config.js ./
COPY src ./src
RUN npm run build

FROM python:3.12-slim-bookworm
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

COPY requirements-prod.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend ./backend
COPY --from=frontend /build/dist ./dist

EXPOSE 8080
CMD ["sh", "-c", "exec uvicorn backend.api.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
