#!/usr/bin/env bash
# Stand up (or re-seed) the local dogfood PostgreSQL for the postgres connector.
#
# Unlike the cloud connectors' setup scripts, nothing here provisions cloud
# infrastructure: the operational-database connector is exercised against a
# throwaway local container. The same scripts/postgres_seed.sql drives the CI
# service container in .github/workflows/integration.yml.
#
# Usage:
#   scripts/setup_postgres_dev.sh          # start container if needed, (re)seed
#   scripts/setup_postgres_dev.sh --down   # remove the container
#
# Idempotent: re-running drops and recreates the dex_dogfood database.

set -euo pipefail

CONTAINER=dex-pg
PORT="${DEX_PG_PORT:-5433}"
# postgres:16, pinned by its multi-arch index digest so every machine and every
# CI run start the same bytes. Bump it deliberately, re-reading the digest with
#   docker buildx imagetools inspect postgres:16 --format '{{json .Manifest.Digest}}'
# and keep the service container in .github/workflows/integration.yml in step.
DIGEST=sha256:ca0bd484cb98bf4b24eb1010e73fb3fcbd6714d240fbc1a10eea5b7dbecb641d
IMAGE="postgres@$DIGEST"
# No capabilities at all. Started as root, the image's entrypoint needs SETUID and
# SETGID to drop to postgres (and CHOWN for a data directory it does not own).
# Started as postgres, the data directory the image ships is already its own, so
# nothing has to be granted, and `docker exec` (the seeding path below) runs as
# postgres too. scripts/check_container_hardening.sh refuses the container if any
# of these is missing.
HARDENING=(
    --user postgres
    --cap-drop ALL
    --security-opt no-new-privileges:true
    --pids-limit 256
    --memory 1g
)
SCRIPTS="$(cd "$(dirname "$0")" && pwd)"
SEED="$SCRIPTS/postgres_seed.sql"
# The connection exports are written here rather than printed, so no password
# lands in a terminal's scrollback or a CI log.
STATE_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/dex-dogfood"
EXPORTS="$STATE_DIR/postgres.env"

if [[ "${1:-}" == "--down" ]]; then
    docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
    echo "removed container $CONTAINER"
    exit 0
fi

if ! docker info >/dev/null 2>&1; then
    echo "docker daemon is not running; start Docker Desktop first" >&2
    exit 1
fi

if ! docker inspect "$CONTAINER" >/dev/null 2>&1; then
    # The image requires a superuser password, and nothing here needs it:
    # seeding runs through `docker exec`, over the container's local socket. So
    # it is random per container and handed over in a file read once and
    # removed, never as `-e` on a command line other processes can read. The
    # port is published on loopback only: a superuser can run
    # `COPY ... FROM PROGRAM`, and a shared network must not reach it.
    envfile="$(mktemp)"
    trap 'rm -f "$envfile"' EXIT
    chmod 600 "$envfile"
    printf 'POSTGRES_PASSWORD=%s\n' "$(openssl rand -hex 16)" >"$envfile"
    docker run -d --name "$CONTAINER" \
        "${HARDENING[@]}" \
        --env-file "$envfile" \
        -p "127.0.0.1:$PORT:5432" \
        "$IMAGE" >/dev/null
    rm -f "$envfile"
    echo "started $IMAGE as $CONTAINER on 127.0.0.1:$PORT"
fi
# Checked before a stopped container is started again, so one this script
# created before it hardened them is refused rather than reused.
"$SCRIPTS/check_container_hardening.sh" "$CONTAINER" "$DIGEST"
"$SCRIPTS/check_loopback_ports.sh" "$CONTAINER"
if [[ "$(docker inspect -f '{{.State.Running}}' "$CONTAINER")" != "true" ]]; then
    docker start "$CONTAINER" >/dev/null
    echo "restarted existing container $CONTAINER"
fi

until docker exec "$CONTAINER" pg_isready -U postgres -q; do
    sleep 0.5
done

docker exec "$CONTAINER" psql -U postgres -q \
    -c "DROP DATABASE IF EXISTS dex_dogfood WITH (FORCE)" \
    -c "CREATE DATABASE dex_dogfood"
docker exec -i "$CONTAINER" psql -U postgres -q -d dex_dogfood -v ON_ERROR_STOP=1 \
    <"$SEED"

install -d -m 700 "$STATE_DIR"
(
    umask 077
    cat >"$EXPORTS" <<EXPORTS
# dex reads as the read-only role:
export DATABASE_URL=postgresql://dex_ro:dex_ro@127.0.0.1:$PORT/dex_dogfood
# dbt dev builds (transform build) authenticate as dbt_dev; profiles.yml reads
# it via env_var:
export PGPASSWORD=dbt_dev
EXPORTS
)

echo "seeded dex_dogfood from scripts/postgres_seed.sql"
echo "connection exports: source $EXPORTS"
