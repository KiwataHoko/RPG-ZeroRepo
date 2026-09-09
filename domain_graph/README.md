# Domain Graph core

[![Release: 0.1.1](https://img.shields.io/badge/release-0.1.1-blue.svg)](https://github.com/KiwataHoko/RPG-ZeroRepo/releases/tag/domain-graph-v0.1.1)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Wire format: v1](https://img.shields.io/badge/wire%20format-v1-green.svg)](./COMPATIBILITY.md)

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

Release resources: [0.1.1 downloads](https://github.com/KiwataHoko/RPG-ZeroRepo/releases/tag/domain-graph-v0.1.1)
· [changelog](./CHANGELOG.md) · [compatibility policy](./COMPATIBILITY.md).

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

## Content adapter

> Available on the development branch and scheduled for the next release.

`ContentDomainAdapter` models reusable, source-traceable content independently
of its final presentation format. Its vocabulary covers documents, sections,
content blocks, assets, citations, and references to nodes in source graphs.
Only `contains` is hierarchical; ordering, provenance, explanation, summary,
and variant relationships remain ordinary directed edges.

```python
from domain_graph.adapters import ContentDomainAdapter

adapter = ContentDomainAdapter()
graph = adapter.create_document("reading", "doc:reading", title="A short guide")
adapter.add_section(graph, "section:intro", "doc:reading", title="Introduction")
adapter.add_block(
    graph,
    "block:claim",
    "section:intro",
    kind="paragraph",
    text="A claim grounded in the research graph.",
)
adapter.add_source_ref(
    graph,
    "source:claim-7",
    source_graph="research:project-alpha",
    source_node_id="claim-7",
)
graph.add_edge("block:claim", "source:claim-7", "derived_from")

assert adapter.validate_content(graph) == ()
```

Renderers and research-to-content transformations are intentionally separate
from the adapter. This prevents output concerns such as Markdown syntax, PDF
layout, or slide styling from entering the portable content graph.

`validate_content()` combines the core schema check with content-specific
invariants: structural nodes must belong to a document, source references must
identify an external graph and node, and provenance relations must target a
`source_ref`. Each citation must have exactly one outgoing `cites` relation.
