"""Checkpointed, dependency-driven research construction workflow."""

import argparse
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ..adapters import ResearchDomainAdapter
from ..graph import DomainGraph, ValidationIssue


@dataclass(frozen=True)
class ResearchBrief:
    question: str
    scope: str = ""
    constraints: tuple[str, ...] = ()
    success_criteria: tuple[str, ...] = ()

    def __post_init__(self):
        if not self.question.strip():
            raise ValueError("research question must be non-empty")


@dataclass
class ResearchTask:
    id: str
    title: str
    stage: str
    depends_on: tuple[str, ...] = ()
    status: str = "pending"
    attempts: int = 0
    result: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["depends_on"] = list(self.depends_on)
        return value

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ResearchTask":
        return cls(**{**value, "depends_on": tuple(value.get("depends_on", ()))})


class ResearchPlan:
    STAGES = ("specification", "discovery", "challenge", "synthesis")

    def __init__(self, tasks: tuple[ResearchTask, ...]):
        self.tasks = list(tasks)
        self._validate()

    @classmethod
    def default(cls, brief: ResearchBrief) -> "ResearchPlan":
        del brief
        return cls(
            tasks=(
                ResearchTask(
                    "define-concepts",
                    "Define terms, scope, and discriminating criteria",
                    "specification",
                ),
                ResearchTask(
                    "candidate-theories",
                    "Build competing explanatory candidates",
                    "discovery",
                    ("define-concepts",),
                ),
                ResearchTask(
                    "textbook-search",
                    "Verify professional textbooks and chapter coverage",
                    "discovery",
                    ("define-concepts",),
                ),
                ResearchTask(
                    "evidence-search",
                    "Collect primary evidence for each candidate",
                    "discovery",
                    ("candidate-theories",),
                ),
                ResearchTask(
                    "counterexample-search",
                    "Seek strongest counterexamples for each candidate",
                    "challenge",
                    ("evidence-search",),
                ),
                ResearchTask(
                    "discriminatory-tests",
                    "Compare predictions and boundary failures",
                    "challenge",
                    ("counterexample-search",),
                ),
                ResearchTask(
                    "synthesize",
                    "Revise claims and synthesize surviving structure",
                    "synthesis",
                    ("discriminatory-tests", "textbook-search"),
                ),
            )
        )

    def _validate(self) -> None:
        ids = [task.id for task in self.tasks]
        if len(ids) != len(set(ids)) or any(not value for value in ids):
            raise ValueError("research task IDs must be unique and non-empty")
        by_id = {task.id: task for task in self.tasks}
        for task in self.tasks:
            if task.stage not in self.STAGES:
                raise ValueError(f"unknown research stage: {task.stage}")
            missing = set(task.depends_on) - set(by_id)
            if missing:
                raise ValueError(
                    f"task {task.id!r} has missing dependencies: {sorted(missing)}"
                )
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(task_id: str) -> None:
            if task_id in visiting:
                raise ValueError("research task dependency cycle")
            if task_id in visited:
                return
            visiting.add(task_id)
            for dependency in by_id[task_id].depends_on:
                visit(dependency)
            visiting.remove(task_id)
            visited.add(task_id)

        for task_id in ids:
            visit(task_id)

    def ready_task_ids(self) -> tuple[str, ...]:
        completed = {task.id for task in self.tasks if task.status == "completed"}
        return tuple(
            task.id
            for task in self.tasks
            if task.status in {"pending", "failed"}
            and set(task.depends_on) <= completed
        )

    def get(self, task_id: str) -> ResearchTask:
        for task in self.tasks:
            if task.id == task_id:
                return task
        raise KeyError(task_id)

    def start(self, task_id: str) -> None:
        if task_id not in self.ready_task_ids():
            raise ValueError(f"task {task_id!r} is not ready")
        task = self.get(task_id)
        task.status = "running"
        task.attempts += 1

    def complete(self, task_id: str, result: dict[str, Any]) -> None:
        task = self.get(task_id)
        if task.status != "running":
            raise ValueError(f"task {task_id!r} is not running")
        task.status = "completed"
        task.result = dict(result)

    def fail(self, task_id: str, result: dict[str, Any]) -> None:
        task = self.get(task_id)
        if task.status != "running":
            raise ValueError(f"task {task_id!r} is not running")
        task.status = "failed"
        task.result = dict(result)

    def to_dict(self) -> dict[str, Any]:
        return {"version": 1, "tasks": [task.to_dict() for task in self.tasks]}

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ResearchPlan":
        return cls(tuple(ResearchTask.from_dict(item) for item in value["tasks"]))


@dataclass(frozen=True)
class ResearchWorkflowStatus:
    completed_task_ids: tuple[str, ...]
    ready_task_ids: tuple[str, ...]
    running_task_ids: tuple[str, ...]
    failed_task_ids: tuple[str, ...]
    blocked_task_ids: tuple[str, ...]
    complete: bool


