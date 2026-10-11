# shellcheck shell=bash
# Long-lived ClickHouse Cloud credentials, read from files and handed to one
# command at a time. Source this file; it defines functions and exports nothing.
#
# A secret in a script's environment is inherited by every process the script
# starts: jq, curl, gh, uv, pytest, dbt, and whatever code those load. Here each
# secret is a file in DEX_SECRETS_DIR, and only the command that needs it gets
# it: as a variable set on that one command (`cloudctl`, `with_admin_password`),
# or for curl as a config read from a private pipe (`cloud_api_curl_config`).
# Sourcing also unsets the same values if they arrived in the environment, so a
# shell that still exports them from an older setup cannot pass them along.
#
# Two credential sets, named so that neither can stand in for the other:
#   scoped  clickhouse_api_key, clickhouse_api_secret
#           the CI key, which can only read the dedicated service and the
#           organization's usage (preflight.sh, run_integration.sh, the tests)
#   admin   clickhouse_admin_api_key, clickhouse_admin_api_secret,
#           clickhouse_admin_password
#           the bootstrap key and the service's admin password, used only on an
#           operator's machine by setup_clickhouse_cloud_ci.sh and teardown.sh
#
# DEX_SECRETS_DIR defaults to $RUNNER_TEMP/dex-secrets on a GitHub runner and
# $TMPDIR/dex-secrets elsewhere. It must belong to the caller and be closed to
# group and others, or it is refused. README.md shows how to write the files.
#
# Written for bash 3.2, the /bin/bash an operator's Mac runs setup with.

_dex_secrets_base="${RUNNER_TEMP:-${TMPDIR:-/tmp}}"
DEX_SECRETS_DIR="${DEX_SECRETS_DIR:-${_dex_secrets_base%/}/dex-secrets}"
DEX_SECRETS_DIR="${DEX_SECRETS_DIR%/}"
unset _dex_secrets_base
unset CLICKHOUSE_CLOUD_API_KEY CLICKHOUSE_CLOUD_API_SECRET CLICKHOUSE_PASSWORD \
    DEX_TEST_CH_CLOUD_API_KEY DEX_TEST_CH_CLOUD_API_SECRET

# Select a credential set and refuse (exit 2, naming every missing path) unless
# all of its files are present, non-empty, and in a directory only the caller
# can open. An empty file is refused like a missing one: an empty key set on a
# command would let clickhousectl fall back to whatever login it has stored,
# and a check meant to prove the scoped key would pass on someone else's.
use_cloud_credentials() {
    local role=$1 file mode
    local missing=()
    case "$role" in
        scoped)
            CLOUD_API_KEY_FILE="$DEX_SECRETS_DIR/clickhouse_api_key"
            CLOUD_API_SECRET_FILE="$DEX_SECRETS_DIR/clickhouse_api_secret"
            ADMIN_PASSWORD_FILE=""
            ;;
        admin)
            CLOUD_API_KEY_FILE="$DEX_SECRETS_DIR/clickhouse_admin_api_key"
            CLOUD_API_SECRET_FILE="$DEX_SECRETS_DIR/clickhouse_admin_api_secret"
            ADMIN_PASSWORD_FILE="$DEX_SECRETS_DIR/clickhouse_admin_password"
            ;;
        *)
            echo "use_cloud_credentials: unknown credential set '$role'" >&2
            exit 2
            ;;
    esac
    if [[ -d "$DEX_SECRETS_DIR" ]]; then
        if [[ ! -O "$DEX_SECRETS_DIR" ]]; then
            echo "refusing $DEX_SECRETS_DIR: it does not belong to $(id -un)" >&2
            exit 2
        fi
        mode=$(stat -c %a "$DEX_SECRETS_DIR" 2>/dev/null ||
            stat -f %Lp "$DEX_SECRETS_DIR")
        if (( 8#$mode & 8#077 )); then
            echo "refusing $DEX_SECRETS_DIR: mode $mode lets other accounts in;" \
                "run chmod 700 $DEX_SECRETS_DIR" >&2
            exit 2
        fi
    fi
    for file in "$CLOUD_API_KEY_FILE" "$CLOUD_API_SECRET_FILE" \
        ${ADMIN_PASSWORD_FILE:+"$ADMIN_PASSWORD_FILE"}; do
        [[ -s "$file" ]] || missing+=("$file")
    done
    if [[ ${#missing[@]} -gt 0 ]]; then
        echo "missing ClickHouse Cloud $role credential file(s):" >&2
        printf '  %s\n' "${missing[@]}" >&2
        echo "write each value to its own owner-only file;" \
            "see scripts/clickhouse_cloud/README.md" >&2
        exit 2
    fi
}

# clickhousectl with the selected Cloud API key, on this one invocation only.
cloudctl() {
    CLICKHOUSE_CLOUD_API_KEY="$(<"$CLOUD_API_KEY_FILE")" \
        CLICKHOUSE_CLOUD_API_SECRET="$(<"$CLOUD_API_SECRET_FILE")" \
        clickhousectl "$@"
}

# Any command (in practice `clickhouse client`) with the service's admin
# password, on this one invocation only. Needs the admin set.
with_admin_password() {
    CLICKHOUSE_PASSWORD="$(<"$ADMIN_PASSWORD_FILE")" "$@"
}

# The selected key as a curl config, for `curl --config <(cloud_api_curl_config)`.
# Basic credentials travel on that private pipe because `curl --user key:secret`
# would expose them in the process list, even though nothing prints them.
cloud_api_curl_config() {
    local credentials
    credentials="$(<"$CLOUD_API_KEY_FILE"):$(<"$CLOUD_API_SECRET_FILE")"
    credentials=${credentials//\\/\\\\}
    credentials=${credentials//\"/\\\"}
    printf 'user = "%s"\n' "$credentials"
}
