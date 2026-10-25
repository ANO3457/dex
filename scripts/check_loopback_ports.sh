#!/usr/bin/env bash
# Refuse a dogfood database container that publishes a port beyond loopback.
#
# The dogfood databases carry committed role passwords, and ClickHouse runs with
# an open `default` user until it is seeded, so a port published on every host
# interface hands them to anyone on the same network. Both setup scripts publish
# on 127.0.0.1 and run this after starting their container, so a container left
# over from before that, which `docker run` would never recreate, fails here
# instead of being reused.
#
# Usage:
#   scripts/check_loopback_ports.sh <container>

set -euo pipefail

if [[ $# -ne 1 ]]; then
    echo "usage: $0 <container>" >&2
    exit 2
fi
CONTAINER=$1

if ! BINDINGS=$(docker inspect --format \
    '{{range $port, $binds := .HostConfig.PortBindings}}{{range $binds}}{{$port}}={{.HostIp}} {{end}}{{end}}' \
    "$CONTAINER" 2>/dev/null); then
    echo "no container named $CONTAINER to check" >&2
    exit 1
fi

PROBLEMS=()
for binding in $BINDINGS; do
    host_ip=${binding#*=}
    [[ "$host_ip" == "127.0.0.1" ]] ||
        PROBLEMS+=("${binding%%=*} is published on '${host_ip:-all interfaces}', not 127.0.0.1")
done

if [[ ${#PROBLEMS[@]} -gt 0 ]]; then
    echo "$CONTAINER publishes a port beyond loopback:" >&2
    printf '  %s\n' "${PROBLEMS[@]}" >&2
    echo "remove it and start it again: $(dirname "$0")/setup_*_dev.sh --down" >&2
    exit 1
fi
