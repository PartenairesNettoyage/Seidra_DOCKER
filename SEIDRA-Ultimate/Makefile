PYTHON ?= python3
BACKEND_DIR := backend
FRONTEND_DIR := frontend
VENV_BIN := .venv/bin


.PHONY: help install-dev install-prod dev-backend dev-frontend lint format type-check backend-type-check frontend-type-check backend-test frontend-test test test-e2e e2e coverage check qa-report hooks compat observability-up observability-down loadtest docs-api rotate-demo-user monitoring-validate

help:
	@echo "Cibles disponibles :"
	@echo "  make install-dev        # exécute install-dev.sh"
	@echo "  make install-prod       # exécute install-prod.sh"
	@echo "  make dev-backend        # lance l'API FastAPI"
	@echo "  make dev-frontend       # lance le frontend Next.js"
        @echo "  make check              # lint + type-check + tests + observabilité"
	@echo "  make observability-up   # démarre Prometheus/Grafana/Loki/Tempo"
	@echo "  make observability-down # arrête la stack d'observabilité"
	@echo "  make loadtest           # lance les tests de charge Locust via Docker"
	@echo "  make docs-api           # génère la documentation HTML Redoc"
	@echo "  make rotate-demo-user   # fait tourner le mot de passe du compte démo"

install-dev:
	./install-dev.sh

install-prod:
	./install-prod.sh

dev-backend:
	./scripts/dev-backend.sh

dev-frontend:
	./scripts/dev-frontend.sh

RUFF_PATHS := backend/tests backend/core/config.py backend/tests/test_config.py
MYPY_PATHS := backend/core backend/tests

lint:
	$(VENV_BIN)/ruff check $(RUFF_PATHS) || ruff check $(RUFF_PATHS)
	npm run lint --prefix $(FRONTEND_DIR) -- --dir src/lib --dir src/__tests__

format:
	$(VENV_BIN)/black $(BACKEND_DIR) || black $(BACKEND_DIR)
	npm run lint:fix --prefix $(FRONTEND_DIR)

backend-type-check:
	$(VENV_BIN)/mypy $(MYPY_PATHS) || mypy $(MYPY_PATHS)

frontend-type-check:
	npm run type-check --prefix $(FRONTEND_DIR)

type-check: frontend-type-check

backend-test:
	$(VENV_BIN)/pytest $(BACKEND_DIR)/tests || pytest $(BACKEND_DIR)/tests

frontend-test:
	npm run test --prefix $(FRONTEND_DIR) -- --run

test: backend-test frontend-test

test-e2e:
	npm run test:e2e --prefix $(FRONTEND_DIR)

coverage:
	$(VENV_BIN)/pytest --cov=$(BACKEND_DIR) --cov-report=xml $(BACKEND_DIR)/tests || pytest --cov=$(BACKEND_DIR) --cov-report=xml $(BACKEND_DIR)/tests

qa-report:
	mkdir -p reports/qa
	$(VENV_BIN)/pytest --cov=$(BACKEND_DIR) --cov-report=html:reports/qa/backend || pytest --cov=$(BACKEND_DIR) --cov-report=html:reports/qa/backend
	npm run test --prefix $(FRONTEND_DIR) -- --run --coverage

hooks:
	pre-commit install

compat:
	./scripts/check-backward-compat.py openapi/classic.json openapi/ultimate.json
	$(VENV_BIN)/pytest tests/contract || pytest tests/contract

MONITORING_COMPOSE_FILE ?= docker-compose.dev.yml

check: lint type-check compat test monitoring-validate


observability-up:
	./scripts/start-monitoring.sh

observability-down:
        ./scripts/stop-monitoring.sh


monitoring-validate:
	docker compose -f $(MONITORING_COMPOSE_FILE) up -d prometheus grafana
	$(PYTHON) scripts/monitoring/check_dashboards.py --require-http --http-retries 15 --http-delay 4
	docker compose -f $(MONITORING_COMPOSE_FILE) stop prometheus grafana
	docker compose -f $(MONITORING_COMPOSE_FILE) rm -f prometheus grafana


loadtest:
	@if [ -z "$(SEIDRA_API_URL)" ]; then \
		echo "❌ SEIDRA_API_URL doit être défini"; \
		exit 1; \
	fi
	@if [ -z "$(SEIDRA_JWT)" ]; then \
		echo "❌ SEIDRA_JWT doit être défini"; \
		exit 1; \
	fi
	mkdir -p reports/perf
	docker build -t seidra-loadtest scripts/load-testing
	docker run --rm \
		-e SEIDRA_API_URL="$(SEIDRA_API_URL)" \
		-e SEIDRA_JWT="$(SEIDRA_JWT)" \
		-e USERS="$(USERS)" \
		-e SPAWN_RATE="$(SPAWN_RATE)" \
		-e RUN_TIME="$(RUN_TIME)" \
		-e REPORT_DIR="/opt/locust/reports" \
	        -e REPORT_BASENAME="$(or $(REPORT_BASENAME),seidra_loadtest)" \
	        -v "$(PWD)/reports/perf:/opt/locust/reports" \
	        seidra-loadtest
	$(PYTHON) scripts/load-testing/generate_report.py \
	        --reports-dir reports/perf \
	        --basename $(or $(REPORT_BASENAME),seidra_loadtest)
	@echo "Rapports de charge disponibles dans reports/perf"

docs-api:
	mkdir -p docs/api
	npx --yes redoc-cli bundle openapi/ultimate.json -o docs/api/reference.html

rotate-demo-user:
	python scripts/rotate-default-user.py


