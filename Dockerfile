FROM python:3.12-slim
WORKDIR /app
ENV PORT=8080
COPY scanner-api/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY scanner-api/app ./app
EXPOSE 8080
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
