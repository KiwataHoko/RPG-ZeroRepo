"""Research workflow acceptance tests."""

import json

import pytest

from domain_graph.adapters import ResearchDomainAdapter
from domain_graph.workflows import (
    ResearchBrief,
    ResearchBuildPipeline,
    ResearchPlan,
    ResearchTask,
)
from domain_graph.workflows.research import main


def _money_graph():
    adapter = ResearchDomainAdapter()
    graph = adapter.create_graph("research:money", strict_schema=True)
    graph.add_node("q:money", "question", name="赚钱到底是什么？")
    for theory_id, name in (
        ("t:value", "value creation and capture"),
        ("t:rent", "institutional rent"),
    ):
        graph.add_node(theory_id, "theory", name=name)
        graph.add_edge("q:money", theory_id, "contains")
    for claim_id, theory_id, name in (
        ("c:value", "t:value", "Some durable returns follow value creation."),
        ("c:rent", "t:rent", "Some returns follow privileged control."),
    ):
        graph.add_node(claim_id, "claim", name=name)
        graph.add_edge("q:money", claim_id, "contains")
        graph.add_edge(theory_id, claim_id, "explains")
    for source_id, name, url in (
        ("s:textbook", "Economics textbook", "https://example.test/textbook"),
        ("s:paper", "Rent paper", "https://example.test/paper"),
    ):
        graph.add_node(
            source_id,
            "source",
            name=name,
            data={
                "url": url,
                "source_type": "textbook" if "textbook" in source_id else "paper",
                "accessed_at": "2026-09-10",
            },
        )
    evidence = (
        ("e:value+", "c:value", "s:textbook", "supports", "chapter 8", "support"),
        ("e:value-", "c:value", "s:paper", "contradicts", "p. 10", "counterexample"),
        ("e:rent+", "c:rent", "s:paper", "supports", "p. 4", "support"),
        (
            "e:rent-",
            "c:rent",
            "s:textbook",
            "contradicts",
            "chapter 13",
            "counterexample",
        ),
    )
    for evidence_id, claim_id, source_id, relation, locator, role in evidence:
        graph.add_node(
            evidence_id,
            "evidence",
            name=f"Evidence for {claim_id}",
            data={"locator": locator, "role": role},
        )
        graph.add_edge(evidence_id, source_id, "derived_from")
        graph.add_edge(evidence_id, claim_id, relation)
    return graph


def _task_result(task_id):
    source_textbook = {
        "id": "s:textbook",
        "source_type": "textbook",
        "locator": "https://example.test/textbook",
        "accessed_at": "2026-09-10",
    }
    source_paper = {
        "id": "s:paper",
        "source_type": "paper",
        "locator": "https://example.test/paper",
        "accessed_at": "2026-09-10",
    }
    return {
        "define-concepts": {
            "concepts": ["profit", "cash flow"],
            "distinctions": ["profit != cash"],
            "acceptance_tests": ["distinguishes rents"],
        },
        "candidate-theories": {"theories": [{"id": "t:value"}, {"id": "t:rent"}]},
        "textbook-search": {"sources": [source_textbook]},
        "evidence-search": {
            "sources": [source_textbook, source_paper],
            "claim_ids": ["c:value", "c:rent"],
        },
        "counterexample-search": {
            "sources": [source_textbook, source_paper],
            "counterexamples": [{"claim_id": "c:value"}, {"claim_id": "c:rent"}],
        },
        "discriminatory-tests": {"comparisons": ["value versus rent"]},
        "synthesize": {
            "claim_ids": ["c:value", "c:rent"],
            "revisions": ["narrowed value claim"],
        },
    }[task_id]


def test_research_plan_is_dependency_ordered_and_rejects_cycles():
    plan = ResearchPlan.default(ResearchBrief(question="赚钱到底是什么？"))
    assert plan.ready_task_ids() == ("define-concepts",)
    plan.start("define-concepts")
    plan.complete("define-concepts", _task_result("define-concepts"))
    assert plan.ready_task_ids() == ("candidate-theories", "textbook-search")

    with pytest.raises(ValueError, match="cycle"):
        ResearchPlan(
            tasks=(
                ResearchTask("a", "A", "discovery", depends_on=("b",)),
                ResearchTask("b", "B", "challenge", depends_on=("a",)),
            )
        )


def test_pipeline_persists_and_resumes_checkpoints(tmp_path):
    pipeline = ResearchBuildPipeline(tmp_path)
    pipeline.initialize(ResearchBrief(question="赚钱到底是什么？"))
    pipeline.start_task("define-concepts")
    pipeline.complete_task("define-concepts", _task_result("define-concepts"))

    resumed = ResearchBuildPipeline(tmp_path)
    status = resumed.status()
    assert status.completed_task_ids == ("define-concepts",)
    assert status.ready_task_ids == ("candidate-theories", "textbook-search")
    assert (tmp_path / ".research/research-spec.json").is_file()
    assert (tmp_path / ".research/research-plan.json").is_file()
    assert (tmp_path / ".research/research-state.jsonl").is_file()


def test_validate_research_enforces_provenance_and_adversarial_coverage():
    adapter = ResearchDomainAdapter()
    graph = _money_graph()
    assert adapter.validate_research(graph) == ()

    graph.remove_edge("e:value-", "c:value", "contradicts")
    kinds = {issue.kind for issue in adapter.validate_research(graph)}
    assert "missing_counterexample" in kinds


def test_money_making_end_to_end_requires_plan_completion(tmp_path):
    pipeline = ResearchBuildPipeline(tmp_path)
    pipeline.initialize(
        ResearchBrief(
            question="赚钱到底是什么？",
            constraints=("no invented formula", "avoid actor enumeration"),
            success_criteria=("competing theories", "counterexample coverage"),
        )
    )
    graph = _money_graph()

    with pytest.raises(ValueError, match="unfinished research tasks"):
        pipeline.finalize(graph)

    while pipeline.status().ready_task_ids:
        for task_id in pipeline.status().ready_task_ids:
            pipeline.start_task(task_id)
            pipeline.complete_task(task_id, _task_result(task_id))

    output = pipeline.finalize(graph)
    assert output == tmp_path / ".research/research.domain-graph.json"
    assert json.loads(output.read_text())["name"] == "research:money"
    coverage = json.loads((tmp_path / ".research/coverage-report.json").read_text())
    assert coverage["passed"] is True
    assert coverage["theory_count"] == 2
    assert coverage["counterexample_covered_theory_count"] == 2


def test_cli_initializes_and_reports_ready_tasks(tmp_path, capsys):
    assert main(["--workspace", str(tmp_path), "status"]) == 0
    uninitialized = json.loads(capsys.readouterr().out)
    assert uninitialized == {"type": "uninitialized", "next_action": "init"}
    assert (
        main(["--workspace", str(tmp_path), "init", "--question", "赚钱到底是什么？"])
        == 0
    )
    initialized = json.loads(capsys.readouterr().out)
    assert initialized["next"] == ["define-concepts"]
    assert main(["--workspace", str(tmp_path), "status"]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["ready_task_ids"] == ["define-concepts"]


def test_pipeline_rejects_placeholder_task_results(tmp_path):
    pipeline = ResearchBuildPipeline(tmp_path)
    pipeline.initialize(ResearchBrief(question="赚钱到底是什么？"))
    pipeline.start_task("define-concepts")
    with pytest.raises(ValueError, match="missing non-empty fields"):
        pipeline.complete_task("define-concepts", {"artifact": "looks-finished.json"})
