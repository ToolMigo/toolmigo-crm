FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends postgresql-client && rm -rf /var/lib/apt/lists/*
RUN addgroup --system crm && adduser --system --ingroup crm crm
COPY app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app .
COPY assets/toolmigo-logo.jpeg static/img/toolmigo-logo.jpeg
RUN mkdir -p /app/staticfiles /app/media && chown -R crm:crm /app
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod 755 /entrypoint.sh
EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]
