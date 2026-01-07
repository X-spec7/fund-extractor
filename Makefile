VENV := .venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

BLACKROCK_PDF ?= ./fund_reports/blackrock.pdf
GSAM_PDF ?= ./fund_reports/gsam.pdf


.PHONY: venv install run-blackrock run-gsam-em gen-config clean run-postgres start-postgres stop-postgres remove-postgres dropdb createdb

run-postgres:
	docker run --name postgres16 -p 5432:5432 -e POSTGRES_USER=root -e POSTGRES_PASSWORD=secret -d postgres:16-alpine

start-postgres:
	docker start postgres16

stop-postgres:
	docker stop postgres16

remove-postgres:
	docker rm -f postgres16

dropdb:
	docker exec -it postgres16 dropdb fund-extractor

createdb:
	docker exec -it postgres16 createdb --username=root --owner=root fund-extractor

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

