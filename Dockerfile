FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 BOBA_DATA_DIR=/data BOBA_COOKIE_SECURE=true
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY server.py /app/server.py
COPY static /app/static
RUN mkdir -p /data
EXPOSE 8000
CMD ["sh","-c","uvicorn server:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --proxy-headers"]