class ResearchBuildPipeline:
    """Persist research specification, task state, quality gates, and final graph."""

    def __init__(self, workspace: str | Path, *, directory: str = ".research"):
        self.workspace = Path(workspace)
        self.directory = self.workspace / directory
        self.spec_path = self.directory / "research-spec.json"
        self.plan_path = self.directory / "research-plan.json"
        self.state_path = self.directory / "research-state.jsonl"

    def initialize(
        self,
        brief: ResearchBrief,
        plan: ResearchPlan | None = None,
        *,
        overwrite: bool = False,
    ) -> None:
        if self.spec_path.exists() and not overwrite:
            raise FileExistsError(
                "research workflow already initialized; resume it instead"
            )
        self.directory.mkdir(parents=True, exist_ok=True)
        self._write_json(self.spec_path, {"version": 1, **asdict(brief)})
        self._write_plan(plan or ResearchPlan.default(brief))
        self._event("initialized", question=brief.question)

    def status(self) -> ResearchWorkflowStatus:
        plan = self._load_plan()
        completed = tuple(task.id for task in plan.tasks if task.status == "completed")
        running = tuple(task.id for task in plan.tasks if task.status == "running")
        failed = tuple(task.id for task in plan.tasks if task.status == "failed")
        ready = plan.ready_task_ids()
        blocked = tuple(
            task.id
            for task in plan.tasks
            if task.status == "pending" and task.id not in ready
        )
        return ResearchWorkflowStatus(
            completed,
            ready,
            running,
            failed,
            blocked,
            len(completed) == len(plan.tasks),
        )

    def start_task(self, task_id: str) -> None:
        plan = self._load_plan()
        plan.start(task_id)
        self._write_plan(plan)
        self._event("task_started", task_id=task_id)

    def complete_task(self, task_id: str, result: dict[str, Any]) -> None:
        if not result:
            raise ValueError("completed task requires a non-empty result checkpoint")
        plan = self._load_plan()
        self._validate_task_result(plan.get(task_id), result)
        plan.complete(task_id, result)
        self._write_plan(plan)
        self._event("task_completed", task_id=task_id)

    def fail_task(self, task_id: str, result: dict[str, Any]) -> None:
        plan = self._load_plan()
        plan.fail(task_id, result)
        self._write_plan(plan)
        self._event("task_failed", task_id=task_id)

    def validate_graph(self, graph: DomainGraph) -> tuple[ValidationIssue, ...]:
        return ResearchDomainAdapter().validate_research(graph)

    def finalize(self, graph: DomainGraph) -> Path:
        status = self.status()
        if not status.complete:
            unfinished = (
                status.ready_task_ids
                + status.running_task_ids
                + status.failed_task_ids
                + status.blocked_task_ids
            )
            raise ValueError(f"unfinished research tasks: {', '.join(unfinished)}")
        issues = self.validate_graph(graph)
        plan = self._load_plan()
        theory_ids = {node.id for node in graph.get_nodes_by_type("theory")}
        planned_theories = {
            str(item["id"])
            for item in plan.get("candidate-theories").result["theories"]
        }
        if theory_ids != planned_theories:
            raise ValueError(
                "research quality gates failed: final theories differ from candidate-theories checkpoint"
            )
        ledger_sources = {
            str(source["id"]): source
            for task in plan.tasks
            for source in task.result.get("sources", ())
        }
        graph_sources = {node.id for node in graph.get_nodes_by_type("source")}
        if not graph_sources <= set(ledger_sources):
            raise ValueError(
                "research quality gates failed: graph contains sources absent from retrieval checkpoints"
            )
        locator_fields = ("url", "doi", "isbn", "path", "document_id")
        for source in graph.get_nodes_by_type("source"):
            graph_locators = {
                str(source.data[field])
                for field in locator_fields
                if source.data.get(field)
            }
            if str(ledger_sources[source.id]["locator"]) not in graph_locators:
                raise ValueError(
                    f"research quality gates failed: source {source.id!r} locator differs from retrieval checkpoint"
                )
        challenged_claims = {
            str(item["claim_id"])
            for item in plan.get("counterexample-search").result["counterexamples"]
        }
        graph_challenges = {
            edge.target for edge in graph.edges if edge.relation == "contradicts"
        }
        if not challenged_claims <= graph_challenges:
            raise ValueError(
                "research quality gates failed: planned counterexamples are absent from graph"
            )
        if issues:
            raise ValueError(
                "research quality gates failed: "
                + ", ".join(f"{issue.kind}@{issue.location}" for issue in issues)
            )
        output = self.directory / "research.domain-graph.json"
        output.write_text(graph.to_json(indent=2) + "\n", encoding="utf-8")
        restored = DomainGraph.from_json(output.read_text(encoding="utf-8"))
        roundtrip_issues = self.validate_graph(restored)
        if roundtrip_issues:
            raise ValueError("round-trip research validation failed")
        theories = graph.get_nodes_by_type("theory")
        challenged = 0
        for theory in theories:
            claims = {
                edge.target
                for edge in graph.edges
                if edge.source == theory.id and edge.relation == "explains"
            }
            if any(
                edge.target in claims and edge.relation == "contradicts"
                for edge in graph.edges
            ):
                challenged += 1
        self._write_json(
            self.directory / "coverage-report.json",
            {
                "version": 1,
                "passed": True,
                "issue_count": 0,
                "theory_count": len(theories),
                "counterexample_covered_theory_count": challenged,
                "claim_count": len(graph.get_nodes_by_type("claim")),
                "evidence_count": len(graph.get_nodes_by_type("evidence")),
                "source_count": len(graph.get_nodes_by_type("source")),
            },
        )
        self._event("finalized", output=str(output))
        return output

    @staticmethod
    def _validate_task_result(task: ResearchTask, result: dict[str, Any]) -> None:
        required = {
            "define-concepts": ("concepts", "distinctions", "acceptance_tests"),
            "candidate-theories": ("theories",),
            "textbook-search": ("sources",),
            "evidence-search": ("sources", "claim_ids"),
            "counterexample-search": ("sources", "counterexamples"),
            "discriminatory-tests": ("comparisons",),
            "synthesize": ("claim_ids", "revisions"),
        }.get(task.id, ())
        missing = [field for field in required if not result.get(field)]
        if missing:
            raise ValueError(
                f"task {task.id!r} result is missing non-empty fields: {', '.join(missing)}"
            )
        if task.id == "candidate-theories" and len(result["theories"]) < 2:
            raise ValueError(
                "candidate-theories requires at least two competing theories"
            )
        if "sources" in required:
            for source in result["sources"]:
                fields = ("id", "source_type", "locator", "accessed_at")
                absent = [field for field in fields if not source.get(field)]
                if absent:
                    raise ValueError(
                        f"retrieved source is missing fields: {', '.join(absent)}"
                    )
        if task.id == "textbook-search" and not any(
            source["source_type"] == "textbook" for source in result["sources"]
        ):
            raise ValueError("textbook-search must verify at least one textbook")

    def _load_plan(self) -> ResearchPlan:
        if not self.plan_path.exists():
            raise FileNotFoundError("research workflow is not initialized")
        return ResearchPlan.from_dict(
            json.loads(self.plan_path.read_text(encoding="utf-8"))
        )

    def _write_plan(self, plan: ResearchPlan) -> None:
        self._write_json(self.plan_path, plan.to_dict())

    @staticmethod
    def _write_json(path: Path, value: dict[str, Any]) -> None:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        temporary.replace(path)

    def _event(self, event: str, **data: Any) -> None:
        with self.state_path.open("a", encoding="utf-8") as stream:
            stream.write(
                json.dumps({"event": event, **data}, ensure_ascii=False) + "\n"
            )


