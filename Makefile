.PHONY: install install-dev run demo-ui seed train-no-show evaluate gate test lint lint-fix format-check typecheck check

install:
	python -m pip install -e .

install-dev:
	python -m pip install -e ".[dev]"

run:
	uvicorn dealerai_ops.main:create_app --factory --host $${DEALERAI_API_HOST:-127.0.0.1} --port $${DEALERAI_API_PORT:-8000}

demo-ui:
	streamlit run src/dealerai_ops/ui/streamlit_app.py

seed:
	python -m dealerai_ops.scripts.seed_synthetic_data --reset

train-no-show:
	python -m dealerai_ops.scripts.train_no_show_model

evaluate:
	python -m evaluation.run

gate:
	python -m evaluation.gate

test:
	pytest

lint:
	ruff check .

lint-fix:
	ruff check . --fix

format-check:
	ruff format --check src tests

typecheck:
	mypy

check: lint format-check typecheck test
