#
# Builder docker
#

FROM public.ecr.aws/docker/library/python:3.14-alpine AS builder

# NOTE: git is required to get the "hatch-vcs" plugin to work and produce the _optolink2mqtt_version.py file
RUN apk add build-base linux-headers git

WORKDIR /build
COPY requirements.txt pyproject.toml README.md ./
COPY ./src ./src/
COPY ./.git ./.git/

RUN python -m pip install --upgrade pip
RUN pip install --target=/build/deps -r requirements.txt
RUN pip install build
RUN python -m build --wheel --outdir /build/wheel


#
# Production docker
#

FROM public.ecr.aws/docker/library/python:3.14-alpine

ARG USERNAME=optolink2mqtt
LABEL org.opencontainers.image.source=https://github.com/f18m/optolink2mqtt

WORKDIR /opt/optolink2mqtt

# copy the dependencies from the builder stage
COPY --from=builder /build/deps ./deps/

# copy all source code
COPY src/optolink2mqtt/*.py ./src/

# copy the version file produced by hatch-vcs plugin from the builder stage:
COPY --from=builder /build/src/optolink2mqtt/_optolink2mqtt_version.py ./src/

RUN mkdir ./conf ./schema
COPY src/optolink2mqtt/schema/* ./schema/

# do not copy the default configuration file: it's better to error out loudly
# if the user fails to bind-mount his own config file, rather than using a default config file.
# the reason is that at least the MQTT broker IP address is something the user
# will need to configure
RUN mkdir /etc/optolink2mqtt/

# add user optolink2mqtt to image
RUN if [[ "$USERNAME" != "root" ]]; then \
    addgroup -S optolink2mqtt && \
    adduser -S ${USERNAME} -G optolink2mqtt && \
    chown -R ${USERNAME}:optolink2mqtt /opt/optolink2mqtt ; \
    fi

# process run as optolink2mqtt user
USER ${USERNAME}

# set conf path
ENV OPTOLINK2MQTT_CONFIG="/etc/optolink2mqtt/optolink2mqtt.yaml"
ENV OPTOLINK2MQTT_CONFIGSCHEMA="/opt/optolink2mqtt/schema/optolink2mqtt.schema.yaml"

# add deps to PYTHONPATH
ENV PYTHONPATH="/opt/optolink2mqtt/src:/opt/optolink2mqtt/deps"

# run process
# it's important to use python -m to run the module, otherwise the relative imports
# will not work. Remember that the docker image does not contain the actual optolink2mqtt
# wheel installed (this is to make it possible to remove "pip" from the base image in future)
CMD ["python", "-m", "src.main"]
