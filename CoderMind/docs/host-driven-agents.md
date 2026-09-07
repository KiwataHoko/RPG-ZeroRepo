# Host-driven coding-agent adapters

CoderMind's Codex, Pi, and oh-my-pi adapters keep model reasoning in the
currently running coding-agent session. CoderMind does not invoke a second
`codex exec`, `pi -p`, or `omp -p` process to obtain model output.

## Architecture

The integration has three surfaces:

- **Workflow:** CoderMind command templates are materialized as Agent Skills.
- **Tools:** RPG query operations are exposed through `cmind-mcp` (Pi uses a
  generated extension that bridges the MCP server into Pi tools).
- **Model execution:** legacy Python pipelines are run through the `cmind host`
  transport. If a pipeline reaches `LLMClient.generate()`, the prompt is
  surfaced back to the current host agent for reasoning.

For Codex this means the same project scaffold is usable from Codex App, Codex
CLI, and Codex IDE integrations: `.agents/skills/` provides workflows and
`.codex/config.toml` provides the RPG MCP server. The Codex CLI executable is
not required merely to provision the project.

## Workspace configuration

A newly initialized host-driven workspace contains:

```toml
[cmind]
execution_mode = "host"
agent = "codex" # or pi / omp
```

It intentionally has no `ai_cli_cmd`. Older adapter-generated values such as
`ai_cli_cmd = "codex exec"` are migrated to host mode when they exactly match
the previous generated default. Custom `ai_cli_cmd` values are preserved.

## Host protocol

Generated skills translate packaged-script commands from:

```bash
cmind script rpg_encoder/run_encode.py --json
```

to:

```bash
cmind host start rpg_encoder/run_encode.py --json
```

`start` immediately returns a `run_id`. The host agent then drives the run:

```bash
cmind host next <run_id>
```

When the result is `input_required`, the JSON contains a `request_id` and the
CoderMind prompt. The current host agent answers that prompt itself and submits
the result:

```bash
cat <<'CMIND_RESPONSE' | cmind host reply <run_id> <request_id>
<host agent response>
CMIND_RESPONSE
```

The host repeats `next` / `reply` until `next` returns `completed` or `failed`.
On completion, `stdout` contains the original script output and `stderr`
contains diagnostics.

## How the bridge avoids a nested model call

The background CoderMind worker overrides `CMIND_AI_CLI_CMD` with an internal,
non-model proxy command. The existing `LLMClient` still executes its normal
subprocess path and trajectory bookkeeping, but that subprocess only transports
the prompt to `.cmind/host-runs/<run-id>/requests/` and waits for a response.
The generated skill causes the current coding-agent session to provide that
response via `cmind host reply`.

The generic `NullSessionManager` sends the prompt over stdin to this internal
proxy. No coding-agent CLI is launched by the bridge.

## Agent-specific files

### Codex

```text
.agents/skills/cmind-*/SKILL.md
.codex/config.toml
```

The generated Codex MCP server key is `rpg_tools` and starts `cmind-mcp`.

### Pi

```text
.agents/skills/cmind-*/SKILL.md
.pi/mcp.json
.pi/extensions/cmind-mcp.ts
```

The TypeScript extension starts `cmind-mcp`, discovers its tools, and registers
them with Pi.

### oh-my-pi

```text
.omp/skills/cmind-*/SKILL.md
.omp/mcp.json
```

OMP uses its native project MCP configuration.

## Compatibility

Claude Code and GitHub Copilot keep their existing CoderMind execution path.
The host bridge is installed by the multi-agent adapter entry point and is used
only when a generated host-driven skill invokes `cmind host start`.
