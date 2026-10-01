HOST_UID := $(shell id -u)
HOST_GID := $(shell id -g)
export HOST_UID
export HOST_GID

RUN = docker compose run --rm --no-deps app

.DEFAULT_GOAL := help
.PHONY: help lock build check test fix extract evaluate report serve test-set

help: ## List the available targets
	@grep -E '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

lock: ## Resolve the dependencies into uv.lock
	docker run --rm --user $(HOST_UID):$(HOST_GID) -e HOME=/tmp -v $(CURDIR):/app -w /app python:3.13-slim \
		sh -c 'pip install --quiet --no-cache-dir --target /tmp/uv uv==0.12.21 && PYTHONPATH=/tmp/uv python -m uv lock'

build: ## Build the image
	docker compose build app

check: ## The whole gate: Ruff, mypy, pytest
	$(RUN) sh -c 'ruff check . && ruff format --check . && mypy && pytest -q'

test: ## Tests only; none of them calls the model
	$(RUN) pytest -q

fix: ## Apply the fixes and formatting of Ruff
	$(RUN) sh -c 'ruff format . && ruff check --fix .'

extract: ## Extract one invoice: make extract FILE=evaluation/test-set/pdfs/2026-000236.pdf (one paid call)
	$(RUN) extract-invoice $(FILE)

evaluate: ## Run the measurement: make evaluate LIMIT=3 QUALITY="poor harsh" (one paid call per image)
	$(RUN) evaluate-extraction $(if $(LIMIT),--limit $(LIMIT)) $(if $(QUALITY),--quality $(QUALITY)) \
		$(if $(RESULTS),--results $(RESULTS))

report: ## Print the figures of a finished run again, free: make report RESULTS=evaluation/results.jsonl SECOND_READ=evaluation/second-read.jsonl
	$(RUN) evaluate-extraction --report-only $(if $(RESULTS),--results $(RESULTS)) \
		$(if $(SECOND_READ),--second-read $(SECOND_READ))

serve: ## Start the endpoint on http://127.0.0.1:8083
	docker compose up app

test-set: ## Rebuild the test set from a running ../invoice-book
	docker compose --profile tools run --rm test-set
