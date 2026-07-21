.PHONY: install lint format test run seed demo smoke ingest redis test-redis test-queue

install:
	uv pip install -r requirements.txt

lint:
	ruff check src/ tests/

format:
	ruff format src/ tests/

test:
	PYTHONPATH=src pytest tests/ -v

run:
	uvicorn src.api.main:app --reload --port 8000

redis:
	docker compose up -d redis

test-redis:
	PYTHONPATH=src .venv/bin/python scripts/test_redis.py

test-queue:
	PYTHONPATH=src .venv/bin/python scripts/test_queue.py

seed:
	python scripts/seed_data.py

demo:
	docker compose up --build

smoke:
	PYTHONPATH=src .venv/bin/python scripts/smoke_test.py

ingest:
	PYTHONPATH=src .venv/bin/python scripts/ingest_to_qdrant.py --source kb --strategy parent_child
