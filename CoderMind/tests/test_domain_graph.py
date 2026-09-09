"""Focused tests for the domain-extensible RPG core."""

from rpg import (
    CODE_DOMAIN_SCHEMA,
    CodeDomainAdapter,
    DomainGraph,
    DomainSchema,
    EdgeType,
    Node,
    NodeMetaData,
    NodeType,
    RPG,
    RelationSpec,
)


def _research_schema() -> DomainSchema:
    return DomainSchema(
        name="research",
        entity_types=("claim", "evidence"),
        relations=(
            RelationSpec("contains", hierarchy=True),
            RelationSpec("supports"),
            RelationSpec("contradicts"),
        ),
    )


def test_custom_domain_uses_schema_for_hierarchy_and_arbitrary_relations():
    graph = DomainGraph("research", _research_schema())
    claim = Node("claim-1", name="Claim", meta=NodeMetaData(type_name="claim"))
    evidence = Node("evidence-1", name="Evidence", meta=NodeMetaData(type_name="evidence"))
    graph.add_node(claim)
    graph.add_node(evidence)

    graph.add_edge(graph.repo_node, claim, "contains")
    graph.add_edge(claim, evidence, "supports")

    assert claim.parent() is graph.repo_node
    assert graph.edges[0].relation == "supports"
    assert graph.get_nodes_by_type("claim") == [claim]


def test_custom_domain_schema_and_string_symbols_round_trip():
    graph = DomainGraph("research", domain_schema=_research_schema())
    claim = Node("claim-1", name="Claim", meta=NodeMetaData(type_name="claim"))
    evidence = Node("evidence-1", name="Evidence", meta=NodeMetaData(type_name="evidence"))
    graph.add_node(claim)
    graph.add_node(evidence)
    graph.add_edge(graph.repo_node, claim, "contains")
    graph.add_edge(graph.repo_node, evidence, "contains")
    graph.add_edge(evidence, claim, "supports")

    payload = graph.to_dict(include_dep_graph=False)
    restored = DomainGraph.from_dict(payload)

    assert payload["meta"]["domain_schema"]["name"] == "research"
    assert restored.domain_schema == _research_schema()
    assert restored.get_node_by_id("claim-1").meta.type_name == "claim"
    assert restored.edges[0].relation == "supports"


def test_flat_loader_restores_schema_before_classifying_edges():
    payload = {
        "repo_name": "research",
        "repo_node_id": "root",
        "nodes": [
            {"id": "root", "name": "research", "node_type": "repo", "level": 0, "meta": None},
            {"id": "claim-1", "name": "Claim", "node_type": "claim", "level": 1,
             "meta": {"type_name": "claim"}},
        ],
        "edges": [{"src": "root", "dst": "claim-1", "relation": "contains"}],
        "meta": {"domain_schema": _research_schema().to_dict()},
    }

    restored = DomainGraph.from_dict(payload)

    assert restored.get_node_by_id("claim-1").parent() is restored.repo_node
    assert restored.edges == []


def test_code_domain_compatibility_exports_and_defaults():
    graph = RPG("code")
    adapter = CodeDomainAdapter()

    assert graph.domain_schema == CODE_DOMAIN_SCHEMA
    assert adapter.schema == CODE_DOMAIN_SCHEMA
    assert NodeType.FILE.value == "file"
    assert EdgeType.is_hierarchy(EdgeType.CONTAINS)
    assert not EdgeType.is_hierarchy(EdgeType.INVOKES)
