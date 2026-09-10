"""Tests for the source-traceable content reference adapter."""

import pytest

from domain_graph import DomainGraph, NodeNotFoundError
from domain_graph.adapters import CONTENT_DOMAIN_SCHEMA, ContentDomainAdapter


def test_content_adapter_builds_traceable_article_and_round_trips():
    adapter = ContentDomainAdapter()
    graph = adapter.create_document(
        "research-reading",
        "doc:article",
        title="Why maintenance costs grow",
        data={"audience": "general"},
    )
    adapter.add_section(
        graph,
        "section:introduction",
        "doc:article",
        title="Introduction",
    )
    adapter.add_block(
        graph,
        "block:claim",
        "section:introduction",
        kind="paragraph",
        text="Implicit dependencies increase long-term maintenance costs.",
        data={"status": "reviewed"},
    )
    adapter.add_source_ref(
        graph,
        "source:claim-7",
        source_graph="research:project-alpha",
        source_node_id="claim-7",
        snapshot_version=3,
    )
    graph.add_edge("block:claim", "source:claim-7", "derived_from")
    adapter.add_citation(
        graph,
        "citation:1",
        "block:claim",
        "source:claim-7",
        locator="p. 12",
    )

    assert adapter.schema == CONTENT_DOMAIN_SCHEMA
    assert [node.id for node in graph.descendants("doc:article")] == [
        "section:introduction",
        "block:claim",
        "citation:1",
    ]
    assert graph.neighbors("block:claim", relation="derived_from")[0].id == (
        "source:claim-7"
    )
    assert adapter.validate_content(graph) == ()

    restored = DomainGraph.from_json(graph.to_json())

    assert restored.to_dict() == graph.to_dict()
    assert restored.get_node("doc:article").data == {
        "audience": "general",
        "content_type": "article",
    }
    assert restored.get_node("source:claim-7").data == {
        "source_graph": "research:project-alpha",
        "source_node_id": "claim-7",
        "snapshot_version": 3,
    }
    assert restored.get_node("citation:1").data == {"locator": "p. 12"}


def test_content_adapter_keeps_presentation_details_out_of_the_schema():
    adapter = ContentDomainAdapter()
    graph = adapter.create_document("tutorial", "doc:tutorial")
    adapter.add_section(graph, "section:one", "doc:tutorial")
    adapter.add_block(
        graph,
        "block:example",
        "section:one",
        kind="code",
        text="print('domain graph')",
        data={"language": "python"},
    )

    assert "markdown" not in adapter.schema.entity_types
    assert "pdf" not in adapter.schema.entity_types
    assert graph.get_node("block:example").data == {
        "language": "python",
        "kind": "code",
        "text": "print('domain graph')",
    }


def test_content_validator_reports_orphans_and_invalid_provenance():
    adapter = ContentDomainAdapter()
    graph = adapter.create_document("invalid", "doc:invalid")
    graph.add_node("block:orphan", "block")
    graph.add_node("citation:orphan", "citation")
    graph.add_node("citation:missing-target", "citation")
    graph.add_node("source:empty", "source_ref")
    graph.add_edge("citation:orphan", "block:orphan", "cites")

    issues = adapter.validate_content(graph)

    assert {issue.kind for issue in issues} == {
        "citation_target",
        "orphan_content",
        "provenance_target",
        "source_reference",
    }


def test_content_builders_validate_prerequisites_before_mutating():
    adapter = ContentDomainAdapter()
    graph = adapter.create_document("atomic", "document")

    with pytest.raises(NodeNotFoundError):
        adapter.add_section(graph, "section", "missing")
    assert "section" not in graph.nodes

    adapter.add_section(graph, "section", "document")
    adapter.add_block(graph, "block", "section", kind="paragraph")
    with pytest.raises(NodeNotFoundError):
        adapter.add_citation(graph, "citation", "block", "missing-source")
    assert "citation" not in graph.nodes


def test_content_adapter_adds_assets_and_rejects_empty_source_references():
    adapter = ContentDomainAdapter()
    graph = adapter.create_document("assets", "document")
    asset = adapter.add_asset(
        graph,
        "asset:diagram",
        "document",
        name="Domain flow",
        uri="diagram.svg",
        media_type="image/svg+xml",
        alt="Research to content flow",
    )

    assert asset.data == {
        "uri": "diagram.svg",
        "media_type": "image/svg+xml",
        "alt": "Research to content flow",
    }
    assert adapter.validate_content(graph) == ()

    with pytest.raises(ValueError, match="source_graph"):
        adapter.add_source_ref(
            graph,
            "source:empty",
            source_graph="",
            source_node_id="claim",
        )
    assert "source:empty" not in graph.nodes


def test_content_validator_rejects_multiple_hierarchy_parents():
    adapter = ContentDomainAdapter()
    graph = adapter.create_document("parents", "document")
    adapter.add_section(graph, "section:a", "document")
    adapter.add_section(graph, "section:b", "document")
    adapter.add_block(graph, "block", "section:a", kind="paragraph")
    graph.add_edge("section:b", "block", "contains")

    issues = adapter.validate_content(graph)

    assert [issue.kind for issue in issues].count("content_parent") == 1
