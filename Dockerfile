FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv/app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt && groupadd --gid 10001 appgroup && useradd --uid 10001 --gid 10001 --no-create-home appuser
COPY app/ ./app/
RUN mkdir -p /data && chown -R appuser:appgroup /data /srv/app
USER appuser
EXPOSE 8099
HEALTHCHECK --interval=30s --timeout=5s --start-period=25s --retries=3 CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8099/health',timeout=3)" || exit 1
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8099","--workers","1"]
