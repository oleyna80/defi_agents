.PHONY: setup install test run hedger-run live-l3 lint clean dry-run krystal-probe hedger-gate-report

VENV := .venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
PYTEST := $(VENV)/bin/pytest
MYPY := $(VENV)/bin/mypy

setup:
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	@echo "Environment ready. Use 'make run' or 'make live-l3'."

install:
	$(PIP) install -r requirements.txt

run:
	PYTHONPATH=src $(PYTHON) main.py

hedger-run:
	PYTHONPATH=src $(PYTHON) hedger_main.py

dry-run:
	PYTHONPATH=src $(PYTHON) main.py

krystal-probe:
	PYTHONPATH=src $(PYTHON) scripts/krystal_execution_probe.py

hedger-gate-report:
	./scripts/hedger_shadow_gate_report.sh "24 hours ago"

test:
	PYTHONPATH=src $(PYTEST) -v tests/

live-l3:
	PYTHONPATH=src $(PYTHON) debug_l3_live.py

lint:
	@if [ -x "$(MYPY)" ]; then \
		PYTHONPATH=src $(MYPY) src/ ; \
	else \
		echo "mypy is not installed in $(VENV)."; \
	fi

clean:
	rm -rf $(VENV)
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
