#!/bin/zsh
# User LaunchAgent entry point. Credentials are read only by Docker Compose.
set -eu
cd "${0:A:h}"
export PATH="$HOME/.docker/bin:/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"
docker desktop start --timeout 120
docker compose -f compose.yaml -f compose.local.yaml up -d --no-build
# Docker restart policies supervise processes. Do not race a manual deployment.
exec /usr/bin/caffeinate -s
