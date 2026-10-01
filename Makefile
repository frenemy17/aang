.PHONY: install tui run test-easy test-medium test-hard web log-ui clean aang

VENV = venv/bin
AANG = $(VENV)/aang
ION = $(VENV)/ion
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

test-easy:
	@echo "Running easy test (Target: 1 iteration)..."
	@rm -rf /tmp/ion-test-easy
	@cp -r tests/easy /tmp/ion-test-easy
	@cd /tmp/ion-test-easy && git init && git add -A && git commit -m "init" 2>/dev/null
	$(ION) --repo /tmp/ion-test-easy "Fix the failing tests. Run: python -m pytest test_calc.py"

test-medium:
	@echo "Running medium test (Multi-bug across functions)..."
	@rm -rf /tmp/ion-test-medium
	@cp -r tests/medium /tmp/ion-test-medium
	@cd /tmp/ion-test-medium && git init && git add -A && git commit -m "init" 2>/dev/null
	$(ION) --repo /tmp/ion-test-medium "Fix the failing tests. Run: python -m pytest test_cart.py"

test-hard:
	@echo "Running hard test (Multi-file cross-module bug)..."
	@rm -rf /tmp/ion-test-hard
	@cp -r tests/hard /tmp/ion-test-hard
	@cd /tmp/ion-test-hard && git init && git add -A && git commit -m "init" 2>/dev/null
	$(ION) --repo /tmp/ion-test-hard "Fix the failing tests. Run: python -m pytest"

clean:
	rm -rf /tmp/ion-test-*
	rm -rf .aang .ion
	rm -rf aang.log ion.log
	rm -rf ion-easy.log
