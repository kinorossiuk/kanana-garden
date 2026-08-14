PYTHON ?= python3
KANANA ?= PYTHONPATH=src $(PYTHON) -m kanana_garden

ifneq (,$(wildcard .env))
include .env
export
endif

.PHONY: setup test validate server-doctor device-doctor capture ota-download github-check

setup:
	$(PYTHON) -m venv .venv
	.venv/bin/python -m pip install -e .

test:
	PYTHONPATH=src $(PYTHON) -m unittest discover -s tests -v

validate:
	$(KANANA) validate
	$(KANANA) suite-validate pi5-parity-ko-v1
	$(KANANA) report-validate

server-doctor:
	$(KANANA) doctor

device-doctor:
	$(KANANA) uis7862s-doctor

# Example: make capture CAPTURE_ARGS='--label issue-12 --package com.example.app --ota-version 2026.08'
capture:
	$(KANANA) uis7862s-capture $(CAPTURE_ARGS)

ota-download:
	@test -n "$(OTA_VERSION)" -a -n "$(OTA_DOWNLOAD_URL)" -a -n "$(OTA_SHA256)" || \
		{ echo 'Set OTA_VERSION, OTA_DOWNLOAD_URL and OTA_SHA256 in .env'; exit 2; }
	$(KANANA) ota-download --version "$(OTA_VERSION)" --url "$(OTA_DOWNLOAD_URL)" --sha256 "$(OTA_SHA256)"

github-check:
	curl -fsS "https://api.github.com/repos/$(GITHUB_REPOSITORY)" >/dev/null
