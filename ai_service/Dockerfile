FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ai_service ./ai_service
EXPOSE 8091
CMD ["uvicorn", "ai_service.app:app", "--host", "0.0.0.0", "--port", "8091"]
