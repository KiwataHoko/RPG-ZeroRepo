"""Host-driven execution bridge for CoderMind workflows.

The bridge lets a coding-agent host (Codex App/CLI/IDE, Pi, OMP, etc.) keep
ownership of all model reasoning while reusing CoderMind's existing Python
pipelines unchanged.

A CoderMind script is started in a background worker with ``CMIND_AI_CLI_CMD``
pointing at this module's ``_proxy`` entry.  Whenever ``LLMClient.generate``
would normally launch an AI CLI, it launches the proxy instead.  The proxy
publishes the prompt as a pending request and blocks until the *current host
agent* submits a response with ``cmind host reply``.  No second model/agent is
started.
"""

from __future__ import annotations

import json
import os
import shlex
import signal
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import typer

from . import _assets

_RUNS_RELPATH = Path(".cmind") / "host-runs"
_POLL_SECONDS = 0.1


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    _atomic_write_text(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _find_workspace_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".cmind").exists():
            return candidate
    return current


def _resolve_script(relpath: str) -> Path:
    root = _assets.scripts_dir().resolve()
    target = (root / relpath).resolve()
    if target.suffix != ".py" or root not in target.parents:
        raise ValueError(f"Script must be a .py file under the CoderMind scripts bundle: {relpath}")
    if not target.is_file():
        raise FileNotFoundError(f"CoderMind script not found: {relpath}")
    return target


def _run_dir(workspace: Path, run_id: str) -> Path:
    if not run_id or any(ch not in "0123456789abcdefghijklmnopqrstuvwxyz-" for ch in run_id.lower()):
        raise ValueError("Invalid run id")
    return workspace / _RUNS_RELPATH / run_id


def _new_run_dir(workspace: Path) -> tuple[str, Path]:
    run_id = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
    run_dir = _run_dir(workspace, run_id)
    (run_dir / "requests").mkdir(parents=True, exist_ok=False)
    (run_dir / "responses").mkdir(parents=True, exist_ok=False)
    return run_id, run_dir


def _proxy_command() -> str:
    return shlex.join([sys.executable, "-m", "cmind_cli.host_bridge", "_proxy"])


def _request_paths(run_dir: Path, request_id: str) -> tuple[Path, Path]:
    return (
        run_dir / "requests" / f"{request_id}.json",
        run_dir / "responses" / f"{request_id}.txt",
    )


def _publish_request(run_dir: Path, prompt: str) -> str:
    request_id = uuid.uuid4().hex
    request_path, response_path = _request_paths(run_dir, request_id)
    _atomic_write_json(
        request_path,
        {
            "request_id": request_id,
            "created_at": _utc_now(),
            "prompt": prompt,
        },
    )

    cancelled = run_dir / "cancelled"
    while not response_path.exists():
        if cancelled.exists():
            raise RuntimeError("CoderMind host run was cancelled")
        time.sleep(_POLL_SECONDS)

    return response_path.read_text(encoding="utf-8")


def _proxy_main() -> int:
    run_dir_raw = os.environ.get("CMIND_HOST_RUN_DIR", "").strip()
    if not run_dir_raw:
        sys.stderr.write("cmind host proxy: CMIND_HOST_RUN_DIR is not set\n")
        return 2

    run_dir = Path(run_dir_raw).resolve()
    if not run_dir.is_dir():
        sys.stderr.write(f"cmind host proxy: run directory does not exist: {run_dir}\n")
        return 2

    prompt = sys.stdin.read()
    if not prompt:
        sys.stderr.write("cmind host proxy: received an empty prompt\n")
        return 2

    try:
        response = _publish_request(run_dir, prompt)
    except Exception as exc:
        sys.stderr.write(f"cmind host proxy: {exc}\n")
        return 1

    sys.stdout.write(response)
    return 0


def _worker_main(argv: list[str]) -> int:
    if len(argv) < 2:
        sys.stderr.write("usage: _worker <run-dir> <script> [args...]\n")
        return 2

    run_dir = Path(argv[0]).resolve()
    script = Path(argv[1]).resolve()
    script_args = argv[2:]
    workspace = Path(os.environ.get("CMIND_HOST_WORKSPACE", str(Path.cwd()))).resolve()

    env = dict(os.environ)
    env["CMIND_HOST_RUN_DIR"] = str(run_dir)
    env["CMIND_AI_CLI_CMD"] = _proxy_command()
    env["PYTHONUNBUFFERED"] = "1"

    stdout_path = run_dir / "stdout.txt"
    stderr_path = run_dir / "stderr.txt"
    started_at = _utc_now()

    try:
        with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open(
            "w", encoding="utf-8"
        ) as stderr:
            completed = subprocess.run(
                [sys.executable, str(script), *script_args],
                cwd=workspace,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
                text=True,
                check=False,
            )
        exit_code = completed.returncode
        status = "completed" if exit_code == 0 else "failed"
    except BaseException as exc:
        exit_code = 1
        status = "failed"
        with stderr_path.open("a", encoding="utf-8") as stderr:
            stderr.write(f"host worker failed: {exc}\n")

    _atomic_write_json(
        run_dir / "result.json",
        {
            "status": status,
            "exit_code": exit_code,
            "started_at": started_at,
            "finished_at": _utc_now(),
        },
    )
    return exit_code


