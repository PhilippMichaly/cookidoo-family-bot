FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /data

ENV DATA_DIR=/data
ENV PYTHONUNBUFFERED=1

EXPOSE 8443

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8443/health')" || exit 1

ENTRYPOINT ["python", "cli.py"]
CMD ["serve"]
