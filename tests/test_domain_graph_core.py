"""Standalone tests for the domain graph core."""

import ast
from pathlib import Path

import pytest

from domain_graph import (
    DomainAdapter,
    DomainGraph,
    DomainSchema,
    HierarchyCycleError,
    RelationSpec,
    SchemaViolation,
)


def _research_schema() -> DomainSchema:
    return DomainSchema(
        name="research",
        entity_types=("claim", "evidence", "source"),
        relations=(
            RelationSpec("contains", hierarchy=True),
            RelationSpec("supports"),
            RelationSpec("contradicts"),
        ),
    )


def test_core_has_no_coder_mind_or_rpg_imports():
    package_root = Path(__file__).resolve().parents[1] / "domain_graph"
    for path in package_root.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module)
        assert not any(
            name == "rpg" or name.startswith("rpg.")
            or name == "CoderMind" or name.startswith("CoderMind.")
            for name in imported
        ), path


def test_public_api_supports_build_query_and_hierarchy_traversal():
    graph = DomainGraph("paper", _research_schema())
    graph.add_node("source-1", "source", name="Paper")
    graph.add_node("claim-1", "claim", name="Claim")
    graph.add_node("evidence-1", "evidence", name="Evidence")
    graph.add_edge("source-1", "claim-1", "contains")
    graph.add_edge("claim-1", "evidence-1", "contains")
    graph.add_edge("evidence-1", "claim-1", "supports")

    assert [node.id for node in graph.children("source-1")] == ["claim-1"]
    assert [node.id for node in graph.descendants("source-1")] == [
        "claim-1", "evidence-1",
    ]
    assert [node.id for node in graph.ancestors("evidence-1")] == [
        "claim-1", "source-1",
    ]
    assert graph.get_nodes_by_type("claim")[0].name == "Claim"
    assert graph.neighbors("evidence-1", relation="supports")[0].id == "claim-1"


def test_open_world_symbols_validate_without_forcing_enumeration():
    graph = DomainGraph("paper", _research_schema())
    graph.add_node("hypothesis-1", "hypothesis")
    graph.add_node("claim-1", "claim")
    graph.add_edge("hypothesis-1", "claim-1", "qualifies")

    assert {(issue.kind, issue.value) for issue in graph.validate()} == {
        ("unknown_entity_type", "hypothesis"),
        ("unknown_relation", "qualifies"),
    }


def test_strict_schema_rejects_unknown_symbols():
    graph = DomainGraph("paper", _research_schema(), strict_schema=True)
    with pytest.raises(SchemaViolation):
        graph.add_node("hypothesis-1", "hypothesis")
    graph.add_node("claim-1", "claim")
    graph.add_node("evidence-1", "evidence")
    with pytest.raises(SchemaViolation):
        graph.add_edge("claim-1", "evidence-1", "qualifies")


def test_hierarchy_edges_reject_cycles_but_non_hierarchy_edges_do_not():
    graph = DomainGraph("paper", _research_schema())
    graph.add_node("a", "claim")
    graph.add_node("b", "claim")
    graph.add_edge("a", "b", "contains")
    graph.add_edge("b", "a", "supports")
    with pytest.raises(HierarchyCycleError):
        graph.add_edge("b", "a", "contains")


def test_versioned_json_round_trip_preserves_schema_nodes_edges_and_mode():
    graph = DomainGraph("paper", _research_schema())
    graph.add_node("claim-1", "claim", data={"confidence": 0.8})
    graph.add_node("evidence-1", "evidence")
    graph.add_edge("claim-1", "evidence-1", "contains")
    graph.add_edge("evidence-1", "claim-1", "supports", data={"weight": 2})

    payload = graph.to_dict()
    restored = DomainGraph.from_json(graph.to_json())

    assert payload["format"] == "domain-graph"
    assert payload["version"] == 1
    assert restored.domain_schema == _research_schema()
    assert restored.get_node("claim-1").data == {"confidence": 0.8}
    assert restored.edges[1].data == {"weight": 2}


def test_mutation_api_removes_edges_and_incident_edges():
    graph = DomainGraph("paper", _research_schema())
    graph.add_node("source-1", "source")
    graph.add_node("claim-1", "claim")
    graph.add_node("evidence-1", "evidence")
    graph.add_edge("source-1", "claim-1", "contains")
    graph.add_edge("claim-1", "evidence-1", "supports")

    assert graph.remove_edge("claim-1", "evidence-1", "supports") == 1
    graph.add_edge("claim-1", "evidence-1", "supports")
    removed = graph.remove_node("claim-1")

    assert removed.id == "claim-1"
    assert "claim-1" not in graph.nodes
    assert graph.edges == ()


def test_adapter_constructs_graph_from_domain_schema():
    adapter = DomainAdapter(_research_schema())
    graph = adapter.create_graph("paper")
    assert graph.domain_schema == _research_schema()
    assert adapter.entity_type("claim") == "claim"
    assert adapter.relation("supports") == "supports"
