VENV     := .venv
BIN      := $(VENV)/bin
ACTIVATE := . $(BIN)/activate &&
PYTHON   ?= python3
LOCAL_K8S ?= local-k8s

reformat: format-local-k8s

format-local-k8s: $(VENV)
	$(BIN)/ruff format $(LOCAL_K8S)
	$(BIN)/ruff check --fix $(LOCAL_K8S)

check-local-k8s: $(VENV)
	$(BIN)/ruff format --check $(LOCAL_K8S)
	$(BIN)/ruff check $(LOCAL_K8S)
	cd $(LOCAL_K8S) && ../$(BIN)/mypy -p local_k8s

test-local-k8s: $(VENV)
	cd $(LOCAL_K8S) && ../$(BIN)/pytest

check-staged-formatted: reformat
	@set -eu; \
	staged=$$(git diff --cached --name-only --diff-filter=ACMR); \
	[ -n "$$staged" ] || exit 0; \
	git diff --exit-code -- $$staged || { \
		echo >&2 "Staged files need formatting. Reformatted on disk; review and git add."; \
		exit 1; \
	}

setup-k8s: $(VENV)
	$(BIN)/local-k8s create-cluster \
		--kind-config local-k8s/examples/kind-cluster.yaml \
		--components local-k8s/examples/components.yaml

teardown-k8s: $(VENV)
	$(BIN)/local-k8s teardown-cluster

$(VENV): $(LOCAL_K8S)/pyproject.toml .python-version
	$(PYTHON) -m venv $(VENV)
	$(ACTIVATE) pip install yamllint
	$(ACTIVATE) pip install -e "./$(LOCAL_K8S)[dev]"
	touch $(VENV)
