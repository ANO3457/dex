**The documentation site is published as the `/dex` section of the Exmergo
site.** https://docs.exmergo.com is now served from exmergo/docs, which owns the
site's settings and home page, and `scripts/build_docs_site.py` builds only the
Dex section, `dex/`, served at `/dex`: every page under `/dex/...`, plus the
section's own menu and redirects, which the shared site reads. `docs/section.json`
replaces `docs/docs.json` and holds only that menu and those redirects; site
settings and `skill.md` move to exmergo/docs. `--site` assembles the whole site
from an exmergo/docs checkout, and refuses to write into a git checkout. Pull
requests validate the section inside the current shared site, and each release
now commits `dex/` to exmergo/docs with a short-lived token from the
organization's docs publisher app, instead of replacing a `docs-site` branch.
