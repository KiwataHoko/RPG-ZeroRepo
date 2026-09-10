"""Release-level compatibility checks for the standalone package."""

import importlib.metadata

from domain_graph import (
    DomainGraph,
    DomainSchema,
    RelationSpec,
    __all__ as public_api,
    __version__,
)
from domain_graph.adapters import __all__ as adapter_api
from domain_graph.renderers import __all__ as renderer_api
from domain_graph.transforms import __all__ as transform_api


EXPECTED_PUBLIC_API = {
    "__version__",
    "DomainAdapter",
    "DomainEdge",
    "DomainGraph",
    "DomainGraphError",
    "DomainNode",
    "DomainSchema",
    "DuplicateNodeError",
    "HierarchyCycleError",
    "NodeNotFoundError",
    "RelationSpec",
    "SchemaViolation",
    "ValidationIssue",
    "symbol_value",
}


def test_distribution_and_public_versions_match_release():
    assert importlib.metadata.version("domain-graph") == __version__ == "0.2.0"


def test_initial_public_api_remains_available():
    assert set(public_api) >= EXPECTED_PUBLIC_API


def test_v020_public_subpackages_are_explicit():
    assert set(adapter_api) == {
        "CONTENT_DOMAIN_SCHEMA",
        "RESEARCH_DOMAIN_SCHEMA",
        "ContentDomainAdapter",
        "ResearchDomainAdapter",
    }
    assert set(transform_api) == {
        "ContentBrief",
        "ContentMappingResult",
        "ResearchToContentMapper",
    }
    assert set(renderer_api) == {"HtmlRenderer", "MarkdownRenderer"}


def test_wire_format_v1_contract_is_stable():
    schema = DomainSchema(
        "release-contract",
        entity_types=("parent", "child"),
        relations=(RelationSpec("contains", hierarchy=True),),
    )
    graph = DomainGraph("example", schema, strict_schema=True)
    graph.add_node("p", "parent", data={"rank": 1})
    graph.add_node("c", "child")
    graph.add_edge("p", "c", "contains", data={"weight": 2})

    payload = graph.to_dict()

    assert list(payload) == [
        "format",
        "version",
        "name",
        "schema",
        "strict_schema",
        "nodes",
        "edges",
    ]
    assert payload["format"] == "domain-graph"
    assert payload["version"] == 1
    assert payload["schema"] == {
        "name": "release-contract",
        "entity_types": ["parent", "child"],
        "relations": [{"name": "contains", "hierarchy": True}],
    }
    assert payload["nodes"][0] == {
        "id": "p",
        "entity_type": "parent",
        "name": "",
        "data": {"rank": 1},
    }
    assert payload["edges"][0] == {
        "source": "p",
        "target": "c",
        "relation": "contains",
        "data": {"weight": 2},
    }

    restored = DomainGraph.from_dict(payload)
    assert restored.to_dict() == payload
