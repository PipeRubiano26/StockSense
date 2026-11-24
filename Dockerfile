# Imagen de StockSense para Kubernetes.
# Incluye el modelo ya entrenado (models/): el contenedor solo lo CARGA, nunca entrena.
FROM python:3.12.8-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    STOCKSENSE_DB_PATH=/data/stocksense.db

WORKDIR /app

COPY requirements-docker.txt .
RUN pip install --no-cache-dir --default-timeout=120 --retries 10 -r requirements-docker.txt

COPY app.py config.py ./
COPY database/ database/
COPY ml/ ml/
COPY models/ models/
COPY routes/ routes/
COPY services/ services/
COPY static/ static/
COPY templates/ templates/

# Usuario sin privilegios; /data es el volumen persistente con la base SQLite
RUN useradd --uid 1000 --create-home stocksense && mkdir -p /data && chown stocksense /data
USER stocksense

EXPOSE 5000

# Gunicorn es el proceso principal (PID 1). 1 proceso con 4 hilos por réplica.
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "4", \
     "--timeout", "120", "--access-logfile", "-", "app:create_app()"]
