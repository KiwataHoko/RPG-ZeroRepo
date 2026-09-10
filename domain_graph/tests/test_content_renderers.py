"""Markdown and HTML rendering contract tests."""

import pytest

from domain_graph.adapters import ContentDomainAdapter, ResearchDomainAdapter
from domain_graph.renderers import HtmlRenderer, MarkdownRenderer
from domain_graph.transforms import ContentBrief, ResearchToContentMapper


def _mapped_content():
    research = ResearchDomainAdapter().create_graph(
        "research:render", strict_schema=True
    )
    research.add_node("q1", "question", name="What does <safe> rendering require?")
    research.add_node("c1", "claim", name="Escape <unsafe> markup & preserve evidence.")
    research.add_node("e1", "evidence", name="Renderer comparison")
    research.add_node(
        "s1",
        "source",
        name="Rendering & Safety",
        data={"url": "https://example.test/rendering?a=1&b=2"},
    )
    research.add_edge("q1", "c1", "contains")
    research.add_edge("e1", "c1", "supports")
    research.add_edge("e1", "s1", "derived_from", data={"locator": "sec. 3"})
    return (
        ResearchToContentMapper()
        .convert(
            research,
            ContentBrief(title="Rendering <Guide>"),
        )
        .graph
    )


def test_markdown_renderer_emits_structure_and_source_footnotes():
    rendered = MarkdownRenderer().render(_mapped_content())

    assert rendered.startswith("# Rendering <Guide>\n")
    assert "## What does <safe> rendering require?" in rendered
    assert "Escape <unsafe> markup & preserve evidence." in rendered
    assert "[^citation:s1:e1:c1]" in rendered
    assert (
        "[^citation:s1:e1:c1]: [Rendering & Safety]"
        "(https://example.test/rendering?a=1&b=2), sec. 3"
    ) in rendered


def test_html_renderer_escapes_content_and_emits_citation_links():
    rendered = HtmlRenderer().render(_mapped_content())

    assert rendered.startswith('<article data-document-id="document">')
    assert "<h1>Rendering &lt;Guide&gt;</h1>" in rendered
    assert "Escape &lt;unsafe&gt; markup &amp; preserve evidence." in rendered
    assert 'href="#citation-s1-e1-c1"' in rendered
    assert "Rendering &amp; Safety" in rendered
    assert "https://example.test/rendering?a=1&amp;b=2" in rendered


def test_renderers_reject_invalid_content_graphs():
    adapter = ContentDomainAdapter()
    graph = adapter.create_document("invalid", "document")
    graph.add_node("orphan", "block")

    for renderer in (MarkdownRenderer(), HtmlRenderer()):
        with pytest.raises(ValueError, match="orphan_content"):
            renderer.render(graph)


def test_renderers_require_a_document_selection_for_multi_document_graphs():
    adapter = ContentDomainAdapter()
    graph = adapter.create_document("variants", "document:long", title="Long")
    graph.add_node("document:short", "document", name="Short")

    for renderer in (MarkdownRenderer(), HtmlRenderer()):
        with pytest.raises(ValueError, match="document_id is required"):
            renderer.render(graph)
        assert "Short" in renderer.render(graph, document_id="document:short")


def test_renderers_reject_precedes_cycles_between_siblings():
    adapter = ContentDomainAdapter()
    graph = adapter.create_document("cycle", "document")
    adapter.add_section(graph, "section:a", "document", title="A")
    adapter.add_section(graph, "section:b", "document", title="B")
    graph.add_edge("section:a", "section:b", "precedes")
    graph.add_edge("section:b", "section:a", "precedes")

    for renderer in (MarkdownRenderer(), HtmlRenderer()):
        with pytest.raises(ValueError, match="precedes cycle"):
            renderer.render(graph)


def test_non_paragraph_blocks_keep_visible_citation_markers():
    adapter = ContentDomainAdapter()
    graph = adapter.create_document("code", "document", title="Code")
    adapter.add_section(graph, "section", "document", title="Example")
    adapter.add_block(
        graph,
        "block",
        "section",
        kind="code",
        text="print('grounded')",
        data={"language": "python"},
    )
    adapter.add_source_ref(
        graph,
        "source",
        source_graph="research",
        source_node_id="evidence",
        name="Evidence",
    )
    adapter.add_citation(graph, "citation", "block", "source")

    markdown = MarkdownRenderer().render(graph)
    html = HtmlRenderer().render(graph)

    assert "```python\nprint('grounded')\n```\n[^citation]" in markdown
    assert '<p class="citations"><sup>' in html
