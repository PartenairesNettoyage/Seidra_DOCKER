FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copie des fichiers nécessaires à l'installation des dépendances
COPY pyproject.toml README.md ./
COPY backend/requirements-dev.txt ./backend/requirements-dev.txt

RUN pip install --upgrade pip \
    && pip install -r backend/requirements-dev.txt

# Copie du code de l'application
COPY backend ./backend

WORKDIR /app/backend

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
