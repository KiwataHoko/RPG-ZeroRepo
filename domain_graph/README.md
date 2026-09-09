# Domain Graph core

`domain_graph` is the domain-neutral graph core extracted from CoderMind. It
has no dependency on CoderMind, RPG, repository analysis, or code-specific
entity enums.

The stable public surface is exported from `domain_graph`:

- `DomainSchema` and `RelationSpec` describe domain vocabulary and hierarchy
  semantics.
- `DomainGraph` provides node/edge mutation, queries, hierarchy traversal,
  validation, and versioned JSON round-trips.
- `DomainNode` and `DomainEdge` are the neutral data model.
- `DomainAdapter` is the integration boundary for domain-specific adapters.

Schemas are open-world by default. Undeclared string entity types and
relations are accepted and reported by `graph.validate()`. Use
`strict_schema=True` to reject undeclared symbols at mutation time.

```python
from domain_graph import DomainGraph, DomainSchema, RelationSpec

schema = DomainSchema(
    "research",
    entity_types=("claim", "evidence"),
    relations=(
        RelationSpec("contains", hierarchy=True),
        RelationSpec("supports"),
    ),
)

graph = DomainGraph("paper", schema)
graph.add_node("claim-1", "claim")
graph.add_node("evidence-1", "evidence")
graph.add_edge("claim-1", "evidence-1", "contains")

payload = graph.to_json()
restored = DomainGraph.from_json(payload)
```
