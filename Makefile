VENV := .venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

BLACKROCK_PDF ?= ./fund_reports/blackrock.pdf
GSAM_PDF ?= ./fund_reports/gsam.pdf


.PHONY: venv install run-blackrock run-gsam-em gen-config clean

venv:
	python3 -m venv $(VENV)

install: venv 
	$(PIP) install -r requirements.txt

run-blackrock:
	$(PYTHON) main.py --fund-id blackrock_international $(BLACKROCK_PDF) --verbose

run-gsam-em:
	$(PYTHON) main.py --fund-id gsam_emerging_markets_equity $(GSAM_PDF) --verbose

gen-config:
	$(PYTHON) generate_config.py

clean:
	rm -rf $(VENV) output

