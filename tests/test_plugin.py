"""The Claude Code plugin manifests that package the agent skill."""

import json
import pathlib
import re

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


def test_every_install_command_installs_this_release():
    """Users get the tagged release, not whatever is on main; a release PR moves every pin."""
    url = "git+https://github.com/hohieuai/colab-monitor"
    files = [
        ROOT / "README.md",
        *sorted((ROOT / "docs").glob("*.md")),
        *sorted((ROOT / "skills").rglob("*.md")),
    ]
    found = 0
    for path in files:
        for match in re.finditer(re.escape(url) + r"(@[\w.-]+)?", path.read_text()):
            found += 1
            assert match[1] == f"@v{__version__}", f"{path.name}: {match[0]}"
    assert found
