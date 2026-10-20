#!/usr/bin/env bash
# Read-only ClickHouse Cloud admission check. This performs no SQL connection,
# so an over-budget refusal cannot wake an idled service. It authenticates with
# the scoped CI key from DEX_SECRETS_DIR (see secrets.sh), and only the two
# clickhousectl calls ever hold it.

set -euo pipefail
# jq -e and a failed command substitution exit under set -e without a word, which
# leaves a red CI step with nothing to go on; name the line instead.
trap 'echo "preflight failed at line $LINENO (exit $?)" >&2' ERR

ORGANIZATION="${DEX_TEST_CH_CLOUD_ORG_ID:-}"
SERVICE="${DEX_TEST_CH_CLOUD_SERVICE_ID:-}"
LIMIT="${DEX_TEST_CH_CLOUD_MAX_DAILY_CHC:-2}"
REPORT_ONLY=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --organization) ORGANIZATION="$2"; shift 2 ;;
    --service) SERVICE="$2"; shift 2 ;;
    --limit) LIMIT="$2"; shift 2 ;;
    --report-only) REPORT_ONLY=true; shift ;;
    *) echo "unknown flag: $1" >&2; exit 2 ;;
  esac
done

[[ -n "$ORGANIZATION" ]] || { echo "organization is required" >&2; exit 2; }
[[ -n "$SERVICE" ]] || { echo "service is required" >&2; exit 2; }
[[ "$LIMIT" =~ ^[0-9]+([.][0-9]+)?$ ]] || {
  echo "daily CHC limit must be a non-negative number" >&2; exit 2; }
for tool in clickhousectl jq; do
  command -v "$tool" >/dev/null || { echo "$tool is required on PATH" >&2; exit 2; }
done

# shellcheck source=scripts/clickhouse_cloud/secrets.sh
source "$(dirname "${BASH_SOURCE[0]}")/secrets.sh"
use_cloud_credentials scoped

SERVICE_JSON=$(cloudctl cloud service get "$SERVICE" --org-id "$ORGANIZATION" --json)
ACTUAL_ID=$(jq -er '.id' <<<"$SERVICE_JSON")
[[ "$ACTUAL_ID" == "$SERVICE" ]] || {
  echo "control plane returned service $ACTUAL_ID, expected $SERVICE" >&2; exit 1; }

TODAY=$(date -u +%F)
USAGE_JSON=$(cloudctl cloud org usage \
  --org-id "$ORGANIZATION" --from-date "$TODAY" --to-date "$TODAY" --json)
COMPUTE_CHC=$(jq -er --arg service "$SERVICE" '
  [.costs[]? | select((.serviceId // .entityId) == $service) |
    (.metrics.computeCHC // 0)] | add // 0
' <<<"$USAGE_JSON")
# A boolean, so no -e: false is a valid answer, not a missing field. A day with no
# row for the service yet has no final figure, so it reads as provisional too.
PROVISIONAL=$(jq -r --arg service "$SERVICE" '
  [.costs[]? | select((.serviceId // .entityId) == $service)]
  | length == 0 or any(.[]; .locked != true)
' <<<"$USAGE_JSON")
STATE=$(jq -er '.state' <<<"$SERVICE_JSON")

jq -n \
  --arg organization_id "$ORGANIZATION" \
  --arg service_id "$SERVICE" \
  --arg date "$TODAY" \
  --arg state "$STATE" \
  --argjson compute_chc "$COMPUTE_CHC" \
  --argjson limit_chc "$LIMIT" \
  --argjson provisional "$PROVISIONAL" \
  '{organization_id:$organization_id,service_id:$service_id,date:$date,
    service_state:$state,compute_chc:$compute_chc,limit_chc:$limit_chc,
    provisional:$provisional}'

if [[ "$REPORT_ONLY" != true ]] && ! jq -en \
    --argjson used "$COMPUTE_CHC" --argjson limit "$LIMIT" '$used < $limit' >/dev/null; then
  echo "ClickHouse Cloud admission refused: service has used ${COMPUTE_CHC} CHC today (limit ${LIMIT})" >&2
  exit 1
fi
