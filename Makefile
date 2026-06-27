.PHONY: test lint format

test:  ## Run the pure unit tests (no Django needed).
	PYTHONPATH=src uv run --no-project --with 'diffsync>=2,<3' --with pytest python -m pytest

lint:
	uvx ruff check src tests
	uvx ruff format --check src tests

format:
	uvx ruff format src tests
