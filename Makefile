.PHONY: install lint format test run seed demo

install:
uv pip install -r requirements.txt

lint:
ruff check src/ tests/

format:
ruff format src/ tests/

test:
pytest tests/ -v

run:
uvicorn src.api.main:app --reload --port 8000

seed:
python scripts/seed_data.py

demo:
docker compose up --build