# optolink2mqtt Makefile

#
# Python development targets:
#

format:
	black .

lint: lint-python #lint-yaml lint-yaml-with-schema

lint-python:
	ruff check src/
	flake8 -v

build-wheel:
	python3 -m build --wheel --outdir dist/

test-wheel:
	rm -rf dist/ && \
 		pip3 uninstall -y optolink2mqtt && \
		$(MAKE) build-wheel && \
		pip3 install dist/optolink2mqtt-*-py3-none-any.whl

inspect-wheel:
	# see https://github.com/wheelodex/wheel-inspect
	wheel2json dist/optolink2mqtt-*-py3-none-any.whl

run-from-local-git-clone:
	# this is useful if you are running on e.g. your Raspberry PI / any other Single Board Computer (SBC)
	# connected to the Viessmann device and you want to test some changes to a local "git cloned"
	# optolink2mqtt source tree:
	python -m src.optolink2mqtt.main 


test: unit-test integration-test

unit-test:
ifeq ($(REGEX),)
	pytest -vvv --log-level=INFO -m unit
else
	pytest -vvvv --log-level=INFO -s -m unit -k $(REGEX)
endif

# During integration-tests the "testcontainers" project will be used to spin up 
# both a Mosquitto broker and the optolink2mqtt docker, so make sure you don't
# have a Mosquitto broker (or other containers) already listening on the 1883 port
# when using this target:
integration-test:
ifeq ($(REGEX),)
	pytest -vvvv --log-level=INFO -s -m integration
else
	pytest -vvvv --log-level=INFO -s -m integration -k $(REGEX)
endif



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

docker-run:
	docker run -v $(CFGFILE):/opt/optolink2mqtt/conf/optolink2mqtt.yaml \
		--hostname $(shell hostname) \
		--network=host \
		optolink2mqtt:latest $(ARGS)

docker-run-mosquitto:
	docker container stop mosquitto || true
	docker container rm mosquitto || true
	docker run -d --name=mosquitto --network=host eclipse-mosquitto:latest 


# to cross-build docker images for other platforms (e.g. ARM), the buildx image builder backend is required:

docker-native:
	docker build --platform linux/amd64 --tag optolink2mqtt:latest --build-arg USERNAME=root .

docker-armv6:
	docker buildx build --platform linux/arm/v6 --tag optolink2mqtt:latest --build-arg USERNAME=root .

docker-armv7:
	docker buildx build --platform linux/arm/v7 --tag optolink2mqtt:latest --build-arg USERNAME=root .

docker-arm64:
	docker buildx build --platform linux/arm64/v8 --tag optolink2mqtt:latest --build-arg USERNAME=root .
