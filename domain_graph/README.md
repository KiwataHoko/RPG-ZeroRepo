# Domain Graph core

[![Release: 0.2.0](https://img.shields.io/badge/release-0.2.0-blue.svg)](https://github.com/KiwataHoko/RPG-ZeroRepo/releases/tag/domain-graph-v0.2.0)
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

Install the 0.2.0 wheel from the GitHub Release:

```bash
python -m pip install https://github.com/KiwataHoko/RPG-ZeroRepo/releases/download/domain-graph-v0.2.0/domain_graph-0.2.0-py3-none-any.whl
```

For development from this repository:

```bash
python -m pip install -e ./domain_graph
```

The distribution name is `domain-graph`; the import package remains
`domain_graph`. Version `0.2.0` has no runtime dependencies.

Release artifacts include both a wheel and source distribution plus SHA-256
checksums. The release workflow verifies the package metadata, runs the core
and adapter tests, and installs both artifacts in clean virtual environments
before publishing the GitHub Release.

Release resources: [0.2.0 downloads](https://github.com/KiwataHoko/RPG-ZeroRepo/releases/tag/domain-graph-v0.2.0)
· [changelog](./CHANGELOG.md) · [compatibility policy](./COMPATIBILITY.md).

## Compatibility

The current JSON wire format is `format="domain-graph"`, `version=1`. Version
`0.2.0` reads v1 payloads from the `0.1.x` line and preserves their graph
semantics; it does not promise byte-for-byte equality of serialized JSON. Node
and edge `data` must be JSON-native, and real adapters must preserve domain
semantics through validation and serialization round-trips.

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

## Research-to-content transformation

`ResearchToContentMapper` produces a deterministic editorial outline from a
research graph. It groups selected claims under their research questions,
places supporting evidence after each claim, creates source references and
citations, and reports unused or unsupported claims.

```python
from domain_graph.transforms import ContentBrief, ResearchToContentMapper

result = ResearchToContentMapper().convert(
    research_graph,
    ContentBrief(
        title="A practical guide",
        audience="general",
        selected_claim_ids=("claim-1", "claim-3"),
    ),
    snapshot_version=4,
)

content_graph = result.graph
assert result.validation_issues == ()
print(result.unsupported_claim_ids)
```

The mapper structures grounded content; it does not ask a model to invent or
polish prose. Editorial revisions can update block text while preserving stable
IDs and provenance edges.

## Markdown and HTML rendering

Renderers consume validated content graphs and do not modify them:

```python
from domain_graph.renderers import HtmlRenderer, MarkdownRenderer

markdown = MarkdownRenderer().render(content_graph)
html = HtmlRenderer().render(content_graph)
```

Both renderers honor `precedes` relationships between siblings and reject
ordering cycles. Markdown emits source footnotes. HTML escapes text and
attribute values and emits linked reference entries. When a graph contains
multiple document roots, pass `document_id=` explicitly.
