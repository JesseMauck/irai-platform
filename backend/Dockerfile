FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
# libatomic1: needed by Playwright's bundled Node driver before `--with-deps` can install the rest.
RUN apt-get update && apt-get install -y --no-install-recommends libatomic1 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install -r requirements.txt && playwright install --with-deps chromium && rm -rf /var/lib/apt/lists/*
COPY . .
EXPOSE 8000
# API: migrate, load reference data (idempotent), serve. The worker service overrides this command with
#   python -m app.jobs worker
CMD ["sh", "-c", "alembic upgrade head && python -m app.seed && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
