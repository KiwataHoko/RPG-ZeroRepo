"""Checkpointed, dependency-driven research construction workflow."""

import argparse
import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ..adapters import ResearchDomainAdapter
from ..adapters.research import ALLOWED_SOURCE_TYPES, canonical_source_locator
from ..graph import DomainGraph, ValidationIssue


def _require_records(
    label: str, records: list[dict[str, Any]], fields: tuple[str, ...]
) -> None:
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise TypeError(f"{label} record {index} must be an object")
        missing = [field for field in fields if not record.get(field)]
        if missing:
            raise ValueError(
                f"{label} record {index} is missing fields: {', '.join(missing)}"
            )


def _materialized_source_data(source: dict[str, Any]) -> dict[str, Any]:
    data = {
        key: value
        for key, value in source.items()
        if key not in {"id", "title", "locator"}
    }
    locator = str(source["locator"])
    if locator.startswith(("https://", "http://")):
        data["url"] = locator
    elif locator.upper().startswith("ISBN "):
        data["isbn"] = locator[5:].strip()
    elif locator.upper().startswith("DOI "):
        data["doi"] = locator[4:].strip()
    else:
        data["document_id"] = locator
    return data


def _source_key(source: dict[str, Any]) -> tuple[str, str]:
    return canonical_source_locator(_materialized_source_data(source))


def _validate_source(source: dict[str, Any]) -> None:
    fields = ("id", "source_type", "locator", "accessed_at", "authenticity_review")
    absent = [field for field in fields if not source.get(field)]
    if absent:
        raise ValueError(f"retrieved source is missing fields: {', '.join(absent)}")
    if source["source_type"] not in ALLOWED_SOURCE_TYPES:
        raise ValueError(
            "retrieved source_type must be one of: "
            + ", ".join(sorted(ALLOWED_SOURCE_TYPES))
        )
    canonical_source_locator(_materialized_source_data(source))
    review = source["authenticity_review"]
    if (
        not isinstance(review, dict)
        or review.get("status") != "passed"
        or not review.get("method")
    ):
        raise ValueError(
            "retrieved source requires a passed authenticity_review with method"
        )


