VENV := .venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

HARTFORD_PDF ?= /root/test/fund-extractor/fund-reports/hartford.pdf
BLACKROCK_PDF ?= /root/test/fund-extractor/fund-reports/blackrock.pdf
GSAM_PDF ?= /root/test/fund-extractor/fund-reports/gsam.pdf

.PHONY: venv install run-hartford run-blackrock run-gsam-em clean

venv:
	python3 -m venv $(VENV)

install: venv 
	$(PIP) install -r requirements.txt

run-hartford:
	$(PYTHON) main.py --fund-id hartford_balanced_income $(HARTFORD_PDF) --verbose

run-blackrock:
	$(PYTHON) main.py --fund-id blackrock_international $(BLACKROCK_PDF) --verbose

run-gsam-em:
	$(PYTHON) main.py --fund-id gsam_emerging_markets_equity $(GSAM_PDF) --verbose

clean:
	rm -rf $(VENV) output

