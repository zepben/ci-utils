VENV     := .venv
BIN      := $(VENV)/bin
ACTIVATE := . $(BIN)/activate &&
PYTHON   ?= python3
ZEP_DEV ?= zep-dev

reformat: format-zep-dev
check: check-zep-dev check-staged-formatted

format-zep-dev: $(VENV)
	$(BIN)/ruff format $(ZEP_DEV)
	$(BIN)/ruff check --fix $(ZEP_DEV)

check-zep-dev: $(VENV)
	$(BIN)/ruff format --check $(ZEP_DEV)
	$(BIN)/ruff check $(ZEP_DEV)
	cd $(ZEP_DEV) && ../$(BIN)/mypy -p zep_dev

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

setup-k8s: install-tools
	$(BIN)/zep-dev cluster create \
		--kind-config zep-dev/examples/kind-cluster.yaml \
		--components zep-dev/examples/components.yaml

teardown-k8s: install-tools
	$(BIN)/zep-dev cluster teardown

install-tools: $(VENV)
	$(BIN)/zep-dev tools install

$(VENV): $(ZEP_DEV)/pyproject.toml .python-version
	$(PYTHON) -m venv $(VENV)
	$(ACTIVATE) pip install yamllint
	$(ACTIVATE) pip install -e "./$(ZEP_DEV)[dev]"
	touch $(VENV)
