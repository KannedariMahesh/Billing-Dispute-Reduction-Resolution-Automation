FROM python:3.12-slim

WORKDIR /app
COPY ai-gateway/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY ai-gateway/app ./app
COPY ai-gateway/certs /certs
COPY src ./src
COPY data ./data
ENV PYTHONPATH=/app/src

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "443", "--ssl-keyfile", "/certs/key.pem", "--ssl-certfile", "/certs/cert.pem"]
