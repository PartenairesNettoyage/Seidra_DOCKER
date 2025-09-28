#!/bin/sh
set -eu

USERS="${USERS:-5}"
SPAWN_RATE="${SPAWN_RATE:-1}"
RUN_TIME="${RUN_TIME:-5m}"
REPORT_DIR="${REPORT_DIR:-/opt/locust/reports}"
REPORT_BASENAME="${REPORT_BASENAME:-seidra_loadtest}"

mkdir -p "${REPORT_DIR}"

exec locust \
    -f /opt/locust/locustfile.py \
    --headless \
    -u "${USERS}" \
    -r "${SPAWN_RATE}" \
    -t "${RUN_TIME}" \
    --csv "${REPORT_DIR}/${REPORT_BASENAME}" \
    --html "${REPORT_DIR}/${REPORT_BASENAME}.html"
