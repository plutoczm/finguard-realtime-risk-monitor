FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FINGUARD_AI_DB_PATH=/app/state/finguard_ai.sqlite3

WORKDIR /app
COPY ai_service/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/state \
    && chown -R appuser:appuser /app

COPY --chown=appuser:appuser ai_service ./ai_service

USER appuser
EXPOSE 8091
CMD ["uvicorn", "ai_service.app:app", "--host", "0.0.0.0", "--port", "8091"]
