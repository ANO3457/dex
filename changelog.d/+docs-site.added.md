**A documentation site build.** `scripts/build_docs_site.py` builds the Dex
section of https://docs.exmergo.com, served at `/dex`, from `docs/`,
`references/`, the CLI parser and the latest releases in `CHANGELOG.md`: every
reference document is published at a stable route with a title and description,
links between references become site routes, and the CLI reference is rendered
from the same help text `dex --help` prints. The section ships its own menu and
redirects, which the shared site in exmergo/docs reads. The build refuses a
broken link or anchor, an unpublished reference, a page missing from
navigation, an em dash, or anything Mintlify could not parse. Pull requests
that touch those sources validate the section inside the shared site in CI,
and each release commits it to exmergo/docs after PyPI publish.