@dataclass(frozen=True)
class ResearchBrief:
    question: str
    scope: str = ""
    constraints: tuple[str, ...] = ()
    success_criteria: tuple[str, ...] = ()

    def __post_init__(self):
        if not self.question.strip():
            raise ValueError("research question must be non-empty")
        if not self.constraints or any(not value.strip() for value in self.constraints):
            raise ValueError("research constraints must be non-empty")
        if not self.success_criteria or any(
            not value.strip() for value in self.success_criteria
        ):
            raise ValueError("research success criteria must be non-empty")


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

    def reopen(self, task_id: str) -> tuple[str, ...]:
        self.get(task_id)
        reopened = {task_id}
        changed = True
        while changed:
            changed = False
            for task in self.tasks:
                if task.id not in reopened and set(task.depends_on) & reopened:
                    reopened.add(task.id)
                    changed = True
        for task in self.tasks:
            if task.id in reopened:
                task.status = "pending"
                task.result = {}
        return tuple(task.id for task in self.tasks if task.id in reopened)

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

    def complete_task(
        self,
        task_id: str,
        result: dict[str, Any],
        *,
        result_file: str | Path | None = None,
    ) -> None:
        if not result:
            raise ValueError("completed task requires a non-empty result checkpoint")
        plan = self._load_plan()
        task = plan.get(task_id)
        if task.status != "running":
            raise ValueError(f"task {task_id!r} is not running")
        self._validate_task_result(task, result)
        self._write_attempt_checkpoint(task, "completed", result, result_file)
        plan.complete(task_id, result)
        self._write_plan(plan)
        self._event("task_completed", task_id=task_id)

    def fail_task(
        self,
        task_id: str,
        result: dict[str, Any],
        *,
        result_file: str | Path | None = None,
    ) -> None:
        plan = self._load_plan()
        task = plan.get(task_id)
        if task.status != "running":
            raise ValueError(f"task {task_id!r} is not running")
        self._write_attempt_checkpoint(task, "failed", result, result_file)
        plan.fail(task_id, result)
        self._write_plan(plan)
        self._event("task_failed", task_id=task_id)

    def reopen_task(self, task_id: str) -> tuple[str, ...]:
        plan = self._load_plan()
        reopened = plan.reopen(task_id)
        self._write_plan(plan)
        self._event("tasks_reopened", task_ids=list(reopened))
        return reopened

    def validate_graph(self, graph: DomainGraph) -> tuple[ValidationIssue, ...]:
        return ResearchDomainAdapter().validate_research(graph)

    def materialize(self) -> Path:
        """Build a strict draft graph deterministically from completed checkpoints."""
        status = self.status()
        if not status.complete:
            unfinished = (
                status.ready_task_ids
                + status.running_task_ids
                + status.failed_task_ids
                + status.blocked_task_ids
            )
            raise ValueError(f"unfinished research tasks: {', '.join(unfinished)}")
        plan = self._load_plan()
        checkpoint_errors = []
        for task in plan.tasks:
            try:
                self._validate_task_result(task, task.result)
            except (TypeError, ValueError) as exc:
                checkpoint_errors.append(f"{task.id}: {exc}")
        if checkpoint_errors:
            raise ValueError(
                "invalid task checkpoints; reopen the named tasks: "
                + "; ".join(checkpoint_errors)
            )
        brief = json.loads(self.spec_path.read_text(encoding="utf-8"))
        theory_records = plan.get("candidate-theories").result["theories"]
        evidence_result = plan.get("evidence-search").result
        counterexample_result = plan.get("counterexample-search").result
        final_claim_ids = {
            str(value) for value in plan.get("synthesize").result["claim_ids"]
        }
        claim_records = {str(item["id"]): item for item in evidence_result["claims"]}
        if final_claim_ids != set(claim_records):
            raise ValueError(
                "synthesize claim_ids must exactly match materialized claim records"
            )
        source_records: dict[str, dict[str, Any]] = {}
        source_aliases: dict[str, str] = {}
        canonical_ids: dict[tuple[str, str], str] = {}
        for task in plan.tasks:
            for source in task.result.get("sources", ()):
                source_id = str(source["id"])
                key = _source_key(source)
                canonical_id = canonical_ids.setdefault(key, source_id)
                source_aliases[source_id] = canonical_id
                if canonical_id not in source_records:
                    source_records[canonical_id] = {**source, "id": canonical_id}
                    continue
                merged = source_records[canonical_id]
                conflicts = {
                    key
                    for key, value in source.items()
                    if key not in {"id", "title", "locator"}
                    and key in merged
                    and merged[key] != value
                }
                if conflicts:
                    raise ValueError(
                        f"conflicting retrieval records for source {canonical_id!r}: "
                        + ", ".join(sorted(conflicts))
                    )
                merged.update(
                    {key: value for key, value in source.items() if key != "id"}
                )

        adapter = ResearchDomainAdapter()
        graph = adapter.create_graph(
            f"research:{self.workspace.name}", strict_schema=True
        )
        question_id = "q:research"
        graph.add_node(
            question_id,
            "question",
            name=str(brief["question"]),
            data={
                "scope": brief.get("scope", ""),
                "constraints": brief.get("constraints", []),
                "success_criteria": brief.get("success_criteria", []),
            },
        )
        for theory in theory_records:
            theory_id = str(theory["id"])
            graph.add_node(
                theory_id,
                "theory",
                name=str(theory["name"]),
                data={
                    key: theory[key]
                    for key in (
                        "mechanism",
                        "boundary_conditions",
                        "failure_conditions",
                        "predictions",
                    )
                },
            )
            graph.add_edge(question_id, theory_id, "contains")
        for claim in claim_records.values():
            claim_id = str(claim["id"])
            graph.add_node(
                claim_id,
                "claim",
                name=str(claim["name"]),
                data={"status": str(claim.get("status", "supported"))},
            )
            graph.add_edge(question_id, claim_id, "contains")
            for theory_id in claim["theory_ids"]:
                graph.add_edge(str(theory_id), claim_id, "explains")
        for source in source_records.values():
            graph.add_node(
                str(source["id"]),
                "source",
                name=str(source.get("title") or source["id"]),
                data=_materialized_source_data(source),
            )
        evidence_records = list(evidence_result["evidence"]) + list(
            counterexample_result["counterexamples"]
        )
        for evidence in evidence_records:
            evidence_id = str(evidence["id"])
            graph.add_node(
                evidence_id,
                "evidence",
                name=str(evidence["name"]),
                data={
                    "locator": str(evidence["locator"]),
                    "role": (
                        "counterexample"
                        if evidence["relation"] == "contradicts"
                        else "support"
                    ),
                    "observation": str(evidence["observation"]),
                    "reasoning": str(
                        evidence.get("reasoning") or evidence["conflict_reason"]
                    ),
                    **{
                        key: evidence[key]
                        for key in (
                            "challenged_prediction",
                            "conflict_reason",
                            "rival_theory_id",
                            "rival_prediction",
                            "logic_review",
                        )
                        if key in evidence
                    },
                },
            )
            graph.add_edge(
                evidence_id,
                source_aliases[str(evidence["source_id"])],
                "derived_from",
            )
            graph.add_edge(
                evidence_id, str(evidence["claim_id"]), str(evidence["relation"])
            )
        issues = self.validate_graph(graph)
        if issues:
            raise ValueError(
                "materialized research graph failed quality gates: "
                + ", ".join(f"{issue.kind}@{issue.location}" for issue in issues)
            )
        output = self.directory / "draft-research.json"
        output.write_text(graph.to_json(indent=2) + "\n", encoding="utf-8")
        self._event("materialized", output=str(output))
        return output

    def finalize(self, graph: DomainGraph | None = None) -> Path:
        if graph is None:
            graph = DomainGraph.from_json(
                self.materialize().read_text(encoding="utf-8")
            )
        status = self.status()
        if not status.complete:
            raise ValueError("unfinished research tasks")
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
        for source in graph.get_nodes_by_type("source"):
            if canonical_source_locator(source.data) != _source_key(
                ledger_sources[source.id]
            ):
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
        verified_sources = [
            source
            for source in graph.get_nodes_by_type("source")
            if source.data.get("authenticity_review", {}).get("status") == "passed"
        ]
        reviewed_counterexamples = [
            evidence
            for evidence in graph.get_nodes_by_type("evidence")
            if evidence.data.get("role") == "counterexample"
            and evidence.data.get("logic_review", {}).get("status") == "passed"
        ]
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
                "verified_source_count": len(verified_sources),
                "logic_reviewed_counterexample_count": len(
                    reviewed_counterexamples
                ),
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
            "evidence-search": ("sources", "claims", "evidence"),
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
        if task.id == "candidate-theories":
            _require_records(
                "theory",
                result["theories"],
                (
                    "id",
                    "name",
                    "mechanism",
                    "boundary_conditions",
                    "failure_conditions",
                    "predictions",
                ),
            )
        if "sources" in required:
            for source in result["sources"]:
                _validate_source(source)
        if task.id == "textbook-search" and not any(
            source["source_type"] == "textbook" for source in result["sources"]
        ):
            raise ValueError("textbook-search must verify at least one textbook")
        if task.id == "evidence-search":
            _require_records("claim", result["claims"], ("id", "name", "theory_ids"))
            _require_records(
                "evidence",
                result["evidence"],
                (
                    "id",
                    "name",
                    "claim_id",
                    "source_id",
                    "locator",
                    "relation",
                    "observation",
                    "reasoning",
                ),
            )
            if any(item["relation"] != "supports" for item in result["evidence"]):
                raise ValueError("evidence-search records must use supports")
        if task.id == "counterexample-search":
            _require_records(
                "counterexample",
                result["counterexamples"],
                (
                    "id",
                    "name",
                    "claim_id",
                    "source_id",
                    "locator",
                    "relation",
                    "challenged_prediction",
                    "observation",
                    "conflict_reason",
                    "rival_theory_id",
                    "rival_prediction",
                    "logic_review",
                ),
            )
            if any(
                item["relation"] != "contradicts" for item in result["counterexamples"]
            ):
                raise ValueError("counterexample-search records must use contradicts")
            for item in result["counterexamples"]:
                review = item["logic_review"]
                if (
                    not isinstance(review, dict)
                    or review.get("status") != "passed"
                    or not review.get("reason")
                ):
                    raise ValueError(
                        "counterexample requires a passed logic_review with reason"
                    )

    def _write_attempt_checkpoint(
        self,
        task: ResearchTask,
        outcome: str,
        result: dict[str, Any],
        result_file: str | Path | None,
    ) -> Path:
        """Store the exact accepted payload once under its task attempt number."""
        checkpoint_dir = self.directory / "checkpoints" / task.id
        checkpoint_dir.mkdir(parents=True, exist_ok=True)
        checkpoint = checkpoint_dir / f"attempt-{task.attempts:04d}.{outcome}.json"
        if checkpoint.exists():
            raise FileExistsError(f"attempt checkpoint already exists: {checkpoint}")
        if result_file is not None:
            payload = Path(result_file).read_bytes()
            if json.loads(payload) != result:
                raise ValueError("result file changed before checkpointing")
        else:
            payload = (json.dumps(result, ensure_ascii=False, indent=2) + "\n").encode()
        descriptor = os.open(checkpoint, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
        return checkpoint

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
    for name in ("start", "reopen"):
        command = commands.add_parser(name)
        command.add_argument("task_id")
    for name in ("complete", "fail"):
        command = commands.add_parser(name)
        command.add_argument("task_id")
        command.add_argument("--result-file", required=True)
    commands.add_parser("materialize")
    validate = commands.add_parser("validate")
    validate.add_argument("--graph", required=True)
    finalize = commands.add_parser("finalize")
    finalize.add_argument("--graph")
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
    elif args.command == "reopen":
        payload = {
            "type": "tasks_reopened",
            "task_ids": list(pipeline.reopen_task(args.task_id)),
        }
    elif args.command in {"complete", "fail"}:
        result = json.loads(Path(args.result_file).read_text(encoding="utf-8"))
        getattr(pipeline, f"{args.command}_task")(
            args.task_id, result, result_file=args.result_file
        )
        payload = {
            "type": f"task_{args.command}d",
            "task_id": args.task_id,
            "next": list(pipeline.status().ready_task_ids),
        }
    elif args.command == "materialize":
        output = pipeline.materialize()
        payload = {"type": "materialized", "output": str(output)}
    elif args.command == "validate":
        graph = DomainGraph.from_json(Path(args.graph).read_text(encoding="utf-8"))
        issues = pipeline.validate_graph(graph)
        payload = {
            "type": "validation",
            "passed": not issues,
            "issues": [asdict(issue) for issue in issues],
        }
    else:
        graph = (
            DomainGraph.from_json(Path(args.graph).read_text(encoding="utf-8"))
            if args.graph
            else None
        )
        output = pipeline.finalize(graph)
        payload = {"type": "finalized", "output": str(output)}
    print(json.dumps(payload, ensure_ascii=False))
    return 0


def cli() -> int:
    """Console entry point that reports recoverable workflow errors as JSON."""
    try:
        return main()
    except (FileNotFoundError, KeyError, TypeError, ValueError) as exc:
        print(
            json.dumps(
                {"type": "error", "error": str(exc)},
                ensure_ascii=False,
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(cli())
