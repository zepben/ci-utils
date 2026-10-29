VENV     := .venv
BIN      := $(VENV)/bin
ACTIVATE := . $(BIN)/activate &&
PYTHON   ?= python3
ZEP_DEV ?= zep-dev

TEMPLATE_DIR = $(ZEP_DEV)/examples/integration
TEMPLATE_NAME = integration

.PHONY: reformat check format-zep-dev check-zep-dev test-zep-dev check-staged-formatted k8s-tools build-distribution create-environment destroy-environment clean

reformat: format-zep-dev
check: check-zep-dev check-staged-formatted

format-zep-dev: $(VENV)
	$(BIN)/ruff format $(ZEP_DEV)
	$(BIN)/ruff check --fix $(ZEP_DEV)

check-zep-dev: $(VENV)
	$(BIN)/ruff format --check $(ZEP_DEV)
	$(BIN)/ruff check $(ZEP_DEV)
	cd $(ZEP_DEV) && ../$(BIN)/mypy --config-file pyproject.toml src tests

test-zep-dev: $(VENV)
	cd $(ZEP_DEV) && ../$(BIN)/pytest

check-staged-formatted: reformat
	@set -eu; \
	staged=$$(git diff --cached --name-only --diff-filter=ACMR); \
	[ -n "$$staged" ] || exit 0; \
	git diff --exit-code -- $$staged || { \
		echo >&2 "Staged files need formatting. Reformatted on disk; review and git add."; \
		exit 1; \
	}

k8s-tools: $(VENV)
	$(ACTIVATE) zep-dev tools install

build-distribution: k8s-tools
	$(ACTIVATE) zep-dev distribution build --distribution $(TEMPLATE_DIR)/distribution.yaml

create-environment: k8s-tools
	$(ACTIVATE) zep-dev environment create --template $(TEMPLATE_DIR)/template.yaml --allow-reuse

destroy-environment: $(VENV)
	$(ACTIVATE) zep-dev environment destroy $(TEMPLATE_NAME)

clean:
	rm -rf $(VENV)

$(VENV): $(ZEP_DEV)/pyproject.toml .python-version
	$(PYTHON) -m venv $(VENV)
	$(ACTIVATE) pip install yamllint
	$(ACTIVATE) pip install -e "./$(ZEP_DEV)[dev]"
	touch $(VENV)
