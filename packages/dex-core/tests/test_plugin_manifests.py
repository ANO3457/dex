"""The plugin manifests each agent reads, held in step.

Claude Code reads `.claude-plugin/plugin.json`; Copilot CLI, Cursor and Kiro read
the Agent Plugins `plugin.json` at the repository root; Gemini CLI reads
`gemini-extension.json`. `scripts/prepare_release.sh` bumps the version in all
three, and the descriptions and keywords are copies of one another. A manifest
that falls behind advertises the previous version, or a stale description, to that
agent's users and to the directories that list it, with nothing else in the repo
noticing.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
CLAUDE = ".claude-plugin/plugin.json"
AGENT_PLUGINS = "plugin.json"
GEMINI = "gemini-extension.json"
MANIFESTS = (CLAUDE, AGENT_PLUGINS, GEMINI)

# Same reasoning as test_skill_bodies.py: an installed wheel has no manifests beside it.
pytestmark = pytest.mark.skipif(
    not (ROOT / "skills").is_dir(), reason="needs a repository checkout"
)


def manifests() -> dict[str, dict]:
    return {
        path: json.loads((ROOT / path).read_text(encoding="utf-8"))
        for path in MANIFESTS
    }


@pytest.mark.parametrize("field", ["name", "version", "description"])
def test_the_manifests_agree(field: str):
    values = {path: manifest.get(field) for path, manifest in manifests().items()}
    assert len(set(values.values())) == 1, f"manifest {field}s disagree: {values}"


def test_the_name_is_the_install_id():
    """`name` is the install id (`dex@exmergo`) and the `/dex:*` namespace in
    Claude Code; the directory listing name is `displayName`, which only the
    Claude manifest carries because the Agent Plugins schema is closed."""

    assert manifests()[CLAUDE]["name"] == "dex"


def test_the_plugin_manifests_carry_the_same_keywords():
    loaded = manifests()
    assert loaded[AGENT_PLUGINS]["keywords"] == loaded[CLAUDE]["keywords"]
