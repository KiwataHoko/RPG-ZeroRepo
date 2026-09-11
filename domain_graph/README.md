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

### Checkpointed research workflow

`ResearchBuildPipeline` applies the ZeroRepo workflow pattern to research:
specification, dependency-planned discovery, adversarial challenge, synthesis,
and gated finalization. It persists `.research/research-spec.json`,
`research-plan.json`, and `research-state.jsonl`, so interrupted work resumes
without replacing prior evidence.

```bash
domain-graph-research --workspace . init \
  --question "What is earning?" \
  --constraint "Do not invent formulas" \
  --success-criterion "Every theory faces a discriminating counterexample"
domain-graph-research --workspace . status
```

The brief requires material constraints and observable success criteria. Only
ready tasks may start. Retrieval records use validated URLs, DOIs, or ISBN-13s,
canonical source deduplication, and an explicit authenticity review. Evidence
records carry a concrete observation, locator, and reasoning; counterexamples
also bind a challenged prediction to a different rival theory's prediction and
must pass a logic review.

The CLI stores every submitted result as a read-only, attempt-numbered file under
`.research/checkpoints/`. `materialize` deterministically constructs the draft
graph from accepted task results, and `reopen` resets an invalid task and every
transitive dependent. `finalize` counts only quality-gated sources and logical
counterexamples before emitting the final graph and coverage report.

### Starting research in Codex

The repository's neutral skills separate evidence work from editorial and
presentation decisions:

```text
$research-build → ResearchDomainGraph → $research-content
                → ContentDomainGraph → $publish-content → Markdown / HTML
```

Invoke `$research-build` with a question, scope, and any source constraints. It
collects and assesses sources, represents atomic claims and supporting or
contradictory evidence with the adapter vocabulary, validates the strict graph,
and returns versioned JSON. The later skills preserve that provenance while
turning the findings into readable output.

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
Use `add_asset()` for format-neutral media references; renderers recognize its
`uri`, `media_type`, and `alt` metadata without embedding presentation layout.

## Research-to-content transformation

`ResearchToContentMapper` produces a deterministic editorial outline from a
research graph. It groups selected claims under their research questions,
places supporting evidence after each claim, creates source references and
citations, and reports unused or unsupported claims.

```python
from domain_graph.adapters import ResearchDomainAdapter
from domain_graph.transforms import ContentBrief, ResearchToContentMapper

research_graph = ResearchDomainAdapter().create_graph(
    "research:maintenance",
    strict_schema=True,
)
research_graph.add_node("question-1", "question", name="Why do costs grow?")
research_graph.add_node("claim-1", "claim", name="Dependencies accumulate.")
research_graph.add_node("evidence-1", "evidence", name="Longitudinal study")
research_graph.add_node(
    "source-1",
    "source",
    name="Maintenance study",
    data={"url": "https://example.test/study"},
)
research_graph.add_edge("question-1", "claim-1", "contains")
research_graph.add_edge("evidence-1", "claim-1", "supports")
research_graph.add_edge(
    "evidence-1",
    "source-1",
    "derived_from",
    data={"page": 12},
)

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

## 0.2.0 boundaries

- The mapper creates a grounded editorial outline; it does not generate or
  polish prose by itself.
- `source_ref` preserves external graph identity and metadata but does not fetch
  or resolve remote sources.
- The built-in renderers produce Markdown text and an HTML article fragment.
  PDF, EPUB, slides, and site layout remain downstream publishing concerns.
- Renderer-specific styling does not belong in the serialized Content Graph.
