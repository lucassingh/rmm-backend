FROM python:3.9.16-slim-bullseye

WORKDIR /app

# Instalar dependencias del sistema
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    python3-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Actualizar pip
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# Copiar requirements e instalar dependencias
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar aplicación
COPY . .

# Configurar PYTHONPATH
ENV PYTHONPATH=/app

# Usar usuario no-root
RUN useradd -m myuser && chown -R myuser:myuser /app
USER myuser

# Comando de inicio (ajustado a tu estructura)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]