# Image for GitHub Codespaces (see devcontainer.json).
# Pixi itself is the only addition; the packages come from pixi.lock.
FROM mcr.microsoft.com/devcontainers/base:ubuntu-24.04

# Same pixi version as used to write pixi.lock
ARG PIXI_VERSION=v0.63.2
RUN curl -fsSL -o /usr/local/bin/pixi \
        "https://github.com/prefix-dev/pixi/releases/download/${PIXI_VERSION}/pixi-$(uname -m)-unknown-linux-musl" \
    && chmod +x /usr/local/bin/pixi \
    && pixi --version
