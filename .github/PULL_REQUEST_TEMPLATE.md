## What this changes

<!-- A short description of the change and why it is needed. -->

## Related issues

<!-- e.g. Closes #123. Delete if none. -->

## Checklist

- [ ] Tests pass (`uv run pytest` in `packages/dex-core`)
- [ ] Eval scoring-core tests pass (`uvx pytest evals`)
- [ ] If a safety path is touched, the spine still holds: read-only against data,
      cost-guarded, PII flagged not surfaced, propose-don't-impose
- [ ] PR title is ready for release notes; applicable release-note labels and
      upgrade guidance are included
- [ ] A changelog fragment is in `changelog.d/` (`<this PR's number>.<type>.md`),
      or the change is invisible to users and needs the `no-changelog` label;
      `CHANGELOG.md` itself is not edited
      ([how to add one](https://github.com/exmergo/dex/blob/main/CONTRIBUTING.md#changelog-fragments))
- [ ] User-facing behavior changes are reflected in `references/` or `docs/`
      (the documentation site is rebuilt from them on each release)
- [ ] Prose is em-dash free (checked in CI)
- [ ] No credentials, secrets, or raw warehouse rows in code, tests, or fixtures
