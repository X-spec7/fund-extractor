VENV := .venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

HARTFORD_PDF ?= /root/test/fund-extractor/hartford.pdf

.PHONY: venv install run-hartford clean

venv:
	python3 -m venv $(VENV)

install: venv
	$(PIP) install -r requirements.txt

run-hartford:
	$(PYTHON) main.py $(HARTFORD_PDF)

clean:
	rm -rf $(VENV) output