def _pending_request(run_dir: Path) -> dict[str, Any] | None:
    requests_dir = run_dir / "requests"
    responses_dir = run_dir / "responses"
    if not requests_dir.is_dir():
        return None

    candidates = sorted(requests_dir.glob("*.json"), key=lambda p: (p.stat().st_mtime_ns, p.name))
    for path in candidates:
        request_id = path.stem
        if not (responses_dir / f"{request_id}.txt").exists():
            return _read_json(path)
    return None


def _read_output(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _snapshot(run_dir: Path, run_id: str) -> dict[str, Any]:
    pending = _pending_request(run_dir)
    if pending is not None:
        return {
            "status": "input_required",
            "run_id": run_id,
            **pending,
        }

    result_path = run_dir / "result.json"
    if result_path.exists():
        result = _read_json(result_path)
        return {
            **result,
            "run_id": run_id,
            "stdout": _read_output(run_dir / "stdout.txt"),
            "stderr": _read_output(run_dir / "stderr.txt"),
        }

    metadata_path = run_dir / "run.json"
    metadata = _read_json(metadata_path) if metadata_path.exists() else {}
    return {
        "status": "running",
        "run_id": run_id,
        "pid": metadata.get("pid"),
    }


def _emit(data: dict[str, Any]) -> None:
    typer.echo(json.dumps(data, indent=2, ensure_ascii=False))


def _start(script: str, script_args: list[str]) -> dict[str, Any]:
    workspace = _find_workspace_root()
    target = _resolve_script(script)
    run_id, run_dir = _new_run_dir(workspace)

    env = dict(os.environ)
    env["CMIND_HOST_WORKSPACE"] = str(workspace)

    worker_cmd = [
        sys.executable,
        "-m",
        "cmind_cli.host_bridge",
        "_worker",
        str(run_dir),
        str(target),
        *script_args,
    ]

    popen_kwargs: dict[str, Any] = {
        "cwd": workspace,
        "env": env,
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
    }
    if os.name == "nt":
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    else:
        popen_kwargs["start_new_session"] = True

    proc = subprocess.Popen(worker_cmd, **popen_kwargs)
    _atomic_write_json(
        run_dir / "run.json",
        {
            "run_id": run_id,
            "status": "running",
            "pid": proc.pid,
            "workspace": str(workspace),
            "script": script,
            "args": script_args,
            "started_at": _utc_now(),
            "model_execution": "host",
        },
    )
    return {"status": "started", "run_id": run_id, "pid": proc.pid}


def install_cli(app: typer.Typer) -> None:
    """Register ``cmind host`` commands on the legacy Typer app once."""
    if getattr(app, "_cmind_host_bridge_installed", False):
        return

    host_app = typer.Typer(
        name="host",
        help="Run CoderMind pipelines with model reasoning supplied by the current host agent.",
        add_completion=False,
    )

    @host_app.command(
        "start",
        context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
    )
    def start_command(
        ctx: typer.Context,
        script: str = typer.Argument(..., help="Script path relative to CoderMind/scripts."),
    ) -> None:
        """Start a CoderMind script without launching a secondary AI agent."""
        try:
            _emit(_start(script, list(ctx.args)))
        except Exception as exc:
            raise typer.BadParameter(str(exc)) from exc

    @host_app.command("next")
    def next_command(run_id: str = typer.Argument(...)) -> None:
        """Return the next host-model request, or the completed script result."""
        workspace = _find_workspace_root()
        run_dir = _run_dir(workspace, run_id)
        if not run_dir.is_dir():
            raise typer.BadParameter(f"Unknown host run: {run_id}")
        _emit(_snapshot(run_dir, run_id))

    @host_app.command("reply")
    def reply_command(
        run_id: str = typer.Argument(...),
        request_id: str = typer.Argument(...),
        response_file: Path | None = typer.Option(
            None,
            "--file",
            exists=True,
            dir_okay=False,
            readable=True,
            help="Read the host model response from a file instead of stdin.",
        ),
    ) -> None:
        """Submit the current host agent's answer to a pending CoderMind request."""
        workspace = _find_workspace_root()
        run_dir = _run_dir(workspace, run_id)
        request_path, response_path = _request_paths(run_dir, request_id)
        if not request_path.is_file():
            raise typer.BadParameter(f"Unknown request {request_id} for run {run_id}")
        if response_path.exists():
            raise typer.BadParameter(f"Request {request_id} already has a response")

        if response_file is not None:
            response = response_file.read_text(encoding="utf-8")
        else:
            if sys.stdin.isatty():
                raise typer.BadParameter("Pipe the model response on stdin or pass --file PATH")
            response = sys.stdin.read()

        if not response.strip():
            raise typer.BadParameter("Host model response must not be empty")
        _atomic_write_text(response_path, response)
        _emit({"status": "accepted", "run_id": run_id, "request_id": request_id})

    app.add_typer(host_app, name="host")
    setattr(app, "_cmind_host_bridge_installed", True)


def _module_main() -> int:
    if len(sys.argv) >= 2 and sys.argv[1] == "_proxy":
        return _proxy_main()
    if len(sys.argv) >= 2 and sys.argv[1] == "_worker":
        return _worker_main(sys.argv[2:])
    sys.stderr.write("cmind_cli.host_bridge is an internal module; use `cmind host --help`.\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(_module_main())
