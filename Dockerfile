FROM python:3.12-slim

# Crear directorio de la app
WORKDIR /app

# Copiar dependencias
COPY requirements.txt .

# Instalar dependencias
RUN pip install --no-cache-dir -r requirements.txt

# Copiar todo el código de la carpeta app dentro del contenedor en /app
COPY ./app /app

# Exponer puerto
EXPOSE 8000

# Arrancar FastAPI
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]