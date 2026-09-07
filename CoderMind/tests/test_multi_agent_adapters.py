#!/usr/bin/env python3
"""Tests for CoderMind multi-agent harness adapters."""

from __future__ import annotations

import json
import subprocess
import sys
import tomllib
from pathlib import Path
from types import SimpleNamespace

import pytest


_CODERMIND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_CODERMIND_ROOT / "src"))
sys.path.insert(0, str(_CODERMIND_ROOT / "scripts"))

from cmind_cli.agent_adapters import install  # noqa: E402
from common.session_manager import NullSessionManager, create_session_manager  # noqa: E402


class _Console:
    def print(self, *_args, **_kwargs) -> None:
        pass


class _Tracker:
    def __init__(self) -> None:
        self.completed = []
        self.errors = []

    def complete(self, key: str, detail: str = "") -> None:
        self.completed.append((key, detail))

    def error(self, key: str, detail: str = "") -> None:
        self.errors.append((key, detail))


def _fake_core():
    calls = {"materialise": [], "mcp": []}

    def original_materialise(ai, src, project):
        calls["materialise"].append((ai, src, project))

    def original_mcp(project, ai, tracker=None):
        calls["mcp"].append((project, ai, tracker))

    core = SimpleNamespace(
        AGENT_CONFIG={
            "claude": {
                "name": "Claude Code",
                "folder": ".claude/",
                "install_url": "https://example.invalid/claude",
                "requires_cli": True,
            }
        },
        _AI_TO_CLI_CMD={"claude": "claude"},
        _GITIGNORE_CMIND_AI={"claude": ".claude/commands/\n"},
        _materialise_commands_for_agent=original_materialise,
        _generate_mcp_config=original_mcp,
        console=_Console(),
    )
    return core, calls


def _write_command_template(root: Path, stem: str = "encode") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{stem}.md"
    path.write_text(
        "---\n"
        f"name: cmind.{stem}\n"
        f"description: Run {stem}\n"
        "---\n\n"
        "## User Input\n\n"
        "```text\n$ARGUMENTS\n```\n\n"
        "If needed, run /cmind.update_rpg next.\n",
        encoding="utf-8",
    )
    return path


def test_install_registers_new_agents_and_cli_commands():
    core, _ = _fake_core()
    install(core)

    assert core._AI_TO_CLI_CMD["codex"] == "codex exec"
    assert core._AI_TO_CLI_CMD["pi"] == "pi -p"
    assert core._AI_TO_CLI_CMD["omp"] == "omp -p"
    assert core.AGENT_CONFIG["codex"]["folder"] == ".codex/"
    assert core.AGENT_CONFIG["pi"]["folder"] == ".pi/"
    assert core.AGENT_CONFIG["omp"]["folder"] == ".omp/"

    # Installation is intentionally idempotent because entry points/tests may
    # invoke it more than once in the same interpreter.
    wrapped = core._materialise_commands_for_agent
    install(core)
    assert core._materialise_commands_for_agent is wrapped


@pytest.mark.parametrize(
    ("agent", "skill_path", "expected_reference"),
    [
        ("codex", Path(".agents/skills/cmind-encode/SKILL.md"), "$cmind-update-rpg"),
        ("pi", Path(".agents/skills/cmind-encode/SKILL.md"), "/skill:cmind-update-rpg"),
        ("omp", Path(".omp/skills/cmind-encode/SKILL.md"), "/skill:cmind-update-rpg"),
    ],
)
def test_materialises_agent_skills(tmp_path: Path, agent, skill_path, expected_reference):
    core, _ = _fake_core()
    install(core)
    commands = tmp_path / "commands"
    _write_command_template(commands)
    project = tmp_path / "project"

    core._materialise_commands_for_agent(agent, commands, project)

    skill = (project / skill_path).read_text(encoding="utf-8")
    assert "name: cmind-encode" in skill
    assert "description: Run encode" in skill
    assert expected_reference in skill
    assert "$ARGUMENTS" not in skill


def test_codex_mcp_config_is_project_scoped_and_idempotent(tmp_path: Path):
    core, _ = _fake_core()
    install(core)
    project = tmp_path / "project"
    tracker = _Tracker()

    core._generate_mcp_config(project, "codex", tracker=tracker)
    core._generate_mcp_config(project, "codex", tracker=tracker)

    config_path = project / ".codex" / "config.toml"
    text = config_path.read_text(encoding="utf-8")
    parsed = tomllib.loads(text)
    assert parsed["mcp_servers"]["rpg_tools"]["command"] == "cmind-mcp"
    assert parsed["mcp_servers"]["rpg_tools"]["args"] == []
    assert text.count("[mcp_servers.rpg_tools]") == 1
    assert not tracker.errors


def test_codex_mcp_preserves_existing_custom_server(tmp_path: Path):
    core, _ = _fake_core()
    install(core)
    project = tmp_path / "project"
    config = project / ".codex" / "config.toml"
    config.parent.mkdir(parents=True)
    config.write_text(
        "[mcp_servers.rpg_tools]\n"
        'command = "custom-rpg-server"\n'
        "args = [\"--dev\"]\n",
        encoding="utf-8",
    )

    core._generate_mcp_config(project, "codex")

    parsed = tomllib.loads(config.read_text(encoding="utf-8"))
    assert parsed["mcp_servers"]["rpg_tools"]["command"] == "custom-rpg-server"


def test_pi_generates_mcp_bridge_extension(tmp_path: Path):
    core, _ = _fake_core()
    install(core)
    project = tmp_path / "project"

    core._generate_mcp_config(project, "pi")

    mcp = json.loads((project / ".pi/mcp.json").read_text(encoding="utf-8"))
    assert mcp["mcpServers"]["rpg-tools"]["command"] == "cmind-mcp"
    extension = (project / ".pi/extensions/cmind-mcp.ts").read_text(encoding="utf-8")
    assert 'request("tools/list")' in extension
    assert 'request("tools/call"' in extension
    assert "mcp_rpg_tools_" in extension


def test_omp_generates_native_mcp_config(tmp_path: Path):
    core, _ = _fake_core()
    install(core)
    project = tmp_path / "project"

    core._generate_mcp_config(project, "omp")

    data = json.loads((project / ".omp/mcp.json").read_text(encoding="utf-8"))
    server = data["mcpServers"]["rpg-tools"]
    assert server == {"type": "stdio", "command": "cmind-mcp", "args": []}


def test_existing_agents_still_delegate_to_legacy_provisioners(tmp_path: Path):
    core, calls = _fake_core()
    install(core)
    commands = tmp_path / "commands"
    project = tmp_path / "project"

    core._materialise_commands_for_agent("claude", commands, project)
    core._generate_mcp_config(project, "claude")

    assert calls["materialise"] == [("claude", commands, project)]
    assert calls["mcp"][0][1] == "claude"


@pytest.mark.parametrize("agent_type", ["codex", "pi", "omp", "unknown"])
def test_generic_session_manager_pipes_prompt_to_subprocess(tmp_path: Path, agent_type: str):
    manager = create_session_manager(agent_type, tmp_path)
    assert isinstance(manager, NullSessionManager)

    with manager.trace("hello from CoderMind") as ctx:
        completed = subprocess.run(
            [sys.executable, "-c", "import sys; print(sys.stdin.read(), end='')"],
            stdin=ctx.stdin,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            check=True,
        )
        assert completed.stdout == "hello from CoderMind"
