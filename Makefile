TARGET ?= http://localhost:8000
PORT ?= 9000
BACKEND_ARGS ?=

.PHONY: backend-install frontend-install test lint build backend frontend

backend-install:
	cd backend && python3 -m venv .venv && .venv/bin/python -m pip install -e '.[dev]'

frontend-install:
	cd frontend && npm ci

test:
	cd backend && .venv/bin/python -m pytest

lint:
	cd backend && .venv/bin/python -m ruff check .
	cd frontend && npm run lint

build:
	cd frontend && npm run build

backend:
	cd backend && .venv/bin/tracelens --target $(TARGET) --port $(PORT) $(BACKEND_ARGS)

frontend:
	cd frontend && npm run dev
