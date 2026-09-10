FROM python:3.12-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends git curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -s /bin/bash ubuntu

USER ubuntu
WORKDIR /home/ubuntu
