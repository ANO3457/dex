**Dex ships a plugin folder for Anthropic's Claude plugin directory.** `claude/`
holds the Claude plugin the directory reads: the three skills, the Claude manifest,
the license, the Exmergo icon, and the README with its links made absolute. The
directory scans only that folder, so the monorepo stays whole. Installed from it,
the skills run the engine release they pin from PyPI. `scripts/prepare_release.sh`
regenerates the folder at every release, after the pins move, so nothing in it but
the icon is edited by hand. The skill wrappers' "uv not found" message now names
uv's installation docs rather than linking them, and the wrappers carry no URL.
