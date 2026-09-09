#!/usr/bin/env python3
"""Tests for CoderMind multi-agent harness adapters and host transport."""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
import tomllib
from pathlib import Path
from types import SimpleNamespace

import pytest


_CODERMIND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_CODERMIND_ROOT / "src"))
sys.path.insert(0, str(_CODERMIND_ROOT / "scripts"))

from cmind_cli.agent_adapters import install  # noqa: E402
from cmind_cli.host_bridge import _publish_request, _request_paths, _snapshot  # noqa: E402
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
    calls = {"materialise": [], "mcp": [], "workspace": []}

    def original_materialise(ai, src, project):
        calls["materialise"].append((ai, src, project))

    def original_mcp(project, ai, tracker=None):
        calls["mcp"].append((project, ai, tracker))

    def original_workspace(project, ai):
        calls["workspace"].append((project, ai))

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
        _CONFIG_RELPATH=Path(".cmind/config.toml"),
        _materialise_commands_for_agent=original_materialise,
        _generate_mcp_config=original_mcp,
        _write_workspace_config=original_workspace,
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
        "Run the pipeline:\n\n"
        "```bash\ncmind script example.py --json\n```\n\n"
        "If needed, run /cmind.update_rpg next.\n",
        encoding="utf-8",
    )
    return path


def test_install_registers_host_agents_without_nested_cli_commands():
    core, _ = _fake_core()
    install(core)

    # New adapters intentionally do not become LLM subprocess backends.
    assert core._AI_TO_CLI_CMD == {"claude": "claude"}
    for agent in ("codex", "pi", "omp"):
        assert core.AGENT_CONFIG[agent]["requires_cli"] is False

    assert core.AGENT_CONFIG["codex"]["folder"] == ".codex/"
    assert core.AGENT_CONFIG["pi"]["folder"] == ".pi/"
    assert core.AGENT_CONFIG["omp"]["folder"] == ".omp/"

    # Installation is idempotent because entry points/tests may invoke it more
    # than once in the same interpreter.
    wrapped = core._materialise_commands_for_agent
    install(core)
    assert core._materialise_commands_for_agent is wrapped


@pytest.mark.parametrize(
    ("agent", "skill_path", "protocol_path", "expected_reference"),
    [
        (
            "codex",
            Path(".agents/skills/cmind-encode/SKILL.md"),
            Path(".agents/cmind/host-protocol.md"),
            "$cmind-update-rpg",
        ),
        (
            "pi",
            Path(".agents/skills/cmind-encode/SKILL.md"),
            Path(".agents/cmind/host-protocol.md"),
            "/skill:cmind-update-rpg",
        ),
        (
            "omp",
            Path(".omp/skills/cmind-encode/SKILL.md"),
            Path(".omp/cmind/host-protocol.md"),
            "/skill:cmind-update-rpg",
        ),
    ],
)
def test_materialises_host_driven_agent_skills(
    tmp_path: Path, agent, skill_path, protocol_path, expected_reference
):
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
    assert "cmind host start example.py --json" in skill
    assert "../../cmind/host-protocol.md" in skill
    assert "cmind host next <run_id>" not in skill

    protocol = (project / protocol_path).read_text(encoding="utf-8")
    assert "cmind host next <run_id>" in protocol
    assert "cmind host reply <run_id> <request_id>" in protocol
    assert "Do not replace this protocol with `codex exec`" in protocol


def test_host_protocol_generated_once_for_multiple_skills(tmp_path: Path):
    core, _ = _fake_core()
    install(core)
    commands = tmp_path / "commands"
    _write_command_template(commands, "encode")
    _write_command_template(commands, "update_rpg")
    project = tmp_path / "project"

    core._materialise_commands_for_agent("codex", commands, project)

    protocol = project / ".agents" / "cmind" / "host-protocol.md"
    assert protocol.is_file()
    assert len(list(protocol.parent.glob("host-protocol.md"))) == 1
    for skill_path in (project / ".agents" / "skills").glob("cmind-*/SKILL.md"):
        assert "../../cmind/host-protocol.md" in skill_path.read_text(encoding="utf-8")


@pytest.mark.parametrize("agent", ["codex", "pi", "omp"])
def test_host_workspace_config_has_no_ai_cli_command(tmp_path: Path, agent: str):
    core, _ = _fake_core()
    install(core)
    project = tmp_path / "project"

    core._write_workspace_config(project, agent)

    config = tomllib.loads((project / ".cmind/config.toml").read_text(encoding="utf-8"))
    assert config["cmind"]["execution_mode"] == "host"
    assert config["cmind"]["agent"] == agent
    assert "ai_cli_cmd" not in config["cmind"]


def test_host_workspace_config_migrates_prior_generated_codex_command(tmp_path: Path):
    core, _ = _fake_core()
    install(core)
    project = tmp_path / "project"
    config_path = project / ".cmind/config.toml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        "# generated by previous adapter\n[cmind]\nai_cli_cmd = \"codex exec\"\n",
        encoding="utf-8",
    )

    core._write_workspace_config(project, "codex")

    config = tomllib.loads(config_path.read_text(encoding="utf-8"))
    assert config["cmind"] == {"execution_mode": "host", "agent": "codex"}


def test_host_workspace_config_preserves_custom_cli_command(tmp_path: Path):
    core, _ = _fake_core()
    install(core)
    project = tmp_path / "project"
    config_path = project / ".cmind/config.toml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        "[cmind]\nai_cli_cmd = \"my-custom-runner\"\n",
        encoding="utf-8",
    )

    core._write_workspace_config(project, "codex")

    config = tomllib.loads(config_path.read_text(encoding="utf-8"))
    assert config["cmind"]["ai_cli_cmd"] == "my-custom-runner"
    assert "execution_mode" not in config["cmind"]


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
    core._write_workspace_config(project, "claude")

    assert calls["materialise"] == [("claude", commands, project)]
    assert calls["mcp"][0][1] == "claude"
    assert calls["workspace"] == [(project, "claude")]


def test_host_transport_publishes_prompt_and_accepts_same_session_response(tmp_path: Path):
    run_dir = tmp_path / "run"
    (run_dir / "requests").mkdir(parents=True)
    (run_dir / "responses").mkdir(parents=True)
    result: dict[str, str] = {}

    def publish() -> None:
        result["response"] = _publish_request(run_dir, "plan the repository edit")

    thread = threading.Thread(target=publish, daemon=True)
    thread.start()

    deadline = time.time() + 2
    request_files = []
    while time.time() < deadline:
        request_files = list((run_dir / "requests").glob("*.json"))
        if request_files:
            break
        time.sleep(0.01)

    assert len(request_files) == 1
    request = json.loads(request_files[0].read_text(encoding="utf-8"))
    snapshot = _snapshot(run_dir, "test-run")
    assert snapshot["status"] == "input_required"
    assert snapshot["request_id"] == request["request_id"]
    assert snapshot["prompt"] == "plan the repository edit"

    _, response_path = _request_paths(run_dir, request["request_id"])
    response_path.write_text("host agent answer", encoding="utf-8")
    thread.join(timeout=2)

    assert not thread.is_alive()
    assert result["response"] == "host agent answer"


def test_generic_session_manager_pipes_prompt_to_host_proxy(tmp_path: Path):
    manager = create_session_manager("unknown", tmp_path)
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
