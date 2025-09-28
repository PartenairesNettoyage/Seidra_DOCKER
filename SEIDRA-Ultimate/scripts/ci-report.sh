#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

REPORT_DIR="$ROOT_DIR/reports/qa"
LOG_DIR="$REPORT_DIR/logs"
BACKEND_REPORT_DIR="$REPORT_DIR/backend"
FRONTEND_REPORT_DIR="$REPORT_DIR/frontend"
LOAD_TEST_DIR="$REPORT_DIR/load-tests"

# Reset previous artifacts
rm -rf "$REPORT_DIR"
mkdir -p "$LOG_DIR" "$BACKEND_REPORT_DIR" "$FRONTEND_REPORT_DIR" "$LOAD_TEST_DIR"

echo "[ci-report] Running make check"
make check | tee "$LOG_DIR/make-check.log"

echo "[ci-report] Running pytest with coverage"
pytest backend/tests \
  --cov=backend \
  --cov-report=xml:"$BACKEND_REPORT_DIR/coverage.xml" \
  --cov-report=html:"$BACKEND_REPORT_DIR/html" \
  --cov-report=term-missing \
  | tee "$LOG_DIR/backend-pytest.log"

echo "[ci-report] Running vitest with coverage"
pushd frontend > /dev/null
npx vitest run --coverage --reporter=default --coverage.reporter=lcov --coverage.reporter=html \
  | tee "$LOG_DIR/frontend-vitest.log"
if [ -d coverage ]; then
  rm -rf "$FRONTEND_REPORT_DIR/coverage"
  mkdir -p "$FRONTEND_REPORT_DIR"
  cp -R coverage "$FRONTEND_REPORT_DIR/coverage"
  rm -rf coverage
fi
popd > /dev/null

echo "[ci-report] Génération des scénarios de charge vidéo"
python scripts/load-testing/video_celery_scenario.py \
  --output "$LOAD_TEST_DIR/celery-video-plan.json" \
  --concurrency 3 \
  --duration 90 \
  --interval 10 \
  | tee "$LOG_DIR/video-celery-scenario.log"

python scripts/load-testing/export_k6_video_scenario.py \
  --output "$LOAD_TEST_DIR/video-k6-scenario.js" \
  --arrival-rate 5 \
  --start-rate 2 \
  --preallocated 8 \
  --max-vus 30 \
  | tee "$LOG_DIR/video-k6-scenario.log"

ARTIFACT_NAME="${QA_ARTIFACT_NAME:-ultimate-qa-reports}"

if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
  {
    echo "artifact-name=$ARTIFACT_NAME"
    echo "artifact-path=$REPORT_DIR"
  } >> "$GITHUB_OUTPUT"
fi

if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
  cat <<EOT >> "$GITHUB_STEP_SUMMARY"
### QA automation summary
- **make check** log: `reports/qa/logs/make-check.log`
- **pytest** HTML report: `reports/qa/backend/html/index.html`
- **vitest** coverage: `reports/qa/frontend/coverage/index.html`
- **Scénarios vidéo Celery/k6**: `reports/qa/load-tests/`
- **Artifact name**: `$ARTIFACT_NAME`
EOT
fi

echo "[ci-report] QA reports available in $REPORT_DIR"
