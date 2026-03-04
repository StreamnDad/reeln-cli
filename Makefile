.PHONY: dev-install test test-coverage test-integration lint format check install docs docs-serve completion-zsh completion-bash completion-fish

VENV := .venv/bin

dev-install:
	uv venv --clear
	uv pip install -e ".[dev,interactive,docs]"
	uv tool install --force --no-cache --from ".[interactive]" reeln

test:
	$(VENV)/python -m pytest tests/ -n auto --cov=reeln --cov-branch --cov-fail-under=100 -m "not integration" -q

test-coverage:
	$(VENV)/python -m pytest tests/ -n auto --cov=reeln --cov-branch --cov-fail-under=100 -m "not integration" --cov-report=html

test-integration:
	$(VENV)/python -m pytest tests/integration/ -m integration -v

lint:
	$(VENV)/ruff check .

format:
	$(VENV)/ruff format .

check: lint
	$(VENV)/mypy reeln/
	$(MAKE) test

install:
	uv tool install --force --no-cache --from ".[interactive]" reeln

docs:
	$(VENV)/python -m sphinx docs/ docs/_build/html

docs-serve: docs
	$(VENV)/python -m http.server -d docs/_build/html 8000

completion-zsh:
	$(VENV)/reeln --install-completion zsh

completion-bash:
	$(VENV)/reeln --install-completion bash

completion-fish:
	$(VENV)/reeln --install-completion fish
