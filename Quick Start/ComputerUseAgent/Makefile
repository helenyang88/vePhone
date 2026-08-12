.PHONY: dev test test-backend test-frontend build e2e e2e-server

dev: build
	uv run uvicorn cua_platform.main:app --reload

test: test-backend test-frontend

test-backend:
	APP_SECRET_KEY=test-secret-key-at-least-32-bytes uv run pytest tests/backend

test-frontend:
	npm test

build:
	npm run build

e2e:
	npm run test:e2e

e2e-server: build
	APP_ENV=e2e APP_SECRET_KEY=e2e-test-secret-key-at-least-32-bytes APP_DATA_DIR=$$(mktemp -d) uv run uvicorn cua_platform.main:app --host 127.0.0.1 --port $${E2E_PORT:-8000}
