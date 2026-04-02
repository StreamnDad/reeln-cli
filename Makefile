.PHONY: dev-install native-dev plugins test test-coverage test-integration lint format check install docs docs-serve

VENV := .venv/bin
CORE_DIR := ../reeln-core
PLUGIN_DIR := ..

PLUGINS := \
	reeln-plugin-google \
	reeln-plugin-meta \
	reeln-plugin-openai \
	reeln-plugin-streamn-scoreboard \
	reeln-plugin-cloudflare

dev-install:
	uv venv --clear
	uv pip install -e ".[dev,interactive,docs]"
	ln -sf $(CURDIR)/.venv/bin/reeln $(HOME)/.local/bin/reeln

plugins:
	uv pip install $(foreach p,$(PLUGINS),-e $(PLUGIN_DIR)/$(p))

native-dev:
	cd $(CORE_DIR)/crates/reeln-python && VIRTUAL_ENV=$(CURDIR)/.venv maturin develop --release

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
	ln -sf $(CURDIR)/.venv/bin/reeln $(HOME)/.local/bin/reeln

docs:
	$(VENV)/python -m sphinx docs/ docs/_build/html

docs-serve: docs
	$(VENV)/python -m http.server -d docs/_build/html 8000
