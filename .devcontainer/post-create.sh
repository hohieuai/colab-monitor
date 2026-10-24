#!/usr/bin/env bash
# Set up the dev container: uv, the locked dependencies, and Chromium for the browser tests.
set -euo pipefail

# The base image lists the Yarn apt repository, whose signing key it lacks, so apt-get fails.
# This project doesn't use Yarn.
sudo rm -f /etc/apt/sources.list.d/yarn.list

pipx install uv
uv sync --locked
uv run playwright install --with-deps chromium
