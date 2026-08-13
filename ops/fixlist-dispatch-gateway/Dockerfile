FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY main.py ./

USER nobody
CMD ["sh", "-c", "exec gunicorn --bind :${PORT} --workers 2 --threads 4 --timeout 60 main:app"]
