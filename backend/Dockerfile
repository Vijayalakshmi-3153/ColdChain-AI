FROM python:3.11-slim

WORKDIR /app

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY ml ./ml

# Verify ML artifacts are included in the Docker image
RUN echo "=== ML ARTIFACTS ===" && ls -lah /app/ml/artifacts

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]