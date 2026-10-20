#!/usr/bin/env bash
# Refuse a dogfood database container that is not running hardened.
#
# The invariants are fixed here rather than derived from the `docker run` flags
# that set them, so a flag dropped from a setup script, or a container left over
# from before the flags existed, fails this check instead of quietly passing it.
# Both setup scripts run it after starting their container, and the postgres
# Integration job runs it against its service container.
#
# Usage:
#   scripts/check_container_hardening.sh <container> <sha256:digest> [cap ...]
#
#   <sha256:digest>  the image digest the container must be pinned to
#   [cap ...]        capabilities deliberately added back, each documented where
#                    it is granted; any other addition is refused

set -euo pipefail

if [[ $# -lt 2 ]]; then
    echo "usage: $0 <container> <sha256:digest> [cap ...]" >&2
    exit 2
fi
CONTAINER=$1
DIGEST=$2
shift 2

# Docker reports capabilities with or without the CAP_ prefix depending on its
# version and on how they were requested, so both sides are compared in one form.
normalize_caps() {
    local cap
    for cap in "$@"; do
        cap=$(printf '%s' "$cap" | tr '[:lower:]' '[:upper:]')
        printf 'CAP_%s\n' "${cap#CAP_}"
    done | sort -u
}

# A JSON array of plain tokens (or null) as space-separated words.
json_words() {
    local raw=$1
    [[ "$raw" == "null" ]] && return 0
    raw=${raw#[}
    raw=${raw%]}
    raw=${raw//\"/}
    printf '%s' "${raw//,/ }"
}

if ! FIELDS=$(docker inspect --format \
    '{{.Config.Image}}|{{json .HostConfig.CapDrop}}|{{json .HostConfig.CapAdd}}|{{json .HostConfig.SecurityOpt}}|{{.HostConfig.PidsLimit}}|{{.HostConfig.Memory}}|{{.HostConfig.Privileged}}' \
    "$CONTAINER" 2>/dev/null); then
    echo "no container named $CONTAINER to check" >&2
    exit 1
fi
IFS='|' read -r IMAGE CAP_DROP CAP_ADD SECURITY_OPT PIDS_LIMIT MEMORY PRIVILEGED <<<"$FIELDS"

PROBLEMS=()
[[ "$IMAGE" == *"@$DIGEST" ]] ||
    PROBLEMS+=("image is $IMAGE, not pinned to @$DIGEST")
# shellcheck disable=SC2046 # word splitting is the point: one cap per word
[[ "$(normalize_caps $(json_words "$CAP_DROP"))" == "CAP_ALL" ]] ||
    PROBLEMS+=("capabilities dropped are $CAP_DROP, not [\"ALL\"]")
# shellcheck disable=SC2046
if [[ "$(normalize_caps $(json_words "$CAP_ADD"))" != "$(normalize_caps "$@")" ]]; then
    PROBLEMS+=("capabilities added back are $CAP_ADD, expected [${*:-}]")
fi
case " $(json_words "$SECURITY_OPT") " in
    *" no-new-privileges "* | *" no-new-privileges:true "*) ;;
    *) PROBLEMS+=("security options are $SECURITY_OPT, without no-new-privileges") ;;
esac
# A limit the daemon cannot enforce reads back as 0 (rootless Docker without
# delegated cgroup controllers does this silently), and that is refused too: an
# unenforced limit is no limit.
[[ "$PIDS_LIMIT" =~ ^[1-9][0-9]*$ ]] ||
    PROBLEMS+=("pids limit is $PIDS_LIMIT, not a positive limit")
[[ "$MEMORY" =~ ^[1-9][0-9]*$ ]] ||
    PROBLEMS+=("memory limit is $MEMORY, not a positive limit")
[[ "$PRIVILEGED" == "false" ]] ||
    PROBLEMS+=("container is privileged")

if [[ ${#PROBLEMS[@]} -gt 0 ]]; then
    echo "refusing $CONTAINER: it is not running hardened" >&2
    printf '  - %s\n' "${PROBLEMS[@]}" >&2
    echo "recreate it from the current setup script (its --down flag removes the old one)," >&2
    echo "and on rootless Docker delegate the pids and memory cgroup controllers" >&2
    exit 1
fi
echo "$CONTAINER is hardened: image @$DIGEST, all capabilities dropped${*:+ except $*}," \
    "no-new-privileges, pids limit $PIDS_LIMIT, memory limit $MEMORY bytes"
