#!/usr/bin/env python3
"""Session management for AI CLI subprocesses used by CoderMind.

Each manager controls prompt delivery, CLI-specific arguments, and optional
session-trace capture.  Unknown/unregistered CLIs use a generic stdin manager;
this is the interoperability path used by headless agents such as ``codex
exec``, ``pi -p`` and ``omp -p``.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import tempfile
import uuid
from abc import ABC, abstractmethod
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional

from .paths import CLAUDE_LOGS_DIR, COPILOT_LOGS_DIR


logger = logging.getLogger(__name__)


class TraceContext:
    """State prepared by a :class:`SessionManager` for one subprocess call."""

    def __init__(self) -> None:
        self.extra_args: List[str] = []
        self.env: Dict[str, str] = os.environ.copy()
        self.stdin: Optional[Any] = None
        self.captured_path: Optional[Path] = None

    def reset_stdin(self) -> None:
        """Reset stdin read position for retry attempts."""
        if self.stdin is not None and hasattr(self.stdin, "seek"):
            self.stdin.seek(0)

    def refresh_for_retry(self) -> None:
        """Reset prompt input and refresh single-use CLI arguments."""
        self.reset_stdin()
        refresh = getattr(self, "_refresh_hook", None)
        if refresh:
            refresh(self)


class SessionManager(ABC):
    """Base class for CLI prompt delivery and trace capture."""

    DEFAULT_TRAJECTORY_DIR: Path = Path("trajectory")

    def __init__(
        self,
        project_dir: Path,
        trace_filename_builder: Optional[Callable[[str], str]] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.project_dir = project_dir
        self.trajectory_dir = self.DEFAULT_TRAJECTORY_DIR
        self._build_filename = trace_filename_builder or self._default_filename_builder
        self.logger = logger or logging.getLogger(self.__class__.__name__)

    @abstractmethod
    def before(self, ctx: TraceContext, prompt: str) -> None:
        """Populate subprocess arguments/stdin before the LLM call."""
        ...

    @abstractmethod
    def after(self, purpose: str) -> Optional[Path]:
        """Capture a trace and clean up temporary resources after the call."""
        ...

    @contextmanager
    def trace(self, prompt: str, purpose: str = "general") -> Iterator[TraceContext]:
        ctx = TraceContext()
        self.before(ctx, prompt)
        try:
            yield ctx
        finally:
            ctx.captured_path = self.after(purpose)

    @staticmethod
    def _default_filename_builder(purpose: str) -> str:
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        safe = re.sub(r"[^\w\-]", "_", purpose) if purpose else "llm_call"
        return f"{safe}-{ts}.jsonl"

    def _dest_dir(self) -> Path:
        if self.trajectory_dir.is_absolute():
            dest = self.trajectory_dir
        else:
            dest = self.project_dir / self.trajectory_dir
        dest.mkdir(parents=True, exist_ok=True)
        return dest


class NullSessionManager(SessionManager):
    """Generic stdin-based manager for CLIs without a specialized adapter.

    Historically this manager did nothing, which meant the prompt never
    reached unregistered subprocesses.  Most modern headless coding agents
    accept a piped prompt, so the fallback now provides it through a real
    temporary file descriptor.  Specialized managers can still override this
    behavior when an agent requires command-line arguments or trace handling.
    """

    def __init__(
        self,
        project_dir: Path,
        trace_filename_builder: Optional[Callable[[str], str]] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        super().__init__(project_dir, trace_filename_builder, logger)
        self._stdin_fh: Optional[Any] = None

    def _cleanup_stdin(self) -> None:
        if self._stdin_fh is not None:
            try:
                self._stdin_fh.close()
            except Exception:
                pass
            self._stdin_fh = None

    def before(self, ctx: TraceContext, prompt: str) -> None:
        self._cleanup_stdin()
        fh = tempfile.TemporaryFile(mode="w+", encoding="utf-8")
        fh.write(prompt)
        fh.flush()
        fh.seek(0)
        self._stdin_fh = fh
        ctx.stdin = fh

    def after(self, purpose: str) -> Optional[Path]:
        self._cleanup_stdin()
        return None


class ClaudeSessionManager(SessionManager):
    """Claude CLI manager with deterministic session trace capture."""

    DEFAULT_TRAJECTORY_DIR: Path = CLAUDE_LOGS_DIR

    def __init__(
        self,
        project_dir: Path,
        trace_filename_builder: Optional[Callable[[str], str]] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        super().__init__(project_dir, trace_filename_builder, logger)
        self._sessions_dir: Optional[Path] = self._get_projects_dir()
        self._session_id: Optional[str] = None
        self._tmp_prompt_path: Optional[str] = None
        self._tmp_prompt_fh: Optional[Any] = None

    @staticmethod
    def encode_path(abs_path: str) -> str:
        return abs_path.replace("/", "-").replace("_", "-")

    def _get_projects_dir(self) -> Optional[Path]:
        claude_base = Path.home() / ".claude" / "projects"
        candidate = claude_base / self.encode_path(str(self.project_dir))
        return candidate if candidate.is_dir() else None

    def before(self, ctx: TraceContext, prompt: str) -> None:
        self._session_id = str(uuid.uuid4())
        ctx.extra_args.extend(
            [
                "-p",
                "--session-id",
                self._session_id,
                "--dangerously-skip-permissions",
            ]
        )
        ctx.env.pop("CLAUDECODE", None)
        ctx._refresh_hook = self._regenerate_session_id

        self._cleanup_tmp_prompt()
        fd, tmp_path = tempfile.mkstemp(suffix=".txt", prefix="llm_prompt_")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(prompt)
            self._tmp_prompt_path = tmp_path
            self._tmp_prompt_fh = open(tmp_path, "r", encoding="utf-8")
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            self._tmp_prompt_path = None
            self._tmp_prompt_fh = None
            raise
        ctx.stdin = self._tmp_prompt_fh

    def _regenerate_session_id(self, ctx: TraceContext) -> None:
        new_id = str(uuid.uuid4())
        for i, arg in enumerate(ctx.extra_args):
            if arg == "--session-id" and i + 1 < len(ctx.extra_args):
                ctx.extra_args[i + 1] = new_id
                break
        self._session_id = new_id

    def _cleanup_tmp_prompt(self) -> None:
        if self._tmp_prompt_fh is not None:
            try:
                self._tmp_prompt_fh.close()
            except Exception:
                pass
            self._tmp_prompt_fh = None
        if self._tmp_prompt_path is not None:
            try:
                os.unlink(self._tmp_prompt_path)
            except OSError:
                pass
            self._tmp_prompt_path = None

    def after(self, purpose: str) -> Optional[Path]:
        self._cleanup_tmp_prompt()
        if self._sessions_dir is None:
            self._sessions_dir = self._get_projects_dir()
        if self._sessions_dir is None or self._session_id is None:
            return None

        source = self._sessions_dir / f"{self._session_id}.jsonl"
        try:
            if not source.exists():
                self.logger.debug("Claude session file not found: %s", source.name)
                return None

            dest_dir = self._dest_dir()
            dest_name = self._build_filename(purpose)
            dest = dest_dir / dest_name
            shutil.copy2(source, dest)

            subagent_dir = self._sessions_dir / self._session_id / "subagents"
            if subagent_dir.is_dir():
                dest_sub = dest_dir / dest_name.replace(".jsonl", "") / "subagents"
                if dest_sub.exists():
                    shutil.rmtree(dest_sub)
                shutil.copytree(subagent_dir, dest_sub)

            self.logger.info(
                "Captured Claude session trace: %s -> %s", source.name, dest
            )
            return dest
        except Exception as exc:
            self.logger.warning("Failed to capture Claude session trace: %s", exc)
            return None


class CopilotSessionManager(SessionManager):
    """GitHub Copilot CLI manager."""

    def before(self, ctx: TraceContext, prompt: str) -> None:
        log_dir = COPILOT_LOGS_DIR
        log_dir.mkdir(parents=True, exist_ok=True)
        ctx.extra_args.extend(
            [
                "--log-dir",
                str(log_dir),
                "--log-level",
                "all",
                "--allow-all",
                "-p",
                prompt,
            ]
        )

    def after(self, purpose: str) -> Optional[Path]:
        return None


_MANAGER_REGISTRY: Dict[str, type] = {
    "claude": ClaudeSessionManager,
    "copilot": CopilotSessionManager,
}


def register_manager(agent_type: str, manager_cls: type) -> None:
    """Register a custom manager class for an agent type."""
    _MANAGER_REGISTRY[agent_type] = manager_cls


def create_session_manager(
    agent_type: str,
    project_dir: Path,
    trace_filename_builder: Optional[Callable[[str], str]] = None,
    logger: Optional[logging.Logger] = None,
) -> SessionManager:
    """Return the specialized manager or the generic stdin fallback."""
    manager_cls = _MANAGER_REGISTRY.get(agent_type, NullSessionManager)
    return manager_cls(
        project_dir=project_dir,
        trace_filename_builder=trace_filename_builder,
        logger=logger,
    )
