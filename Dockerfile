FROM python:3.13.5-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip3 install --no-cache-dir -r requirements.txt

# --- AQUÍ COPIAMOS TUS CARPETAS DE DATOS ---
COPY app.py .
COPY recomendador/ ./recomendador/
COPY portadas/ ./portadas/
# Si tienes archivos en src que aún usas:
# COPY src/ ./src/ 

EXPOSE 8501

HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health

ENTRYPOINT ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]