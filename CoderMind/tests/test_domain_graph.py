"""CoderMind compatibility tests for the standalone domain graph core."""

from domain_graph import DomainGraph, DomainSchema
from rpg import CODE_DOMAIN_SCHEMA, CodeDomainAdapter, EdgeType, NodeType, RPG


def test_rpg_reexports_standalone_public_types():
    from rpg import DomainGraph as RPGDomainGraph, DomainSchema as RPGDomainSchema

    assert RPGDomainGraph is DomainGraph
    assert RPGDomainSchema is DomainSchema


def test_coder_mind_code_domain_remains_compatible():
    graph = RPG("code")
    adapter = CodeDomainAdapter()

    assert graph.domain_schema == CODE_DOMAIN_SCHEMA
    assert adapter.schema == CODE_DOMAIN_SCHEMA
    assert NodeType.FILE.value == "file"
    assert EdgeType.is_hierarchy(EdgeType.CONTAINS)
    assert not EdgeType.is_hierarchy(EdgeType.INVOKES)
