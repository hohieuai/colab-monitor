"""The Claude Code plugin manifests that package the agent skill."""

import json
import pathlib

from colab_monitor import __version__

ROOT = pathlib.Path(__file__).resolve().parent.parent
PLUGIN = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())
MARKETPLACE = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text())


def test_plugin_version_matches_the_package():
    assert PLUGIN["version"] == __version__


def test_marketplace_lists_this_plugin_from_the_repository_root():
    [entry] = MARKETPLACE["plugins"]
    assert entry["name"] == PLUGIN["name"] == "colab-monitor"
    assert entry["source"] == "./"


def test_the_plugin_contains_the_agent_skill():
    skill = ROOT / "skills" / "colab-monitor" / "SKILL.md"
    assert skill.read_text().startswith("---\nname: colab-monitor\n")
