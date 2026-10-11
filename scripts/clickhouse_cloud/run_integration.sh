#!/usr/bin/env bash
# Local runner for the same preflight and pytest marker used in GitHub Actions.
# The scoped Cloud API key comes from DEX_SECRETS_DIR (see secrets.sh); the rest
# are the environment's non-secret values plus the two database credentials the
# tests read.

set -euo pipefail

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
REQUIRED=(
  DEX_TEST_CH_CLOUD_ORG_ID DEX_TEST_CH_CLOUD_SERVICE_ID
  DEX_TEST_CH_CLOUD_HOST DEX_TEST_CH_CLOUD_PORT
  DEX_TEST_CH_CLOUD_DATABASE DEX_TEST_CH_CLOUD_DEV_DATABASE
  DEX_TEST_CH_CLOUD_COMPUTE_UNIT_PRICE_USD DEX_TEST_CH_CLOUD_MAX_SECONDS
  DEX_TEST_CH_CLOUD_MAX_DAILY_CHC DEX_TEST_CH_CLOUD_DSN
  DEX_TEST_CH_CLOUD_DEV_PASSWORD
)
for name in "${REQUIRED[@]}"; do
  [[ -n "${!name:-}" ]] || { echo "$name is required" >&2; exit 2; }
done
# shellcheck source=scripts/clickhouse_cloud/secrets.sh
source "$ROOT/scripts/clickhouse_cloud/secrets.sh"
use_cloud_credentials scoped

"$ROOT/scripts/clickhouse_cloud/preflight.sh"
cd "$ROOT/packages/dex-core"
uv run pytest tests/integration/test_clickhouse_cloud.py -q --tb=line \
  -m clickhouse_cloud "$@"
