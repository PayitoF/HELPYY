.PHONY: setup dev test test-unit test-pii test-agents test-contract health ollama-pull lint format

setup:
	pip install -e ".[dev]"
	cd frontend/app-mockup && npm install

dev:
	@./scripts/run_local.sh

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
