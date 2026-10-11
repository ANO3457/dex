#!/usr/bin/env bash
# Stand up (or re-seed) the ClickHouse target for the clickhouse connector.
#
# Unlike the cloud connectors' setup scripts, nothing here provisions cloud
# infrastructure: self-hosted ClickHouse is a container, so this script is both
# the local dogfood stand-up and what the clickhouse job in
# .github/workflows/integration.yml runs. That is deliberate. The Postgres pair
# spells its seeding twice (once here, once as a psql step in the workflow) and
# the two can drift; this connector has exactly one seeding path, so they cannot.
#
# The seed is applied through `clickhouse-client --multiquery` inside the
# container rather than over HTTP, because the HTTP interface refuses
# multi-statement bodies.
#
# Usage:
#   scripts/setup_clickhouse_dev.sh          # start container if needed, (re)seed
#   scripts/setup_clickhouse_dev.sh --down   # remove the container
#
# Idempotent: re-running drops and recreates the app and dbt_dev databases.

set -euo pipefail

CONTAINER=dex-ch
HTTP_PORT="${DEX_CH_PORT:-8124}"
NATIVE_PORT="${DEX_CH_NATIVE_PORT:-9001}"
# clickhouse/clickhouse-server:25.3, pinned by its multi-arch index digest so
# every machine and every CI run start the same bytes. Bump it deliberately,
# re-reading the digest with
#   docker buildx imagetools inspect clickhouse/clickhouse-server:25.3 \
#     --format '{{json .Manifest.Digest}}'
DIGEST=sha256:b627d7a9bc0e0c1bac26cdbe9d2fc6316faa29c5d8a174f28f5abd57d0fa6ba2
IMAGE="clickhouse/clickhouse-server@$DIGEST"
# No capabilities at all. Started as root, the image's entrypoint needs CHOWN for
# the directories it creates and SETUID/SETGID for `clickhouse su`; started as
# clickhouse, every directory the image ships is already its own, so nothing has
# to be granted, and `docker exec` (the seeding path below) runs as clickhouse
# too. The server logs that it lacks the optional capabilities it would use for
# memory locking and thread priorities, and runs without them.
#
# Both limits are sized from measurement, not copied from the Postgres script.
# The pids limit counts threads, and ClickHouse starts about 675 of them for its
# background pools before it serves a query, peaking near 700 over the whole
# `-m clickhouse` suite, so 2048 bounds a runaway with room to spare. On memory,
# the server refuses a query once its resident set reaches 90% of the limit; it
# idles at about 0.6 GiB and peaked near 1.9 GiB over the suite, so 1g fails the
# first verified map on a fresh server and 2g leaves almost no headroom.
# scripts/check_container_hardening.sh refuses the container if any of these is
# missing.
HARDENING=(
    --user clickhouse
    --cap-drop ALL
    --security-opt no-new-privileges:true
    --pids-limit 2048
    --memory 4g
)
SCRIPTS="$(cd "$(dirname "$0")" && pwd)"
SEED="$SCRIPTS/clickhouse_seed.sql"
USERS="$SCRIPTS/clickhouse_local_users.sql"

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
    # CLICKHOUSE_SKIP_USER_SETUP leaves the built-in `default` user open so the
    # seed can create the two real users below; dex never connects as `default`.
    docker run -d --name "$CONTAINER" \
        "${HARDENING[@]}" \
        -e CLICKHOUSE_SKIP_USER_SETUP=1 \
        -p "$HTTP_PORT":8123 \
        -p "$NATIVE_PORT":9000 \
        --ulimit nofile=262144:262144 \
        "$IMAGE" >/dev/null
    echo "started $IMAGE as $CONTAINER on http port $HTTP_PORT"
fi
# Checked before a stopped container is started again, so one this script
# created before it hardened them is refused rather than reused.
"$SCRIPTS/check_container_hardening.sh" "$CONTAINER" "$DIGEST"
if [[ "$(docker inspect -f '{{.State.Running}}' "$CONTAINER")" != "true" ]]; then
    docker start "$CONTAINER" >/dev/null
    echo "restarted existing container $CONTAINER"
fi

# The server accepts TCP before it will answer queries, so poll /ping rather
# than sleeping a fixed amount.
for _ in $(seq 1 60); do
    if docker exec "$CONTAINER" wget -q -O- http://localhost:8123/ping 2>/dev/null | grep -q Ok; then
        break
    fi
    sleep 1
done

docker exec -i "$CONTAINER" clickhouse-client --multiquery \
    --param_app_database=app \
    --param_dev_database=dbt_dev <"$SEED"
docker exec -i "$CONTAINER" clickhouse-client --multiquery <"$USERS"

echo "seeded app and dbt_dev from scripts/clickhouse_seed.sql"
echo
echo "connect dex as the read-only user:"
echo "  export DEX_TEST_CH_DSN=clickhouse://dex_ro:dex_ro@localhost:$HTTP_PORT/app"
echo "dbt dev builds (transform build) authenticate as dbt_dev:"
echo "  export DEX_TEST_CH_DEV_PASSWORD=dbt_dev   # profiles.yml reads it via env_var"
