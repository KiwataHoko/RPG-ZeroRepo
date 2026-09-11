"""Research workflow acceptance tests."""

import json

import pytest

from domain_graph import DomainGraph
from domain_graph.adapters import ResearchDomainAdapter
from domain_graph.adapters.research import canonical_source_locator
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
        graph.add_node(
            theory_id,
            "theory",
            name=name,
            data={
                "predictions": (
                    ["returns decay without value", "value predicts the observed outcome"]
                    if theory_id == "t:value"
                    else ["returns change with rules", "rent predicts the observed outcome"]
                )
            },
        )
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
                "authenticity_review": {
                    "status": "passed",
                    "method": "publisher or repository record checked",
                },
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
            data={
                "locator": locator,
                "role": role,
                "observation": f"Observed result for {claim_id}",
                "reasoning": f"The observation bears on {claim_id}",
                **(
                    {
                        "challenged_prediction": (
                            "returns decay without value"
                            if claim_id == "c:value"
                            else "returns change with rules"
                        ),
                        "conflict_reason": "The observed outcome differs from it",
                        "rival_theory_id": (
                            "t:rent" if claim_id == "c:value" else "t:value"
                        ),
                        "rival_prediction": (
                            "rent predicts the observed outcome"
                            if claim_id == "c:value"
                            else "value predicts the observed outcome"
                        ),
                        "logic_review": {
                            "status": "passed",
                            "reason": "Prediction and observation are incompatible",
                        },
                    }
                    if role == "counterexample"
                    else {}
                ),
            },
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
        "authenticity_review": {
            "status": "passed",
            "method": "publisher record checked",
        },
    }
    source_paper = {
        "id": "s:paper",
        "source_type": "paper",
        "locator": "https://example.test/paper",
        "accessed_at": "2026-09-10",
        "authenticity_review": {
            "status": "passed",
            "method": "journal record checked",
        },
    }
    return {
        "define-concepts": {
            "concepts": ["profit", "cash flow"],
            "distinctions": ["profit != cash"],
            "acceptance_tests": ["distinguishes rents"],
        },
        "candidate-theories": {
            "theories": [
                {
                    "id": "t:value",
                    "name": "value creation and capture",
                    "mechanism": "valuable output",
                    "boundary_conditions": ["exchange"],
                    "failure_conditions": ["rent"],
                    "predictions": [
                        "returns decay without value",
                        "value predicts the observed outcome",
                    ],
                },
                {
                    "id": "t:rent",
                    "name": "institutional rent",
                    "mechanism": "privileged control",
                    "boundary_conditions": ["exclusion"],
                    "failure_conditions": ["open entry"],
                    "predictions": [
                        "returns change with rules",
                        "rent predicts the observed outcome",
                    ],
                },
            ]
        },
        "textbook-search": {"sources": [source_textbook]},
        "evidence-search": {
            "sources": [source_textbook, source_paper],
            "claims": [
                {
                    "id": "c:value",
                    "name": "Some durable returns follow value creation.",
                    "theory_ids": ["t:value"],
                },
                {
                    "id": "c:rent",
                    "name": "Some returns follow privileged control.",
                    "theory_ids": ["t:rent"],
                },
            ],
            "evidence": [
                {
                    "id": "e:value+",
                    "name": "Evidence for value",
                    "claim_id": "c:value",
                    "source_id": "s:textbook",
                    "locator": "chapter 8",
                    "relation": "supports",
                    "observation": "Returns persist where buyers retain surplus.",
                    "reasoning": "This directly supports the value mechanism.",
                },
                {
                    "id": "e:rent+",
                    "name": "Evidence for rent",
                    "claim_id": "c:rent",
                    "source_id": "s:paper",
                    "locator": "p. 4",
                    "relation": "supports",
                    "observation": "Protected entry is associated with excess returns.",
                    "reasoning": "The observation follows the rent mechanism.",
                },
            ],
        },
        "counterexample-search": {
            "sources": [source_textbook, {**source_paper, "title": "Rent paper"}],
            "counterexamples": [
                {
                    "id": "e:value-",
                    "name": "Rent challenges value",
                    "claim_id": "c:value",
                    "source_id": "s:paper",
                    "locator": "p. 10",
                    "relation": "contradicts",
                    "challenged_prediction": "returns decay without value",
                    "observation": "Protected incumbents earned returns without added output.",
                    "conflict_reason": "Returns occurred while the predicted cause was absent.",
                    "rival_theory_id": "t:rent",
                    "rival_prediction": "rent predicts the observed outcome",
                    "logic_review": {
                        "status": "passed",
                        "reason": "The observation separates value and rent predictions.",
                    },
                },
                {
                    "id": "e:rent-",
                    "name": "Entry challenges rent",
                    "claim_id": "c:rent",
                    "source_id": "s:textbook",
                    "locator": "chapter 13",
                    "relation": "contradicts",
                    "challenged_prediction": "returns change with rules",
                    "observation": "Returns disappeared after entry became open.",
                    "conflict_reason": "The return did not persist outside the stated protection.",
                    "rival_theory_id": "t:value",
                    "rival_prediction": "value predicts the observed outcome",
                    "logic_review": {
                        "status": "passed",
                        "reason": "The observation discriminates between protection and value.",
                    },
                },
            ],
        },
        "discriminatory-tests": {"comparisons": ["value versus rent"]},
        "synthesize": {
            "claim_ids": ["c:value", "c:rent"],
            "revisions": ["narrowed value claim"],
        },
    }[task_id]


