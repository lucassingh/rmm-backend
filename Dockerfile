FROM python:3.9.16-slim-bullseye

WORKDIR /app

# Instalar solo lo necesario y limpiar cache
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Actualizar herramientas de Python
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# Copiar e instalar dependencias
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar aplicación
COPY backend .

# Usar usuario no-root para mayor seguridad
RUN useradd -m myuser && chown -R myuser:myuser /app
USER myuser

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]