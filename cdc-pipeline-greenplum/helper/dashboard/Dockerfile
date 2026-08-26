FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY main.py config.py logging_config.json ./
COPY backends/ ./backends/
COPY monitoring/ ./monitoring/
COPY static ./static
EXPOSE 8080
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--log-config", "logging_config.json"]
