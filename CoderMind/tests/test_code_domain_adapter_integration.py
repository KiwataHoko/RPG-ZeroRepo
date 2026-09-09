"""Integration coverage for the legacy CoderMind code-domain vocabulary."""

import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

from domain_graph import HierarchyCycleError, SchemaViolation
from rpg import CodeDomainAdapter, EdgeType, NodeType


FIXTURE = Path(__file__).parent / "fixtures" / "code_domain" / "legacy_code_graph.json"


def _load_fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _build_graph(*, strict_schema: bool = True):
    payload = _load_fixture()
    adapter = CodeDomainAdapter()
    graph = adapter.create_graph(payload["name"], strict_schema=strict_schema)
    for node in payload["nodes"]:
        graph.add_node(
            node["id"],
            node["entity_type"],
            name=node["name"],
            data=node["data"],
        )
    for edge in payload["edges"]:
        graph.add_edge(
            edge["source"],
            edge["target"],
            edge["relation"],
            data=edge["data"],
        )
    return graph, payload


def _ids(nodes):
    return {node.id for node in nodes}


def test_realistic_fixture_loads_under_strict_code_schema():
    graph, payload = _build_graph(strict_schema=True)

    assert graph.validate() == ()
    assert graph.name == payload["name"]
    assert len(graph.nodes) == len(payload["nodes"])
    assert len(graph.edges) == len(payload["edges"])
    assert [node.to_dict() for node in graph.nodes.values()] == payload["nodes"]
    assert [edge.to_dict() for edge in graph.edges] == payload["edges"]
    assert set(node.entity_type for node in graph.nodes.values()) == {
        "repo",
        "directory",
        "file",
        "class",
        "method",
        "function",
        "interface",
        "data",
    }
    assert {edge.relation for edge in graph.edges} == {
        "contains",
        "composes",
        "invokes",
        "imports",
        "inherits",
        "references",
    }


def test_adapter_normalizes_enum_symbols_and_preserves_node_edge_data():
    adapter = CodeDomainAdapter()
    graph = adapter.create_graph("normalization", strict_schema=True)
    graph.add_node("class-1", NodeType.CLASS, name="Service", data={"line": 10})
    graph.add_node("fn-1", "function", name="run", data={"签名": "run()"})
    edge = graph.add_edge(
        "class-1",
        "fn-1",
        EdgeType.COMPOSES,
        data={"reason": "legacy containment"},
    )

    assert adapter.entity_type(NodeType.CLASS) == "class"
    assert adapter.relation(EdgeType.COMPOSES) == "composes"
    assert graph.get_node("class-1").data == {"line": 10}
    assert edge.relation == "composes"
    assert edge.data == {"reason": "legacy containment"}


def test_hierarchy_queries_follow_realistic_repository_structure():
    graph, _ = _build_graph()

    assert [node.id for node in graph.children("repo:legacy-service")] == [
        "dir:src"
    ]
    assert _ids(graph.parents("file:api")) == {"dir:src/core"}
    assert _ids(graph.ancestors("method:service.list")) == {
        "class:service",
        "file:api",
        "dir:src/core",
        "dir:src",
        "repo:legacy-service",
    }
    assert _ids(graph.descendants("file:api")) == {
        "class:service",
        "method:service.list",
        "function:normalize",
    }


def test_neighbors_include_non_hierarchy_relations_in_both_directions():
    graph, _ = _build_graph()

    assert _ids(graph.neighbors("class:service", direction="both")) == {
        "method:service.list",
        "file:api",
        "interface:repository",
        "data:service-config",
    }
    assert _ids(
        graph.neighbors("file:api", relation=EdgeType.IMPORTS, direction="out")
    ) == {"file:models"}
    assert _ids(
        graph.neighbors("interface:repository", relation="inherits", direction="in")
    ) == {"class:service"}


def test_json_round_trip_preserves_graph_semantics_and_wire_data():
    graph, _ = _build_graph()

    restored = type(graph).from_json(graph.to_json(indent=2))

    assert restored.to_dict() == graph.to_dict()
    assert restored.strict_schema is True
    assert restored.get_node("data:service-config").data["description"] == "服务配置"
    assert _ids(restored.descendants("repo:legacy-service")) == _ids(
        graph.descendants("repo:legacy-service")
    )


def test_hierarchy_cycle_is_rejected():
    graph, _ = _build_graph()

    with pytest.raises(HierarchyCycleError):
        graph.add_edge("file:models", "repo:legacy-service", EdgeType.CONTAINS)


def test_unknown_symbols_are_reported_open_but_rejected_strict():
    adapter = CodeDomainAdapter()
    open_graph = adapter.create_graph("open-world", strict_schema=False)
    open_graph.add_node("macro:1", "macro", name="Generated")
    open_graph.add_node("file:one", NodeType.FILE)
    open_graph.add_edge("file:one", "macro:1", "generates")

    issues = open_graph.validate()
    assert {(issue.kind, issue.value) for issue in issues} == {
        ("unknown_entity_type", "macro"),
        ("unknown_relation", "generates"),
    }

    strict_graph = adapter.create_graph("strict-world", strict_schema=True)
    with pytest.raises(SchemaViolation):
        strict_graph.add_node("macro:1", "macro")
    strict_graph.add_node("file:one", NodeType.FILE)
    strict_graph.add_node("file:two", NodeType.FILE)
    with pytest.raises(SchemaViolation):
        strict_graph.add_edge("file:one", "file:two", "generates")


def test_node_deletion_removes_all_incident_edges():
    graph, _ = _build_graph()
    before = len(graph.edges)

    removed = graph.remove_node("file:models")

    assert removed.id == "file:models"
    assert "file:models" not in graph.nodes
    assert len(graph.edges) < before
    assert all(
        edge.source != "file:models" and edge.target != "file:models"
        for edge in graph.edges
    )
    assert graph.validate() == ()
