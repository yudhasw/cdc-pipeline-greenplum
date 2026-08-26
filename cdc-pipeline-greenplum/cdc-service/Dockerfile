FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir psycopg2-binary==2.9.9 requests==2.31.0

COPY config.py .
COPY main.py .
COPY merge.py .
COPY checks/ checks/

CMD ["python", "main.py"]
