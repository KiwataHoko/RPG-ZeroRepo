"""Standalone package tests for the research reference adapter."""

import importlib.metadata

from domain_graph import DomainGraph, __version__
from domain_graph.adapters import RESEARCH_DOMAIN_SCHEMA, ResearchDomainAdapter


def test_distribution_version_matches_public_version():
    assert importlib.metadata.version("domain-graph") == __version__ == "0.1.1"


def test_research_adapter_builds_and_round_trips_real_domain_graph():
    adapter = ResearchDomainAdapter()
    graph = adapter.create_graph("paper", strict_schema=True)

    graph.add_node("q1", "question", name="What causes X?")
    graph.add_node("c1", "claim", name="Mechanism A causes X")
    graph.add_node("e1", "evidence", name="Experiment 1")
    graph.add_node("s1", "source", name="Paper 1")
    graph.add_edge("q1", "c1", "contains")
    graph.add_edge("e1", "c1", "supports")
    graph.add_edge("e1", "s1", "derived_from")

    assert adapter.schema == RESEARCH_DOMAIN_SCHEMA
    assert [node.id for node in graph.children("q1")] == ["c1"]
    assert graph.neighbors("e1", relation="supports")[0].id == "c1"
    assert graph.validate() == ()

    restored = DomainGraph.from_json(graph.to_json())
    assert restored.domain_schema == RESEARCH_DOMAIN_SCHEMA
    assert restored.get_node("s1").entity_type == "source"
    assert restored.edges[-1].relation == "derived_from"


def test_reference_adapter_does_not_require_coder_mind_symbols():
    adapter = ResearchDomainAdapter()
    graph = adapter.create_graph("research")
    graph.add_node("claim-1", "claim")
    graph.add_node("evidence-1", "evidence")
    graph.add_edge("evidence-1", "claim-1", "supports")

    assert graph.get_nodes_by_type("claim")[0].id == "claim-1"
