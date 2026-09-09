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

## Install

Install the 0.1.1 wheel from the GitHub Release:

```bash
python -m pip install https://github.com/KiwataHoko/RPG-ZeroRepo/releases/download/domain-graph-v0.1.1/domain_graph-0.1.1-py3-none-any.whl
```

For development from this repository:

```bash
python -m pip install -e ./domain_graph
```

The distribution name is `domain-graph`; the import package remains
`domain_graph`. Version `0.1.1` has no runtime dependencies.

Release artifacts include both a wheel and source distribution plus SHA-256
checksums. The release workflow verifies the package metadata, runs the core
and adapter tests, and installs both artifacts in clean virtual environments
before publishing the GitHub Release.

## Compatibility

The current JSON wire format is `format="domain-graph"`, `version=1`. The
`0.1.x` release line promises semantic backward compatibility for v1 payloads
and the public package surface; it does not promise byte-for-byte equality of
serialized JSON. Node and edge `data` must be JSON-native, and real adapters
must preserve domain semantics through validation and serialization
round-trips.

See the [compatibility policy](./COMPATIBILITY.md) for the v1 contract, golden
fixture rules, forward-compatibility limits, adapter acceptance criteria, and
Python/CI expectations.

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

## Reference research adapter

`domain_graph.adapters.research` is a non-code reference implementation. It
declares `question`, `claim`, `evidence`, and `source` entities together with
`contains`, `supports`, `contradicts`, and `derived_from` relations.

```python
from domain_graph.adapters import ResearchDomainAdapter

adapter = ResearchDomainAdapter()
graph = adapter.create_graph("paper", strict_schema=True)
graph.add_node("q1", "question")
graph.add_node("c1", "claim")
graph.add_edge("q1", "c1", "contains")
```

The adapter is intentionally outside the core root API. New domains can add
their own adapters without modifying the graph implementation or extending a
central enum.
