**A documentation site build.** `scripts/build_docs_site.py` assembles a Mintlify
site from `docs/`, `references/`, the CLI parser and the latest releases in
`CHANGELOG.md`: every reference document is published at a stable route with a
title and description, links between references become site routes, and the CLI
reference is rendered from the same help text `dex --help` prints. The build
refuses a broken link or anchor, an unpublished reference, a page missing from
navigation, an em dash, or anything Mintlify could not parse. Pull requests that
touch those sources build and validate the site in CI, and each release deploys
it to a generated `docs-site` branch after PyPI publish.
