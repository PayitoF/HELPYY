.PHONY: setup dev test test-unit test-pii test-agents test-contract health ollama-pull lint format

setup:
	pip install -e ".[dev]"
	cd frontend/app-mockup && npm install

dev:
	@./scripts/run_local.sh

dev-local:
	@echo "Starting backend API on :8000..."
	@uvicorn backend.api.main:app --host 0.0.0.0 --port 8000 --reload &
	@echo "Starting ML mock on :8001..."
	@uvicorn backend.ml_client.mock_server:app --host 0.0.0.0 --port 8001 --reload &
	@echo "Starting frontend on :5173..."
	@cd frontend/app-mockup && npm run dev &
	@echo ""
	@echo "Helpyy Hand (local, no Ollama):"
	@echo "  Frontend:  http://localhost:5173"
	@echo "  API docs:  http://localhost:8000/docs"
	@echo "  ML Mock:   http://localhost:8001/docs"
	@echo ""
	@echo "To stop: kill %1 %2 %3"
	@wait

test:
	pytest tests/ -v --cov=backend

test-unit:
	pytest tests/unit/ -v

test-pii:
	pytest tests/ -v -m pii

test-agents:
	pytest tests/ -v -m agents

test-contract:
	pytest tests/contract/ -v -m contract

health:
	@echo "Checking API..."
	@curl -sf http://localhost:8000/health || echo "API: DOWN"
	@echo "Checking ML Mock..."
	@curl -sf http://localhost:8001/health || echo "ML Mock: DOWN"
	@echo "Checking Ollama..."
	@curl -sf http://localhost:11434/api/tags || echo "Ollama: DOWN"

ollama-pull:
	ollama pull gemma4:e4b

lint:
	ruff check backend/ tests/

format:
	black backend/ tests/
	ruff check --fix backend/ tests/
