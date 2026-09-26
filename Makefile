# HomeBrain developer commands. `make help` lists them.
SHELL := /bin/bash
.DEFAULT_GOAL := help

UV       ?= uv
COMPOSE  ?= docker compose
MCP_URL  ?= http://localhost:8080/mcp

.PHONY: help
help: ## List commands
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

# ------------------------------------------------------------------ setup
.PHONY: install
install: ## Install dependencies and git hooks
	$(UV) sync --all-groups
	$(UV) run pre-commit install

# ------------------------------------------------------------------ quality
.PHONY: fmt
fmt: ## Format and auto-fix
	$(UV) run ruff format .
	$(UV) run ruff check --fix .

.PHONY: lint
lint: ## Lint and check formatting
	$(UV) run ruff check .
	$(UV) run ruff format --check .

.PHONY: typecheck
typecheck: ## mypy --strict
	$(UV) run mypy

.PHONY: test
test: ## Run tests
	$(UV) run pytest -q

.PHONY: cov
cov: ## Tests with branch coverage; the domain must be at 100%
	$(UV) run pytest -q --cov --cov-report=term --cov-report=xml
	$(UV) run coverage report --include='*/homebrain/domain/*' --fail-under=100

.PHONY: check
check: lint typecheck cov ## Everything CI runs

# ------------------------------------------------------------------ run
.PHONY: run
run: ## Run the server on the host (http://localhost:8080)
	$(UV) run homebrain

.PHONY: up
up: ## Start the local stack (server + DynamoDB Local)
	$(COMPOSE) up --build -d
	@echo "HomeBrain: http://localhost:8080/healthz"

.PHONY: down
down: ## Stop the local stack
	$(COMPOSE) down

.PHONY: logs
logs: ## Follow local stack logs
	$(COMPOSE) logs -f

# ------------------------------------------------------------------ inspectors
.PHONY: inspector
inspector: ## Open MCP Inspector against the local server
	npx -y @modelcontextprotocol/inspector

.PHONY: local-inspector
local-inspector: ## Run Amazon's Alexa+ Local Inspector (installed from the Developer Console)
	@command -v addon-local-inspector >/dev/null || { \
	  echo "addon-local-inspector not found. Install it from the Alexa Developer Console (see DESIGN.md §10)."; exit 1; }
	addon-local-inspector $(MCP_URL)
	mkdir -p certification
	cp /tmp/alexaplus-addon-local-inspector-live/certification-verdict.json \
	   /tmp/alexaplus-addon-local-inspector-live/inspection-summary.json certification/

# ------------------------------------------------------------------ later steps
.PHONY: ingest
ingest: ## Real Textract + Bedrock extraction over seed PDFs (week 2)
	@echo "make ingest arrives in week 2 (DESIGN.md §8). It always calls real AWS; it is never stubbed."; exit 1

.PHONY: clean
clean: ## Remove caches and build output
	rm -rf .pytest_cache .mypy_cache .ruff_cache .hypothesis .coverage coverage.xml htmlcov dist build
