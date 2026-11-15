# ==============================================================================
# Tailscale AgentBot Makefile
# ==============================================================================
# Lives in MA-Edge-Computing/ops/network/ alongside the Tailscale install,
# edge preflight and grants tooling.
#
# The AgentBot runtime itself is a separate checkout. Point AGENTBOT_ROOT at it
# (or run make from there):
#
#   make preflight                       # edge-preflight.sh, in this directory
#   make status                          # tailscale status
#   make setup                           # venv + runtime deps
#   make repair-cloud NODE=aperture-node # needs AGENTBOT_ROOT with tools/remediation
#
# Targets that need runtime/, tools/, hujson/ or tests/ are guarded: without
# them they exit with a message naming the missing directory, never a traceback.
#
# Usage:
#   make help                            # list every target
# ==============================================================================

SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c
MAKEFLAGS += --warn-undefined-variables

# Interpreter and venv for the AgentBot checkout.
PYTHON         ?= python3
VENV           ?= .venv
BIN            := $(VENV)/bin

# Checkout containing runtime/, tools/, tests/ — the AgentBot project itself.
AGENTBOT_ROOT  ?= .

# Target node for repair-cloud (required, no default).
NODE           ?=

# HuJSON policy path, relative to AGENTBOT_ROOT.
POLICY         ?= hujson/policy.hujson

.DEFAULT_GOAL := help

# Guards — a missing prerequisite names itself instead of failing opaquely.
define require
@test -e $(AGENTBOT_ROOT)/$(1) || { \
	echo "ERROR: $(AGENTBOT_ROOT)/$(1) not found."; \
	echo "       The AgentBot runtime is a separate checkout; set AGENTBOT_ROOT=<path>."; \
	exit 1; }
endef

# ==============================================================================
# Environment & Setup
# ==============================================================================

.PHONY: venv
venv: ## Create virtual environment if it does not exist
	@if [ ! -d "$(VENV)" ]; then \
		echo "==> Creating virtual environment in $(VENV)..."; \
		$(PYTHON) -m venv $(VENV); \
	fi

.PHONY: setup
setup: venv ## Install project requirements and dependencies
	@test -f $(AGENTBOT_ROOT)/requirements.txt || { \
		echo "ERROR: $(AGENTBOT_ROOT)/requirements.txt not found."; \
		echo "       Set AGENTBOT_ROOT=<AgentBot checkout>."; exit 1; }
	@echo "==> Installing Python dependencies..."
	@$(BIN)/pip install --upgrade pip setuptools wheel
	@$(BIN)/pip install -r $(AGENTBOT_ROOT)/requirements.txt
	@echo "==> Setup complete."

.PHONY: setup-dev
setup-dev: setup ## Install dev dependencies (linting, testing, formatting)
	@echo "==> Installing dev dependencies..."
	@$(BIN)/pip install ruff black pytest pytest-cov mypy
	@echo "==> Dev setup complete."

.PHONY: install
install: setup ## Alias for setup

.PHONY: clean
clean: ## Remove virtual environment, pycache, and build artifacts
	@echo "==> Cleaning cache and artifacts..."
	@rm -rf $(VENV) .pytest_cache .mypy_cache .ruff_cache build dist *.egg-info htmlcov .coverage
	@find . -type d -name "__pycache__" -prune -exec rm -rf {} +
	@find . -type f -name "*.pyc" -delete
	@find . -type f -name "*.pyo" -delete
	@echo "==> Clean complete."

# ==============================================================================
# Execution & Core Runtime
# ==============================================================================

.PHONY: all
all: setup run ## Setup and run the AgentBot

.PHONY: run
run: ## Run the AgentBot runtime daemon
	$(call require,runtime)
	@cd $(AGENTBOT_ROOT) && $(BIN)/python -m runtime.agent

.PHONY: run-debug
run-debug: ## Run the AgentBot with debug logging
	$(call require,runtime)
	@cd $(AGENTBOT_ROOT) && AVA_LOG=debug $(BIN)/python -m runtime.agent

.PHONY: agent-serve
agent-serve: ## Expose ingestion endpoint on AgentBot via tailscale serve (Port 8080)
	@echo "==> Configuring Tailscale serve for ingestion..."
	tailscale serve --bg --tcp 8080 127.0.0.1:8080
	@echo "==> Tailscale serve active on port 8080."

.PHONY: agent-stop
agent-stop: ## Stop the tailscale serve ingestion endpoint
	@echo "==> Stopping Tailscale serve..."
	tailscale serve --bg --tcp 8080 remove || true
	@echo "==> Tailscale serve stopped."

# ==============================================================================
# Diagnostics
# ==============================================================================

