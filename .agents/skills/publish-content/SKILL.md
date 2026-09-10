---
name: publish-content
description: Validate and render an existing ContentDomainGraph as Markdown or HTML. Use when a user requests a readable output from portable content; use research-content first when the input is still research findings or a ResearchDomainGraph.
---

# Publish validated content

Publish only from a valid content graph so source traceability survives the
presentation step.

## Workflow

1. Load the v1 graph with `DomainGraph.from_json()`. When the input is research
   rather than a content graph, apply `$research-content` first.
2. Run `ContentDomainAdapter.validate_content()`. Resolve every issue before
   rendering; publishing an orphaned or broken citation graph is incomplete.
3. Select `MarkdownRenderer` or `HtmlRenderer` from `domain_graph.renderers`
   according to the requested format. If the graph contains multiple documents,
   pass the requested `document_id` explicitly.
4. Render once, then inspect the result for complete section order, visible
   citations, reference targets, and correct escaping. Write an output file only
   when the user requested a file or supplied a destination.

The current publishing boundary supports Markdown and HTML. PDF, EPUB, slide,
and site production belong to their format-specific tooling after this semantic
rendering step; do not encode those layout rules back into the Content Graph.

Completion requires a valid source graph, a non-empty rendered document, and
preserved citation references. API examples live in
the [Domain Graph 0.2.0 guide](https://github.com/KiwataHoko/RPG-ZeroRepo/blob/domain-graph-v0.2.0/domain_graph/README.md).
