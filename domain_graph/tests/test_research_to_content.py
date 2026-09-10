"""Research-to-content mapping contract tests."""

import pytest

from domain_graph.adapters import ResearchDomainAdapter
from domain_graph.transforms import ContentBrief, ResearchToContentMapper


def _research_graph():
    graph = ResearchDomainAdapter().create_graph(
        "research:maintenance", strict_schema=True
    )
    graph.add_node("q1", "question", name="Why do maintenance costs grow?")
    graph.add_node("c1", "claim", name="Implicit dependencies raise costs.")
    graph.add_node("c2", "claim", name="Tooling eliminates all maintenance.")
    graph.add_node("e1", "evidence", name="A longitudinal study of 120 projects.")
    graph.add_node(
        "s1",
        "source",
        name="Maintenance Study <2026>",
        data={"url": "https://example.test/study"},
    )
    graph.add_edge("q1", "c1", "contains")
    graph.add_edge("q1", "c2", "contains")
    graph.add_edge("e1", "c1", "supports", data={"strength": "strong"})
    graph.add_edge("e1", "s1", "derived_from", data={"page": 12})
    return graph


def test_mapper_preserves_research_provenance_and_reports_coverage():
    result = ResearchToContentMapper().convert(
        _research_graph(),
        ContentBrief(
            title="A practical maintenance guide",
            audience="general",
            purpose="explain the evidence",
            tone="clear",
            locale="en",
            selected_claim_ids=("c1",),
        ),
        snapshot_version=4,
    )
    graph = result.graph

    assert result.used_claim_ids == ("c1",)
    assert result.unused_claim_ids == ("c2",)
    assert result.unsupported_claim_ids == ()
    assert graph.get_node("document").data == {
        "audience": "general",
        "purpose": "explain the evidence",
        "tone": "clear",
        "locale": "en",
        "depth": "standard",
        "content_type": "article",
    }
    assert graph.get_node("block:claim:c1").data["text"] == (
        "Implicit dependencies raise costs."
    )
    assert graph.get_node("source_ref:c1").data == {
        "source_entity_type": "claim",
        "source_graph": "research:maintenance",
        "source_node_id": "c1",
        "snapshot_version": 4,
    }
    assert graph.get_node("citation:s1:e1:c1").data == {"locator": "p. 12"}
    assert [
        node.id for node in graph.neighbors("block:claim:c1", relation="derived_from")
    ] == ["source_ref:c1"]
    assert result.validation_issues == ()

    restored = type(graph).from_json(graph.to_json())
    assert restored.to_dict() == graph.to_dict()


def test_mapper_reports_selected_claims_without_supporting_evidence():
    result = ResearchToContentMapper().convert(
        _research_graph(),
        ContentBrief(title="Contrarian view", selected_claim_ids=("c2",)),
    )

    assert result.used_claim_ids == ("c2",)
    assert result.unused_claim_ids == ("c1",)
    assert result.unsupported_claim_ids == ("c2",)
    assert result.validation_issues == ()


def test_mapper_uses_brief_title_for_claims_without_a_question():
    research = ResearchDomainAdapter().create_graph("research:zh", strict_schema=True)
    research.add_node("c1", "claim", name="孤立论点")

    result = ResearchToContentMapper().convert(
        research,
        ContentBrief(title="读物", findings_title="补充发现"),
    )

    assert result.graph.get_node("section:additional-findings").name == "补充发现"


def test_mapper_rejects_unknown_claims_and_non_research_graphs():
    mapper = ResearchToContentMapper()
    with pytest.raises(ValueError, match="unknown selected claim IDs: missing"):
        mapper.convert(
            _research_graph(),
            ContentBrief(title="Invalid", selected_claim_ids=("missing",)),
        )

    content_graph = mapper.content_adapter.create_document("content", "document")
    with pytest.raises(ValueError, match="research domain schema"):
        mapper.convert(content_graph, ContentBrief(title="Invalid source"))

    invalid_research = _research_graph()
    invalid_research.strict_schema = False
    invalid_research.add_node("unknown", "unknown")
    with pytest.raises(ValueError, match="invalid research graph"):
        mapper.convert(invalid_research, ContentBrief(title="Invalid graph"))


def test_mapper_assigns_a_shared_claim_to_the_first_question_once():
    research = _research_graph()
    research.add_node("q2", "question", name="What else affects maintenance?")
    research.add_edge("q2", "c1", "contains")

    result = ResearchToContentMapper().convert(
        research,
        ContentBrief(title="Shared claim", selected_claim_ids=("c1",)),
    )

    assert result.graph.get_node("block:claim:c1").name == ""
    assert [node.id for node in result.graph.get_nodes_by_type("section")] == [
        "section:question:q1"
    ]


def test_mapper_deduplicates_repeated_support_and_source_edges():
    research = _research_graph()
    research.add_edge("e1", "c1", "supports")
    research.add_edge("e1", "s1", "derived_from", data={"page": 12})

    result = ResearchToContentMapper().convert(
        research,
        ContentBrief(title="Duplicates", selected_claim_ids=("c1",)),
    )

    assert [node.id for node in result.graph.get_nodes_by_type("citation")] == [
        "citation:s1:e1:c1"
    ]
    assert result.validation_issues == ()
