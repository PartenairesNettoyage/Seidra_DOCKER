FROM python:3.11-slim

ENV PIP_NO_CACHE_DIR=1
WORKDIR /opt/locust

COPY locustfile.py /opt/locust/locustfile.py
COPY entrypoint.sh /opt/locust/entrypoint.sh

RUN pip install --no-cache-dir locust==2.21.0 \
    && chmod +x /opt/locust/entrypoint.sh

ENV REPORT_DIR=/opt/locust/reports

ENTRYPOINT ["/opt/locust/entrypoint.sh"]