def main(argv: list[str] | None = None) -> int:
    """Run the checkpoint workflow from an agent-friendly JSON CLI."""
    parser = argparse.ArgumentParser(prog="domain-graph-research")
    parser.add_argument("--workspace", default=".")
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init")
    init.add_argument("--question", required=True)
    init.add_argument("--scope", default="")
    init.add_argument("--constraint", action="append", default=[])
    init.add_argument("--success-criterion", action="append", default=[])
    init.add_argument("--overwrite", action="store_true")
    commands.add_parser("status")
    for name in ("start",):
        command = commands.add_parser(name)
        command.add_argument("task_id")
    for name in ("complete", "fail"):
        command = commands.add_parser(name)
        command.add_argument("task_id")
        command.add_argument("--result-file", required=True)
    for name in ("validate", "finalize"):
        command = commands.add_parser(name)
        command.add_argument("--graph", required=True)
    args = parser.parse_args(argv)
    pipeline = ResearchBuildPipeline(args.workspace)
    if args.command == "init":
        pipeline.initialize(
            ResearchBrief(
                args.question,
                args.scope,
                tuple(args.constraint),
                tuple(args.success_criterion),
            ),
            overwrite=args.overwrite,
        )
        payload = {
            "type": "initialized",
            "next": list(pipeline.status().ready_task_ids),
        }
    elif args.command == "status":
        payload = (
            {"type": "status", **asdict(pipeline.status())}
            if pipeline.plan_path.exists()
            else {"type": "uninitialized", "next_action": "init"}
        )
    elif args.command == "start":
        pipeline.start_task(args.task_id)
        payload = {"type": "task_started", "task_id": args.task_id}
    elif args.command in {"complete", "fail"}:
        result = json.loads(Path(args.result_file).read_text(encoding="utf-8"))
        getattr(pipeline, f"{args.command}_task")(args.task_id, result)
        payload = {
            "type": f"task_{args.command}d",
            "task_id": args.task_id,
            "next": list(pipeline.status().ready_task_ids),
        }
    else:
        graph = DomainGraph.from_json(Path(args.graph).read_text(encoding="utf-8"))
        if args.command == "validate":
            issues = pipeline.validate_graph(graph)
            payload = {
                "type": "validation",
                "passed": not issues,
                "issues": [asdict(issue) for issue in issues],
            }
        else:
            output = pipeline.finalize(graph)
            payload = {"type": "finalized", "output": str(output)}
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
