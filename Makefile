.PHONY: install aang tui run web setup doctor log-ui clean

VENV = venv/bin
AANG = $(VENV)/aang
PYTHON = $(VENV)/python

install:
	python3 -m venv venv
	$(VENV)/pip install -e .
	@echo "✓ Aang installed! Run 'make setup' (or 'aang setup') to configure your API keys."
	@echo "  Run 'make aang' (or 'aang') to start coding."

aang:
	$(AANG) --repo .

tui:
	$(AANG) --repo .

setup:
	$(AANG) setup

doctor:
	$(AANG) doctor

run:
	$(AANG) --repo . "$(TASK)"

web:
	$(PYTHON) -m aang.server 5173

log-ui: web

clean:
	rm -rf .aang .ion
	rm -rf aang.log ion.log ion-easy.log
	rm -rf /tmp/aang-test-* /tmp/ion-test-*