def _brief():
    return ResearchBrief(
        question="赚钱到底是什么？",
        constraints=("no invented formula",),
        success_criteria=("counterexample coverage",),
    )


def test_research_brief_requires_constraints_and_success_criteria():
    with pytest.raises(ValueError, match="constraints"):
        ResearchBrief(question="赚钱到底是什么？")
    with pytest.raises(ValueError, match="success criteria"):
        ResearchBrief(question="赚钱到底是什么？", constraints=("no formulas",))


def test_research_plan_is_dependency_ordered_and_rejects_cycles():
    plan = ResearchPlan.default(_brief())
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
    pipeline.initialize(_brief())
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

    graph = _money_graph()
    graph.get_node("s:paper").data["authenticity_review"]["status"] = "failed"
    graph.get_node("e:value-").data["logic_review"]["status"] = "failed"
    kinds = {issue.kind for issue in adapter.validate_research(graph)}
    assert "source_authenticity" in kinds
    assert "counterexample_logic_review" in kinds


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
    assert coverage["verified_source_count"] == 2
    assert coverage["logic_reviewed_counterexample_count"] == 2


def test_cli_initializes_and_reports_ready_tasks(tmp_path, capsys):
    assert main(["--workspace", str(tmp_path), "status"]) == 0
    uninitialized = json.loads(capsys.readouterr().out)
    assert uninitialized == {"type": "uninitialized", "next_action": "init"}
    assert (
        main([
            "--workspace", str(tmp_path), "init", "--question", "赚钱到底是什么？",
            "--constraint", "no invented formula",
            "--success-criterion", "counterexample coverage",
        ])
        == 0
    )
    initialized = json.loads(capsys.readouterr().out)
    assert initialized["next"] == ["define-concepts"]
    assert main(["--workspace", str(tmp_path), "status"]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["ready_task_ids"] == ["define-concepts"]


def test_pipeline_rejects_placeholder_task_results(tmp_path):
    pipeline = ResearchBuildPipeline(tmp_path)
    pipeline.initialize(_brief())
    pipeline.start_task("define-concepts")
    with pytest.raises(ValueError, match="missing non-empty fields"):
        pipeline.complete_task("define-concepts", {"artifact": "looks-finished.json"})


def test_pipeline_materializes_graph_from_normalized_checkpoints(tmp_path):
    pipeline = ResearchBuildPipeline(tmp_path)
    pipeline.initialize(_brief())
    while pipeline.status().ready_task_ids:
        for task_id in pipeline.status().ready_task_ids:
            pipeline.start_task(task_id)
            pipeline.complete_task(task_id, _task_result(task_id))

    draft = pipeline.materialize()
    graph = DomainGraph.from_json(draft.read_text())
    assert graph.get_node("q:research").name == "赚钱到底是什么？"
    assert {node.id for node in graph.get_nodes_by_type("theory")} == {
        "t:value",
        "t:rent",
    }
    assert ResearchDomainAdapter().validate_research(graph) == ()
    assert pipeline.finalize() == tmp_path / ".research/research.domain-graph.json"


def test_reopen_resets_task_and_transitive_dependents(tmp_path):
    pipeline = ResearchBuildPipeline(tmp_path)
    pipeline.initialize(_brief())
    while pipeline.status().ready_task_ids:
        for task_id in pipeline.status().ready_task_ids:
            pipeline.start_task(task_id)
            pipeline.complete_task(task_id, _task_result(task_id))

    pipeline.reopen_task("candidate-theories")
    status = pipeline.status()
    assert "candidate-theories" in status.ready_task_ids
    assert "evidence-search" in status.blocked_task_ids
    assert "synthesize" in status.blocked_task_ids
    assert "textbook-search" in status.completed_task_ids


def test_source_quality_and_canonical_deduplication(tmp_path):
    pipeline = ResearchBuildPipeline(tmp_path)
    pipeline.initialize(_brief())
    pipeline.start_task("define-concepts")
    pipeline.complete_task("define-concepts", _task_result("define-concepts"))
    pipeline.start_task("textbook-search")
    invalid = _task_result("textbook-search")
    invalid["sources"][0] = {
        **invalid["sources"][0],
        "locator": "ISBN 9780000000000",
    }
    with pytest.raises(ValueError, match="invalid ISBN-13"):
        pipeline.complete_task("textbook-search", invalid)

    for locator, message in (("DOI not-a-doi", "invalid DOI"), ("https://", "invalid URL")):
        bad_source = {
            **_task_result("textbook-search")["sources"][0],
            "locator": locator,
        }
        with pytest.raises(ValueError, match=message):
            ResearchBuildPipeline._validate_task_result(
                ResearchTask("textbook-search", "", "discovery"),
                {"sources": [bad_source]},
            )

    with pytest.raises(ValueError, match="source_type"):
        ResearchBuildPipeline._validate_task_result(
            ResearchTask("textbook-search", "", "discovery"),
            {
                "sources": [
                    {
                        **_task_result("textbook-search")["sources"][0],
                        "source_type": "analysis",
                    }
                ]
            },
        )

    assert canonical_source_locator({"doi": "10.1000/ABC"}) == (
        "doi",
        "10.1000/abc",
    )
    assert canonical_source_locator({"url": "https://doi.org/10.1000/abc"}) == (
        "doi",
        "10.1000/abc",
    )
    assert canonical_source_locator({"isbn": "978-0-19-507340-9"}) == (
        "isbn",
        "9780195073409",
    )


def test_materialize_deduplicates_normalized_source_aliases(tmp_path):
    pipeline = ResearchBuildPipeline(tmp_path)
    pipeline.initialize(_brief())
    results = {task_id: _task_result(task_id) for task_id in (
        "define-concepts", "candidate-theories", "textbook-search",
        "evidence-search", "counterexample-search", "discriminatory-tests",
        "synthesize",
    )}
    alias = {
        **results["counterexample-search"]["sources"][1],
        "id": "s:paper-alias",
        "locator": "https://example.test/paper/",
    }
    results["counterexample-search"]["sources"][1] = alias
    results["counterexample-search"]["counterexamples"][0]["source_id"] = alias["id"]
    while pipeline.status().ready_task_ids:
        for task_id in pipeline.status().ready_task_ids:
            pipeline.start_task(task_id)
            pipeline.complete_task(task_id, results[task_id])

    graph = DomainGraph.from_json(pipeline.materialize().read_text())
    assert {node.id for node in graph.get_nodes_by_type("source")} == {
        "s:textbook",
        "s:paper",
    }
    assert pipeline.finalize() == tmp_path / ".research/research.domain-graph.json"


def test_cli_copies_result_to_immutable_attempt_checkpoint(tmp_path, capsys):
    pipeline = ResearchBuildPipeline(tmp_path)
    pipeline.initialize(_brief())
    pipeline.start_task("define-concepts")
    result_path = tmp_path / "result.json"
    result_path.write_text(json.dumps(_task_result("define-concepts")))
    assert main([
        "--workspace", str(tmp_path), "complete", "define-concepts",
        "--result-file", str(result_path),
    ]) == 0
    capsys.readouterr()
    checkpoint = tmp_path / ".research/checkpoints/define-concepts/attempt-0001.completed.json"
    assert json.loads(checkpoint.read_text()) == _task_result("define-concepts")
    assert checkpoint.stat().st_mode & 0o222 == 0


def test_rejects_weak_evidence_and_counterexample_contracts(tmp_path):
    pipeline = ResearchBuildPipeline(tmp_path)
    evidence = _task_result("evidence-search")
    del evidence["evidence"][0]["observation"]
    with pytest.raises(ValueError, match="observation"):
        pipeline._validate_task_result(ResearchTask("evidence-search", "", "discovery"), evidence)

    counter = _task_result("counterexample-search")
    del counter["counterexamples"][0]["conflict_reason"]
    with pytest.raises(ValueError, match="conflict_reason"):
        pipeline._validate_task_result(ResearchTask("counterexample-search", "", "challenge"), counter)
