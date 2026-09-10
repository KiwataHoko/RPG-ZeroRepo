"""Compatibility tests for the immutable domain-graph v1 wire fixtures."""

import json
from pathlib import Path

import pytest

from domain_graph import DomainGraph


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "v1"
FIXTURE_NAMES = ("minimal", "research", "content", "unicode_nested", "open_world")


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURE_DIR / f"{name}.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("fixture_name", FIXTURE_NAMES)
def test_released_v1_fixture_has_stable_wire_contract(fixture_name: str):
    payload = load_fixture(fixture_name)

    assert payload["format"] == "domain-graph"
    assert payload["version"] == 1
    assert set(payload) == {
        "format",
        "version",
        "name",
        "schema",
        "strict_schema",
        "nodes",
        "edges",
    }
    assert set(payload["schema"]) == {"name", "entity_types", "relations"}
    assert all(
        set(relation) == {"name", "hierarchy"}
        for relation in payload["schema"]["relations"]
    )
    assert all(
        set(node) == {"id", "entity_type", "name", "data"}
        for node in payload["nodes"]
    )
    assert all(
        set(edge) == {"source", "target", "relation", "data"}
        for edge in payload["edges"]
    )


@pytest.mark.parametrize("fixture_name", FIXTURE_NAMES)
def test_released_v1_fixture_restores_and_round_trips_semantically(fixture_name: str):
    payload = load_fixture(fixture_name)

    graph = DomainGraph.from_dict(payload)
    restored = DomainGraph.from_json(graph.to_json())

    assert graph.to_dict() == payload
    assert restored.to_dict() == payload


def test_minimal_fixture_preserves_hierarchy_queries():
    graph = DomainGraph.from_dict(load_fixture("minimal"))

    assert [node.id for node in graph.children("root")] == ["leaf"]
    assert [node.id for node in graph.parents("leaf")] == ["root"]
    assert [node.id for node in graph.descendants("root")] == ["leaf"]
    assert [node.id for node in graph.ancestors("leaf")] == ["root"]


def test_research_fixture_preserves_schema_and_query_semantics():
    graph = DomainGraph.from_dict(load_fixture("research"))

    assert graph.domain_schema.name == "research"
    assert graph.domain_schema.entity_types == (
        "question",
        "claim",
        "evidence",
        "source",
    )
    assert [node.id for node in graph.children("q1")] == ["c1", "c2"]
    assert [node.id for node in graph.descendants("q1")] == ["c1", "c2", "e1"]
    assert [node.id for node in graph.neighbors("e1", relation="supports")] == ["c1"]


def test_content_fixture_preserves_structure_and_provenance():
    graph = DomainGraph.from_dict(load_fixture("content"))

    assert graph.domain_schema.name == "content"
    assert [node.id for node in graph.descendants("document")] == [
        "section:intro",
        "block:claim",
        "citation:claim",
    ]
    assert [
        node.id for node in graph.neighbors("block:claim", relation="derived_from")
    ] == ["source_ref:claim"]
    assert graph.get_node("source_ref:claim").data["snapshot_version"] == 4


def test_unicode_nested_fixture_preserves_unicode_and_nested_data():
    graph = DomainGraph.from_dict(load_fixture("unicode_nested"))
    node = graph.get_node("节点-一")

    assert node.name == "研究问题：为什么？"
    assert node.data == {
        "labels": ["中文", "日本語", "emoji 🚀"],
        "metadata": {"作者": "李雷", "scores": [0, 1, 1.5]},
    }
    assert graph.edges[0].data == {"引用": {"页码": 12, "段落": "第二段"}}


def test_open_world_fixture_keeps_undeclared_symbols_valid():
    graph = DomainGraph.from_dict(load_fixture("open_world"))

    assert graph.domain_schema.entity_types == ()
    assert graph.domain_schema.relations == ()
    assert graph.get_node("m1").entity_type == "unregistered_entity"
    assert graph.edges[0].relation == "unregistered_relation"
    assert graph.validate() == ()


def test_reader_rejects_unsupported_wire_version():
    payload = load_fixture("minimal")
    payload["version"] = 2

    with pytest.raises(ValueError, match="unsupported domain graph version: 2"):
        DomainGraph.from_dict(payload)
