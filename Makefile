.DEFAULT_GOAL := help

.PHONY: help dev-single dev-mesh dev-stop dev-logs test test-cov lint fmt build-deb build-rust

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

dev-single: ## Run single-node from source
	uv run astromeshd --config ./config --log-level debug

dev-mesh: ## Start 3-node gossip mesh
	docker compose -f docker/docker-compose.gossip.yml up -d --build

dev-stop: ## Stop mesh
	docker compose -f docker/docker-compose.gossip.yml down

dev-logs: ## Tail mesh logs
	docker compose -f docker/docker-compose.gossip.yml logs -f

test: ## Run tests
	uv run pytest -v

test-cov: ## Tests with coverage
	uv run pytest --cov=astromesh -v

lint: ## Lint
	uv run ruff check astromesh/ tests/

fmt: ## Format
	uv run ruff format astromesh/ tests/

build-deb: ## Build .deb package
	bash packaging/build-deb.sh

build-rust: ## Build Rust native extensions
	maturin develop --release
