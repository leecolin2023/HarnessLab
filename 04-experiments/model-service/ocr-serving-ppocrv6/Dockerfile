FROM python:3.11-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PADDLEX_HOME=/models OMP_NUM_THREADS=2
WORKDIR /srv
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libgomp1 curl && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
EXPOSE 8008
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8008","--workers","1","--no-access-log"]
