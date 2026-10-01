.PHONY: install aang tui run web log-ui clean

VENV = venv/bin
AANG = $(VENV)/aang
PYTHON = $(VENV)/python

install:
	python3 -m venv venv
	$(VENV)/pip install -e .
	@echo "✓ Aang installed. Ensure your API key is exported:"
	@echo "  export GROQ_API_KEY=your-key"

aang:
	$(AANG) --repo .

tui:
	$(AANG) --repo .

run:
	$(AANG) --repo . "$(TASK)"

web:
	$(PYTHON) -m aang.server 5173

log-ui: web

clean:
	rm -rf .aang .ion
	rm -rf aang.log ion.log ion-easy.log
	rm -rf /tmp/aang-test-* /tmp/ion-test-*
