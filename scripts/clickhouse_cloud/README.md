# ClickHouse Cloud integration operations

These helpers manage the dedicated, repository-owned Cloud test service. They
never discover an arbitrary service, and teardown never stops or deletes one.
The dedicated organization, service, AWS region, Scale-tier prices, repository,
environment, `dex_ci_*` resource names, and CI policy are stable non-secret
constants in the scripts. Flags exist for deliberate migration/testing; normal
setup does not scatter those values through an operator's shell.

## Credentials are files, handed to one command at a time

Long-lived credentials never travel through the environment of these scripts,
because every process a script starts would inherit them. Each one is a file in
`DEX_SECRETS_DIR` (default `$RUNNER_TEMP/dex-secrets` on a GitHub runner,
`$TMPDIR/dex-secrets` elsewhere), and `secrets.sh` hands it to the single
`clickhousectl`, `clickhouse client`, or `curl` invocation that needs it. The
directory must belong to you and be closed to group and others (`chmod 700`), or
the scripts refuse it. A missing or empty file is refused with its path (exit 2).
Sourcing `secrets.sh` also unsets `CLICKHOUSE_CLOUD_API_KEY`,
`CLICKHOUSE_CLOUD_API_SECRET`, and `CLICKHOUSE_PASSWORD`, so a shell that still
exports them from an older setup does not pass them on.

| File | Holds | Read by |
|---|---|---|
| `clickhouse_api_key`, `clickhouse_api_secret` | the scoped CI key | `preflight.sh`, `run_integration.sh`, the Cloud tests |
| `clickhouse_admin_api_key`, `clickhouse_admin_api_secret` | the bootstrap admin key | setup and `teardown.sh` |
| `clickhouse_admin_password` | the service's `default` user password | setup and `teardown.sh` |

The two sets have different names so that neither can stand in for the other: a
suite that passed on the admin key would hide a scope regression in the CI key.
Only `CLICKHOUSE_USER` (the admin user name, not a secret) stays an environment
variable.

Write the admin files once, without the values reaching your shell history or a
command line (this works in bash and zsh):

```bash
export DEX_SECRETS_DIR="${TMPDIR%/}/dex-secrets"
install -d -m 700 "$DEX_SECRETS_DIR"
for name in clickhouse_admin_api_key clickhouse_admin_api_secret \
    clickhouse_admin_password; do
  printf '%s: ' "$name"; IFS= read -rs value; echo
  (umask 077 && printf '%s' "$value" >"$DEX_SECRETS_DIR/$name")
done
unset value
export CLICKHOUSE_USER=default
```

Remove the directory when you are done. In CI, one workflow step writes the two
scoped files from the environment secrets into `/dev/shm`, and a final step
removes them; no other step sees the key.

## Setup and rotation

First setup (the explicit adoption flag is needed only while the ownership tag
is absent):

```bash
scripts/setup_clickhouse_cloud_ci.sh \
  --adopt-service
```

Rerun the same command without `--adopt-service` to rotate both database
passwords and the scoped API key. A new API key is verified and installed in
GitHub before older `dex-ci-usage-*` keys are removed. Ensure no Cloud
integration workflow is active while rotating.

The scoped control-plane key accepts IPv4 from any runner because GitHub-hosted
runners have no stable egress address. Its custom role can only read the exact
service and organization billing usage; setup verifies that a service update is
denied. This does not modify or broaden the service's SQL endpoint allowlist.

Pass `--dogfood` on a setup/rotation run to execute the narrow live suite with
the newly generated credentials while they exist only for that run. This is
the local validation path; GitHub secrets remain write-only and are never read
back onto the machine.

The new scoped key is written to a temporary secrets directory of its own,
removed when setup exits. The readiness check and the `--dogfood` run point
`DEX_SECRETS_DIR` there, so they prove the key that was just minted rather than
the admin key setup runs with.

`preflight.sh` reads the exact service and UTC-day usage through the Cloud API,
performs no SQL connection, and refuses at the configured CHC threshold.
`run_integration.sh` requires the same non-secret values and database credentials
as CI plus the scoped key files, runs that preflight, and then invokes only the
`clickhouse_cloud` pytest marker. Neither helper echoes credentials.

## Teardown

Bounded teardown requires an explicit confirmation and the ownership tag:

```bash
scripts/clickhouse_cloud/teardown.sh \
  --confirm
```

Organization, service, repository, and environment default to the same
committed constants as setup. Their flags are migration/testing overrides, not
ordinary operator inputs.

It removes only the two `dex_ci_*` databases, the two users and settings
profiles, the custom usage-reader role, `dex-ci-usage-*` API keys, the named
GitHub environment, and the two attribution tags. It does not touch other
databases, users, keys, roles, billing configuration, or the service lifecycle.