.PHONY: preflight
preflight: ## Run the read-only edge network preflight for this host
	@test -x ./edge-preflight.sh || { echo "ERROR: ./edge-preflight.sh not found"; exit 1; }
	./edge-preflight.sh

.PHONY: status
status: ## Show Tailscale tailnet status
	@tailscale status

.PHONY: local
local: ## Run diagnostics on the local host OS and Tailscale daemon
	$(call require,tools)
	@cd $(AGENTBOT_ROOT) && $(BIN)/python -m tools.local_diagnostics

.PHONY: cloud
cloud: ## Run remote diagnostics across managed nodes in the tailnet
	$(call require,tools)
	@cd $(AGENTBOT_ROOT) && $(BIN)/python -m tools.cloud_diagnostics

.PHONY: diagnose
diagnose: ## Run comprehensive triage (local + cloud)
	$(call require,tools)
	@cd $(AGENTBOT_ROOT) && $(BIN)/python -m tools.remediation diagnose --scope all

# ==============================================================================
# Remediation
# ==============================================================================

.PHONY: repair-local
repair-local: ## Execute local OS and Tailscale service repairs
	$(call require,tools)
	@cd $(AGENTBOT_ROOT) && $(BIN)/python -m tools.remediation repair --target local

.PHONY: repair-cloud
repair-cloud: ## Execute remediation against a remote node (NODE=<name>)
	@test -n "$(NODE)" || { echo "ERROR: NODE=<name> is required. Example: make repair-cloud NODE=aperture-node"; exit 1; }
	$(call require,tools)
	@cd $(AGENTBOT_ROOT) && $(BIN)/python -m tools.remediation repair --target cloud --node $(NODE)

# ==============================================================================
# Policy & Security Validation
# ==============================================================================

.PHONY: validate-policy
validate-policy: ## Validate HuJSON policy syntax and check ACL rules
	@test -f $(AGENTBOT_ROOT)/$(POLICY) || { echo "ERROR: $(AGENTBOT_ROOT)/$(POLICY) not found"; exit 1; }
	$(call require,tools)
	@echo "==> Validating $(POLICY)..."
	@cd $(AGENTBOT_ROOT) && $(BIN)/python -m tools.policy validate $(POLICY)

.PHONY: audit
audit: ## Run security audit on tailnet + policy
	@test -f $(AGENTBOT_ROOT)/$(POLICY) || { echo "ERROR: $(AGENTBOT_ROOT)/$(POLICY) not found"; exit 1; }
	$(call require,tools)
	@cd $(AGENTBOT_ROOT) && $(BIN)/python -m tools.policy audit $(POLICY)

# ==============================================================================
# Code Quality & Tests
# ==============================================================================

.PHONY: format
format: ## Auto-format code with black + ruff
	@$(BIN)/ruff check --fix . || true
	@$(BIN)/black . || true

.PHONY: lint
lint: ## Check formatting and linting (non-blocking)
	@$(BIN)/ruff check . || true
	@$(BIN)/black --check . || true

.PHONY: lint-strict
lint-strict: ## Check formatting and linting (fail on errors)
	@$(BIN)/ruff check .
	@$(BIN)/black --check .

.PHONY: typecheck
typecheck: ## Run mypy type checking
	@test -x $(BIN)/mypy || { echo "ERROR: mypy not installed — run 'make setup-dev'"; exit 1; }
	@cd $(AGENTBOT_ROOT) && $(BIN)/mypy . --ignore-missing-imports

.PHONY: test
test: ## Run unit and integration tests
	$(call require,tests)
	@cd $(AGENTBOT_ROOT) && $(BIN)/pytest -v tests/

.PHONY: test-cov
test-cov: ## Run tests with coverage report
	$(call require,tests)
	@cd $(AGENTBOT_ROOT) && $(BIN)/pytest -v --cov=. --cov-report=html --cov-report=term-missing tests/
	@echo "==> Coverage report: htmlcov/index.html"

.PHONY: test-quick
test-quick: ## Run tests fast (no coverage, stop on first failure)
	$(call require,tests)
	@cd $(AGENTBOT_ROOT) && $(BIN)/pytest -x -q tests/

# ==============================================================================
# CI Pipeline
# ==============================================================================

.PHONY: ci
ci: lint-strict typecheck test ## Full CI pipeline: lint + typecheck + test

# ==============================================================================
# Help
# ==============================================================================

.PHONY: help
help: ## Display this help message
	@echo ""
	@echo "Tailscale AgentBot - Available Targets:"
	@echo "========================================"
	@{ grep -E '^[a-zA-Z_-]+:.*## .*$$' $(MAKEFILE_LIST) || true; } \
		| sort \
		| awk 'BEGIN {FS = ":.*## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'
	@echo ""
