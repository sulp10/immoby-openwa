FROM python:3.12-slim@sha256:a0f57064cbdcd6285fa45f51237ab0b35ea8ebaed06a1f5973e89e19dfb86704
WORKDIR /app
RUN pip install --no-cache-dir gunicorn==26.2.0 && useradd --uid 10001 --create-home bot
COPY --chown=bot:bot cloud /app/cloud
COPY --chown=bot:bot core /app/core
COPY --chown=bot:bot prompts /app/prompts
RUN mkdir -p /app/data /app/private && chown bot:bot /app/data /app/private
USER bot
ENV STATE_DIR=/app/data PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
EXPOSE 8080
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "4", "--timeout", "30", "cloud.service:application"]
