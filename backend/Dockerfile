FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
RUN addgroup --system app && adduser --system --ingroup app app

COPY requirements.txt ./
COPY requirements-face-opencv.txt ./
ARG INSTALL_FACE_OPENCV=false
RUN pip install --no-cache-dir -r requirements.txt
RUN if [ "$INSTALL_FACE_OPENCV" = "true" ]; then pip install --no-cache-dir -r requirements-face-opencv.txt; fi

COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app

RUN mkdir -p /app/storage/media && chown -R app:app /app
USER app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers", "--forwarded-allow-ips=*"]
