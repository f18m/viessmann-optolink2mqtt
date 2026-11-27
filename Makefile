# optolink2mqtt Makefile
#
# Run "make help" for the list of targets; plain "make" runs "all".
# Coding agents: prefer these targets over raw commands (see AGENTS.md).

# Use the tools of the project virtual environment, if present (created by
# "make dev-setup"), without having to activate it; otherwise use the ones in PATH:
VENV ?= .venv
ifneq ($(wildcard $(VENV)/bin/python),)
BIN := $(VENV)/bin/
PYTHON ?= $(BIN)python
else
BIN :=
PYTHON ?= python3
endif

# plain "make" formats, lints and tests (see "all")
.DEFAULT_GOAL := all

# development tools, on top of the runtime dependencies in requirements.txt
DEV_TOOLS := pytest black flake8 ruff build

.PHONY: help all dev-setup format format-check lint lint-python lint-workflows check \
	test unit-test test-hw build-wheel test-wheel inspect-wheel clean \
	run-from-local-git-clone docker-run docker-run-mosquitto \
	docker-native docker-armv6 docker-armv7 docker-arm64

help: ## Show this list of targets
	@grep -hE '^[a-zA-Z0-9_-]+:.*## ' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*## "}; {printf "  %-26s %s\n", $$1, $$2}'

#
# Python development targets:
#

all: format lint test ## Format the code, then lint and test it

dev-setup: ## Create the .venv virtualenv (VENV=<dir> to change it) with runtime deps and dev tools (pytest, black, flake8, ruff, build)
	python3 -m venv $(VENV)
	$(VENV)/bin/python -m pip install --upgrade pip
	$(VENV)/bin/python -m pip install -r requirements.txt $(DEV_TOOLS)

format: ## Reformat all Python code with black (modifies files)
	$(BIN)black .

format-check: ## Check the formatting with black, without modifying files
	$(BIN)black --check --diff .

lint: lint-python ## Run all Python linters (ruff, flake8)

lint-python:
	$(BIN)ruff check src/ tests/
	$(BIN)flake8 -v

lint-workflows: ## Lint the GitHub Actions workflows (requires actionlint)
	actionlint

check: format-check lint test ## Everything CI checks: run this before committing

test: unit-test ## Run the unit tests (REGEX=<pytest -k expression> to filter them)

unit-test:
ifeq ($(REGEX),)
	$(BIN)pytest -vvv --log-level=INFO
else
	$(BIN)pytest -vvvv --log-level=INFO -s -k $(REGEX)
endif

test-hw: ## Run the read-only hardware test against a real device: SERIAL_PORT=/dev/ttyUSB0
ifeq ($(SERIAL_PORT),)
	$(error SERIAL_PORT is not set, e.g. make test-hw SERIAL_PORT=/dev/ttyUSB0)
endif
	OPTOLINK2MQTT_TEST_SERIAL_PORT=$(SERIAL_PORT) $(BIN)pytest -vvv -s tests/test_optolinkvs2_protocol.py

build-wheel: ## Build the wheel into dist/
	$(PYTHON) -m build --wheel --outdir dist/

test-wheel: ## Rebuild the wheel and install it in the current environment
	rm -rf dist/ && \
		$(PYTHON) -m pip uninstall -y viessmann-optolink2mqtt && \
		$(MAKE) build-wheel && \
		$(PYTHON) -m pip install dist/viessmann_optolink2mqtt-*-py3-none-any.whl

inspect-wheel: ## Show the metadata of the built wheel (requires wheel2json)
	# see https://github.com/wheelodex/wheel-inspect
	wheel2json dist/viessmann_optolink2mqtt-*-py3-none-any.whl

clean: ## Remove build artifacts and caches
	rm -rf dist/ build/ .pytest_cache/ .ruff_cache/
	find . -name __pycache__ -type d -not -path './$(VENV)/*' -prune -exec rm -rf {} +

run-from-local-git-clone: ## Run optolink2mqtt from this checkout (ARGS="read-register 0x00f8 8" etc.)
	# this is useful if you are running on e.g. your Raspberry PI / any other Single Board Computer (SBC)
	# connected to the Viessmann device and you want to test some changes to a local "git cloned"
	# optolink2mqtt source tree:
	$(PYTHON) -m src.optolink2mqtt.main $(ARGS)


#
# Docker helper targets
#

# note that by using --network=host on the Mosquitto container, its default configuration
# will work out of the box (by default Mosquitto listens only local connections);
# and by using --network=host on the optolink2mqtt container, also the optolink2mqtt default config
# pointing to "localhost" as MQTT broker will work fine:

ifeq ($(CFGFILE),)
CFGFILE:=$(shell pwd)/optolink2mqtt.yaml
endif

docker-run: ## Run the optolink2mqtt:latest image with CFGFILE (default: ./optolink2mqtt.yaml)
	docker run -v $(CFGFILE):/etc/optolink2mqtt/optolink2mqtt.yaml \
		--hostname $(shell hostname) \
		--network=host \
		optolink2mqtt:latest $(ARGS)

docker-run-mosquitto: ## (Re)start a local Mosquitto broker container
	docker container stop mosquitto || true
	docker container rm mosquitto || true
	docker run -d --name=mosquitto --network=host eclipse-mosquitto:latest


# to cross-build docker images for other platforms (e.g. ARM), the buildx image builder backend is required:

docker-native: ## Build the optolink2mqtt:latest image for amd64
	docker build --platform linux/amd64 --tag optolink2mqtt:latest --build-arg USERNAME=root .

docker-armv6: ## Build the image for arm/v6
	docker buildx build --platform linux/arm/v6 --tag optolink2mqtt:latest --build-arg USERNAME=root .

docker-armv7: ## Build the image for arm/v7
	docker buildx build --platform linux/arm/v7 --tag optolink2mqtt:latest --build-arg USERNAME=root .

docker-arm64: ## Build the image for arm64
	docker buildx build --platform linux/arm64/v8 --tag optolink2mqtt:latest --build-arg USERNAME=root .
