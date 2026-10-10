FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    BACKEND_HOST=0.0.0.0 \
    BACKEND_PORT=8080 \
    BACKEND_WORKERS=1 \
    BACKEND_PRODUCTION=true

WORKDIR /app

RUN groupadd --system app && useradd --system --gid app --home /app app

COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir .

USER app
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('BACKEND_PORT', '8080') + '/health', timeout=2).read()"]

CMD ["python", "-m", "nos_anonymizer.server"]
